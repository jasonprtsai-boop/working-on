from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.application.bootstrap import _robot_connection_failure_message


class BootstrapRobotMessageTest(unittest.TestCase):
    def test_robot_connection_failure_message_includes_target_and_operator_hint(self):
        message = _robot_connection_failure_message(SimpleNamespace(
            ROBOT_ADAPTER="modbus",
            ROBOT_IP="192.168.10.10",
            ROBOT_PORT=502,
            ROBOT_PC_IP="192.168.10.50",
        ))

        self.assertIn("adapter=modbus", message)
        self.assertIn("endpoint=192.168.10.10:502", message)
        self.assertIn("PC IP is configured as 192.168.10.50", message)
        self.assertIn("verify the PC/TM robot network", message)


if __name__ == "__main__":
    unittest.main()
