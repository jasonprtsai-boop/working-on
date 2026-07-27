import base64
import unittest
from unittest.mock import patch

import numpy as np

from backend.events.event_types import EventType
from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state
from backend.infrastructure.robot.tmflow_socket_ingest_server import TMflowSocketIngestServer


def _jpeg_payload(width=16, height=12, frame_id="frame"):
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - depends on optional vision runtime
        raise unittest.SkipTest(f"OpenCV unavailable: {exc}") from exc

    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = 120
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise AssertionError("JPEG encode failed")
    return {
        "id": frame_id,
        "image": base64.b64encode(encoded.tobytes()).decode("ascii"),
    }


class TestTMflowSocketIngestServer(unittest.TestCase):
    def setUp(self):
        tmflow_ingest_state.clear()

    def tearDown(self):
        tmflow_ingest_state.clear()

    def test_state_normalizes_tcp_joint_io_and_merges_status(self):
        snapshot = tmflow_ingest_state.update(
            {
                "tcp": [500.0, 100.0, 320.0, -180.0, 0.5, 90.0],
                "joint": [0, 20, -15, 90, 0, 45],
                "io": {"di1": True},
                "speed": 30,
            },
            remote=("127.0.0.1", 1000),
        )

        self.assertEqual(snapshot["position"], {"x": 500.0, "y": 100.0, "z": 320.0})
        self.assertEqual(snapshot["orientation"]["rz"], 90.0)
        self.assertEqual(snapshot["joint_angles"]["j2"], 20.0)
        self.assertTrue(snapshot["telemetry"]["io"]["di1"])

        merged = tmflow_ingest_state.merge_status({"connected": False, "telemetry": {"source": "tmflow_json"}})
        self.assertFalse(merged["connected"])
        self.assertEqual(merged["position"]["x"], 500.0)
        self.assertEqual(merged["telemetry"]["source"], "tmflow_socket_ingest")
        self.assertTrue(merged["connection"]["telemetry_connected"])

    def test_server_ingests_json_telemetry_and_image(self):
        payload = {
            **_jpeg_payload(frame_id="tm-001"),
            "type": "TMFLOW_TELEMETRY",
            "tcp": [500.0, 100.0, 320.0, -180.0, 0.5, 90.0],
            "joints": [0, 20, -15, 90, 0, 45],
        }
        server = TMflowSocketIngestServer(ingest_key="", send_ack=False)
        published = []

        with patch("backend.infrastructure.robot.tmflow_socket_ingest_server.bus.publish", side_effect=published.append):
            result = server.ingest_message(payload, remote=("127.0.0.1", 1000))

        self.assertTrue(result["ok"])
        self.assertTrue(result["telemetry_updated"])
        self.assertEqual(result["image"]["frame_size"], [16, 12])
        self.assertEqual(server.messages_received, 1)
        self.assertEqual(server.frames_received, 1)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].event_type, EventType.ROBOT_STATUS_UPDATED)
        self.assertEqual(published[0].payload["position"]["z"], 320.0)

    def test_server_accepts_csv_pose_from_socket_send(self):
        server = TMflowSocketIngestServer(ingest_key="", send_ack=False)

        result = server.ingest_message("500.23,100.25,320.11,-179.98,0.12,90.00\n", remote=("127.0.0.1", 1000))
        snapshot = tmflow_ingest_state.snapshot()

        self.assertTrue(result["ok"])
        self.assertEqual(snapshot["position"]["x"], 500.23)
        self.assertEqual(snapshot["orientation"]["rz"], 90.0)

    def test_invalid_pose_values_do_not_shift_axes(self):
        server = TMflowSocketIngestServer(ingest_key="", send_ack=False)

        result = server.ingest_message({"tcp": [1, 2, "bad", 4, 5, 6]}, remote=("127.0.0.1", 1000))

        self.assertFalse(result["ok"])
        self.assertIsNone(tmflow_ingest_state.snapshot())

    def test_server_requires_trusted_remote_or_key(self):
        server = TMflowSocketIngestServer(ingest_key="", send_ack=False)

        result = server.ingest_message({"tcp": [1, 2, 3, 4, 5, 6]}, remote=("203.0.113.10", 1000))

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "unauthorized")

    def test_server_accepts_configured_key(self):
        server = TMflowSocketIngestServer(ingest_key="secret", send_ack=False)

        result = server.ingest_message(
            {"key": "secret", "tcp": [1, 2, 3, 4, 5, 6]},
            remote=("203.0.113.10", 1000),
        )

        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
