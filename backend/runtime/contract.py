"""
Runtime contract helpers.

This module centralizes the minimal, stable event/type contract sent to the frontend
and used across the runnable E2E path.
"""

from __future__ import annotations

from typing import Any, Dict


CONTRACT_VERSION = "1.0"

CONTRACT_EVENTS = {
    "STATE_UPDATE",
    "ENGINE.INFO_UPDATED",
    "DIAGNOSTICS.UPDATED",
    "VISION.FRAME_PROCESSED",
    "ROBOT.STATUS_UPDATED",
    "UI_TOAST",
}


def contract_event(event_type: str, payload: Dict[str, Any] | None = None, source: str | None = None) -> Dict[str, Any]:
    return {
        "type": event_type,
        "payload": payload or {},
        "source": source or "runtime",
        "contract_version": CONTRACT_VERSION,
    }


def is_contract_event(event_type: str) -> bool:
    return event_type in CONTRACT_EVENTS
