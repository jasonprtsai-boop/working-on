import time
import unittest
import os

from tests.helpers import socket_auth


class TestContractPayloadSchemas(unittest.TestCase):
    def test_contract_payloads_roundtrip_via_socket(self):
        os.environ["FAKE_VISION"] = "1"
        from backend.utils import config

        config.FAKE_VISION = True
        from backend.main import create_app
        from backend.events.bus.event_bus import bus
        from backend.runtime.contract_schema import validate_contract_payload
        from backend.events.models.base_event import BaseEvent
        from backend.events.event_types import EventType

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            # Drain initial connect snapshot
            client.get_received()

            test_events = [
                (
                    "ENGINE.INFO_UPDATED",
                    {
                        "score": 12.3,
                        "depth": 8,
                        "nodes": 1000,
                        "nps": 5000,
                        "best_move": "e2e4",
                        "pv": ["e2e4", "e7e5"],
                        "multiPv": [],
                        "is_thinking": False,
                    },
                ),
                (
                    "DIAGNOSTICS.UPDATED",
                    {
                        "ui": {},
                        "sync": {},
                        "engine": {"status": "OK"},
                        "robot": {"connected": False},
                        "vision": {"status": "OK"},
                    },
                ),
                (
                    "VISION.FRAME_PROCESSED",
                    {
                        "timestamp": time.time(),
                        "latency_ms": 10.0,
                        "fen": "fen-test",
                        "fen_after": "fen-test",
                        "ucci_position": "position fen fen-test",
                        "board_state": {"0,0": "R"},
                        "detections": [
                            {
                                "class_name": "red_rook",
                                "confidence": 0.91,
                                "bbox": [0, 0, 10, 10],
                                "cell": {"key": "0,0"},
                            }
                        ],
                        "detections_count": 1,
                        "avg_confidence": 0.91,
                        "min_confidence": 0.91,
                        "confidence": 0.91,
                        "sahi_enabled": True,
                        "stable": True,
                    },
                ),
                (
                    "ROBOT.STATUS_UPDATED",
                    {
                        "connected": False,
                        "busy": False,
                        "error": None,
                        "last_action": "",
                        "queue_size": 0,
                        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    },
                ),
            ]

            for et, payload in test_events:
                # Validate our outgoing test payloads match schema
                validate_contract_payload(et, payload)
                bus.publish({"type": et, "payload": payload, "source": "test"})

            # Also validate the canonical producer path: BaseEvent(ENGINE_ANALYSIS_COMPLETED) -> ENGINE.INFO_UPDATED
            bus.publish(
                BaseEvent.create(
                    event_type=EventType.ENGINE_ANALYSIS_COMPLETED,
                    source="test",
                    payload={
                        "bestmove": "e2e4",
                        "final": True,
                        "pv": "e2e4 e7e5",
                        "depth": 12,
                        "nodes": 1234,
                        "nps": 5678,
                        "score": 0.42,
                    },
                )
            )
            bus.publish(
                BaseEvent.create(
                    event_type=EventType.VISION_FRAME_PROCESSED,
                    source="test",
                    payload={
                        "timestamp": time.time(),
                        "latency_ms": 8.5,
                        "fen": "",
                        "fen_after": "",
                        "ucci_position": "",
                        "board_state": {},
                        "detections": [],
                        "detections_count": 0,
                        "avg_confidence": 0,
                        "min_confidence": 0,
                        "confidence": 0,
                        "sahi_enabled": False,
                        "stable": False,
                    },
                )
            )
            socketio.sleep(0.05)

            received = client.get_received()
        finally:
            client.disconnect()

        msgs = [m for m in received if m.get("name") == "SYSTEM_STATE_UPDATE"]
        types = [m.get("args", [{}])[0].get("type") for m in msgs if m.get("args")]

        for et, payload in test_events:
            self.assertIn(et, types, f"Missing socket emission for contract event: {et}")
        self.assertIn("ENGINE.INFO_UPDATED", types, "Missing ENGINE.INFO_UPDATED from BaseEvent producer path")
        self.assertIn("VISION.FRAME_PROCESSED", types, "Missing VISION.FRAME_PROCESSED from BaseEvent producer path")

        # Validate received payloads match schema too
        for m in msgs:
            arg0 = (m.get("args") or [{}])[0] or {}
            self.assertTrue(arg0.get("contract_version"), "Socket envelope missing contract_version")
            et = arg0.get("type")
            payload = arg0.get("payload") or {}
            validate_contract_payload(et, payload)
