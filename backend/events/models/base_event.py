from dataclasses import dataclass
from typing import Dict, Any
import uuid
import time

@dataclass
class BaseEvent:
    event_id: str
    trace_id: str
    event_type: str
    timestamp: float
    source: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        session_id = self.metadata.get("session_id") or self.payload.get("session_id")
        return {
            "event_id": self.event_id,
            "session_id": session_id,
            "trace_id": self.trace_id,
            "event_type": self.event_type,
            "type": self.event_type,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @staticmethod
    def create(
        event_type: str,
        source: str,
        payload: Dict[str, Any],
        trace_id: str = None,
        metadata: Dict[str, Any] = None
    ):
        return BaseEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace_id or str(uuid.uuid4()),
            event_type=event_type,
            timestamp=time.time(),
            source=source,
            payload=payload,
            metadata=metadata or {}
        )
