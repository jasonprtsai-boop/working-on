from pathlib import Path
import sqlite3

from backend.utils import config
from backend.utils.logger import logger


def init_db():
    db_path = Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[init_db] initializing SQLite database: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
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
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                message TEXT,
                timestamp TEXT
            )
        """)
        conn.commit()

    logger.info("[init_db] schema created")


if __name__ == "__main__":
    init_db()
