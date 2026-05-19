import sqlite3
import os
import sys

# Ensure root directory is in path for imports
sys.path.append(os.getcwd())

from backend.utils import config

def migrate():
    db_path = config.DB_PATH
    print(f"Migrating DB: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Update game_records
    cursor.execute("PRAGMA table_info(game_records)")
    cols = [c[1] for c in cursor.fetchall()]

    if 'experiment_tag' not in cols:
        print("Adding experiment_tag to game_records")
        cursor.execute("ALTER TABLE game_records ADD COLUMN experiment_tag TEXT DEFAULT 'PROD_RUN'")
    if 'player_name' not in cols:
        print("Adding player_name to game_records")
        cursor.execute("ALTER TABLE game_records ADD COLUMN player_name TEXT DEFAULT 'Human'")
    if 'difficulty' not in cols:
        print("Adding difficulty to game_records")
        cursor.execute("ALTER TABLE game_records ADD COLUMN difficulty INTEGER DEFAULT 15")

    # 2. Update technical_records
    cursor.execute("PRAGMA table_info(technical_records)")
    cols = [c[1] for c in cursor.fetchall()]

    if 'vision_latency' not in cols:
        print("Adding vision_latency to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN vision_latency INTEGER DEFAULT 0")
    if 'ai_latency' not in cols:
        print("Adding ai_latency to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN ai_latency INTEGER DEFAULT 0")
    if 'robot_latency' not in cols:
        print("Adding robot_latency to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN robot_latency INTEGER DEFAULT 0")
    if 'yolo_confidence' not in cols:
        print("Adding yolo_confidence to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN yolo_confidence REAL DEFAULT 0.0")
    if 'yolo_conf' not in cols:
        print("Adding yolo_conf to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN yolo_conf REAL DEFAULT 0.0")
    if 'match_score' not in cols:
        print("Adding match_score to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN match_score REAL DEFAULT 0.0")
    if 'ai_score_cp' not in cols:
        print("Adding ai_score_cp to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN ai_score_cp INTEGER DEFAULT 0")
    if 'ai_depth' not in cols:
        print("Adding ai_depth to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN ai_depth INTEGER DEFAULT 0")
    if 'delta_x' not in cols:
        print("Adding delta_x to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN delta_x REAL DEFAULT 0.0")
    if 'delta_y' not in cols:
        print("Adding delta_y to technical_records")
        cursor.execute("ALTER TABLE technical_records ADD COLUMN delta_y REAL DEFAULT 0.0")

    conn.commit()
    conn.close()
    print("Migration finished.")

if __name__ == "__main__":
    migrate()
