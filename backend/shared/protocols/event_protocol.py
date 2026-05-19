from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

class EventEnvelope(BaseModel):
    """
    [Industrial Standard] Standardized event envelope for all system communications.
    Ensures traceability, versioning, and type safety.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    sequence_id: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: str
    source: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1

    model_config = ConfigDict(populate_by_name=True)

    def to_dict(self):
        return self.model_dump()

    @classmethod
    def create(cls, event_type: str, source: str, payload: Dict[str, Any],
               trace_id: Optional[str] = None, correlation_id: Optional[str] = None,
               sequence_id: int = 0):
        return cls(
            event_type=event_type,
            source=source,
            payload=payload,
            trace_id=trace_id or str(uuid.uuid4()),
            correlation_id=correlation_id,
            sequence_id=sequence_id
        )
