import asyncio
import time
import unittest
from unittest.mock import patch

from backend.application.services.robot_service import MotionProfile, RobotService
from backend.application.services.estop import estop
from backend.infrastructure.robot import modbus_adapter
from backend.infrastructure.robot.modbus_adapter import ModbusAdapter
from backend.infrastructure.robot.safety import RobotSafety
from backend.infrastructure.simulation.fake_robot import FakeRobot
from backend.utils import config
from backend.utils.kinematics import Kinematics, kinematics


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def send_move(self, coordinates):
        self.calls.append(coordinates)
        return self.result


class ProfileAdapter:
    def __init__(self, motion_result=True, gripper_result=True, trigger_stop_after_first_motion=False):
        self.motion_result = motion_result
        self.gripper_result = gripper_result
        self.trigger_stop_after_first_motion = trigger_stop_after_first_motion
        self.motion_calls = []
        self.gripper_calls = []

    def send_motion(self, coordinates, speed=None, acceleration=None, timeout=None):
        self.motion_calls.append({
            "coordinates": coordinates,
            "speed": speed,
            "acceleration": acceleration,
            "timeout": timeout,
        })
        if self.trigger_stop_after_first_motion and len(self.motion_calls) == 1:
            estop.GLOBAL_STOP = True
        return self.motion_result

    def set_gripper(self, closed):
        self.gripper_calls.append(bool(closed))
        return self.gripper_result


class SlowMotionAdapter(ProfileAdapter):
    def __init__(self):
        super().__init__()
        self.halted = False

    def send_motion(self, coordinates, speed=None, acceleration=None, timeout=None):
        self.motion_calls.append({
            "coordinates": coordinates,
            "speed": speed,
            "acceleration": acceleration,
            "timeout": timeout,
        })
        time.sleep(0.05)
        return True

    def halt(self):
        self.halted = True


class FakeModbusClient:
    def __init__(self, status_value=2):
        self.status_value = status_value
        self.status_sequence = []
        self.registers = {}
        self.multiple_writes = []
        self.single_writes = []

    def write_multiple_registers(self, register, values):
        self.multiple_writes.append((register, list(values)))
        for index, value in enumerate(values):
            self.registers[register + index] = value
        return True

    def write_single_register(self, register, value):
        self.single_writes.append((register, value))
        self.registers[register] = value
        if register == getattr(config, "ROBOT_COMMAND_TRIGGER_REGISTER", -1) and value == getattr(
            config, "ROBOT_COMMAND_TRIGGER_VALUE", 1
        ):
            self.registers[getattr(config, "ROBOT_COMMAND_ACK_REGISTER", 7101)] = self.registers.get(
                getattr(config, "ROBOT_COMMAND_ID_REGISTER", 6998),
                0,
            )
            self.status_sequence = [getattr(config, "ROBOT_STATUS_MOVING_VALUE", 1), self.status_value]
        if register == getattr(config, "ROBOT_GRIPPER_REGISTER", -1):
            if value == getattr(config, "ROBOT_GRIPPER_CLOSE_VALUE", 1):
                self.registers[getattr(config, "ROBOT_GRIPPER_STATUS_REGISTER", 7103)] = getattr(
                    config,
                    "ROBOT_GRIPPER_CLOSED_VALUE",
                    2,
                )
            elif value == getattr(config, "ROBOT_GRIPPER_OPEN_VALUE", 0):
                self.registers[getattr(config, "ROBOT_GRIPPER_STATUS_REGISTER", 7103)] = getattr(
                    config,
                    "ROBOT_GRIPPER_OPENED_VALUE",
                    1,
                )
        return True

    def read_holding_registers(self, register, count):
        if register == getattr(config, "ROBOT_STATUS_REGISTER", 7100):
            if self.status_sequence:
                return [self.status_sequence.pop(0)]
            return [self.status_value]
        return [self.registers.get(register, 0)]


class NoMovingFakeModbusClient(FakeModbusClient):
    def write_single_register(self, register, value):
        result = super().write_single_register(register, value)
        if register == getattr(config, "ROBOT_COMMAND_TRIGGER_REGISTER", -1) and value == getattr(
            config, "ROBOT_COMMAND_TRIGGER_VALUE", 1
        ):
            self.status_sequence = [getattr(config, "ROBOT_STATUS_COMPLETE_VALUE", 2)]
        return result


