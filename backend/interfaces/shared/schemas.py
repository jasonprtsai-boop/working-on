from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ControlAction(str, Enum):
    START_ENGINE = "start_engine"
    STOP_ENGINE = "stop_engine"
    SYNC_VISION = "sync_vision"
    RESET = "reset"
    PAUSE = "pause"
    UNDO = "undo"
    RESUME = "resume"


_CONTROL_ACTION_ALIASES = {
    "START": ControlAction.START_ENGINE.value,
    "START_ENGINE": ControlAction.START_ENGINE.value,
    "ENGINE_START": ControlAction.START_ENGINE.value,
    "STOP": ControlAction.STOP_ENGINE.value,
    "STOP_ENGINE": ControlAction.STOP_ENGINE.value,
    "ENGINE_STOP": ControlAction.STOP_ENGINE.value,
    "SYNC": ControlAction.SYNC_VISION.value,
    "SYNC_VISION": ControlAction.SYNC_VISION.value,
    "VISION_SYNC": ControlAction.SYNC_VISION.value,
    "RESET": ControlAction.RESET.value,
    "PAUSE": ControlAction.PAUSE.value,
    "UNDO": ControlAction.UNDO.value,
    "RESUME": ControlAction.RESUME.value,
}


class ControlCommandSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    action: ControlAction
    payload: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(None, alias="X-Idempotency-Key")

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value):
        text = str(value or "").strip()
        if not text:
            return value
        key = text.replace("-", "_").upper()
        return _CONTROL_ACTION_ALIASES.get(key, text.lower())


class PlayerMoveSchema(BaseModel):
    move: str = Field(..., min_length=4, max_length=4, pattern=r"^[a-i][0-9][a-i][0-9]$")
    player: str = Field("human", min_length=1, max_length=32)
    trace_id: Optional[str] = None


class VisionUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    trace_id: Optional[str] = None
