import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from backend.events.bus.event_bus import bus
from backend.utils import config
from backend.utils.logger import logger


class Database:
    def __init__(self, db_path: Optional[str] = None):
        is_memory = bool(getattr(config, "TEST_MODE", False)) or db_path == ":memory:"
        self.db_path = ":memory:" if is_memory else os.path.abspath(db_path or config.DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None
        self.connect()
        self._create_tables()
        self._subscribe_once()

    def connect(self):
        if self._conn is not None:
            return self._conn
        parent = Path(self.db_path).parent
        if self.db_path != ":memory:":
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        if getattr(config, "WAL_MODE", False) and self.db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        logger.info(f"[Database] connected: {self.db_path}")
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _create_tables(self):
        conn = self.connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tid TEXT,
                move TEXT,
                fen TEXT,
                experiment_tag TEXT,
                player_name TEXT,
                difficulty INTEGER,
                timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS technical_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tid TEXT,
                vision_latency INTEGER,
                ai_latency INTEGER,
                robot_latency INTEGER,
                yolo_confidence REAL,
                match_score REAL,
                ai_score_cp INTEGER,
                ai_depth INTEGER,
                delta_x REAL,
                delta_y REAL,
                timestamp TEXT
            )
        """)
        self._ensure_columns(
            conn,
            "technical_records",
            {
                "vision_latency": "INTEGER",
                "ai_latency": "INTEGER",
                "robot_latency": "INTEGER",
                "yolo_confidence": "REAL",
                "match_score": "REAL",
                "ai_score_cp": "INTEGER",
                "ai_depth": "INTEGER",
                "delta_x": "REAL",
                "delta_y": "REAL",
            },
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                message TEXT,
                timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                type TEXT,
                source TEXT,
                payload TEXT,
                timestamp REAL
            )
        """)
        conn.commit()

    def _ensure_columns(self, conn, table_name: str, columns: Dict[str, str]) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        for column_name, column_type in columns.items():
            if column_name not in existing:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def _subscribe_once(self):
        if getattr(self, "_subscribed", False):
            return
        self._subscribed = True
        try:
            bus.subscribe_all(self.handle_event)
        except Exception:
            logger.debug("[Database] failed to subscribe to EventBus", exc_info=True)

    def handle_event(self, event: Any):
        try:
            if hasattr(event, "event_id"):
                event_id = getattr(event, "event_id", None)
                event_type = getattr(event, "event_type", None)
                source = getattr(event, "source", "unknown")
                payload = getattr(event, "payload", {}) or {}
                timestamp = getattr(event, "timestamp", datetime.utcnow().timestamp())
            elif isinstance(event, dict):
                event_id = event.get("event_id")
                event_type = event.get("type") or event.get("event_type")
                source = event.get("source", "unknown")
                payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
                timestamp = event.get("timestamp", datetime.utcnow().timestamp())
            else:
                return

            self.connect().execute(
                "INSERT INTO event_logs (event_id, type, source, payload, timestamp) VALUES (?, ?, ?, ?, ?)",
                (event_id, str(event_type or "unknown"), source, json.dumps(payload), float(timestamp)),
            )
            self._conn.commit()
        except Exception:
            logger.debug("[Database] event logging failed", exc_info=True)

    def log_move(self, tid, move, fen, experiment_tag="PROD_RUN", player="Human", difficulty=15):
        self.connect().execute(
            "INSERT INTO game_records (tid, move, fen, experiment_tag, player_name, difficulty, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, move, fen, experiment_tag, player, int(difficulty), datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def log_technical(self, tid, vision_latency, ai_latency, robot_latency, **kwargs):
        self.connect().execute(
            "INSERT INTO technical_records (tid, vision_latency, ai_latency, robot_latency, yolo_confidence, match_score, ai_score_cp, ai_depth, delta_x, delta_y, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                int(vision_latency),
                int(ai_latency),
                int(robot_latency),
                float(kwargs.get("yolo_conf", 0.0)),
                float(kwargs.get("match_score", 0.0)),
                int(kwargs.get("ai_score", 0)),
                int(kwargs.get("ai_depth", 0)),
                float(kwargs.get("delta_x", 0.0)),
                float(kwargs.get("delta_y", 0.0)),
                datetime.utcnow().isoformat(),
            ),
        )
        self._conn.commit()

    def log_message(self, level: str, message: str):
        self.connect().execute(
            "INSERT INTO system_logs (level, message, timestamp) VALUES (?, ?, ?)",
            (level, message, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def export_excel_csv(self, table_name: str, output_path: str) -> bool:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", self.connect())
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.suffix.lower() == ".csv":
                df.to_csv(output, index=False)
            else:
                df.to_excel(output, index=False)
            return True
        except Exception:
            logger.error("[Database] export failed", exc_info=True)
            return False


class _DBProxy:
    _instance: Optional[Database] = None

    def _get(self) -> Database:
        if self._instance is None:
            self._instance = Database()
        return self._instance

    def __getattr__(self, item):
        return getattr(self._get(), item)


DatabaseProxy = _DBProxy
db = _DBProxy()
