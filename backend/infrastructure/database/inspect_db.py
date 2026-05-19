import sqlite3

from backend.utils import config


def main():
    with sqlite3.connect(config.DB_PATH) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        print("Tables:")
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"- {table}: {count}")


if __name__ == "__main__":
    main()
