import base64
import io
import json
import socket
import threading
import time
import unittest

import numpy as np

from backend.infrastructure.vision.camera.tmflow_json_source import TMflowJsonFrameSource


def _jpeg_payload(width=16, height=12, frame_id="frame"):
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - depends on optional vision runtime
        raise unittest.SkipTest(f"OpenCV unavailable: {exc}") from exc

    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 1] = 180
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise AssertionError("JPEG encode failed")
    return {
        "id": frame_id,
        "type": "VISION_FRAME",
        "encoding": "jpeg_base64",
        "image": base64.b64encode(encoded.tobytes()).decode("ascii"),
    }


def _wait_until(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class _ReconnectFrameServer:
    def __init__(self, lines):
        self.lines = list(lines)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(4)
        self._socket.settimeout(3.0)
        self.port = self._socket.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        try:
            self._socket.close()
        except Exception:
            pass
        self.thread.join(timeout=1.0)

    def _serve(self):
        for line in self.lines:
            try:
                conn, _ = self._socket.accept()
            except OSError:
                return
            with conn:
                conn.sendall(line)


class TestTMflowJsonFrameSource(unittest.TestCase):
    def test_decode_payload_accepts_jpeg_base64_frame(self):
        try:
            import cv2
        except Exception as exc:  # pragma: no cover - depends on optional vision runtime
            self.skipTest(f"OpenCV unavailable: {exc}")

        frame = np.zeros((12, 16, 3), dtype=np.uint8)
        frame[:, :, 1] = 180
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)

        decoded = TMflowJsonFrameSource.decode_payload({
            "type": "VISION_FRAME",
            "encoding": "jpeg_base64",
            "image": base64.b64encode(encoded.tobytes()).decode("ascii"),
        })

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, frame.shape)

    def test_decode_payload_accepts_data_url_frame(self):
        try:
            import cv2
        except Exception as exc:  # pragma: no cover - depends on optional vision runtime
            self.skipTest(f"OpenCV unavailable: {exc}")

        frame = np.zeros((8, 10, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)

        decoded = TMflowJsonFrameSource.decode_payload({
            "image": "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii"),
        })

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, frame.shape)

    def test_socket_source_reconnects_after_stream_close(self):
        lines = [
            (json.dumps(_jpeg_payload(frame_id="first")) + "\n").encode("utf-8"),
            (json.dumps(_jpeg_payload(frame_id="second")) + "\n").encode("utf-8"),
        ]
        server = _ReconnectFrameServer(lines)
        source = TMflowJsonFrameSource(
            host="127.0.0.1",
            port=server.port,
            timeout_sec=0.2,
            fps_limit=60.0,
        )
        try:
            server.start()
            self.assertTrue(source.start())
            self.assertTrue(_wait_until(lambda: source.frames_received >= 2 and source.reconnects >= 1))
            self.assertEqual(source.last_frame_id, "second")
        finally:
            source.stop()
            server.close()

    def test_socket_source_rejects_oversized_payload(self):
        class OversizedSocket:
            def makefile(self, _mode):
                return io.BytesIO(b"x" * 12 + b"\n")

        source = TMflowJsonFrameSource(max_message_bytes=8)

        with self.assertRaises(ValueError):
            source._read_loop(OversizedSocket())

    def test_ingest_payload_reports_decode_failure(self):
        source = TMflowJsonFrameSource()

        result = source.ingest_payload({"image": "not-jpeg"}, apply_fps_limit=False)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "decode_failed")
        self.assertEqual(source.decode_failures, 1)
        self.assertIn("could not be decoded", source.last_error)

    def test_ingest_payload_applies_fps_limit(self):
        payload = _jpeg_payload()
        source = TMflowJsonFrameSource(fps_limit=30.0)

        first = source.ingest_payload(payload, apply_fps_limit=True)
        second = source.ingest_payload(payload, apply_fps_limit=True)

        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertTrue(second["dropped"])
        self.assertEqual(second["reason"], "fps_limited")
        self.assertEqual(source.dropped_frames, 1)


if __name__ == "__main__":
    unittest.main()
