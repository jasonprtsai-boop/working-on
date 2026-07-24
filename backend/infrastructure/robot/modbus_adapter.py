import time
from backend.utils.logger import logger
from backend.utils import config

try:
    from pyModbusTCP.client import ModbusClient
    MODBUS_AVAILABLE = True
except ImportError:
    MODBUS_AVAILABLE = False
    logger.warning("pyModbusTCP not installed. ModbusAdapter can only run when FAKE_ROBOT=true.")

class ModbusAdapter:
    """
    Handles Industrial Modbus TCP communication with the TM5-700 robotic arm.
    Default Port: 502 (Standard Modbus TCP)
    """
    def __init__(self, host=config.ROBOT_IP, port=config.ROBOT_PORT):
        self.host = host
        self.port = port
        self.client = None
        self.connected = False
        self._command_id = 0

    def connect(self):
        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                self.connected = True
                logger.info(f"[MOCK] Robot connected on {self.host}:{self.port} (Modbus TCP)")
                return True
            self.connected = False
            logger.error("pyModbusTCP is required when FAKE_ROBOT=false; refusing real robot connection.")
            return False

        try:
            self._validate_register_configuration()
            if not getattr(config, "FAKE_ROBOT", False) and int(self.port) != 502:
                logger.warning(
                    "Robot Modbus port is %s, while standard Modbus TCP is 502. "
                    "Verify the TM5-700/TMflow gateway mapping before enabling AUTO_EXECUTE_ROBOT.",
                    self.port,
                )
            self.client = ModbusClient(host=self.host, port=self.port, auto_open=True, timeout=2.0)
            if self.client.open():
                if not self._verify_status_register_if_enabled():
                    self.connected = False
                    try:
                        self.client.close()
                    except Exception:
                        pass
                    return False
                self.connected = True
                logger.info(f"Robot connected on {self.host}:{self.port} (Modbus TCP)")
                return True
            else:
                logger.error(f"Failed to connect to robot at {self.host}:{self.port}")
                return False
        except Exception as e:
            logger.error(f"Modbus Connection Error: {e}")
            return False

    def send_move(self, coordinates):
        return self.send_motion(coordinates)

    def ping(self) -> bool:
        """Best-effort connectivity check used by diagnostics and setup tests."""
        if not self.connected:
            return False
        if not MODBUS_AVAILABLE:
            return bool(getattr(config, "FAKE_ROBOT", False))
        try:
            if self.client is None:
                return False
            is_open = getattr(self.client, "is_open", None)
            if callable(is_open):
                return bool(is_open())
            if is_open is not None:
                return bool(is_open)
            return bool(self.client.open())
        except Exception as exc:
            logger.warning(f"Modbus ping failed: {exc}")
            self.connected = False
            return False

    def send_motion(self, coordinates, speed=None, acceleration=None, timeout=None):
        """
        Sends target coordinates to Modbus holding registers.
        Register base, scale, and encoding are configurable because real robot
        gateway maps often differ across deployments.
        """
        if not self.connected:
            return False

        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                logger.info(
                    f"[MOCK] Modbus Motion: coords={coordinates}, "
                    f"speed={speed}, acceleration={acceleration}, timeout={timeout}"
                )
                time.sleep(0.5) # Simulate hardware latency
                return True
            logger.error("pyModbusTCP is required when FAKE_ROBOT=false; refusing motion command.")
            return False

        try:
            command_id = None
            if getattr(config, "ROBOT_COMMAND_HANDSHAKE_ENABLED", True):
                command_id = self._next_command_id()
                if not self._write_register(config.ROBOT_COMMAND_ID_REGISTER, command_id):
                    logger.error("Failed to write robot command id register.")
                    return False
            if not self.write_pose_registers(coordinates, speed=speed, acceleration=acceleration):
                return False
            if not getattr(config, "ROBOT_COMMAND_HANDSHAKE_ENABLED", True):
                return self._wait_for_completion(timeout=timeout or config.ROBOT_MOTION_TIMEOUT_SEC)

            if not self._write_register(config.ROBOT_COMMAND_TRIGGER_REGISTER, config.ROBOT_COMMAND_TRIGGER_VALUE):
                logger.error("Failed to write robot command trigger register.")
                return False
            try:
                if not self._wait_for_ack(command_id, timeout=getattr(config, "ROBOT_COMMAND_ACK_TIMEOUT_SEC", 2.0)):
                    return False
                if not self._wait_for_motion_start(command_id, timeout=getattr(config, "ROBOT_COMMAND_ACK_TIMEOUT_SEC", 2.0)):
                    return False
                return self._wait_for_completion(
                    timeout=timeout or config.ROBOT_MOTION_TIMEOUT_SEC,
                    command_id=command_id,
                    saw_moving=True,
                )
            finally:
                self._write_register(config.ROBOT_COMMAND_TRIGGER_REGISTER, config.ROBOT_COMMAND_CLEAR_VALUE)
        except Exception as e:
            logger.error(f"Modbus Write Error: {e}")
            return False

    def write_pose_registers(self, coordinates, speed=None, acceleration=None):
        """Write motion profile and pose registers without toggling the trigger."""
        if not self.connected:
            return False

        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                logger.info(
                    f"[MOCK] Modbus Pose Write: coords={coordinates}, "
                    f"speed={speed}, acceleration={acceleration}"
                )
                return True
            logger.error("pyModbusTCP is required when FAKE_ROBOT=false; refusing pose register write.")
            return False

        if not self._write_motion_profile(speed=speed, acceleration=acceleration):
            return False
        scaled = self._encode_coordinates(coordinates)
        return bool(self.client.write_multiple_registers(config.ROBOT_MOTION_REGISTER_BASE, scaled))

    def _encode_coordinates(self, coordinates):
        encoding = str(config.ROBOT_REGISTER_ENCODING).strip().lower()
        if encoding not in {"scaled_int16", "scaled_int32"}:
            raise ValueError(f"Unsupported robot register encoding: {config.ROBOT_REGISTER_ENCODING!r}")

        encoded = []
        for value in coordinates:
            raw = self._scaled_int(value)
            if encoding == "scaled_int16":
                encoded.append(self._signed_to_register(raw, bits=16))
            else:
                encoded.extend(self._signed_to_register_pair(raw))
        return encoded

    def _validate_register_configuration(self):
        encoding = str(config.ROBOT_REGISTER_ENCODING).strip().lower()
        if encoding not in {"scaled_int16", "scaled_int32"}:
            raise ValueError(f"Unsupported robot register encoding: {config.ROBOT_REGISTER_ENCODING!r}")
        for name in (
            "ROBOT_MOTION_REGISTER_BASE",
            "ROBOT_PROFILE_REGISTER_BASE",
            "ROBOT_STATUS_REGISTER",
            "ROBOT_HALT_REGISTER",
            "ROBOT_GRIPPER_REGISTER",
        ):
            value = int(getattr(config, name))
            if value < 0 or value > 65535:
                raise ValueError(f"{name} must be a valid Modbus register address.")
        if getattr(config, "ROBOT_COMMAND_HANDSHAKE_ENABLED", True):
            for name in (
                "ROBOT_COMMAND_ID_REGISTER",
                "ROBOT_COMMAND_TRIGGER_REGISTER",
                "ROBOT_COMMAND_ACK_REGISTER",
                "ROBOT_ERROR_CODE_REGISTER",
            ):
                value = int(getattr(config, name))
                if value < 0 or value > 65535:
                    raise ValueError(f"{name} must be a valid Modbus register address.")
        if getattr(config, "ROBOT_GRIPPER_FEEDBACK_ENABLED", True):
            value = int(getattr(config, "ROBOT_GRIPPER_STATUS_REGISTER"))
            if value < 0 or value > 65535:
                raise ValueError("ROBOT_GRIPPER_STATUS_REGISTER must be a valid Modbus register address.")
        if getattr(config, "ROBOT_TELEMETRY_ENABLED", False):
            value_width = self._value_register_width()
            for name, width in (
                ("ROBOT_TELEMETRY_POSE_REGISTER_BASE", 6 * value_width),
                ("ROBOT_TELEMETRY_JOINT_REGISTER_BASE", 6 * value_width),
                ("ROBOT_TELEMETRY_SPEED_REGISTER", value_width),
            ):
                value = int(getattr(config, name))
                if value < 0 or value + width - 1 > 65535:
                    raise ValueError(f"{name} must be a valid Modbus register range.")
        if float(config.ROBOT_REGISTER_SCALE) <= 0:
            raise ValueError("ROBOT_REGISTER_SCALE must be positive.")
        if int(getattr(config, "ROBOT_COMMAND_ID_WRAP", 32767)) < 1:
            raise ValueError("ROBOT_COMMAND_ID_WRAP must be positive.")

    def _verify_status_register_if_enabled(self):
        if not getattr(config, "ROBOT_VERIFY_STATUS_ON_CONNECT", False):
            return True
        try:
            status = self.client.read_holding_registers(config.ROBOT_STATUS_REGISTER, 1)
            if not status:
                logger.error(
                    "Robot connected but status register %s did not respond. "
                    "Check the TM5-700 register map before sending motion.",
                    config.ROBOT_STATUS_REGISTER,
                )
                return False
            logger.info("Robot status register %s responded with %s.", config.ROBOT_STATUS_REGISTER, status[0])
            return True
        except Exception as exc:
            logger.error(f"Robot status register verification failed: {exc}")
            return False

    def _scaled_int(self, value):
        return int(round(float(value) * float(config.ROBOT_REGISTER_SCALE)))

    def _signed_to_register(self, value: int, bits: int = 16) -> int:
        min_value = -(1 << (bits - 1))
        max_value = (1 << (bits - 1)) - 1
        if value < min_value or value > max_value:
            raise ValueError(f"Scaled register value {value} exceeds signed {bits}-bit range.")
        if value < 0:
            value += 1 << bits
        return value & ((1 << bits) - 1)

    def _signed_to_register_pair(self, value: int):
        encoded = self._signed_to_register(value, bits=32)
        return [(encoded >> 16) & 0xFFFF, encoded & 0xFFFF]

    def _write_motion_profile(self, speed=None, acceleration=None):
        if speed is None and acceleration is None:
            return True

        registers = []
        if speed is not None:
            registers.append(self._unsigned_profile_register(speed, "speed"))
        if acceleration is not None:
            if not registers:
                registers.append(0)
            registers.append(self._unsigned_profile_register(acceleration, "acceleration"))

        return bool(self.client.write_multiple_registers(config.ROBOT_PROFILE_REGISTER_BASE, registers))

    def _unsigned_profile_register(self, value, name: str) -> int:
        scaled = self._scaled_int(value)
        if scaled < 0 or scaled > 0xFFFF:
            raise ValueError(f"Robot {name} profile value {scaled} exceeds unsigned 16-bit range.")
        return scaled

    def set_gripper(self, closed: bool):
        """Set gripper/vacuum output. Returns False when the command is not confirmed."""
        if not self.connected:
            return False

        value = config.ROBOT_GRIPPER_CLOSE_VALUE if closed else config.ROBOT_GRIPPER_OPEN_VALUE
        action = "CLOSE" if closed else "OPEN"

        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                logger.info(f"[MOCK] Gripper {action}: register {config.ROBOT_GRIPPER_REGISTER} -> {value}")
                return True
            logger.error("pyModbusTCP is required when FAKE_ROBOT=false; refusing gripper command.")
            return False

        try:
            if not self._write_register(config.ROBOT_GRIPPER_REGISTER, value):
                return False
            if getattr(config, "ROBOT_GRIPPER_FEEDBACK_ENABLED", True):
                return self._wait_for_gripper_status(closed)
            return True
        except Exception as e:
            logger.error(f"Modbus Gripper Error: {e}")
            return False

    def _next_command_id(self):
        wrap = max(1, int(getattr(config, "ROBOT_COMMAND_ID_WRAP", 32767)))
        self._command_id = (self._command_id % wrap) + 1
        return self._command_id

    def _write_register(self, register, value) -> bool:
        return bool(self.client.write_single_register(int(register), int(value)))

    def _read_register(self, register):
        values = self.client.read_holding_registers(int(register), 1)
        if not values:
            return None
        return values[0]

    def read_status_registers(self):
        """Return best-effort status/diagnostic registers without blocking motion flow."""
        if not self.connected:
            return {}
        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                return {"status_code": config.ROBOT_STATUS_IDLE_VALUE, "status_label": "idle"}
            return {}

        snapshot = {}
        status = self._read_register(config.ROBOT_STATUS_REGISTER)
        if status is not None:
            snapshot["status_code"] = int(status)
            snapshot["status_label"] = self._status_label(status)

        error_code = self._read_error_code()
        if error_code is not None:
            snapshot["error_code"] = int(error_code)

        if getattr(config, "ROBOT_GRIPPER_FEEDBACK_ENABLED", True):
            gripper_status = self._read_register(config.ROBOT_GRIPPER_STATUS_REGISTER)
            if gripper_status is not None:
                snapshot["gripper_status_code"] = int(gripper_status)
        return snapshot

    def read_telemetry(self):
        """
        Read optional robot feedback registers.

        The register map must be provided by the TMflow/PLC project. When disabled
        this returns a clear marker so callers can fall back to software state.
        """
        if not getattr(config, "ROBOT_TELEMETRY_ENABLED", False):
            return {"enabled": False, "source": "disabled"}
        if not self.connected:
            return {"enabled": True, "source": "unavailable", "error": "not_connected"}
        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                return {"enabled": True, "source": "simulation"}
            return {"enabled": True, "source": "unavailable", "error": "modbus_dependency_unavailable"}

        try:
            pose_values = self._read_scaled_values(config.ROBOT_TELEMETRY_POSE_REGISTER_BASE, 6)
            joint_values = self._read_scaled_values(config.ROBOT_TELEMETRY_JOINT_REGISTER_BASE, 6)
            speed_values = self._read_scaled_values(config.ROBOT_TELEMETRY_SPEED_REGISTER, 1)
            return {
                "enabled": True,
                "source": "hardware",
                "pose": {
                    "x": pose_values[0],
                    "y": pose_values[1],
                    "z": pose_values[2],
                    "rx": pose_values[3],
                    "ry": pose_values[4],
                    "rz": pose_values[5],
                },
                "orientation": {
                    "rx": pose_values[3],
                    "ry": pose_values[4],
                    "rz": pose_values[5],
                },
                "joint_angles": {
                    "j1": joint_values[0],
                    "j2": joint_values[1],
                    "j3": joint_values[2],
                    "j4": joint_values[3],
                    "j5": joint_values[4],
                    "j6": joint_values[5],
                },
                "speed": speed_values[0],
            }
        except Exception as exc:
            logger.warning(f"Robot telemetry read failed: {exc}")
            return {"enabled": True, "source": "unavailable", "error": str(exc)}

    def _status_label(self, status) -> str:
        value = int(status)
        if value == int(getattr(config, "ROBOT_STATUS_IDLE_VALUE", 0)):
            return "idle"
        if value == int(getattr(config, "ROBOT_STATUS_MOVING_VALUE", 1)):
            return "moving"
        if value == int(getattr(config, "ROBOT_STATUS_COMPLETE_VALUE", 2)):
            return "complete"
        if value == int(getattr(config, "ROBOT_STATUS_ERROR_VALUE", 3)):
            return "error"
        return "unknown"

    def _value_register_width(self) -> int:
        return 2 if str(config.ROBOT_REGISTER_ENCODING).strip().lower() == "scaled_int32" else 1

    def _read_scaled_values(self, register, value_count):
        width = self._value_register_width()
        raw_registers = self._read_register_block(register, int(value_count) * width)
        return self._decode_scaled_values(raw_registers, int(value_count))

    def _read_register_block(self, register, count):
        values = self.client.read_holding_registers(int(register), int(count))
        if not values or len(values) < int(count):
            raise RuntimeError(f"register block {register}:{count} did not return enough values")
        return list(values[:int(count)])

    def _decode_scaled_values(self, registers, value_count):
        scale = float(config.ROBOT_REGISTER_SCALE)
        if scale <= 0:
            raise ValueError("ROBOT_REGISTER_SCALE must be positive.")

        width = self._value_register_width()
        expected = int(value_count) * width
        if len(registers) < expected:
            raise ValueError("not enough registers to decode telemetry values")

        values = []
        for index in range(int(value_count)):
            offset = index * width
            if width == 1:
                raw = self._register_to_signed(registers[offset], bits=16)
            else:
                raw = self._register_pair_to_signed(registers[offset], registers[offset + 1])
            values.append(raw / scale)
        return values

    def _register_to_signed(self, value: int, bits: int = 16) -> int:
        value = int(value) & ((1 << bits) - 1)
        sign_bit = 1 << (bits - 1)
        return value - (1 << bits) if value & sign_bit else value

    def _register_pair_to_signed(self, high: int, low: int) -> int:
        value = ((int(high) & 0xFFFF) << 16) | (int(low) & 0xFFFF)
        return self._register_to_signed(value, bits=32)

    def _wait_for_ack(self, command_id, timeout=2.0):
        """Wait until TMflow echoes the command id, proving it consumed the request."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            ack = self._read_register(config.ROBOT_COMMAND_ACK_REGISTER)
            if ack == command_id:
                return True
            status = self._read_register(config.ROBOT_STATUS_REGISTER)
            if status == config.ROBOT_STATUS_ERROR_VALUE:
                logger.error("Robot reported error before command ack. code=%s", self._read_error_code())
                return False
            time.sleep(0.05)
        logger.error("Robot command ack timeout. command_id=%s", command_id)
        return False

    def _wait_for_motion_start(self, command_id, timeout=2.0):
        """Wait for the robot to report moving after acknowledging the command."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self._read_register(config.ROBOT_STATUS_REGISTER)
            if status == getattr(config, "ROBOT_STATUS_MOVING_VALUE", 1):
                return True
            if status == config.ROBOT_STATUS_ERROR_VALUE:
                logger.error("Robot reported error before motion start. code=%s", self._read_error_code())
                return False
            if status == config.ROBOT_STATUS_COMPLETE_VALUE:
                logger.error("Robot reported complete before moving. command_id=%s", command_id)
                return False
            time.sleep(0.05)
        logger.error("Robot motion start timeout. command_id=%s", command_id)
        return False

    def _wait_for_completion(self, timeout=10, command_id=None, saw_moving=False):
        """Polls the completion flag from the robot."""
        start_time = time.time()
        saw_moving = bool(saw_moving or command_id is None)
        while time.time() - start_time < timeout:
            status = self._read_register(config.ROBOT_STATUS_REGISTER)
            if status == getattr(config, "ROBOT_STATUS_MOVING_VALUE", 1):
                saw_moving = True
            elif status == config.ROBOT_STATUS_COMPLETE_VALUE:
                if command_id is not None:
                    ack = self._read_register(config.ROBOT_COMMAND_ACK_REGISTER)
                    if ack != command_id:
                        logger.error("Robot completion ack mismatch. expected=%s actual=%s", command_id, ack)
                        return False
                    if not saw_moving:
                        time.sleep(0.05)
                        continue
                return True
            elif (
                command_id is not None
                and saw_moving
                and status == getattr(config, "ROBOT_STATUS_IDLE_VALUE", 0)
            ):
                ack = self._read_register(config.ROBOT_COMMAND_ACK_REGISTER)
                if ack == command_id:
                    return True
            elif status == config.ROBOT_STATUS_ERROR_VALUE:
                logger.error("Robot reported motion error. code=%s", self._read_error_code())
                return False
            time.sleep(0.1)
        return False

    def _wait_for_gripper_status(self, closed: bool):
        expected = config.ROBOT_GRIPPER_CLOSED_VALUE if closed else config.ROBOT_GRIPPER_OPENED_VALUE
        start_time = time.time()
        timeout = float(getattr(config, "ROBOT_GRIPPER_FEEDBACK_TIMEOUT_SEC", 2.0))
        while time.time() - start_time < timeout:
            status = self._read_register(config.ROBOT_GRIPPER_STATUS_REGISTER)
            if status == expected:
                return True
            if status == getattr(config, "ROBOT_GRIPPER_ERROR_VALUE", 2):
                logger.error("Robot gripper reported error while waiting for %s.", "closed" if closed else "opened")
                return False
            time.sleep(0.05)
        logger.error("Robot gripper feedback timeout while waiting for %s.", "closed" if closed else "opened")
        return False

    def _read_error_code(self):
        try:
            return self._read_register(config.ROBOT_ERROR_CODE_REGISTER)
        except Exception:
            return None

    def halt(self):
        """Sends immediate stop signal to the configured halt register."""
        if self.connected and MODBUS_AVAILABLE:
            self.client.write_single_register(config.ROBOT_HALT_REGISTER, config.ROBOT_HALT_VALUE)
        logger.warning("[Modbus] HALT signal sent")

    def disconnect(self):
        if self.client:
            self.client.close()
        self.connected = False
