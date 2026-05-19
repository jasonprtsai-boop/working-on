from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from backend.infrastructure.database.event_store import EventStore as SqliteEventStore
from backend.utils import config


class EventStore:
    """
    Canonical event-store adapter.

    The runtime persists events into SQLite via `backend.infrastructure.database.event_store`.
    This adapter keeps older application-layer imports working while exposing a
    replay-friendly API over the same underlying store.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH
        self._store = SqliteEventStore(self.db_path)

    def append(self, event: Any):
        if hasattr(event, "to_dict"):
            payload = event.to_dict()
        elif isinstance(event, dict):
            payload = dict(event)
        else:
            payload = {"raw": str(event)}
        self._store.save_event(payload)

    def load_replay(
        self,
        session_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        event_types: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self._load_all_events(session_id=session_id, limit=limit, offset=offset, event_types=event_types)

    def get_all(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        return self._load_all_events(limit=limit, offset=offset)

    def get_history(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        return self._load_all_events(limit=limit, offset=offset)

    def get_by_trace_id(self, trace_id: str) -> List[Dict[str, Any]]:
        if hasattr(self._store, "query_events"):
            return self._store.query_events(trace_id=trace_id)
        return [event for event in self._load_all_events() if event.get("trace_id") == trace_id]

    def _load_all_events(
        self,
        session_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        event_types: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        if hasattr(self._store, "query_events"):
            return self._store.query_events(
                session_id=session_id,
                event_types=event_types,
                limit=limit,
                offset=offset,
            )

        conn = self._store._connect()
        try:
            sql = "SELECT sequence_id, session_id, trace_id, type, payload, timestamp FROM events"
            params: List[Any] = []
            clauses = []
            if session_id:
                clauses.append("session_id = ?")
                params.append(session_id)
            normalized_types = [str(item) for item in (event_types or []) if str(item)]
            if normalized_types:
                placeholders = ",".join("?" for _ in normalized_types)
                clauses.append(f"type IN ({placeholders})")
                params.extend(normalized_types)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY sequence_id ASC"
            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([max(1, int(limit)), max(0, int(offset))])
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        events: List[Dict[str, Any]] = []
        for seq, session_id, trace_id, event_type, payload, timestamp in rows:
            try:
                payload_obj = json.loads(payload) if payload else {}
            except Exception:
                payload_obj = {"raw": payload}
            events.append(
                {
                    "sequence_id": seq,
                    "session_id": session_id,
                    "trace_id": trace_id,
                    "type": event_type,
                    "payload": payload_obj,
                    "timestamp": timestamp,
                }
            )
        return events


event_store = EventStore()
