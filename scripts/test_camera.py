from __future__ import annotations

import os
import sys
import time


def main() -> int:
    try:
        import cv2
    except Exception as e:
        print(f"[camera-test] OpenCV not available: {e}")
        return 2

    camera_index = int(os.environ.get("CAMERA_INDEX", "0"))
    out_path = os.environ.get("CAMERA_TEST_OUT", os.path.join("logs", "camera_test.jpg"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    cap = None
    try:
        try:
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        except Exception:
            cap = cv2.VideoCapture(camera_index)

        if not cap.isOpened():
            print(f"[camera-test] Failed to open camera index={camera_index}")
            return 1

        # warmup
        start = time.time()
        frame = None
        while time.time() - start < 2.0:
            ok, f = cap.read()
            if ok and f is not None and getattr(f, "size", 0) > 0:
                frame = f
                break
            time.sleep(0.05)

        if frame is None:
            print("[camera-test] Opened camera but did not get a valid frame within 2s")
            return 1

        ok = cv2.imwrite(out_path, frame)
        if not ok:
            print(f"[camera-test] Got frame but failed to write: {out_path}")
            return 1

        h, w = frame.shape[:2]
        print(f"[camera-test] OK camera_index={camera_index} frame={w}x{h} saved={out_path}")
        return 0
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
