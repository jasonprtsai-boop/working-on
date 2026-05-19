from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable, List


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}


def _load_cv2():
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"opencv is required for vision benchmark: {exc}") from exc
    return cv2


def frames_from_camera(camera_index: int, limit: int) -> Iterable:
    cv2 = _load_cv2()
    try:
        cap = cv2.VideoCapture(int(camera_index), cv2.CAP_DSHOW)
    except Exception:
        cap = cv2.VideoCapture(int(camera_index))

    if not cap.isOpened():
        raise RuntimeError(f"camera could not be opened: {camera_index}")

    try:
        count = 0
        while count < limit:
            ok, frame = cap.read()
            if ok and frame is not None and getattr(frame, "size", 0) > 0:
                count += 1
                yield frame
            else:
                time.sleep(0.05)
    finally:
        cap.release()


def frames_from_video(path: Path, limit: int) -> Iterable:
    cv2 = _load_cv2()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"video could not be opened: {path}")
    try:
        count = 0
        while count < limit:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            count += 1
            yield frame
    finally:
        cap.release()


def frames_from_images(path: Path, limit: int) -> Iterable:
    cv2 = _load_cv2()
    if path.is_file():
        files = [path]
    else:
        files = sorted(item for item in path.iterdir() if item.suffix.lower() in IMAGE_EXTENSIONS)
    for item in files[:limit]:
        frame = cv2.imread(str(item))
        if frame is not None:
            yield frame


def load_frames(input_path: str, camera_index: int, limit: int) -> List:
    if input_path:
        path = Path(input_path)
        if not path.exists():
            raise RuntimeError(f"input path does not exist: {path}")
        suffix = path.suffix.lower()
        if path.is_dir() or suffix in IMAGE_EXTENSIONS:
            return list(frames_from_images(path, limit))
        if suffix in VIDEO_EXTENSIONS:
            return list(frames_from_video(path, limit))
        raise RuntimeError(f"unsupported input type: {path}")
    return list(frames_from_camera(camera_index, limit))


def append_excel_log(rows: List[dict], workbook: str, session_id: str) -> None:
    from backend.utils.serialization.excel_exporter import ExcelExporter

    exporter = ExcelExporter(filename=workbook, subscribe=False)
    for row in rows:
        payload = dict(row)
        payload.setdefault("session_id", session_id)
        exporter.log_event(
            {"session_id": session_id},
            {
                "type": "VISION_BENCHMARK_RESULT",
                "source": "vision_benchmark",
                "data": payload,
            },
        )


def save_annotated_images(frames: List, rows: List[dict], output_dir: str) -> List[dict]:
    cv2 = _load_cv2()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for row in rows:
        frame_id = int(row.get("frame_id", 0) or 0)
        if frame_id < 0 or frame_id >= len(frames):
            continue

        mode = _safe_filename(str(row.get("mode", "mode") or "mode"))
        image = frames[frame_id].copy()
        detections = _load_detection_rows(row)

        for det in detections:
            bbox = det.get("bbox") if isinstance(det, dict) else None
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
            label = str(det.get("class_name", ""))
            confidence = float(det.get("confidence", 0.0) or 0.0)
            cv2.rectangle(image, (x1, y1), (x2, y2), (36, 160, 237), 2)
            cv2.putText(
                image,
                f"{label} {confidence:.2f}",
                (x1, max(16, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (36, 160, 237),
                1,
                cv2.LINE_AA,
            )

        fen = str(row.get("fen", "") or "")
        overlay = f"{mode} | detections={row.get('detections_count', 0)} | FEN={fen[:72]}"
        cv2.rectangle(image, (0, 0), (image.shape[1], 30), (17, 24, 39), -1)
        cv2.putText(image, overlay, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        filename = f"frame_{frame_id:05d}_{mode}.jpg"
        image_path = out_dir / filename
        cv2.imwrite(str(image_path), image)

        manifest.append(
            {
                "frame_id": frame_id,
                "mode": row.get("mode", ""),
                "fen": fen,
                "fen_valid": bool(row.get("fen_valid")),
                "detections_count": int(row.get("detections_count", 0) or 0),
                "annotated_image": str(image_path),
            }
        )

    manifest_path = out_dir / "fen_results.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _load_detection_rows(row: dict) -> List[dict]:
    value = row.get("detections_json", "[]")
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _safe_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    return safe.strip("_") or "mode"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run A-D runtime comparison for YOLO/SAHI/ROI vision modes.")
    parser.add_argument("--input", help="Image file, image directory, or video file. Omit to use camera.")
    parser.add_argument("--camera-index", type=int, default=int(os.environ.get("CAMERA_INDEX", "0")))
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--modes", default="full_yolo,sahi,roi_yolo,roi_sahi")
    parser.add_argument("--model-path", default=os.environ.get("YOLO_MODEL_PATH", ""))
    parser.add_argument("--output", default="")
    parser.add_argument("--save-annotated", default="", help="Optional directory for annotated prediction images and FEN manifest.")
    parser.add_argument("--append-excel", default="", help="Optional workbook path to append benchmark events.")
    parser.add_argument("--session-id", default=f"vision-benchmark-{int(time.time())}")
    args = parser.parse_args()

    sys.path.insert(0, os.path.abspath("."))

    from backend.infrastructure.vision.benchmark import VisionDetectionBenchmark
    from backend.infrastructure.vision.detection.mode_factory import DetectorModeFactory

    frames = load_frames(args.input or "", args.camera_index, max(1, int(args.frames)))
    if not frames:
        print("[vision-benchmark] no frames loaded")
        return 1

    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    factory = DetectorModeFactory(model_path=args.model_path or None)
    benchmark = VisionDetectionBenchmark(modes=modes, factory=factory)
    rows = benchmark.run_frames(frames)
    summary = benchmark.summarize(rows)

    output = {
        "session_id": args.session_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "frames": len(frames),
        "modes": modes,
        "metric_policy": {
            "runtime_metrics": True,
            "map_50": "N/A",
            "recall": "N/A",
            "reason": "requires_annotations",
        },
        "summary": summary,
        "rows": rows,
    }

    if args.save_annotated:
        manifest = save_annotated_images(frames, rows, args.save_annotated)
        output["annotated_output"] = args.save_annotated
        output["annotated_images"] = manifest

    out_path = Path(args.output) if args.output else Path("logs") / "vision_benchmark" / f"{args.session_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.append_excel:
        append_excel_log(rows, args.append_excel, args.session_id)

    print(f"[vision-benchmark] frames={len(frames)} modes={','.join(modes)} output={out_path}")
    if args.save_annotated:
        print(f"[vision-benchmark] annotated={args.save_annotated}")
    for item in summary:
        print(
            "[vision-benchmark] "
            f"{item['mode']}: avg_fps={item['avg_fps']} "
            f"avg_latency={item['avg_end_to_end_latency_ms']}ms "
            f"small_rate={item['avg_small_object_rate']} "
            "mAP@0.5=N/A recall=N/A"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
