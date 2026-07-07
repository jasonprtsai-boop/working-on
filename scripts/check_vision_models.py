from __future__ import annotations

import argparse
import json
import re
import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.infrastructure.protected_assets.manifest import validate_assets
from backend.infrastructure.vision.model_assets import vision_model_report
from backend.utils import config


MIN_ULTRALYTICS_VERSION = getattr(config, "ULTRALYTICS_MIN_VERSION", "8.4.55")


def _has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _installed_version(package_name: str) -> str | None:
    try:
        return package_version(package_name)
    except PackageNotFoundError:
        return None
    except Exception:
        return None


def _has_package(package_name: str) -> bool:
    return _installed_version(package_name) is not None


def _version_tuple(value: str | None) -> tuple[int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", str(value or ""))[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _version_at_least(installed: str | None, minimum: str) -> bool:
    return bool(installed) and _version_tuple(installed) >= _version_tuple(minimum)


def _check_ultralytics_version(failures: list[str]) -> None:
    installed = _installed_version("ultralytics")
    if not installed:
        failures.append("ultralytics is not installed")
        return
    if not _version_at_least(installed, MIN_ULTRALYTICS_VERSION):
        failures.append(f"ultralytics {installed} is below YOLO26 minimum {MIN_ULTRALYTICS_VERSION}")


def _warmup_candidate(path: str) -> tuple[bool, str | None]:
    import numpy as np

    from backend.infrastructure.vision.detection.yolo_detector import YOLODetector

    detector = YOLODetector(path, warmup_on_load=True)
    status = detector.get_status()
    if not status.get("loaded"):
        return False, str(status.get("last_error") or "model_not_loaded")
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    detector.detect(frame)
    status = detector.get_status()
    if status.get("last_error"):
        return False, str(status.get("last_error"))
    return True, None


def _check_manifest(failures: list[str]) -> None:
    report = validate_assets()
    if not report.get("items"):
        failures.append("protected asset manifest has no entries")
        return
    for item in report["items"]:
        if str(item.get("path", "")).startswith("vision/") and not item.get("ok"):
            failures.append(f"manifest mismatch: {item.get('path')}")


def _check_static(report: dict, failures: list[str]) -> None:
    model = report.get("model") or {}
    label = model.get("path")
    if model.get("extension") != ".onnx":
        failures.append("configured YOLO model must be .onnx")
    if not model.get("exists"):
        failures.append(f"missing YOLO model: {label}")
    if not model.get("protected"):
        failures.append(f"YOLO model is outside protected assets: {label}")
    if model.get("extension") == ".onnx" and not model.get("readonly"):
        failures.append(f"YOLO model is not read-only: {label}")

    dataset = report.get("dataset_mapping") or {}
    if not dataset.get("exists"):
        failures.append("dataset_mapping.yaml is missing")
    if not dataset.get("names_match_nc"):
        failures.append("dataset_mapping.yaml names count does not match nc")
    if report.get("class_count") != dataset.get("names_count"):
        failures.append("config YOLO_CLASS_NAMES count does not match dataset mapping")

    training_args = report.get("training_args") or {}
    if not training_args.get("exists"):
        failures.append("args.yaml is missing")


def _check_warmup(report: dict, failures: list[str], *, allow_runtime_skip: bool) -> None:
    missing_deps = []
    if not _has_module("numpy"):
        missing_deps.append("numpy")
    if not _has_package("ultralytics"):
        missing_deps.append("ultralytics")
    if missing_deps:
        message = "runtime warm-up skipped; missing dependencies: " + ", ".join(missing_deps)
        if allow_runtime_skip:
            print(f"[SKIP] {message}")
            return
        failures.append(message)
        return

    item = report.get("model") or {}
    ok, error = _warmup_candidate(str(item.get("path") or ""))
    status = "OK" if ok else "FAIL"
    print(f"[{status}] warmup {item.get('path')}")
    if not ok:
        failures.append(f"warm-up failed for {item.get('path')}: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate protected YOLO vision model assets.")
    parser.add_argument("--warmup", action="store_true", help="Load each model and run a tiny inference warm-up.")
    parser.add_argument(
        "--allow-runtime-skip",
        action="store_true",
        help="Do not fail warm-up when optional vision runtime dependencies are unavailable.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the model report as JSON.")
    args = parser.parse_args()

    report = vision_model_report()
    failures: list[str] = []
    _check_manifest(failures)
    _check_static(report, failures)
    _check_ultralytics_version(failures)
    if args.warmup:
        _check_warmup(report, failures, allow_runtime_skip=args.allow_runtime_skip)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        item = report.get("model") or {}
        print(
            "Ultralytics: "
            f"installed={report.get('ultralytics_version') or 'missing'} "
            f"minimum={report.get('ultralytics_min_version') or MIN_ULTRALYTICS_VERSION}"
        )
        print(f"YOLO model: {report['model_path']}")
        print(
            f"[{item.get('role', 'active')}] {item.get('path', '')} "
            f"exists={item.get('exists')} protected={item.get('protected')} readonly={item.get('readonly')} "
            f"size={item.get('size_bytes')} sha256={item.get('sha256') or 'n/a'}"
        )
        dataset = report.get("dataset_mapping") or {}
        print(
            "Dataset mapping: "
            f"exists={dataset.get('exists')} nc={dataset.get('nc')} "
            f"names={dataset.get('names_count')} match={dataset.get('names_match_nc')}"
        )

    if failures:
        print("Vision model check FAILED:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Vision model check OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
