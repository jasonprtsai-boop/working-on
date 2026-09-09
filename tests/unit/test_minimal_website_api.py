from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, Response

from backend.interfaces.api.shared import api_bp
from backend.interfaces.api import control_routes, diagnostics_routes, export_routes, runtime_control_routes, vision_routes  # noqa: F401
from backend.interfaces.api import auth_guard
from backend.infrastructure.vision.capture_session import vision_capture_session

event_store_module = importlib.import_module("backend.events.store.event_store")


class MinimalWebsiteApiTest(unittest.TestCase):
    def setUp(self):
        vision_capture_session.stop(reason="test_setup")
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.register_blueprint(api_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def tearDown(self):
        vision_capture_session.stop(reason="test_teardown")

    def test_player_done_starts_backend_recognition(self):
        with patch.object(vision_routes, "_vision_capture_available_status", return_value={}):
            response = self.client.post("/api/player-done", json={"source": "test"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "player_done")
        self.assertTrue(payload["capture_session"]["active"])
        self.assertEqual(payload["capture_session"]["source"], "player_done")

    def test_stop_alias_publishes_pause_event(self):
        with patch.object(control_routes, "publish_base_event", return_value="trace-pause") as publish:
            response = self.client.post("/api/stop", json={"reason": "test_stop"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "stop")
        publish.assert_called_once()
        self.assertEqual(publish.call_args.kwargs["payload"]["reason"], "test_stop")

    def test_player_end_game_requires_explicit_confirmation(self):
        response = self.client.post("/api/player/end-game", json={"confirmed_action": "end_game"})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "player_end_confirmation_required")
        self.assertEqual(payload["details"]["required"]["final_confirmation"], "END_GAME_CONFIRMED")

    def test_player_end_game_returns_game_over_state(self):
        captured = {}

        def end_game(payload):
            captured.update(payload)
            return {
                "trace_id": "trace-ended",
                "game_result": {"ended": True, "reason": "player_ended", "winner": None, "legal_moves_count": 0},
            }

        fake_coordinator = SimpleNamespace(end_game_by_player=end_game)

        with patch.object(control_routes, "workflow_coordinator", fake_coordinator):
            response = self.client.post(
                "/api/player/end-game",
                json={
                    "source": "player_end_button",
                    "confirmed_action": "end_game",
                    "final_confirmation": "END_GAME_CONFIRMED",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "player_end_game")
        self.assertEqual(payload["game_result"]["reason"], "player_ended")
        self.assertEqual(payload["state"]["board"]["game_status"], "GAME_OVER")
        self.assertTrue(payload["state"]["board"]["ended"])
        self.assertEqual(captured["source"], "player_end_button")

    def test_player_start_blocks_when_preflight_has_hard_failure(self):
        preflight = {
            "ok": False,
            "ready": False,
            "checks": [
                {
                    "key": "vision_ready",
                    "ok": False,
                    "label": "Vision",
                    "message": "Vision is unavailable.",
                    "severity": "error",
                }
            ],
        }

        with patch.object(control_routes, "build_preflight_report", return_value=preflight):
            with patch.object(control_routes, "publish_base_event") as publish:
                response = self.client.post("/api/player/start", json={"source": "test"})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "player_preflight_failed")
        self.assertEqual(payload["details"]["preflight"]["failure_count"], 1)
        publish.assert_not_called()

    def test_events_returns_compact_monitor_payload(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.get("/api/events?limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("events", payload)
        self.assertIn("pipeline", payload)

    def test_camera_latest_uses_existing_snapshot_source(self):
        with patch.object(vision_routes, "snapshot", return_value=Response(b"jpg", mimetype="image/jpeg")):
            with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
                response = self.client.get("/api/camera/latest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.data, b"jpg")
        self.assertEqual(response.headers["X-Deprecated-Endpoint"], "true")
        self.assertEqual(response.headers["X-Replacement-Endpoint"], "/api/vision/snapshot")

    def test_legacy_export_aliases_advertise_replacements(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            json_response = self.client.get("/api/export_json")
            kpi_response = self.client.get("/api/export_kpi")

        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.headers["X-Deprecated-Endpoint"], "true")
        self.assertEqual(json_response.headers["X-Replacement-Endpoint"], "/api/state")
        self.assertEqual(kpi_response.status_code, 200)
        self.assertEqual(kpi_response.headers["X-Deprecated-Endpoint"], "true")
        self.assertEqual(kpi_response.headers["X-Replacement-Endpoint"], "/api/runtime/metrics")

    def test_csv_export_preserves_empty_session_filter_for_unassigned_events(self):
        captured = {}

        class FakeEventStore:
            def load_replay(self, *, session_id=None, limit=None):
                captured["session_id"] = session_id
                captured["limit"] = limit
                return [
                    {
                        "sequence_id": 1,
                        "session_id": "",
                        "trace_id": "trace-a",
                        "type": "STATE_UPDATED",
                        "timestamp": 123.0,
                        "payload": {"fen": "fen-a"},
                        "event_id": "event-a",
                        "source": "test",
                        "metadata": {},
                    }
                ]

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(event_store_module, "event_store", FakeEventStore()):
                response = self.client.get("/api/export/csv?session=")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["session_id"], "")
        self.assertIn("smart-chess-events-unassigned.csv", response.headers["Content-Disposition"])

    def test_csv_export_without_session_filter_exports_all_events(self):
        captured = {}

        class FakeEventStore:
            def load_replay(self, *, session_id=None, limit=None):
                captured["session_id"] = session_id
                captured["limit"] = limit
                return []

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(event_store_module, "event_store", FakeEventStore()):
                response = self.client.get("/api/export/csv")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(captured["session_id"])

    def test_legacy_control_shortcut_advertises_replacement(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(control_routes, "publish_base_event", return_value="trace-resume"):
                response = self.client.post("/api/control/resume", json={"source": "test"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Deprecated-Endpoint"], "true")
        self.assertEqual(response.headers["X-Replacement-Endpoint"], "/api/control")

    def test_runtime_ai_mode_rejects_unknown_mode(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.post("/api/runtime/ai-mode", json={"mode": "cinematic"})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "invalid_ai_mode")
        self.assertIn("companionship", payload["details"]["supported_modes"])

    def test_runtime_ai_mode_accepts_supported_alias(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.post("/api/runtime/ai-mode", json={"mode": "train"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["ai_mode"], "training")
        self.assertEqual(payload["engine_depth"], 10)

    def test_runtime_engine_depth_rejects_out_of_range_value(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.post("/api/runtime/engine-depth", json={"depth": 999})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "invalid_depth")
        self.assertEqual(payload["details"]["supported_range"], {"min": 1, "max": 60})

    def test_runtime_engine_depth_accepts_supported_value(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.post("/api/runtime/engine-depth", json={"depth": 20})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["engine_depth"], 20)

    def test_runtime_safe_mode_requires_explicit_boolean_value(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.post("/api/runtime/safe-mode", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "invalid_safe_mode")

    def test_runtime_safe_mode_rejects_unknown_boolean_text(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.post("/api/runtime/safe-mode", json={"enabled": "banana"})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "invalid_safe_mode")

    def test_runtime_safe_mode_accepts_explicit_boolean_text(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            off_response = self.client.post("/api/runtime/safe-mode", json={"enabled": "off"})
            on_response = self.client.post("/api/runtime/safe-mode", json={"enabled": "on"})

        self.assertEqual(off_response.status_code, 200)
        self.assertFalse(off_response.get_json()["safe_mode"])
        self.assertEqual(on_response.status_code, 200)
        self.assertTrue(on_response.get_json()["safe_mode"])

    def test_runtime_session_start_rejects_duplicate_active_session(self):
        fake_runtime = SimpleNamespace(
            active_session_id="session-active",
            snapshot=lambda: {"session": {"session_id": "session-active", "active": True}},
            start_session=lambda participant_id="": self.fail("start_session should not be called"),
        )

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(runtime_control_routes, "runtime_control", fake_runtime):
                response = self.client.post("/api/runtime/session/start", json={"participant_id": "P-1"})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "session_already_active")
        self.assertEqual(payload["details"]["session"]["session_id"], "session-active")

    def test_runtime_session_end_rejects_when_no_session_is_active(self):
        fake_runtime = SimpleNamespace(
            active_session_id=None,
            snapshot=lambda: {"session": {"session_id": "", "active": False}},
            end_session=lambda: self.fail("end_session should not be called"),
        )

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(runtime_control_routes, "runtime_control", fake_runtime):
                response = self.client.post("/api/runtime/session/end", json={})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "session_not_active")
        self.assertFalse(payload["details"]["session"]["active"])


if __name__ == "__main__":
    unittest.main()
