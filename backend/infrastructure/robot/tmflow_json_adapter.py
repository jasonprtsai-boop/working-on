from __future__ import annotations

import threading
import time
from typing import Any

from backend.infrastructure.robot.tmflow_json_client import TMflowJsonClient
from backend.infrastructure.robot.tmflow_json_protocol import CommandIdGenerator, RobotCommand
from backend.utils import config
from backend.utils.logger import logger


class TMflowJsonAdapter:
    """
    TMflow 1.82 TCP JSON adapter.

    Python is the TCP client, TMflow is the socket server, and every message is
    a UTF-8 JSON object terminated by a newline.
    """

    mode = "tmflow_json"

    def __init__(self, host=config.ROBOT_IP, port=config.ROBOT_PORT):
        self.host = str(host)
        self.port = int(port)
        self.connected = False
        self.last_error: str | None = None
        self.last_state = "DISCONNECTED"
        self.last_status = ""
        self.last_result: dict[str, Any] = {}
        self.last_response: dict[str, Any] | None = None
        self.last_command_id: str | None = None
        self.last_checked_at: float | None = None
        self._id_generator = CommandIdGenerator()
        self._lock = threading.RLock()
        self.client = self._new_client()

    def _new_client(self) -> TMflowJsonClient:
        return TMflowJsonClient(
            self.host,
            self.port,
            timeout=float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0)),
            max_message_bytes=int(getattr(config, "ROBOT_TMFLOW_MAX_MESSAGE_BYTES", 4096)),
        )

    def connect(self) -> bool:
        self.last_checked_at = time.time()
        self.last_error = None
        if getattr(config, "FAKE_ROBOT", False):
            self.connected = True
            self.last_state = "READY"
            logger.info("[MOCK] TMflow JSON robot connected on %s:%s", self.host, self.port)
            return True

        with self._lock:
            try:
                self.client = self._new_client()
                self.last_state = "CONNECTING"
                self.client.connect()
                self.connected = True
                self.last_state = "CONNECTED"
                if bool(getattr(config, "ROBOT_TMFLOW_REQUIRE_HELLO", True)):
                    self._request("HELLO", {
                        "client": "python_robot_manager",
                        "client_version": str(getattr(config, "ROBOT_TMFLOW_CLIENT_VERSION", "1.0")),
                    }, expect_ack=False, done_timeout=float(getattr(config, "ROBOT_TMFLOW_ACK_TIMEOUT_SEC", 2.0)))
                self.get_state()
                logger.info("TMflow JSON robot connected on %s:%s", self.host, self.port)
                return True
            except Exception as exc:
                self.last_error = str(exc)
                self.connected = False
                self.last_state = "DISCONNECTED"
                try:
                    self.client.close()
                except Exception:
                    pass
                logger.error("[TMflowJSON] Connection error: %s", exc)
                return False

    def disconnect(self):
        with self._lock:
            try:
                self.client.close()
            finally:
                self.connected = False
                self.last_state = "DISCONNECTED"

    def ping(self) -> bool:
        if not self.connected:
            return False
        if getattr(config, "FAKE_ROBOT", False):
            return True
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return True
        try:
            command = RobotCommand(
                id=self._next_command_id(),
                type="PING",
                payload={},
                version=str(getattr(config, "ROBOT_TMFLOW_PROTOCOL_VERSION", "1.0")),
            )
            response = self.client.transact(
                command,
                wire_format=self._wire_format(),
                done_timeout=float(getattr(config, "ROBOT_TMFLOW_ACK_TIMEOUT_SEC", 2.0)),
                expect_ack=False,
            )
            self._record_response(response.raw)
            return not response.is_error
        except Exception as exc:
            self.last_error = str(exc)
            self.connected = False
            logger.warning("[TMflowJSON] ping failed: %s", exc)
            return False
        finally:
            self._lock.release()

    def get_state(self) -> dict[str, Any]:
        if getattr(config, "FAKE_ROBOT", False):
            self.last_state = "READY"
            self.last_result = {"socket": "CONNECTED", "servo": "SIMULATION", "alarm": False, "current_task": None}
            return dict(self.last_result)
        response = self._request("GET_STATE", {}, expect_ack=False, done_timeout=float(getattr(config, "ROBOT_TMFLOW_ACK_TIMEOUT_SEC", 2.0)))
        return dict(response.get("result") or {})

    def send_move(self, coordinates):
        return self.send_motion(coordinates)

    def send_motion(self, coordinates, speed=None, acceleration=None, timeout=None) -> bool:
        if not self.connected and not self.connect():
            return False
        if getattr(config, "FAKE_ROBOT", False):
            logger.info("[MOCK] TMflow JSON MOVE_L: coords=%s speed=%s acceleration=%s", coordinates, speed, acceleration)
            return True

        try:
            pose = [float(value) for value in coordinates]
            if len(pose) != 6:
                raise ValueError("TMflow JSON MOVE_L coordinates must contain x,y,z,rx,ry,rz.")
            payload = {
                "target": {
                    "x": pose[0],
                    "y": pose[1],
                    "z": pose[2],
                    "rx": pose[3],
                    "ry": pose[4],
                    "rz": pose[5],
                },
                "base": str(getattr(config, "ROBOT_TMFLOW_BASE", "ChessBoard_Base")),
                "tcp": str(getattr(config, "ROBOT_TMFLOW_TCP", "ChessGripper_TCP")),
                "speed": float(speed if speed is not None else getattr(config, "ROBOT_TRAVEL_SPEED", 30.0)),
                "acc": float(acceleration if acceleration is not None else getattr(config, "ROBOT_DEFAULT_ACCELERATION", 60.0)),
                "safe": True,
            }
            final = self._request(
                "MOVE_L",
                payload,
                expect_ack=True,
                done_timeout=float(timeout or getattr(config, "ROBOT_TMFLOW_DONE_TIMEOUT_SEC", 30.0)),
            )
            return self._response_ok(final)
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[TMflowJSON] Motion error: %s", exc)
            return False

    def set_gripper(self, closed: bool) -> bool:
        if not self.connected and not self.connect():
            return False
        action = "CLOSE" if closed else "OPEN"
        if getattr(config, "FAKE_ROBOT", False):
            logger.info("[MOCK] TMflow JSON GRIPPER %s", action)
            return True
        try:
            final = self._request(
                "GRIPPER",
                {
                    "action": action,
                    "wait_ms": int(getattr(config, "ROBOT_TMFLOW_GRIPPER_WAIT_MS", 300)),
                },
                expect_ack=True,
                done_timeout=float(getattr(config, "ROBOT_TMFLOW_DONE_TIMEOUT_SEC", 30.0)),
            )
            return self._response_ok(final)
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[TMflowJSON] Gripper command error: %s", exc)
            return False

    def halt(self):
        if not self.connected:
            return
        if getattr(config, "FAKE_ROBOT", False):
            logger.warning("[MOCK] TMflow JSON STOP")
            return
        try:
            self._request(
                "STOP",
                {
                    "mode": str(getattr(config, "ROBOT_TMFLOW_STOP_MODE", "CONTROLLED_STOP")),
                    "reason": "robot_service_stop_all",
                },
                expect_ack=False,
                done_timeout=float(getattr(config, "ROBOT_TMFLOW_ACK_TIMEOUT_SEC", 2.0)),
            )
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("[TMflowJSON] STOP failed: %s", exc, exc_info=True)

    def read_status_registers(self) -> dict[str, Any]:
        return {
            "adapter": self.mode,
            "protocol": "tcp_json",
            "protocol_version": str(getattr(config, "ROBOT_TMFLOW_PROTOCOL_VERSION", "1.0")),
            "tmflow_json_state": self.last_state,
            "tmflow_json_status": self.last_status,
            "tmflow_json_command_id": self.last_command_id,
            "tmflow_json_result": dict(self.last_result),
            "last_checked_at": self.last_checked_at,
        }

    def read_telemetry(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "source": "tmflow_json",
            "state": self.last_state,
            "result": dict(self.last_result),
        }

    def _request(
        self,
        command_name: str,
        payload: dict[str, Any],
        *,
        expect_ack: bool,
        done_timeout: float,
    ) -> dict[str, Any]:
        with self._lock:
            command = RobotCommand(
                id=self._next_command_id(),
                command=command_name,
                payload=dict(payload or {}),
                meta={
                    "source": "robot_manager",
                    "operator": "system",
                },
                version=str(getattr(config, "ROBOT_TMFLOW_PROTOCOL_VERSION", "1.0")),
            )
            self.last_command_id = command.id
            response = self.client.transact(
                command,
                wire_format=self._wire_format(),
                ack_timeout=float(getattr(config, "ROBOT_TMFLOW_ACK_TIMEOUT_SEC", 2.0)),
                done_timeout=done_timeout,
                expect_ack=expect_ack,
            )
            self._record_response(response.raw)
            return dict(response.raw)

    def _record_response(self, response: dict[str, Any]) -> None:
        self.last_checked_at = time.time()
        self.last_response = dict(response)
        self.last_status = str(response.get("status") or "").upper()
        if response.get("state"):
            self.last_state = str(response.get("state"))
        result = response.get("result")
        if isinstance(result, dict):
            self.last_result = dict(result)
        error = response.get("error")
        self.last_error = str(error.get("message") or error) if isinstance(error, dict) else None

    def _response_ok(self, response: dict[str, Any]) -> bool:
        status = str(response.get("status") or "").upper()
        if status == "DONE":
            return True
        error = response.get("error")
        if isinstance(error, dict):
            self.last_error = str(error.get("message") or error.get("code") or error)
        else:
            self.last_error = f"TMflow command returned {status or 'unknown status'}."
        return False

    def _next_command_id(self) -> str:
        return self._id_generator.next()

    def _wire_format(self) -> str:
        wire_format = str(getattr(config, "ROBOT_TMFLOW_WIRE_FORMAT", "envelope")).strip().lower()
        return wire_format if wire_format in {"envelope", "flat_json"} else "envelope"
