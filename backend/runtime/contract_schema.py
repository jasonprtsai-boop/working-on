from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EngineInfoUpdatedPayload(BaseModel):
    score: float = 0
    depth: int = 0
    nodes: int = 0
    nps: int = 0
    best_move: str = ""
    pv: List[str] = Field(default_factory=list)
    multiPv: List[Any] = Field(default_factory=list)
    is_thinking: bool = False


class DiagnosticsUpdatedPayload(BaseModel):
    ui: Dict[str, Any] = Field(default_factory=dict)
    sync: Dict[str, Any] = Field(default_factory=dict)
    engine: Dict[str, Any] = Field(default_factory=dict)
    robot: Dict[str, Any] = Field(default_factory=dict)
    vision: Dict[str, Any] = Field(default_factory=dict)


class VisionFrameProcessedPayload(BaseModel):
    timestamp: float = 0.0
    latency_ms: float = 0.0
    fen: str = ""
    fen_after: str = ""
    ucci_position: str = ""
    board_state: Dict[str, Any] = Field(default_factory=dict)
    detections: List[Any] = Field(default_factory=list)
    detections_count: int = 0
    avg_confidence: float = 0.0
    min_confidence: float = 0.0
    confidence: float = 0.0
    sahi_enabled: bool = False
    stable: bool = False


class RobotStatusUpdatedPayload(BaseModel):
    connected: bool = False
    busy: bool = False
    error: Optional[str] = None
    last_action: str = ""
    queue_size: int = 0
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})


def validate_contract_payload(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Validate payload shape for contract events that have a stable schema.

    Raises pydantic ValidationError on mismatch.
    """
    if event_type == "ENGINE.INFO_UPDATED":
        EngineInfoUpdatedPayload.model_validate(payload or {})
        return
    if event_type == "DIAGNOSTICS.UPDATED":
        DiagnosticsUpdatedPayload.model_validate(payload or {})
        return
    if event_type == "VISION.FRAME_PROCESSED":
        VisionFrameProcessedPayload.model_validate(payload or {})
        return
    if event_type == "ROBOT.STATUS_UPDATED":
        RobotStatusUpdatedPayload.model_validate(payload or {})
        return

    # STATE_UPDATE payload schema is validated by `tests/integration/test_ws_contract_smoke.py`
    # since it is derived from `state_store` normalization.
    return


def normalize_diagnostics_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure DIAGNOSTICS.UPDATED payload always contains the canonical top-level keys
    so the frontend can safely render without optional chaining everywhere.
    """
    base = {
        "ui": {},
        "sync": {},
        "engine": {},
        "robot": {},
        "vision": {},
    }
    if not isinstance(payload, dict):
        return base
    out = dict(base)
    for k in base.keys():
        v = payload.get(k)
        if isinstance(v, dict):
            out[k] = v
    # Preserve any extra keys for debugging, but keep them out of the normalized contract root.
    extras = {k: v for k, v in payload.items() if k not in base}
    if extras:
        out["ui"] = dict(out["ui"])
        out["ui"].setdefault("extras", extras)
    return out
