"""
Database Maintenance & Optimization Script
Safely creates a backup and performs VACUUM on data/runtime/app.db
"""
from __future__ import annotations
import os
import shutil
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "runtime" / "app.db"
BACKUP_PATH = ROOT / "data" / "runtime" / "app.db.bak"

def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def run_vacuum(dry_run: bool = False):
    if not DB_PATH.exists():
        print(f"[Error] Database not found at: {DB_PATH}")
        return

    init_size = DB_PATH.stat().st_size
    print(f"[Info] Current database size: {format_bytes(init_size)} ({init_size} bytes)")

    if dry_run:
        print("[Dry Run] Would create backup and execute VACUUM;")
        return

    print(f"[1/3] Creating safety backup at: {BACKUP_PATH}")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    backup_size = BACKUP_PATH.stat().st_size
    print(f"      Backup created successfully ({format_bytes(backup_size)})")

    print("[2/3] Executing SQLite VACUUM and ANALYZE...")
    t0 = time.time()
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode;")
        journal_mode = cur.fetchone()[0]
        print(f"      Current Journal Mode: {journal_mode}")

        cur.execute("VACUUM;")
        cur.execute("ANALYZE;")
        conn.commit()
    finally:
        conn.close()

    elapsed = time.time() - t0
    final_size = DB_PATH.stat().st_size
    saved = init_size - final_size

    print(f"[3/3] Optimization complete in {elapsed:.2f}s!")
    print(f"      Initial Size: {format_bytes(init_size)}")
    print(f"      Final Size:   {format_bytes(final_size)}")
    if saved > 0:
        print(f"      Reclaimed:    {format_bytes(saved)} (Reduced by {saved / init_size * 100:.1f}%)")
    else:
        print(f"      Database is already fully compacted.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compact and optimize application database")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without modifying")
    args = parser.parse_args()
    run_vacuum(dry_run=args.dry_run)
