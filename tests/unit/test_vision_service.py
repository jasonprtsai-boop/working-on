import unittest
import os
from unittest.mock import patch

os.environ["FAKE_VISION"] = "1"
from backend.utils import config

config.FAKE_VISION = True

from backend.application.services.vision_service import VisionService
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent


class FakeCoordSystem:
    def pixel_to_cell(self, _x, _y):
        return 0, 0


class FakeMapper:
    coord_system = FakeCoordSystem()

    def map_detections(self, _detections):
        return {"0,0": "R"}


class FakeValidator:
    last_stable_state = {"0,0": "R"}

    def validate(self, board_state):
        return board_state


class EmptyValidator:
    last_stable_state = None


class FakeFenGenerator:
    def __init__(self):
        self.last_turn = None

    def generate(self, _state, turn="w"):
        self.last_turn = turn
        return "fen-from-vision"


class FakeDetector:
    pass


FakeDetector.__name__ = "YOLODetector"


class FakeVisionSystem:
    def __init__(self, *, validator=None, status=None):
        self.mapper = FakeMapper()
        self.validator = validator or FakeValidator()
        self.fen_gen = FakeFenGenerator()
        self.detector = FakeDetector()
        self._status = status or {"mode": "real", "simulation": False, "available": True}

    def get_status(self):
        return dict(self._status)


class FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class TestVisionService(unittest.TestCase):
    def test_board_detected_publishes_fen_ucci_and_detection_payloads(self):
        service = object.__new__(VisionService)
        service._vision = FakeVisionSystem()
        service.is_running = False
        bus = FakeBus()

        event = BaseEvent.create(
            event_type=EventType.VISION_BOARD_DETECTED,
            source="test",
            payload={
                "latency_ms": 12.5,
                "detections": [
                    {
                        "class_id": 1,
                        "class_name": "red_rook",
                        "confidence": 0.92,
                        "bbox": [0, 0, 20, 20],
                    }
                ],
            },
            trace_id="trace-vision",
        )

        with patch("backend.application.services.vision_service.bus", bus):
            service.on_board_detected(event)

        payloads = {item.event_type: item.payload for item in bus.events}
        move_payload = payloads[EventType.VISION_MOVE_DETECTED]
        frame_payload = payloads[EventType.VISION_FRAME_PROCESSED]

        self.assertEqual(move_payload["fen"], "fen-from-vision")
        self.assertEqual(move_payload["ucci_position"], "position fen fen-from-vision")
        self.assertEqual(move_payload["board_state"], {"0,0": "R"})
        self.assertEqual(move_payload["detections_count"], 1)
        self.assertEqual(move_payload["avg_confidence"], 0.92)
        self.assertEqual(move_payload["detections"][0]["cell"]["key"], "0,0")
        self.assertFalse(move_payload["fen_valid"])
        self.assertEqual(move_payload["fps"], 80.0)

        self.assertEqual(frame_payload["fen"], "fen-from-vision")
        self.assertTrue(frame_payload["stable"])
        self.assertEqual(frame_payload["trace_id"], "trace-vision")
        self.assertFalse(frame_payload["fen_valid"])
        self.assertEqual(frame_payload["fps"], 80.0)
        self.assertEqual(service._vision.fen_gen.last_turn, "w")

    def test_board_detected_uses_payload_turn_for_fen_generation(self):
        service = object.__new__(VisionService)
        service._vision = FakeVisionSystem()
        service.is_running = False
        bus = FakeBus()

        event = BaseEvent.create(
            event_type=EventType.VISION_BOARD_DETECTED,
            source="test",
            payload={
                "latency_ms": 12.5,
                "current_turn": "b",
                "detections": [
                    {
                        "class_id": 1,
                        "class_name": "紅色-車",
                        "confidence": 0.92,
                        "bbox": [0, 0, 20, 20],
                    }
                ],
            },
            trace_id="trace-vision",
        )

        with patch("backend.application.services.vision_service.bus", bus):
            service.on_board_detected(event)

        self.assertEqual(service._vision.fen_gen.last_turn, "b")

    def test_real_vision_without_stable_state_does_not_emit_default_fen(self):
        service = object.__new__(VisionService)
        service._vision = FakeVisionSystem(validator=EmptyValidator())

        with self.assertRaisesRegex(RuntimeError, "No stable real vision state"):
            service.get_current_fen()

    def test_simulation_without_stable_state_can_emit_default_fen(self):
        service = object.__new__(VisionService)
        service._vision = FakeVisionSystem(
            validator=EmptyValidator(),
            status={"mode": "simulation", "simulation": True},
        )

        fen, confidence = service.get_current_fen()

        self.assertIn("RNBAKABNR", fen)
        self.assertEqual(confidence, 0.95)


if __name__ == "__main__":
    unittest.main()
