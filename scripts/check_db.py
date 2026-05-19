import os
import sqlite3
import sys

# Ensure root directory is in path for imports
sys.path.append(os.getcwd())

from backend.utils import config

def check():
    db_path = config.DB_PATH
    print(f"Checking DB: {db_path}")
    if not os.path.exists(db_path):
        print("DB does not exist.")
        return

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        tables = ['game_records', 'technical_records']
        for table in tables:
            print(f"\nTable: {table}")
            cursor.execute(f"PRAGMA table_info({table})")
            cols = cursor.fetchall()
            for col in cols:
                print(f" - {col[1]} ({col[2]})")

if __name__ == "__main__":
    check()
