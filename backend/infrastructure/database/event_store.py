import json
import sqlite3
import time
from typing import List, Dict, Any, Optional, Sequence
from backend.utils import config

SCHEMA_VERSION = 4

class EventStore:
    """
    Persistent store for system events (Event Sourcing).
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._memory_uri = None
        self._keeper_conn = None
        if str(db_path).strip() == ":memory:":
            self._memory_uri = "file:smart_chess_event_store?mode=memory&cache=shared"
            self._keeper_conn = sqlite3.connect(self._memory_uri, timeout=5.0, uri=True, check_same_thread=False)
        self._init_db()

    def _connect(self):
        if self._memory_uri:
            conn = sqlite3.connect(self._memory_uri, timeout=5.0, uri=True)
        else:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
        if getattr(config, "WAL_MODE", True) and not self._memory_uri:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def close(self):
        if self._keeper_conn is not None:
            self._keeper_conn.close()
            self._keeper_conn = None

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT,
                    session_id TEXT,
                    trace_id TEXT,
                    type TEXT NOT NULL,
                    source TEXT,
                    payload TEXT NOT NULL,
                    metadata TEXT,
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
            migrations = {
                "event_id": "ALTER TABLE events ADD COLUMN event_id TEXT",
                "session_id": "ALTER TABLE events ADD COLUMN session_id TEXT",
                "source": "ALTER TABLE events ADD COLUMN source TEXT",
                "metadata": "ALTER TABLE events ADD COLUMN metadata TEXT",
            }
            for column, ddl in migrations.items():
                if column not in cols:
                    conn.execute(ddl)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session_sequence ON events(session_id, sequence_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source_sequence ON events(source, sequence_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type_sequence ON events(type, sequence_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session_type_sequence ON events(session_id, type, sequence_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session_timestamp ON events(session_id, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type_timestamp ON events(type, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
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
                payload = event_dict.get("payload")
                if payload is None:
                    payload = event_dict.get("data") or {}
                if not isinstance(payload, dict):
                    payload = {"value": payload}
                metadata = event_dict.get("metadata") or {}
                if not isinstance(metadata, dict):
                    metadata = {"value": metadata}
                row = (
                    event_dict.get("event_id") or payload.get("event_id"),
                    event_dict.get("session_id"),
                    event_dict.get("trace_id"),
                    event_dict.get("type") or event_dict.get("event_type") or "unknown",
                    event_dict.get("source") or payload.get("source"),
                    json.dumps(payload, ensure_ascii=False, default=str),
                    json.dumps(metadata, ensure_ascii=False, default=str),
                    event_dict.get("timestamp") or time.time(),
                )
                conn.execute(
                    "INSERT INTO events (event_id, session_id, trace_id, type, source, payload, metadata, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
            sql = "SELECT sequence_id, session_id, trace_id, type, payload, timestamp, event_id, source, metadata FROM events"
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

    def count_events(
        self,
        *,
        session_id: Optional[str] = None,
        event_types: Optional[Sequence[str]] = None,
    ) -> int:
        conn = self._connect()
        try:
            sql = "SELECT COUNT(*) FROM events"
            clauses = []
            params: List[Any] = []
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
            row = conn.execute(sql, params).fetchone()
            return int((row or [0])[0] or 0)
        finally:
            conn.close()

    def list_sessions(
        self,
        *,
        limit: int = 50,
        event_types: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            sql = """
                SELECT
                    COALESCE(session_id, '') AS sid,
                    COUNT(*) AS event_count,
                    MIN(timestamp) AS first_timestamp,
                    MAX(timestamp) AS last_timestamp,
                    MIN(sequence_id) AS first_sequence_id,
                    MAX(sequence_id) AS last_sequence_id
                FROM events
            """
            params: List[Any] = []
            normalized_types = [str(item) for item in (event_types or []) if str(item)]
            if normalized_types:
                placeholders = ",".join("?" for _ in normalized_types)
                sql += f" WHERE type IN ({placeholders})"
                params.extend(normalized_types)
            sql += " GROUP BY sid ORDER BY last_sequence_id DESC LIMIT ?"
            params.append(max(1, int(limit)))
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        sessions: List[Dict[str, Any]] = []
        for sid, event_count, first_ts, last_ts, first_seq, last_seq in rows:
            sessions.append(
                {
                    "session_id": sid or "",
                    "event_count": int(event_count or 0),
                    "first_timestamp": first_ts,
                    "last_timestamp": last_ts,
                    "first_sequence_id": first_seq,
                    "last_sequence_id": last_seq,
                    "latest_trace_id": self._latest_trace_id(sid or "", event_types=event_types),
                }
            )
        return sessions

    def get_events(self, session_id: str) -> List[Dict[str, Any]]:
        return self.query_events(session_id=session_id)

    def _latest_trace_id(self, session_id: str, event_types: Optional[Sequence[str]] = None) -> Optional[str]:
        conn = self._connect()
        try:
            sql = "SELECT trace_id FROM events"
            clauses = []
            params: List[Any] = []
            if session_id:
                clauses.append("session_id = ?")
                params.append(session_id)
            else:
                clauses.append("(session_id IS NULL OR session_id = '')")
            normalized_types = [str(item) for item in (event_types or []) if str(item)]
            if normalized_types:
                placeholders = ",".join("?" for _ in normalized_types)
                clauses.append(f"type IN ({placeholders})")
                params.extend(normalized_types)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY sequence_id DESC LIMIT 1"
            row = conn.execute(sql, params).fetchone()
            return (row or [None])[0]
        finally:
            conn.close()

    def _rows_to_events(self, rows) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in rows:
            seq, sid, trace, etype, payload, ts = row[:6]
            event_id = row[6] if len(row) > 6 else None
            source = row[7] if len(row) > 7 else None
            metadata = row[8] if len(row) > 8 else None
            try:
                payload_obj = json.loads(payload) if payload else {}
            except Exception:
                payload_obj = {"raw": payload}
            try:
                metadata_obj = json.loads(metadata) if metadata else {}
            except Exception:
                metadata_obj = {"raw": metadata}
            out.append(
                {
                    "sequence_id": seq,
                    "event_id": event_id,
                    "session_id": sid,
                    "trace_id": trace,
                    "type": etype,
                    "source": source or "",
                    "payload": payload_obj,
                    "metadata": metadata_obj,
                    "timestamp": ts,
                }
            )
        return out
