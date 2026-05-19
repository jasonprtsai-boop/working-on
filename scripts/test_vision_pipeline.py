from __future__ import annotations

import os
import sys
import time


def main() -> int:
    try:
        import cv2
        import numpy as np  # noqa: F401
    except Exception as e:
        print(f"[vision-test] Missing base deps (opencv/numpy): {e}")
        return 2

    try:
        from backend.infrastructure.vision.detection.sahi_detector import SAHIDetector, SAHI_AVAILABLE
        from backend.infrastructure.vision.board.board_mapper import BoardMapper
        from backend.utils import config
    except Exception as e:
        print(f"[vision-test] Failed to import SAHIDetector: {e}")
        return 2

    if not SAHI_AVAILABLE:
        print("[vision-test] SAHI not available. Install with: pip install -r requirements.vision.txt")
        return 2

    model_path = os.environ.get("YOLO_MODEL_PATH") or getattr(config, "YOLO_MODEL_PATH", "")
    model_path = os.path.abspath(model_path)
    if not os.path.exists(model_path):
        print(f"[vision-test] Model not found: {model_path}")
        return 1

    camera_index = int(os.environ.get("CAMERA_INDEX", "0"))
    print(f"[vision-test] Loading model: {model_path}")
    detector = SAHIDetector(model_path=model_path)
    if detector.model is None:
        print(f"[vision-test] Model load failed: {detector.get_status()}")
        return 1

    cap = None
    try:
        try:
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        except Exception:
            cap = cv2.VideoCapture(camera_index)

        if not cap.isOpened():
            print(f"[vision-test] Failed to open camera index={camera_index}")
            return 1

        # grab 1 frame
        start = time.time()
        frame = None
        while time.time() - start < 2.0:
            ok, f = cap.read()
            if ok and f is not None and getattr(f, "size", 0) > 0:
                frame = f
                break
            time.sleep(0.05)

        if frame is None:
            print("[vision-test] Camera opened but did not produce a frame within 2s")
            return 1

        dets = detector.detect(frame)
        print(f"[vision-test] OK detections={len(dets)} (camera_index={camera_index})")
        if dets:
            summary = {}
            for det in dets:
                summary[det.class_name] = summary.get(det.class_name, 0) + 1
            print(f"[vision-test] class_summary={summary}")

            mapper = BoardMapper()
            mapped = mapper.map_detections(dets)
            unknown = sorted({
                det.class_name
                for det in dets
                if mapper._map_class_to_piece(det.class_name) is None
            })
            print(f"[vision-test] mapped_cells={len(mapped)} unknown_labels={unknown}")
            if unknown:
                return 3
        return 0
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass


if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath("."))
    raise SystemExit(main())
