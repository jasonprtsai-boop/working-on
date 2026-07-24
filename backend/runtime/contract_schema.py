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
    health: Dict[str, Any] = Field(default_factory=dict)
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    queue: Dict[str, Any] = Field(default_factory=dict)
    queues: Dict[str, Any] = Field(default_factory=dict)
    pipeline: Dict[str, Any] = Field(default_factory=dict)
    topology: Dict[str, Any] = Field(default_factory=dict)
    workers: Dict[str, Any] = Field(default_factory=dict)
    event_bus: Dict[str, Any] = Field(default_factory=dict)
    persistence: Dict[str, Any] = Field(default_factory=dict)
    async_runtime: Dict[str, Any] = Field(default_factory=dict)
    control: Dict[str, Any] = Field(default_factory=dict)
    runtime: Dict[str, Any] = Field(default_factory=dict)


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
    stable: bool = False


class RobotStatusUpdatedPayload(BaseModel):
    connected: bool = False
    is_connected: bool = False
    busy: bool = False
    error: Optional[str] = None
    last_action: str = ""
    queue_size: int = 0
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    orientation: Dict[str, float] = Field(default_factory=dict)
    joint_angles: Dict[str, float] = Field(default_factory=dict)
    speed: float = 0.0
    ip: str = ""
    port: int = 0
    connection: Dict[str, Any] = Field(default_factory=dict)
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    status_code: Optional[int] = None
    status_label: str = ""
    error_code: Optional[int] = None
    gripper_status_code: Optional[int] = None


class StateUpdatePayload(BaseModel):
    board: Dict[str, Any] = Field(default_factory=dict)
    engine: Dict[str, Any] = Field(default_factory=dict)
    robot: Dict[str, Any] = Field(default_factory=dict)
    sync: Dict[str, Any] = Field(default_factory=dict)
    ui: Dict[str, Any] = Field(default_factory=dict)
    notation: Any = None
    vision: Dict[str, Any] = Field(default_factory=dict)
    game: Dict[str, Any] = Field(default_factory=dict)


from backend.utils.logger import logger

class HealthSchema(BaseModel):
    fps: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    threads: int = 0
    gpu: Dict[str, Any] = Field(default_factory=dict)
    temperature: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = 0.0
    interval_sec: float = 0.0

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

        # Soft validation for nested schemas
        p = payload or {}
        if "health" in p:
            try:
                HealthSchema.model_validate(p["health"])
            except Exception as e:
                logger.warning(f"[ContractSchema] DIAGNOSTICS.UPDATED 'health' schema mismatch: {e}")
        return
    if event_type == "VISION.FRAME_PROCESSED":
        VisionFrameProcessedPayload.model_validate(payload or {})
        return
    if event_type == "ROBOT.STATUS_UPDATED":
        RobotStatusUpdatedPayload.model_validate(payload or {})
        return
    if event_type == "STATE_UPDATE":
        StateUpdatePayload.model_validate(payload or {})
        return

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
        "health": {},
        "telemetry": {},
        "queue": {},
        "queues": {},
        "pipeline": {},
        "topology": {},
        "workers": {},
        "event_bus": {},
        "persistence": {},
        "async_runtime": {},
        "control": {},
        "runtime": {},
    }
    if not isinstance(payload, dict):
        return base
    out = {k: {} for k in base.keys()}
    for k in base.keys():
        v = payload.get(k)
        if isinstance(v, dict):
            out[k] = v

    if not out["queue"] and out["queues"]:
        out["queue"] = out["queues"]
    if not out["queues"] and out["queue"]:
        out["queues"] = out["queue"]

    runtime = dict(out["runtime"])
    for key in ("event_bus", "persistence", "async_runtime", "control"):
        if out[key] and key not in runtime:
            runtime[key] = out[key]
    if runtime:
        out["runtime"] = runtime

    # Preserve any extra keys for debugging, but keep them out of the normalized contract root.
    extras = {k: v for k, v in payload.items() if k not in base}
    if extras:
        out["ui"] = dict(out["ui"])
        out["ui"].setdefault("extras", extras)
    return out
