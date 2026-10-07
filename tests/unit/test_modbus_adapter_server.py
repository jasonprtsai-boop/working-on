from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.infrastructure.robot import modbus_adapter


class FakeDataBank:
    def set_holding_registers(self, address, values):
        return True

    def set_input_registers(self, address, values):
        return True


class ModbusAdapterServerTest(unittest.TestCase):
    def test_server_bind_failure_does_not_fallback_to_bind_all(self):
        adapter = modbus_adapter.ModbusAdapter(host="192.168.10.10", port=502)
        error = OSError("[WinError 10049] The requested address is not valid in its context")

        with patch.object(modbus_adapter, "MODBUS_AVAILABLE", True):
            with patch.object(modbus_adapter, "LoggingDataBank", FakeDataBank):
                with patch.object(modbus_adapter, "ModbusServer", side_effect=error, create=True) as server:
                    with patch.object(modbus_adapter.config, "ROBOT_MODBUS_SERVER_HOST", "192.168.10.50", create=True):
                        with patch.object(modbus_adapter.config, "ROBOT_MODBUS_SERVER_PORT", 1502, create=True):
                            self.assertFalse(adapter._connect_server())

        self.assertFalse(adapter.connected)
        self.assertIsNone(adapter.server)
        self.assertIsNone(adapter.data_bank)
        self.assertIn("192.168.10.50:1502", adapter.last_error)
        self.assertIn("ROBOT_MODBUS_SERVER_HOST", adapter.last_error)
        self.assertIn("10049", adapter.last_error)
        server.assert_called_once()
        self.assertEqual(server.call_args.kwargs["host"], "192.168.10.50")


if __name__ == "__main__":
    unittest.main()
