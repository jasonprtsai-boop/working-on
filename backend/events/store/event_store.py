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

    def list_sessions(
        self,
        limit: int = 50,
        event_types: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        if hasattr(self._store, "list_sessions"):
            return self._store.list_sessions(limit=limit, event_types=event_types)
        return self._list_sessions(limit=limit, event_types=event_types)

    def count_replay(
        self,
        session_id: Optional[str] = None,
        event_types: Optional[Sequence[str]] = None,
    ) -> int:
        if hasattr(self._store, "count_events"):
            return self._store.count_events(session_id=session_id, event_types=event_types)
        return len(self._load_all_events(session_id=session_id, event_types=event_types))

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
            sql = "SELECT sequence_id, session_id, trace_id, type, payload, timestamp, event_id, source, metadata FROM events"
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
        for row in rows:
            seq, session_id, trace_id, event_type, payload, timestamp = row[:6]
            event_id = row[6] if len(row) > 6 else None
            source = row[7] if len(row) > 7 else ""
            metadata = row[8] if len(row) > 8 else None
            try:
                payload_obj = json.loads(payload) if payload else {}
            except Exception:
                payload_obj = {"raw": payload}
            try:
                metadata_obj = json.loads(metadata) if metadata else {}
            except Exception:
                metadata_obj = {"raw": metadata}
            events.append(
                {
                    "sequence_id": seq,
                    "event_id": event_id,
                    "session_id": session_id,
                    "trace_id": trace_id,
                    "type": event_type,
                    "source": source or "",
                    "payload": payload_obj,
                    "metadata": metadata_obj,
                    "timestamp": timestamp,
                }
            )
        return events

    def _list_sessions(
        self,
        limit: int = 50,
        event_types: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        events = self._load_all_events(event_types=event_types)
        by_id: Dict[str, Dict[str, Any]] = {}
        for event in events:
            session_id = event.get("session_id") or ""
            entry = by_id.setdefault(
                session_id,
                {
                    "session_id": session_id,
                    "event_count": 0,
                    "first_timestamp": event.get("timestamp"),
                    "last_timestamp": event.get("timestamp"),
                    "first_sequence_id": event.get("sequence_id"),
                    "last_sequence_id": event.get("sequence_id"),
                    "latest_trace_id": event.get("trace_id"),
                },
            )
            entry["event_count"] += 1
            entry["last_timestamp"] = event.get("timestamp")
            entry["last_sequence_id"] = event.get("sequence_id")
            entry["latest_trace_id"] = event.get("trace_id") or entry.get("latest_trace_id")
        sessions = list(by_id.values())
        sessions.sort(key=lambda item: item.get("last_sequence_id") or 0, reverse=True)
        return sessions[: max(1, int(limit))]


event_store = EventStore()
