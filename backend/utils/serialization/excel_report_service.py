from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from backend.utils.serialization.excel_exporter import get_excel_exporter


@dataclass(frozen=True)
class ExcelExportResult:
    path: str
    filename: str


def safe_session_id(session_id: Optional[str]) -> str:
    return "".join([c for c in (session_id or "all") if c.isalnum() or c in ("-", "_")])[:64] or "all"


def export_research_workbook(session_id: Optional[str], export_dir: str = os.path.join("logs", "exports")) -> ExcelExportResult:
    os.makedirs(export_dir, exist_ok=True)
    safe_session = safe_session_id(session_id)
    filename = f"smart-chess-research-report_{safe_session}_{int(time.time())}.xlsx"
    out_path = os.path.abspath(os.path.join(export_dir, filename))
    excel_exporter = get_excel_exporter(subscribe=False)
    excel_exporter.export_session(session_id, out_path)
    return ExcelExportResult(path=out_path, filename=filename)
