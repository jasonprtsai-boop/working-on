from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from backend.utils import config


@dataclass(frozen=True)
class DetectionModeConfig:
    mode: str
    description: str


DETECTION_MODE_CONFIGS: Dict[str, DetectionModeConfig] = {
    "full_yolo": DetectionModeConfig(
        mode="full_yolo",
        description="YOLO full-frame inference",
    ),
}

DEFAULT_DETECTION_MODES = tuple(DETECTION_MODE_CONFIGS.keys())


class DetectorModeFactory:
    """
    Builds the active YOLO detector pipeline.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        yolo_builder: Optional[Callable[[], object]] = None,
    ):
        self.model_path = os.path.abspath(model_path or config.YOLO_MODEL_PATH)
        self.yolo_builder = yolo_builder or self._build_yolo_detector

    def create(self, mode: str):
        self.mode_config(mode)
        return self.yolo_builder()

    def create_all(self, modes=None) -> Dict[str, object]:
        selected = list(modes or DEFAULT_DETECTION_MODES)
        return {mode: self.create(mode) for mode in selected}

    def mode_config(self, mode: str) -> DetectionModeConfig:
        normalized = str(mode or "").strip().lower()
        if normalized not in DETECTION_MODE_CONFIGS:
            raise ValueError(f"Unsupported detection mode: {mode}")
        return DETECTION_MODE_CONFIGS[normalized]

    def _build_yolo_detector(self):
        from backend.infrastructure.vision.detection.yolo_detector import YOLODetector

        return YOLODetector(model_path=self.model_path)
