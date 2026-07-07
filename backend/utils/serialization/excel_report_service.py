from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.utils.serialization.excel_exporter import get_excel_exporter


@dataclass(frozen=True)
class ExcelExportResult:
    path: str
    filename: str


def safe_session_id(session_id: Optional[str]) -> str:
    return "".join([c for c in (session_id or "all") if c.isalnum() or c in ("-", "_")])[:64] or "all"


def game_record_filename(started_at: Optional[float] = None) -> str:
    """Return a Windows-safe filename based on the game start date and time."""
    try:
        timestamp = float(started_at) if started_at is not None else time.time()
    except (TypeError, ValueError):
        timestamp = time.time()
    return time.strftime("%Y-%m-%d_%H-%M-%S.xlsx", time.localtime(timestamp))


def unique_record_path(export_dir: str, filename: str) -> str:
    out_dir = Path(export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".xlsx"
    candidate = out_dir / f"{stem}{suffix}"
    index = 2
    while candidate.exists():
        candidate = out_dir / f"{stem}_{index}{suffix}"
        index += 1
    return str(candidate.resolve())


def _first_event_timestamp(event_store, session_id: Optional[str]) -> Optional[float]:
    if not session_id:
        return None
    events = event_store.load_replay(session_id=session_id, limit=1)
    if not events:
        return None
    try:
        return float(events[0].get("timestamp"))
    except (TypeError, ValueError):
        return None


def export_research_workbook(
    session_id: Optional[str],
    export_dir: str = os.path.join("logs", "exports"),
    event_limit: Optional[int] = None,
    started_at: Optional[float] = None,
) -> ExcelExportResult:
    excel_exporter = get_excel_exporter(subscribe=False)
    from backend.events.store.event_store import event_store
    from backend.utils import config

    record_started_at = started_at if started_at is not None else _first_event_timestamp(event_store, session_id)
    filename = game_record_filename(record_started_at)
    out_path = unique_record_path(export_dir, filename)
    limit = max(1, min(int(event_limit or config.EXCEL_EXPORT_EVENT_LIMIT), 50000))
    total = event_store.count_replay(session_id=session_id)
    offset = max(0, total - limit)
    events = event_store.load_replay(session_id=session_id, limit=limit, offset=offset)
    excel_exporter.export_events(events, out_path, session_id=session_id)
    return ExcelExportResult(path=out_path, filename=os.path.basename(out_path))


def export_session_record(
    session_id: str,
    started_at: Optional[float],
    export_dir: Optional[str] = None,
    event_limit: Optional[int] = None,
) -> ExcelExportResult:
    from backend.utils import config

    return export_research_workbook(
        session_id=session_id,
        export_dir=export_dir or config.GAME_RECORD_EXPORT_DIR,
        event_limit=event_limit,
        started_at=started_at,
    )
