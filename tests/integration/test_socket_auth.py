import os
import unittest

from tests.helpers import socket_auth


def _payload(result):
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, tuple) and result:
        return result[0]
    return result


class TestSocketAuth(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.utils.rate_limit import rate_limiter

        rate_limiter.clear()

    def test_socket_connect_without_token_gets_read_only_snapshot(self):
        from backend.main import create_app

        from backend.utils import config

        old_public_snapshot = config.SOCKET_PUBLIC_SNAPSHOT_ENABLED
        config.SOCKET_PUBLIC_SNAPSHOT_ENABLED = True
        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client())
        try:
            self.assertTrue(client.is_connected())
            received = client.get_received()
            state_msgs = [m for m in received if m.get("name") == "SYSTEM_STATE_UPDATE"]
            self.assertTrue(state_msgs, "Anonymous viewer did not receive state snapshot")

            result = _payload(client.emit("action", {"type": "RESET"}, callback=True))
            self.assertEqual(result.get("error"), "unauthorized")
        finally:
            config.SOCKET_PUBLIC_SNAPSHOT_ENABLED = old_public_snapshot
            client.disconnect()

    def test_socket_connect_without_token_can_be_rejected_when_public_snapshot_disabled(self):
        from backend.main import create_app
        from backend.utils import config

        old_public_snapshot = config.SOCKET_PUBLIC_SNAPSHOT_ENABLED
        config.SOCKET_PUBLIC_SNAPSHOT_ENABLED = False
        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client())
        try:
            self.assertFalse(client.is_connected())
        finally:
            config.SOCKET_PUBLIC_SNAPSHOT_ENABLED = old_public_snapshot
            if client.is_connected():
                client.disconnect()

    def test_socket_mutating_event_requires_admin_role(self):
        from backend.main import create_app

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth("viewer"))
        try:
            self.assertTrue(client.is_connected())
            result = _payload(client.emit("action", {"type": "RESET"}, callback=True))
            self.assertEqual(result.get("error"), "forbidden")
        finally:
            client.disconnect()

    def test_socket_action_validates_payload_and_allows_admin(self):
        from backend.events.bus.event_bus import bus
        from backend.main import create_app

        published = []

        def capture(event):
            event_type = getattr(event, "event_type", None)
            if hasattr(event_type, "value"):
                event_type = event_type.value
            if event_type == "SYSTEM_RESET":
                published.append(event)

        bus.subscribe_all(capture, key="test.socket_auth.capture", replace=True)

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            self.assertTrue(client.is_connected())
            invalid = _payload(client.emit("action", {}, callback=True))
            self.assertEqual(invalid.get("error"), "invalid_payload")
            self.assertIn("details", invalid)

            ok = _payload(client.emit("action", {"type": "RESET"}, callback=True))
            self.assertEqual(ok.get("ok"), True)
            socketio.sleep(0.05)
            self.assertTrue(published, "Expected admin RESET socket action to publish SYSTEM_RESET")
        finally:
            client.disconnect()
            bus.subscribe_all(lambda event: None, key="test.socket_auth.capture", replace=True)

    def test_socket_action_rejects_non_allowlisted_action_and_large_payload(self):
        from backend.main import create_app
        from backend.utils import config

        old_limit = config.MAX_SOCKET_PAYLOAD_BYTES
        old_allowlist = config.SOCKET_ACTION_ALLOWLIST
        config.MAX_SOCKET_PAYLOAD_BYTES = 48
        config.SOCKET_ACTION_ALLOWLIST = ("RESET",)

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            denied = _payload(client.emit("action", {"type": "PAUSE"}, callback=True))
            too_large = _payload(client.emit("vision_update", {"blob": "x" * 256}, callback=True))
        finally:
            config.MAX_SOCKET_PAYLOAD_BYTES = old_limit
            config.SOCKET_ACTION_ALLOWLIST = old_allowlist
            client.disconnect()

        self.assertEqual(denied.get("code"), "event_not_allowed")
        self.assertEqual(too_large.get("code"), "payload_too_large")

    def test_socket_action_rejects_unknown_action_during_validation(self):
        from backend.main import create_app

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            result = _payload(client.emit("action", {"type": "DELETE_DATABASE"}, callback=True))
        finally:
            client.disconnect()

        self.assertEqual(result.get("code"), "invalid_payload")

    def test_socket_action_rate_limit_returns_standard_error(self):
        from backend.main import create_app
        from backend.utils import config
        from backend.utils.rate_limit import rate_limiter

        old_limit = config.SOCKET_RATE_LIMIT_PER_MINUTE
        old_enabled = config.RATE_LIMITS_ENABLED
        config.SOCKET_RATE_LIMIT_PER_MINUTE = 1
        config.RATE_LIMITS_ENABLED = True
        rate_limiter.clear()

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            self.assertTrue(client.is_connected())
            first = _payload(client.emit("action", {"type": "RESET"}, callback=True))
            second = _payload(client.emit("action", {"type": "RESET"}, callback=True))
        finally:
            config.SOCKET_RATE_LIMIT_PER_MINUTE = old_limit
            config.RATE_LIMITS_ENABLED = old_enabled
            rate_limiter.clear()
            client.disconnect()

        self.assertEqual(first.get("ok"), True)
        self.assertEqual(second.get("code"), "rate_limited")
        self.assertTrue(second.get("recoverable"))


if __name__ == "__main__":
    unittest.main()
