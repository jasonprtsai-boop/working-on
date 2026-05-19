import asyncio
import unittest
from unittest.mock import patch

from backend.application.services.robot_service import RobotService
from backend.infrastructure.robot import modbus_adapter
from backend.infrastructure.robot.modbus_adapter import ModbusAdapter


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def send_move(self, coordinates):
        self.calls.append(coordinates)
        return self.result


class TestRobotMotionFailClosed(unittest.TestCase):
    def test_motion_failure_preserves_position_and_raises(self):
        service = RobotService()
        service.connected = True
        service.adapter = FakeAdapter(False)
        service.pos = [10, 20, 30]

        with self.assertRaises(RuntimeError):
            asyncio.run(service._motion(1, 2, 3))

        self.assertEqual(service.pos, [10, 20, 30])
        self.assertEqual(len(service.adapter.calls), 1)

    def test_motion_success_updates_position(self):
        service = RobotService()
        service.connected = True
        service.adapter = FakeAdapter(True)

        asyncio.run(service._motion(1, 2, 3))

        self.assertEqual(service.pos, [1, 2, 3])

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


if __name__ == "__main__":
    unittest.main()
