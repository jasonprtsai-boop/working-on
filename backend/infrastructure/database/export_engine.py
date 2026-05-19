import json
from pathlib import Path
from typing import Optional

import pandas as pd
import sqlite3

from backend.utils import config
from backend.utils.logger import logger


EXPORTABLE_TABLES = {
    "events",
    "schema_migrations",
    "snapshots",
    "game_records",
    "technical_records",
    "system_logs",
    "event_logs",
}


def _connect(db_path: Optional[str] = None):
    return sqlite3.connect(str(Path(db_path or config.DB_PATH).resolve()))


def _safe_table_name(table_name: str) -> str:
    if table_name not in EXPORTABLE_TABLES:
        raise ValueError(f"Table is not exportable: {table_name}")
    return table_name


def export_excel_report(table_name: str, output_path: str, db_path: Optional[str] = None) -> bool:
    try:
        safe_table = _safe_table_name(str(table_name or ""))
    except ValueError as exc:
        logger.warning("[export_engine] export_excel_report rejected table: %s", exc)
        return False

    try:
        with _connect(db_path) as conn:
            df = pd.read_sql_query(f'SELECT * FROM "{safe_table}"', conn)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() == ".csv":
            df.to_csv(out, index=False)
        else:
            df.to_excel(out, index=False)
        return True
    except Exception:
        logger.error("[export_engine] export_excel_report failed", exc_info=True)
        return False


def export_full_snapshot(output_path: str, db_path: Optional[str] = None) -> bool:
    try:
        snapshot = {}
        with _connect(db_path) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            for table in tables:
                if table not in EXPORTABLE_TABLES:
                    continue
                df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
                snapshot[table] = df.to_dict(orient="records")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        logger.error("[export_engine] export_full_snapshot failed", exc_info=True)
        return False
