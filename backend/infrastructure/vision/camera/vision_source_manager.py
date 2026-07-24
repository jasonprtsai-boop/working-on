from __future__ import annotations

from typing import Optional

from backend.utils import config

from .camera_manager import CameraManager
from .tmflow_json_source import TMflowJsonFrameSource


def normalize_vision_source(source: str | None) -> str:
    value = str(source or "opencv").strip().lower()
    if value in {"usb", "usb_camera", "camera", "opencv_usb"}:
        return "opencv"
    if value in {"tmflow", "tmflow_camera", "tmflow_json_camera"}:
        return "tmflow_json"
    if value not in {"opencv", "tmflow_json"}:
        return "opencv"
    return value


class VisionSourceManager:
    """Small adapter that lets the vision pipeline switch frame sources safely."""

    def __init__(self, source: str | None = None):
        self.source = normalize_vision_source(source or getattr(config, "VISION_SOURCE", "opencv"))
        self.running = False
        self._delegate = self._build_delegate()

    def _build_delegate(self):
        if self.source == "tmflow_json":
            return TMflowJsonFrameSource()
        return CameraManager()

    def start(self) -> bool:
        ok = bool(self._delegate.start())
        self.running = ok
        return ok

    def stop(self):
        try:
            self._delegate.stop()
        finally:
            self.running = False

    def set_source(self, source: str | None = None, *, camera_index: Optional[int] = None) -> bool:
        next_source = normalize_vision_source(source or getattr(config, "VISION_SOURCE", self.source))
        was_running = self.running
        if camera_index is not None:
            try:
                config.CAMERA_INDEX = int(camera_index)
            except Exception:
                pass
        if was_running:
            self.stop()
        self.source = next_source
        config.VISION_SOURCE = next_source
        self._delegate = self._build_delegate()
        if was_running:
            return self.start()
        return True

    def set_camera_index(self, camera_index: int) -> bool:
        try:
            config.CAMERA_INDEX = int(camera_index)
        except Exception:
            return False
        if self.source == "opencv" and hasattr(self._delegate, "set_camera_index"):
            return bool(self._delegate.set_camera_index(config.CAMERA_INDEX))
        return True

    def get_resolution(self):
        if hasattr(self._delegate, "get_resolution"):
            return self._delegate.get_resolution()
        return (0, 0)

    def get_status(self) -> dict:
        if hasattr(self._delegate, "get_status"):
            status = dict(self._delegate.get_status())
        else:
            status = {}
        status["source"] = self.source
        status.setdefault("running", bool(self.running))
        status.setdefault("opened", False)
        return status
