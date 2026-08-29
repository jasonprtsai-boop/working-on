import hashlib
import os
import shutil
import tempfile
from typing import Dict, Iterable, List, Optional


def build_nnue_candidate_list(raw_candidates: Iterable[str]) -> List[str]:
    candidates: List[str] = []
    for raw_path in raw_candidates:
        abs_path = os.path.abspath(raw_path)
        if abs_path not in candidates:
            candidates.append(abs_path)
    return candidates


def _ascii_safe_stem(stem: str) -> str:
    safe = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in "._-") else "_"
        for ch in stem
    ).strip("._-")
    return safe or "engine"


def mirror_non_ascii_nnue_path(source_path: str, *, temp_root: Optional[str] = None, logger=None) -> str:
    """
    Mirror non-ASCII paths to an ASCII-safe temp directory for Windows subprocesses.
    """
    if not source_path or not os.path.exists(source_path):
        return source_path

    try:
        source_path.encode("ascii")
        return source_path
    except UnicodeEncodeError:
        pass

    safe_dir = os.path.join(temp_root or tempfile.gettempdir(), "smart-chess-engine")
    os.makedirs(safe_dir, exist_ok=True)
    source_hash = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:10]
    file_name = os.path.basename(source_path)
    name, ext = os.path.splitext(file_name)
    safe_name = _ascii_safe_stem(name)
    safe_ext = ext if ext and ext.isascii() else ".nnue"
    safe_path = os.path.join(safe_dir, f"{safe_name}-{source_hash}{safe_ext}")
    try:
        if not os.path.exists(safe_path) or os.path.getmtime(safe_path) < os.path.getmtime(source_path):
            shutil.copy2(source_path, safe_path)
        if logger:
            logger.info(f"[EngineService] using ASCII-safe NNUE path: {safe_path}")
        return safe_path
    except Exception:
        if logger:
            logger.warning("[EngineService] failed to mirror NNUE file; using original path", exc_info=True)
        return source_path


def probe_status_payload(
    *,
    status: str,
    engine_path: str,
    active_nnue_path: Optional[str],
    candidates: Iterable[str],
    report: Iterable[Dict[str, object]],
    last_startup_error: Optional[str],
) -> Dict[str, object]:
    return {
        "status": status,
        "engine_path": engine_path,
        "active_nnue_path": active_nnue_path,
        "candidates": list(candidates),
        "report": list(report),
        "last_startup_error": last_startup_error,
    }
