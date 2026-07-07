from __future__ import annotations

import time
import uuid
from typing import Any

from backend.events.models.base_event import BaseEvent


def adapt_legacy_event(event: Any) -> BaseEvent | Any | None:
    """Convert the only accepted legacy event shape into the canonical BaseEvent."""
    if not isinstance(event, dict):
        return event

    event_type = event.get("event_type") or event.get("type")
    if not event_type:
        return None

    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    session_id = event.get("session_id")
    if session_id and "session_id" not in metadata:
        metadata = dict(metadata)
        metadata["session_id"] = session_id

    try:
        timestamp = float(event.get("timestamp") or time.time())
    except Exception:
        timestamp = time.time()

    return BaseEvent(
        event_id=str(event.get("event_id") or uuid.uuid4()),
        trace_id=str(event.get("trace_id") or uuid.uuid4()),
        event_type=str(event_type),
        timestamp=timestamp,
        source=str(event.get("source") or "legacy_adapter"),
        payload=payload,
        metadata=metadata,
    )