class TestRobotMotionFailClosed(unittest.TestCase):
    def setUp(self):
        self.original_global_stop = estop.GLOBAL_STOP
        estop.GLOBAL_STOP = False

    def tearDown(self):
        estop.GLOBAL_STOP = self.original_global_stop

    def test_default_kinematics_places_full_board_inside_soft_limits(self):
        mapper = Kinematics()
        safety = RobotSafety(config)

        invalid = []
        for file_char in "abcdefghi":
            for rank in "0123456789":
                xy = mapper.grid_to_robot(file_char, rank)
                ok, msg = safety.validate_move(*xy) if xy else (False, "mapping failed")
                if not ok:
                    invalid.append((f"{file_char}{rank}", xy, msg))

        self.assertEqual(invalid, [])

    def test_default_capture_dead_zone_is_inside_soft_limits(self):
        mapper = Kinematics()
        safety = RobotSafety(config)

        self.assertEqual(safety.validate_move(*mapper.get_dead_zone_coords(1)), (True, "Safe"))

    def test_motion_failure_preserves_position_and_raises(self):
        service = RobotService()
        service.connected = True
        service.adapter = FakeAdapter(False)
        service.pos = [110, 120, 30]

        with self.assertRaises(RuntimeError):
            asyncio.run(service._motion(110, 120, 30))

        self.assertEqual(service.pos, [110, 120, 30])
        self.assertEqual(len(service.adapter.calls), 1)

    def test_motion_success_updates_position(self):
        service = RobotService()
        service.connected = True
        service.adapter = FakeAdapter(True)

        with patch.object(config, "ROBOT_TOOL_RX", 1.0), patch.object(
            config, "ROBOT_TOOL_RY", 2.0
        ), patch.object(config, "ROBOT_TOOL_RZ", 3.0):
            asyncio.run(service._motion(110, 120, 30))

        self.assertEqual(service.pos, [110.0, 120.0, 30.0])
        self.assertEqual(service.adapter.calls[0], [110.0, 120.0, 30.0, 1.0, 2.0, 3.0])

    def test_pick_and_place_sends_motion_profiles_and_gripper_commands(self):
        service = RobotService()
        service.connected = True
        service.adapter = ProfileAdapter()

        with patch.object(config, "ROBOT_GRIPPER_CLOSE_DWELL_SEC", 0.0), patch.object(
            config, "ROBOT_GRIPPER_OPEN_DWELL_SEC", 0.0
        ):
            self.assertTrue(asyncio.run(service.move_piece("a0a1")))

        self.assertEqual(service.adapter.gripper_calls, [True, False])
        self.assertEqual(len(service.adapter.motion_calls), 6)
        self.assertEqual(service.adapter.motion_calls[0]["speed"], config.ROBOT_TRAVEL_SPEED)
        self.assertEqual(service.adapter.motion_calls[1]["speed"], config.ROBOT_APPROACH_SPEED)
        self.assertEqual(service.adapter.motion_calls[2]["speed"], config.ROBOT_LIFT_SPEED)
        self.assertTrue(
            all(call["acceleration"] == config.ROBOT_DEFAULT_ACCELERATION for call in service.adapter.motion_calls)
        )

    def test_gripper_failure_aborts_move(self):
        service = RobotService()
        service.connected = True
        service.adapter = ProfileAdapter(gripper_result=False)

        with patch.object(config, "ROBOT_GRIPPER_CLOSE_DWELL_SEC", 0.0), patch.object(
            config, "ROBOT_GRIPPER_OPEN_DWELL_SEC", 0.0
        ):
            self.assertFalse(asyncio.run(service.move_piece("a0a1")))

        self.assertEqual(len(service.adapter.motion_calls), 2)
        self.assertEqual(service.adapter.gripper_calls, [True])
        self.assertIn("gripper close failed", service.last_error)

    def test_estop_between_motion_segments_aborts_without_updating_position(self):
        service = RobotService()
        service.connected = True
        service.adapter = ProfileAdapter(trigger_stop_after_first_motion=True)
        service.pos = [10.0, 10.0, config.Z_SAFE]

        with patch.object(config, "ROBOT_GRIPPER_CLOSE_DWELL_SEC", 0.0), patch.object(
            config, "ROBOT_GRIPPER_OPEN_DWELL_SEC", 0.0
        ):
            self.assertFalse(asyncio.run(service.move_piece("a0a1")))

        self.assertEqual(len(service.adapter.motion_calls), 1)
        self.assertEqual(service.pos, [10.0, 10.0, config.Z_SAFE])
        self.assertIn("E-Stop active", service.last_error)

    def test_busy_robot_rejects_concurrent_move(self):
        service = RobotService()
        service.connected = True
        service.adapter = ProfileAdapter()
        service._move_lock.acquire()
        try:
            self.assertFalse(asyncio.run(service.move_piece("a0a1")))
        finally:
            service._move_lock.release()

        self.assertEqual(service.adapter.motion_calls, [])
        self.assertEqual(service.last_error, "Robot is already executing a move.")

    def test_motion_timeout_halts_and_preserves_position(self):
        service = RobotService()
        service.connected = True
        service.adapter = SlowMotionAdapter()
        service.pos = [110.0, 120.0, config.Z_SAFE]
        profile = MotionProfile(label="timeout-test", speed=10.0, acceleration=10.0, timeout=0.01)

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(service._motion(110, 120, 30, profile))

        self.assertIn("timed out", str(ctx.exception))
        self.assertTrue(service.adapter.halted)
        self.assertEqual(service.pos, [110.0, 120.0, config.Z_SAFE])

    def test_invalid_or_noop_move_is_rejected_before_motion(self):
        service = RobotService()
        service.connected = True
        service.adapter = FakeAdapter(True)

        self.assertFalse(asyncio.run(service.move_piece("a0a0")))
        self.assertFalse(asyncio.run(service.move_piece("zzzz")))

        self.assertEqual(service.adapter.calls, [])

    def test_unsafe_capture_dead_zone_is_rejected_before_motion(self):
        service = RobotService()
        service.connected = True
        service.adapter = FakeAdapter(True)

        original_dead_zone = kinematics.dead_zone
        try:
            kinematics.dead_zone = (420.0, 40.0)
            self.assertFalse(asyncio.run(service.move_piece("a0a1", is_capture=True)))
        finally:
            kinematics.dead_zone = original_dead_zone

        self.assertEqual(service.adapter.calls, [])

    def test_fake_robot_uses_coordinate_safety_checks(self):
        robot = FakeRobot()
        robot.connected = True

        self.assertFalse(robot.execute_move("zzzz"))
        self.assertFalse(robot.execute_move("a0a0"))
        self.assertTrue(robot.execute_move("a0a1"))
        self.assertEqual(robot.last_action, "a0a1")

    def test_missing_modbus_dependency_fails_closed_in_real_mode(self):
        with patch.object(modbus_adapter, "MODBUS_AVAILABLE", False), patch.object(modbus_adapter.config, "FAKE_ROBOT", False):
            adapter = ModbusAdapter(host="127.0.0.1", port=502)

            self.assertFalse(adapter.connect())
            self.assertFalse(adapter.connected)
            self.assertFalse(adapter.send_move([1, 2, 3, 0, 0, 0]))

    def test_missing_modbus_dependency_still_allows_explicit_fake_mode(self):
        with patch.object(modbus_adapter, "MODBUS_AVAILABLE", False), patch.object(modbus_adapter.config, "FAKE_ROBOT", True):
            adapter = ModbusAdapter(host="127.0.0.1", port=502)

            self.assertTrue(adapter.connect())
            self.assertTrue(adapter.connected)
            self.assertTrue(adapter.send_move([1, 2, 3, 0, 0, 0]))

    def test_modbus_motion_uses_configurable_register_map_and_int32_encoding(self):
        client = FakeModbusClient(status_value=config.ROBOT_STATUS_COMPLETE_VALUE)
        adapter = ModbusAdapter(host="127.0.0.1", port=502)
        adapter.connected = True
        adapter.client = client

        patches = [
            patch.object(modbus_adapter, "MODBUS_AVAILABLE", True),
            patch.object(config, "ROBOT_REGISTER_ENCODING", "scaled_int32"),
            patch.object(config, "ROBOT_REGISTER_SCALE", 100.0),
            patch.object(config, "ROBOT_MOTION_REGISTER_BASE", 7200),
            patch.object(config, "ROBOT_PROFILE_REGISTER_BASE", 7212),
            patch.object(config, "ROBOT_STATUS_REGISTER", 7300),
            patch.object(config, "ROBOT_STATUS_COMPLETE_VALUE", 9),
            patch.object(config, "ROBOT_COMMAND_ID_REGISTER", 7310),
            patch.object(config, "ROBOT_COMMAND_TRIGGER_REGISTER", 7311),
            patch.object(config, "ROBOT_COMMAND_ACK_REGISTER", 7312),
        ]
        for item in patches:
            item.start()
        try:
            client.status_value = 9
            self.assertTrue(adapter.send_motion([-1.25, 2.5, 3.0, 0.0, 0.0, 0.0], speed=4.0, acceleration=5.0, timeout=0.3))
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(client.multiple_writes[0], (7212, [400, 500]))
        self.assertEqual(client.multiple_writes[1][0], 7200)
        self.assertEqual(client.multiple_writes[1][1][:4], [65535, 65411, 0, 250])
        self.assertIn((7310, 1), client.single_writes)
        self.assertIn((7311, config.ROBOT_COMMAND_TRIGGER_VALUE), client.single_writes)
        self.assertEqual(client.single_writes[-1], (7311, config.ROBOT_COMMAND_CLEAR_VALUE))

    def test_modbus_motion_requires_moving_after_ack(self):
        client = NoMovingFakeModbusClient(status_value=config.ROBOT_STATUS_COMPLETE_VALUE)
        adapter = ModbusAdapter(host="127.0.0.1", port=502)
        adapter.connected = True
        adapter.client = client

        with patch.object(modbus_adapter, "MODBUS_AVAILABLE", True):
            self.assertFalse(adapter.send_motion([1, 2, 3, 0, 0, 0], timeout=0.2))

        self.assertEqual(client.single_writes[-1], (
            config.ROBOT_COMMAND_TRIGGER_REGISTER,
            config.ROBOT_COMMAND_CLEAR_VALUE,
        ))

    def test_modbus_pose_register_write_does_not_trigger_motion(self):
        client = FakeModbusClient()
        adapter = ModbusAdapter(host="127.0.0.1", port=502)
        adapter.connected = True
        adapter.client = client

        with patch.object(modbus_adapter, "MODBUS_AVAILABLE", True):
            self.assertTrue(adapter.write_pose_registers([1, 2, 3, 0, 0, 0], speed=4, acceleration=5))

        trigger_writes = [
            item for item in client.single_writes
            if item[0] == getattr(config, "ROBOT_COMMAND_TRIGGER_REGISTER", 6999)
        ]
        self.assertEqual(trigger_writes, [])
        self.assertEqual(client.multiple_writes[0][0], config.ROBOT_PROFILE_REGISTER_BASE)
        self.assertEqual(client.multiple_writes[1][0], config.ROBOT_MOTION_REGISTER_BASE)

    def test_modbus_gripper_and_halt_use_configured_registers(self):
        client = FakeModbusClient()
        adapter = ModbusAdapter(host="127.0.0.1", port=502)
        adapter.connected = True
        adapter.client = client

        with patch.object(modbus_adapter, "MODBUS_AVAILABLE", True), patch.object(
            config, "ROBOT_GRIPPER_REGISTER", 7400
        ), patch.object(config, "ROBOT_GRIPPER_CLOSE_VALUE", 11), patch.object(
            config, "ROBOT_HALT_REGISTER", 7401
        ), patch.object(config, "ROBOT_HALT_VALUE", 99):
            self.assertTrue(adapter.set_gripper(True))
            adapter.halt()

        self.assertEqual(client.single_writes, [(7400, 11), (7401, 99)])


if __name__ == "__main__":
    unittest.main()
