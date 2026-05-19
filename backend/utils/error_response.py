from __future__ import annotations

from typing import Any, Mapping


from backend.core.errors.codes import SystemErrorCode

def build_error(
    code: str | SystemErrorCode,
    message: str,
    *,
    trace_id: str | None = None,
    recoverable: bool = True,
    details: Mapping[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    code_str = code.value if isinstance(code, SystemErrorCode) else str(code)
    return {
        "ok": False,
        "error": code_str,
        "code": code_str,
        "message": message,
        "trace_id": trace_id,
        "recoverable": bool(recoverable),
        "details": details if details is not None else {},
    }
