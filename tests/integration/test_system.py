import os
import unittest


class TestSystemControlFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config

        cls.app, _socketio = create_app()
        cls.client = cls.app.test_client()
        login = cls.client.post(
            "/api/login",
            json={"username": "admin", "password": config.ADMIN_PASSWORD},
        )
        token = (login.get_json() or {}).get("token")
        cls.auth_headers = {"Authorization": f"Bearer {token}"}

    def test_estop_trigger_and_reset_cycle(self):
        before = self.client.get("/api/estop/status").get_json() or {}
        self.assertFalse(before.get("triggered", False))

        trigger = self.client.post(
            "/api/estop/trigger",
            json={"reason": "unit-test"},
            headers=self.auth_headers,
        )
        self.assertEqual(trigger.status_code, 200)

        active = self.client.get("/api/estop/status").get_json() or {}
        self.assertTrue(active.get("triggered"))
        self.assertTrue(active.get("global_stop"))

        reset = self.client.post("/api/estop/reset", headers=self.auth_headers)
        self.assertEqual(reset.status_code, 200)

        after = self.client.get("/api/estop/status").get_json() or {}
        self.assertFalse(after.get("triggered"))
        self.assertFalse(after.get("global_stop"))

    def test_control_endpoint_validates_requests(self):
        ok_resp = self.client.post(
            "/api/control",
            json={"action": "START", "payload": {"source": "test"}},
            headers=self.auth_headers,
        )
        self.assertEqual(ok_resp.status_code, 200)
        self.assertEqual((ok_resp.get_json() or {}).get("status"), "accepted")

        bad_resp = self.client.post("/api/control", json={"payload": {}}, headers=self.auth_headers)
        self.assertEqual(bad_resp.status_code, 400)

        unknown_resp = self.client.post(
            "/api/control",
            json={"action": "delete_database", "payload": {}},
            headers=self.auth_headers,
        )
        self.assertEqual(unknown_resp.status_code, 400)

        legacy_bad_resp = self.client.post("/api/control/delete_database", json={}, headers=self.auth_headers)
        self.assertEqual(legacy_bad_resp.status_code, 400)

    def test_control_endpoint_requires_admin_token(self):
        resp = self.app.test_client().post("/api/control", json={"action": "START", "payload": {}})
        self.assertEqual(resp.status_code, 401)
        payload = resp.get_json() or {}
        for key in ("code", "message", "trace_id", "recoverable", "details"):
            self.assertIn(key, payload)
        self.assertEqual(payload.get("code"), "unauthorized")

    def test_control_endpoint_replays_duplicate_idempotency_key(self):
        from backend.utils.idempotency import idempotency_store

        idempotency_store.clear()
        headers = {
            **self.auth_headers,
            "Idempotency-Key": "unit-test-control-key",
        }
        first = self.client.post(
            "/api/control",
            json={"action": "start_engine", "payload": {"source": "first"}},
            headers=headers,
        )
        second = self.client.post(
            "/api/control",
            json={"action": "reset", "payload": {"source": "second"}},
            headers=headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers.get("X-Idempotent-Replay"), "true")
        self.assertEqual((first.get_json() or {}).get("trace_id"), (second.get_json() or {}).get("trace_id"))

    def test_move_endpoint_rejects_illegal_move_and_accepts_legal_move(self):
        from backend.events.event_types import EventType
        from backend.events.models.base_event import BaseEvent
        from backend.state.store.manager.state_manager import state_manager

        state_manager.dispatch(BaseEvent.create(EventType.SYSTEM_RESET, "test", {}))

        illegal = self.client.post(
            "/api/move",
            json={"move": "b0d1", "player": "human"},
            headers=self.auth_headers,
        )
        self.assertEqual(illegal.status_code, 400)
        self.assertEqual((illegal.get_json() or {}).get("code"), "illegal_move")

        legal = self.client.post(
            "/api/move",
            json={"move": "a0a1", "player": "human"},
            headers=self.auth_headers,
        )
        self.assertEqual(legal.status_code, 200)
        self.assertEqual((legal.get_json() or {}).get("action"), "move")


if __name__ == "__main__":
    unittest.main()
