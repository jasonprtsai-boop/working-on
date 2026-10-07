from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.application.bootstrap import _robot_connection_failure_message


class BootstrapRobotMessageTest(unittest.TestCase):
    def test_modbus_client_failure_message_includes_target_and_operator_hint(self):
        message = _robot_connection_failure_message(SimpleNamespace(
            ROBOT_ADAPTER="modbus",
            ROBOT_MODBUS_ROLE="client",
            ROBOT_IP="192.168.10.10",
            ROBOT_PORT=502,
            ROBOT_PC_IP="192.168.10.50",
        ))

        self.assertIn("adapter=modbus", message)
        self.assertIn("endpoint=192.168.10.10:502", message)
        self.assertIn("PC IP is configured as 192.168.10.50", message)
        self.assertIn("verify the PC/TM robot network", message)

    def test_modbus_server_failure_message_points_to_python_server_endpoint(self):
        message = _robot_connection_failure_message(SimpleNamespace(
            ROBOT_ADAPTER="modbus",
            ROBOT_MODBUS_ROLE="server",
            ROBOT_MODBUS_SERVER_HOST="192.168.10.50",
            ROBOT_MODBUS_SERVER_PORT=1502,
            ROBOT_IP="192.168.10.10",
            ROBOT_PORT=502,
            ROBOT_PC_IP="192.168.10.50",
        ))

        self.assertIn("adapter=modbus", message)
        self.assertIn("role=server", message)
        self.assertIn("server_endpoint=192.168.10.50:1502", message)
        self.assertIn("ROBOT_MODBUS_SERVER_HOST", message)
        self.assertIn("TMflow polls this endpoint", message)
        self.assertIn("Robot target is configured as 192.168.10.10:502", message)


if __name__ == "__main__":
    unittest.main()
