import unittest
import os

from tests.helpers import socket_auth


class TestContractGuardBlocksInvalid(unittest.TestCase):
    def test_invalid_engine_info_payload_is_blocked_and_reports_diagnostics(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.events.bus.event_bus import bus
        from backend.events.models.base_event import BaseEvent

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            client.get_received()  # drain connect snapshot

            # pv must be a list; send a malformed payload to trigger contract guard.
            bus.publish(BaseEvent.create(
                event_type="ENGINE.INFO_UPDATED",
                source="test",
                payload={"pv": "not-a-list"},
            ))
            socketio.sleep(0.05)

            received = client.get_received()
        finally:
            client.disconnect()

        msgs = [m for m in received if m.get("name") == "SYSTEM_STATE_UPDATE"]
        args0 = [m.get("args", [{}])[0] for m in msgs if m.get("args")]

        engine_infos = [a for a in args0 if a.get("type") == "ENGINE.INFO_UPDATED"]
        self.assertFalse(engine_infos, "Invalid ENGINE.INFO_UPDATED should be blocked by contract guard")

        diags = [a for a in args0 if a.get("type") == "DIAGNOSTICS.UPDATED"]
        self.assertTrue(diags, "Expected DIAGNOSTICS.UPDATED after contract violation")

        # At least one diagnostics payload should include contract_error
        has_error = False
        for d in diags:
            payload = d.get("payload") or {}
            ui = payload.get("ui") if isinstance(payload.get("ui"), dict) else {}
            if "contract_error" in ui and "ENGINE.INFO_UPDATED" in str(ui.get("contract_error")):
                has_error = True
                break
        self.assertTrue(has_error, "DIAGNOSTICS.UPDATED should include ui.contract_error for the violation")
