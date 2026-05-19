import json
import sqlite3
from typing import Dict, Any

class SnapshotStore:
    """
    Persistent store for GameState snapshots.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                sequence_id INTEGER PRIMARY KEY,
                state_json TEXT,
                timestamp REAL
            )
        """)
        conn.commit()
        conn.close()

    def save_snapshot(self, sequence_id: int, state: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO snapshots (sequence_id, state_json, timestamp) VALUES (?, ?, ?)",
            (sequence_id, json.dumps(state), time.time() if 'time' in globals() else 0)
        )
        conn.commit()
        conn.close()

    def get_latest_snapshot(self, before_seq: int) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT state_json FROM snapshots WHERE sequence_id <= ? ORDER BY sequence_id DESC LIMIT 1",
            (before_seq,)
        )
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None
