from __future__ import annotations

from backend.interfaces.websocket.serializers import EngineInfoSerializer, StateSerializer
from backend.runtime.contract import is_contract_event
from backend.runtime.contract_schema import normalize_diagnostics_payload, validate_contract_payload
from backend.utils import config
from backend.utils.logger import logger


class SocketEventForwarder:
    def __init__(self, emit):
        self._emit = emit

    def _emit_contract(self, event_type: str, payload: dict) -> bool:
        if not is_contract_event(event_type):
            return False
        if getattr(config, "CONTRACT_VALIDATE", False):
            try:
                validate_contract_payload(event_type, payload or {})
            except Exception as exc:
                logger.error("[Contract] Payload validation failed for %s: %s", event_type, exc, exc_info=True)
                try:
                    self._emit("DIAGNOSTICS.UPDATED", {"ui": {"contract_error": f"{event_type}: {exc}"}})
                except Exception:
                    logger.debug("[Contract] failed to emit DIAGNOSTICS.UPDATED", exc_info=True)
                return False
        self._emit(event_type, payload or {})
        return True

    def forward(self, event) -> None:
        if hasattr(event, "event_type"):
            event_type = event.event_type.value if hasattr(event.event_type, "value") else event.event_type
            payload = getattr(event, "payload", {}) or {}

            if event_type in {"STATE_UPDATED", "STATE_UPDATE"}:
                self._emit_contract("STATE_UPDATE", StateSerializer.serialize(payload))
            elif event_type == "ENGINE_ANALYSIS_COMPLETED":
                self._emit_contract("ENGINE.INFO_UPDATED", EngineInfoSerializer.serialize(payload))
            elif event_type in {"DIAGNOSTICS_UPDATED", "DIAGNOSTICS.UPDATED"}:
                self._emit_contract("DIAGNOSTICS.UPDATED", normalize_diagnostics_payload(payload))
            elif event_type == "ROBOT.STATUS_UPDATED":
                self._emit_contract("ROBOT.STATUS_UPDATED", payload)
            elif event_type == "UI_TOAST":
                self._emit_contract("UI_TOAST", payload)
            else:
                self._emit_contract(str(event_type), payload)
            return

        if isinstance(event, dict):
            event_type = event.get("type") or event.get("event_type") or "unknown"
            payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}

            if event_type in {"STATE_UPDATED", "STATE_UPDATE"}:
                self._emit_contract("STATE_UPDATE", StateSerializer.serialize(payload))
            elif event_type in {"DIAGNOSTICS.UPDATED", "DIAGNOSTICS_UPDATED"}:
                self._emit_contract("DIAGNOSTICS.UPDATED", normalize_diagnostics_payload(payload))
            else:
                self._emit_contract(str(event_type), payload)
