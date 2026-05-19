import unittest
import os

from tests.helpers import socket_auth


class TestWebSocketContractSmoke(unittest.TestCase):
    def test_ws_connect_emits_state_update_contract(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            received = client.get_received()
        finally:
            client.disconnect()

        # Expect at least one SYSTEM_STATE_UPDATE with type STATE_UPDATE
        state_msgs = [m for m in received if m.get("name") == "SYSTEM_STATE_UPDATE"]
        self.assertTrue(state_msgs, "No SYSTEM_STATE_UPDATE received on connect")

        payloads = [m.get("args", [{}])[0] for m in state_msgs if m.get("args")]
        state_updates = [p for p in payloads if p.get("type") == "STATE_UPDATE"]
        self.assertTrue(state_updates, "No STATE_UPDATE contract event received")
        self.assertTrue(state_updates[0].get("contract_version"), "Missing socket contract_version")

        first = state_updates[0].get("payload") or {}
        # Contract: frontend Normalizer expects these keys to exist for STATE_UPDATE.
        for k in ("board", "engine", "robot", "sync", "ui", "notation"):
            self.assertIn(k, first, f"STATE_UPDATE missing key: {k}")

        board = first.get("board") or {}
        pieces = board.get("pieces") or []
        self.assertTrue(pieces, "STATE_UPDATE board has no renderable pieces")
        for key in ("id", "type", "pos"):
            self.assertIn(key, pieces[0], f"STATE_UPDATE board piece missing key: {key}")
        self.assertIn(board.get("turn"), {"red", "black"})

        robot = first.get("robot") or {}
        for key in ("connected", "busy", "error", "last_action", "queue_size", "position"):
            self.assertIn(key, robot, f"STATE_UPDATE robot missing key: {key}")
        self.assertTrue((first.get("sync") or {}).get("contract_version"), "STATE_UPDATE sync missing contract_version")

    def test_ws_connect_snapshot_is_sent_only_to_new_client(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app

        app, socketio = create_app()
        flask_client_one = app.test_client()
        client_one = socketio.test_client(app, flask_test_client=flask_client_one, auth=socket_auth())
        try:
            self.assertTrue(client_one.is_connected())
            client_one.get_received()

            flask_client_two = app.test_client()
            client_two = socketio.test_client(app, flask_test_client=flask_client_two, auth=socket_auth())
            try:
                self.assertTrue(client_two.is_connected())
                leaked_to_first = [
                    (message.get("args") or [{}])[0]
                    for message in client_one.get_received()
                    if message.get("name") == "SYSTEM_STATE_UPDATE"
                    and (message.get("args") or [{}])[0].get("type") == "STATE_UPDATE"
                ]
                received_by_second = [
                    (message.get("args") or [{}])[0]
                    for message in client_two.get_received()
                    if message.get("name") == "SYSTEM_STATE_UPDATE"
                    and (message.get("args") or [{}])[0].get("type") == "STATE_UPDATE"
                ]
            finally:
                client_two.disconnect()
        finally:
            client_one.disconnect()

        self.assertEqual(leaked_to_first, [])
        self.assertTrue(received_by_second, "New client did not receive its initial STATE_UPDATE")
