import asyncio
import concurrent.futures
import socket
import threading
import time
from typing import Any

from backend.utils import config
from backend.utils.logger import logger

try:
    import techmanpy

    TECHMANPY_AVAILABLE = True
except ImportError:
    techmanpy = None
    TECHMANPY_AVAILABLE = False
    logger.warning("techmanpy is not installed. TechmanPyAdapter can only run when FAKE_ROBOT=true.")


class TechmanPyAdapter:
    """
    Techman TMflow External Script adapter.

    This path targets the lab baseline:
    TMflow 1.82 / controller 1.82.51 / External Script on TCP 5890.
    """

    mode = "techmanpy"

    def __init__(self, host=config.ROBOT_IP, port=config.ROBOT_PORT):
        self.host = host
        self.port = int(port)
        self.connected = False
        self.last_error = None
        self.last_listen_node_active = None
        self.last_checked_at = None
        self._queue_tag = 0
        self._loop = None
        self._loop_thread = None
        self._loop_ready = threading.Event()
        self._loop_lock = threading.Lock()
        self._last_async_timeout_at = None
        self._cancelled_operations = 0

    def connect(self) -> bool:
        self.last_checked_at = time.time()
        self.last_error = None

        if int(self.port) != 5890:
            self.last_error = "techmanpy External Script uses TCP port 5890."
            logger.error("[TechmanPy] %s configured=%s", self.last_error, self.port)
            self.connected = False
            return False

        if not TECHMANPY_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                self.connected = True
                self.last_listen_node_active = True
                logger.info("[MOCK] TechmanPy robot connected on %s:%s", self.host, self.port)
                return True
            self.last_error = "techmanpy is required when FAKE_ROBOT=false and ROBOT_ADAPTER=techmanpy."
            logger.error("[TechmanPy] %s", self.last_error)
            self.connected = False
            return False

        try:
            if getattr(config, "ROBOT_TECHMANPY_REQUIRE_LISTEN_NODE", True):
                active = bool(self._run_async(self._check_listen_node()))
                self.last_listen_node_active = active
                if not active:
                    self.last_error = "TMflow Listen Node / External Script is not active."
                    logger.error("[TechmanPy] %s", self.last_error)
                    self.connected = False
                    return False
            elif not self.ping():
                self.last_error = "TCP port 5890 is not reachable."
                logger.error("[TechmanPy] %s", self.last_error)
                self.connected = False
                return False

            self.connected = True
            logger.info("TechmanPy robot connected on %s:%s", self.host, self.port)
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[TechmanPy] Connection error: %s", exc)
            self.connected = False
            return False

    async def _check_listen_node(self) -> bool:
        async with techmanpy.connect_sta(
            robot_ip=self.host,
            conn_timeout=float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0)),
        ) as conn:
            return bool(await conn.is_listen_node_active())

    def ping(self) -> bool:
        if not TECHMANPY_AVAILABLE:
            return bool(getattr(config, "FAKE_ROBOT", False))
        try:
            with socket.create_connection(
                (self.host, int(self.port)),
                timeout=float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0)),
            ):
                return True
        except OSError as exc:
            logger.warning("[TechmanPy] TCP ping failed: %s", exc)
            self.connected = False
            return False

    def send_move(self, coordinates):
        return self.send_motion(coordinates)

    def send_motion(self, coordinates, speed=None, acceleration=None, timeout=None) -> bool:
        if not self.connected and not self.connect():
            return False
        if not TECHMANPY_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                logger.info("[MOCK] TechmanPy motion: coords=%s speed=%s acceleration=%s", coordinates, speed, acceleration)
                return True
            self.last_error = "techmanpy is required for real robot motion."
            logger.error("[TechmanPy] %s", self.last_error)
            return False

        try:
            pose = [float(value) for value in coordinates]
            if len(pose) != 6:
                raise ValueError("TechmanPy motion coordinates must contain x,y,z,rx,ry,rz.")
            speed_perc = self._speed_to_percent(speed if speed is not None else getattr(config, "ROBOT_TRAVEL_SPEED", 30.0))
            accel_ms = self._acceleration_duration_ms(acceleration)
            self._run_async(self._send_motion_script(pose, speed_perc, accel_ms), timeout=timeout)
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[TechmanPy] Motion error: %s", exc)
            return False

    async def _send_motion_script(self, pose: list[float], speed_perc: float, accel_ms: int) -> None:
        async with techmanpy.connect_sct(
            robot_ip=self.host,
            conn_timeout=float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0)),
            suppress_warns=bool(getattr(config, "ROBOT_TECHMANPY_SUPPRESS_WARNINGS", False)),
        ) as conn:
            tag = self._next_queue_tag()
            transaction = conn.start_transaction()
            motion_mode = str(getattr(config, "ROBOT_TECHMANPY_MOTION_MODE", "ptp")).strip().lower()
            if motion_mode == "line":
                transaction.move_to_point_line(pose, speed_perc, accel_ms)
            else:
                transaction.move_to_point_ptp(pose, speed_perc, accel_ms)
            transaction.set_queue_tag(tag, wait_for_completion=True)
            await transaction.submit()

    def set_gripper(self, closed: bool) -> bool:
        script = (
            getattr(config, "ROBOT_GRIPPER_CLOSE_SCRIPT", "")
            if closed
            else getattr(config, "ROBOT_GRIPPER_OPEN_SCRIPT", "")
        )
        script = str(script or "").strip()
        if not script:
            self.last_error = "TechmanPy gripper script is not configured."
            logger.error("[TechmanPy] %s", self.last_error)
            return False
        try:
            self._run_async(self._send_raw_tm_script(script))
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[TechmanPy] Gripper command error: %s", exc)
            return False

    async def _send_raw_tm_script(self, script: str) -> None:
        async with techmanpy.connect_sct(
            robot_ip=self.host,
            conn_timeout=float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0)),
            suppress_warns=bool(getattr(config, "ROBOT_TECHMANPY_SUPPRESS_WARNINGS", False)),
        ) as conn:
            await conn.send_tm_script(script)

    def halt(self):
        if not TECHMANPY_AVAILABLE:
            logger.warning("[TechmanPy] HALT requested but techmanpy is unavailable.")
            return
        try:
            self._run_async(
                self._halt_script(),
                timeout=float(getattr(config, "ROBOT_HALT_TIMEOUT_SEC", 1.5)),
            )
        except Exception as exc:
            logger.warning("[TechmanPy] HALT failed: %s", exc, exc_info=True)

    async def _halt_script(self) -> None:
        async with techmanpy.connect_sct(
            robot_ip=self.host,
            conn_timeout=float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0)),
            suppress_warns=True,
        ) as conn:
            await conn.stop_motion()

    def read_status_registers(self) -> dict[str, Any]:
        return {
            "adapter": self.mode,
            "listen_node_active": self.last_listen_node_active,
            "external_script_port": int(self.port),
            "last_checked_at": self.last_checked_at,
            "async_loop_running": self._loop_is_running(),
            "cancelled_operations": self._cancelled_operations,
            "last_async_timeout_at": self._last_async_timeout_at,
        }

    def read_telemetry(self) -> dict[str, Any]:
        status = self.read_status_registers()
        return {
            "enabled": False,
            "source": "techmanpy",
            "connected": bool(self.connected),
            "status": status,
            "message": (
                "TechmanPy telemetry streaming is not configured in this build; "
                "status is limited to connection, Listen Node, and async runtime health."
            ),
        }

    def disconnect(self):
        self.connected = False
        self._stop_loop()

    def _next_queue_tag(self) -> int:
        self._queue_tag = (self._queue_tag % 32767) + 1
        return self._queue_tag

    def _speed_to_percent(self, value) -> float:
        speed = float(value)
        if speed <= 0:
            raise ValueError("TechmanPy speed must be positive.")
        if speed > 1.0:
            speed = speed / 100.0
        return min(1.0, max(0.01, speed))

    def _acceleration_duration_ms(self, value) -> int:
        if value is None:
            value = getattr(config, "ROBOT_DEFAULT_ACCELERATION", 200)
        return max(150, int(round(float(value))))

    def _run_async(self, coro, timeout=None):
        operation_timeout = float(timeout if timeout is not None else getattr(config, "ROBOT_MOTION_TIMEOUT_SEC", 10.0))
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=max(0.05, operation_timeout))
        except concurrent.futures.TimeoutError as exc:
            self._cancelled_operations += 1
            self._last_async_timeout_at = time.time()
            future.cancel()
            self._observe_cancelled_future(future)
            raise TimeoutError("TechmanPy async operation timed out and was cancelled.") from exc

    def _ensure_loop(self):
        with self._loop_lock:
            if self._loop_is_running():
                return self._loop
            self._loop_ready.clear()
            self._loop_thread = threading.Thread(target=self._run_loop, name="TechmanPyAsyncLoop", daemon=True)
            self._loop_thread.start()
            if not self._loop_ready.wait(timeout=float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0))):
                raise TimeoutError("TechmanPy async loop failed to start.")
            return self._loop

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        try:
            loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    def _loop_is_running(self) -> bool:
        loop = self._loop
        thread = self._loop_thread
        return bool(loop and loop.is_running() and thread and thread.is_alive())

    def _stop_loop(self):
        with self._loop_lock:
            loop = self._loop
            thread = self._loop_thread
            if loop and loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=1.0)
            self._loop = None
            self._loop_thread = None
            self._loop_ready.clear()

    def _observe_cancelled_future(self, future):
        def _consume_result(done):
            try:
                done.result()
            except Exception:
                pass

        future.add_done_callback(_consume_result)
