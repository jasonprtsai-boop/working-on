import unittest
import os

from tests.helpers import socket_auth


class TestDiagnosticsContractKeys(unittest.TestCase):
    def test_diagnostics_updated_has_all_top_level_keys(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.events.bus.event_bus import bus

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            client.get_received()
            bus.publish({"type": "DIAGNOSTICS.UPDATED", "source": "test", "payload": {"engine": {"status": "OK"}}})
            socketio.sleep(0.05)
            received = client.get_received()
        finally:
            client.disconnect()

        msgs = [m for m in received if m.get("name") == "SYSTEM_STATE_UPDATE"]
        args0 = [m.get("args", [{}])[0] for m in msgs if m.get("args")]
        diags = [a for a in args0 if a.get("type") == "DIAGNOSTICS.UPDATED"]
        self.assertTrue(diags, "Expected DIAGNOSTICS.UPDATED emission")

        payload = diags[-1].get("payload") or {}
        for k in ("ui", "sync", "engine", "robot", "vision"):
            self.assertIn(k, payload, f"DIAGNOSTICS.UPDATED missing key: {k}")
            self.assertIsInstance(payload.get(k), dict, f"DIAGNOSTICS.UPDATED key {k} must be a dict")
