from __future__ import annotations

from typing import Mapping


class VisionSystemProxy:
    def _target(self):
        from backend.infrastructure.vision.vision_system import vision_system as real_vision_system

        return real_vision_system

    @property
    def __class__(self):
        return self._target().__class__

    def __getattr__(self, name):
        return getattr(self._target(), name)


def runtime_vision_status_payload(vision_system, config) -> dict:
    if hasattr(vision_system, "get_status"):
        try:
            status = vision_system.get_status()
            if not isinstance(status, dict):
                return {"system": vision_system.__class__.__name__, "status": status}
            fallback_reason = (
                status.get("fallback_reason")
                or ((status.get("calibration") or {}) if isinstance(status.get("calibration"), Mapping) else {}).get("fallback_reason")
                or getattr(vision_system, "_fallback_reason", None)
            )
            fallback = bool(status.get("fallback") or fallback_reason)
            status.setdefault("configured_fake_vision", bool(getattr(config, "FAKE_VISION", False)))
            status["fallback"] = fallback
            if fallback_reason:
                status["fallback_reason"] = str(fallback_reason)
            if fallback:
                status["simulation"] = True
                status.setdefault("mode", "fallback")
            return status
        except Exception as exc:
            return {"error": str(exc), "system": vision_system.__class__.__name__}
    return {"system": vision_system.__class__.__name__}
