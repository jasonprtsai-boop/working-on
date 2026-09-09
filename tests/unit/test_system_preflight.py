from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.application.services import system_preflight


class SystemPreflightTest(unittest.TestCase):
    def test_modbus_server_square_command_requires_tmflow_heartbeat(self):
        robot_status = {"connected": True, "heartbeat": 0, "robot_state_code": 0}

        with patch.object(system_preflight.config, "ROBOT_MODBUS_ROLE", "server", create=True):
            with patch.object(system_preflight.config, "ROBOT_MODBUS_PAYLOAD_MODE", "square_command", create=True):
                summary = system_preflight._robot_communication_summary(
                    fake_robot=False,
                    adapter="modbus",
                    robot_status=robot_status,
                )

        self.assertFalse(summary["ok"])
        self.assertIn("no TMflow heartbeat", summary["message"])

    def test_modbus_server_square_command_accepts_tmflow_heartbeat(self):
        robot_status = {"connected": True, "heartbeat": 3}

        with patch.object(system_preflight.config, "ROBOT_MODBUS_ROLE", "server", create=True):
            with patch.object(system_preflight.config, "ROBOT_MODBUS_PAYLOAD_MODE", "square_command", create=True):
                summary = system_preflight._robot_communication_summary(
                    fake_robot=False,
                    adapter="modbus",
                    robot_status=robot_status,
                )

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["details"]["modbus_heartbeat"], 3)

    def test_modbus_client_readiness_uses_connection_state(self):
        with patch.object(system_preflight.config, "ROBOT_MODBUS_ROLE", "client", create=True):
            summary = system_preflight._robot_communication_summary(
                fake_robot=False,
                adapter="modbus",
                robot_status={"connected": False},
            )

        self.assertFalse(summary["ok"])


if __name__ == "__main__":
    unittest.main()
