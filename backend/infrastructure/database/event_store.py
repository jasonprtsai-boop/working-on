import json
import sqlite3
import time
from typing import List, Dict, Any, Optional, Sequence
from backend.utils import config

SCHEMA_VERSION = 2

class EventStore:
    """
    Persistent store for system events (Event Sourcing).
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        if getattr(config, "WAL_MODE", True):
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    trace_id TEXT,
                    type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    applied_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            conn.execute(
                """
                INSERT INTO schema_migrations (name, version)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    version = excluded.version,
                    applied_at = strftime('%s', 'now')
                """,
                ("event_store", SCHEMA_VERSION),
            )
            # Backward compatible migration if table existed without session_id.
            cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
            if "session_id" not in cols:
                conn.execute("ALTER TABLE events ADD COLUMN session_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session_sequence ON events(session_id, sequence_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type_sequence ON events(type, sequence_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session_type_sequence ON events(session_id, type, sequence_id)")
            conn.commit()
        finally:
            conn.close()

    def save_event(self, event_dict: Dict[str, Any]):
        self.save_events([event_dict])

    def save_events(self, event_dicts: List[Dict[str, Any]]):
        if not event_dicts:
            return
        conn = self._connect()
        try:
            for event_dict in event_dicts:
                row = (
                    event_dict.get("session_id"),
                    event_dict.get("trace_id"),
                    event_dict.get("type") or event_dict.get("event_type") or "unknown",
                    json.dumps(event_dict.get("payload") or {}),
                    event_dict.get("timestamp") or time.time(),
                )
                conn.execute(
                    "INSERT INTO events (session_id, trace_id, type, payload, timestamp) VALUES (?, ?, ?, ?, ?)",
                    row,
                )
            conn.commit()
        finally:
            conn.close()

    def get_max_sequence_id(self) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT COALESCE(MAX(sequence_id), 0) FROM events")
            row = cursor.fetchone()
            return int((row or [0])[0] or 0)
        finally:
            conn.close()

    def get_schema_version(self) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT version FROM schema_migrations WHERE name = ?", ("event_store",))
            row = cursor.fetchone()
            return int((row or [0])[0] or 0)
        finally:
            conn.close()

    def query_events(
        self,
        *,
        session_id: Optional[str] = None,
        event_types: Optional[Sequence[str]] = None,
        trace_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            sql = "SELECT sequence_id, session_id, trace_id, type, payload, timestamp FROM events"
            clauses = []
            params: List[Any] = []
            if session_id:
                clauses.append("session_id = ?")
                params.append(session_id)
            if trace_id:
                clauses.append("trace_id = ?")
                params.append(trace_id)
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
        return self._rows_to_events(rows)

    def get_events(self, session_id: str) -> List[Dict[str, Any]]:
        return self.query_events(session_id=session_id)

    def _rows_to_events(self, rows) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for seq, sid, trace, etype, payload, ts in rows:
            try:
                payload_obj = json.loads(payload) if payload else {}
            except Exception:
                payload_obj = {"raw": payload}
            out.append(
                {
                    "sequence_id": seq,
                    "session_id": sid,
                    "trace_id": trace,
                    "type": etype,
                    "payload": payload_obj,
                    "timestamp": ts,
                }
            )
        return out
