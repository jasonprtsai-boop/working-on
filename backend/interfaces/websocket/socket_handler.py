import threading
import asyncio
import json
from flask import request
from pydantic import ValidationError
from backend.events.bus.event_bus import bus
from backend.application.container import container
from backend.state.store.state_store import state_store
from backend.runtime.contract import CONTRACT_VERSION, is_contract_event
from backend.runtime.contract_schema import validate_contract_payload, normalize_diagnostics_payload
from backend.interfaces.websocket.request_models import SocketAction, SocketPlayerMove, SocketVisionUpdate, normalize_socket_action_payload
from backend.utils.auth import verify_socket_token
from backend.utils.error_response import build_error
from backend.utils.rate_limit import RateLimitExceeded, rate_limiter
from backend.utils.logger import logger
from backend.utils import config

def register_socketio(socketio):
    """
    [Production v4.0] Centralized Socket Event Hub
    Responsibility: Connection lifecycle & Event distribution.
    """
    def _emit(type_name: str, payload: dict, *, room=None):
        socketio.emit("SYSTEM_STATE_UPDATE", {
            "type": type_name,
            "payload": payload or {},
            "contract_version": CONTRACT_VERSION,
        }, room=room)

    socket_claims = {}
    socket_claims_lock = threading.RLock()

    def _viewer_claims():
        return {"role": "viewer", "sub": "anonymous", "authenticated": False}

    def _set_socket_claims(claims: dict):
        sid = getattr(request, "sid", None)
        if sid:
            with socket_claims_lock:
                socket_claims[sid] = dict(claims or {})

    def _drop_socket_claims():
        sid = getattr(request, "sid", None)
        if sid:
            with socket_claims_lock:
                socket_claims.pop(sid, None)

    def _get_socket_claims():
        if not getattr(config, "CONTROL_AUTH_REQUIRED", True):
            return {"role": "admin"}
        sid = getattr(request, "sid", None)
        if not sid:
            return None
        with socket_claims_lock:
            return socket_claims.get(sid)

    def _socket_error(error: str, message: str, *, trace_id=None, recoverable=True, details=None):
        payload = build_error(error, message, trace_id=trace_id, recoverable=recoverable, details=details)
        try:
            socketio.emit("AUTH_ERROR", payload, room=getattr(request, "sid", None))
        except Exception:
            logger.debug("[Socket] failed to emit AUTH_ERROR", exc_info=True)
        return payload

    def _require_admin():
        claims = _get_socket_claims()
        if not claims or claims.get("authenticated") is False:
            return None, _socket_error("unauthorized", "Valid bearer token required.")
        if claims.get("role") != "admin":
            return None, _socket_error("forbidden", "Admin role required.")
        return claims, None

    def _validation_error(exc: ValidationError):
        return _socket_error("invalid_payload", "Invalid socket payload.", details=exc.errors())

    def _payload_too_large_error():
        return _socket_error(
            "payload_too_large",
            "Socket payload exceeds the configured size limit.",
            recoverable=False,
            details={"max_bytes": int(getattr(config, "MAX_SOCKET_PAYLOAD_BYTES", 65536))},
        )

    def _payload_size_ok(data) -> bool:
        try:
            encoded = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except Exception:
            encoded = str(data).encode("utf-8", errors="ignore")
        return len(encoded) <= int(getattr(config, "MAX_SOCKET_PAYLOAD_BYTES", 65536))

    def _rate_limit_socket(event_name: str):
        if not getattr(config, "RATE_LIMITS_ENABLED", True):
            return None
        sid = getattr(request, "sid", None) or "unknown"
        try:
            rate_limiter.check(f"socket:{sid}:{event_name}", int(getattr(config, "SOCKET_RATE_LIMIT_PER_MINUTE", 120)), 60.0)
        except RateLimitExceeded as exc:
            return _socket_error(
                "rate_limited",
                "Too many socket events. Please retry later.",
                details={"retry_after_seconds": exc.retry_after_seconds},
            )
        return None

    try:
        from backend.application.services.estop import estop
        estop.register_socketio(socketio)
    except Exception:
        logger.debug("[Socket] failed to register E-Stop SocketIO reference", exc_info=True)

    # Outbound: forward EventBus events to frontend adapter
    def _forward_event(event):
        from backend.interfaces.websocket.serializers import StateSerializer, EngineInfoSerializer

        def _emit_contract(event_type: str, payload: dict):
            # Only emit known contract events to keep the frontend stable.
            if is_contract_event(event_type):
                if getattr(config, "CONTRACT_VALIDATE", False):
                    try:
                        validate_contract_payload(event_type, payload or {})
                    except Exception as e:
                        logger.error(f"[Contract] Payload validation failed for {event_type}: {e}", exc_info=True)
                        # Emit diagnostics so UI can surface the mismatch without crashing.
                        try:
                            _emit("DIAGNOSTICS.UPDATED", {"ui": {"contract_error": f"{event_type}: {e}"}})
                        except Exception:
                            logger.debug("[Contract] failed to emit DIAGNOSTICS.UPDATED", exc_info=True)
                        return
                _emit(event_type, payload)

        # BaseEvent (dataclass)
        if hasattr(event, "event_type"):
            et = event.event_type.value if hasattr(event.event_type, "value") else event.event_type
            payload = getattr(event, "payload", {}) or {}

            if et == "STATE_UPDATED" or et == "STATE_UPDATE":
                _emit_contract("STATE_UPDATE", StateSerializer.serialize(payload))
            elif et == "ENGINE_ANALYSIS_COMPLETED":
                _emit_contract("ENGINE.INFO_UPDATED", EngineInfoSerializer.serialize(payload))
            elif et == "DIAGNOSTICS_UPDATED" or et == "DIAGNOSTICS.UPDATED":
                _emit_contract("DIAGNOSTICS.UPDATED", normalize_diagnostics_payload(payload))
            elif et == "ROBOT.STATUS_UPDATED":
                _emit_contract("ROBOT.STATUS_UPDATED", payload)
            elif et == "UI_TOAST":
                _emit_contract("UI_TOAST", payload)
            elif is_contract_event(et):
                _emit_contract(et, payload)
            return

        # dict events (legacy support)
        if isinstance(event, dict):
            et = event.get("type") or event.get("event_type") or "unknown"
            payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}

            if et == "STATE_UPDATED" or et == "STATE_UPDATE":
                _emit_contract("STATE_UPDATE", StateSerializer.serialize(payload))
            elif et == "DIAGNOSTICS.UPDATED" or et == "DIAGNOSTICS_UPDATED":
                _emit_contract("DIAGNOSTICS.UPDATED", normalize_diagnostics_payload(payload))
            else:
                _emit_contract(et, payload)
            return

    bus.subscribe_all(_forward_event, key="socketio.forward_event", replace=True, is_async=True)

    def _run_async(coro):
        try:
            runtime = container.get("runtime")
        except Exception:
            runtime = None

        if runtime is not None:
            try:
                runtime.run_task(coro)
                return
            except Exception:
                logger.debug("[Socket] runtime scheduling failed; falling back to thread runner", exc_info=True)

        def runner():
            try:
                asyncio.run(coro)
            except Exception:
                logger.debug("[Socket] background task failed", exc_info=True)

        threading.Thread(target=runner, daemon=True).start()

    @socketio.on("connect")
    def handle_connect(auth=None):
        if getattr(config, "CONTROL_AUTH_REQUIRED", True):
            claims = verify_socket_token(auth)
            if not claims:
                if not getattr(config, "SOCKET_PUBLIC_SNAPSHOT_ENABLED", True):
                    logger.warning(
                        "[Socket] Anonymous connection rejected because public snapshots are disabled. ID: %s",
                        getattr(request, "sid", "Unknown"),
                    )
                    return False
                claims = _viewer_claims()
            else:
                claims = {**claims, "authenticated": True}
            _set_socket_claims(claims)
        else:
            _set_socket_claims({"role": "admin", "sub": "local-dev", "authenticated": True})
        logger.info(
            "[Socket] Client connected. ID: %s role=%s authenticated=%s",
            getattr(request, "sid", "Unknown"),
            (_get_socket_claims() or {}).get("role"),
            (_get_socket_claims() or {}).get("authenticated", True),
        )
        # Full snapshot sync on connect
        raw = state_store.to_dict()
        from backend.interfaces.websocket.serializers import StateSerializer
        _emit("STATE_UPDATE", StateSerializer.serialize(raw if isinstance(raw, dict) else {}), room=request.sid)

    @socketio.on("disconnect")
    def handle_disconnect():
        _drop_socket_claims()

    @socketio.on("player_move")
    def on_player_move(data):
        from backend.events.models.base_event import BaseEvent
        from backend.events.event_types import EventType
        from backend.observability.tracing.trace_manager import TraceManager

        if not _payload_size_ok(data):
            return _payload_too_large_error()
        limited = _rate_limit_socket("player_move")
        if limited:
            return limited
        try:
            cmd = SocketPlayerMove.model_validate(data or {})
        except ValidationError as exc:
            return _validation_error(exc)

        trace_id = cmd.trace_id or TraceManager.create_trace_id()
        logger.info(f"[Socket] Player move received. Trace: {trace_id}")
        from backend.core.rules import ChessLogic

        current_fen = state_store.current.game.fen
        next_fen = ChessLogic.apply_move(current_fen, cmd.move)
        if next_fen == current_fen:
            return _socket_error(
                "illegal_move",
                "Move is not legal for the current board state.",
                trace_id=trace_id,
                details={"move": cmd.move},
            )

        move_payload = cmd.model_dump(exclude_none=True)
        move_payload.update({
            "type": "PLAYER",
            "fen": next_fen,
            "fen_before": current_fen,
            "fen_after": next_fen,
        })

        bus.publish(BaseEvent.create(
            event_type=EventType.GAME_PLAYER_MOVE,
            payload=move_payload,
            source="socket",
            trace_id=trace_id
        ))
        return {"ok": True, "trace_id": trace_id}

    @socketio.on("vision_update")
    def on_vision(data):
        from backend.events.models.base_event import BaseEvent
        from backend.events.event_types import EventType
        _claims, error = _require_admin()
        if error:
            return error
        if not _payload_size_ok(data):
            return _payload_too_large_error()
        limited = _rate_limit_socket("vision_update")
        if limited:
            return limited
        try:
            cmd = SocketVisionUpdate.model_validate(data or {})
        except ValidationError as exc:
            return _validation_error(exc)

        bus.publish(BaseEvent.create(
            event_type=EventType.VISION_FRAME_CAPTURED,
            payload=cmd.model_dump(exclude_none=True),
            source="socket",
            trace_id=cmd.trace_id
        ))
        return {"ok": True}

    @socketio.on("action")
    def on_action(data):
        from backend.events.models.base_event import BaseEvent
        from backend.events.event_types import EventType

        _claims, error = _require_admin()
        if error:
            return error
        if not _payload_size_ok(data):
            return _payload_too_large_error()
        limited = _rate_limit_socket("action")
        if limited:
            return limited

        try:
            cmd = SocketAction.model_validate(normalize_socket_action_payload(data))
        except ValidationError as exc:
            return _validation_error(exc)

        action_type = str(cmd.action).strip().upper()
        payload = cmd.payload
        allowed_actions = {str(action).strip().upper() for action in getattr(config, "SOCKET_ACTION_ALLOWLIST", ())}
        if action_type not in allowed_actions:
            return _socket_error(
                "event_not_allowed",
                f"Socket action is not allowlisted: {action_type}",
                details={"allowed": sorted(allowed_actions)},
            )

        if action_type == "START_ENGINE":
            bus.publish(BaseEvent.create(
                event_type=EventType.ENGINE_ANALYSIS_REQUESTED,
                payload={"mode": "start", "depth": 12},
                source="socket",
                trace_id=cmd.trace_id
            ))

        elif action_type == "STOP_ENGINE":
            bus.publish(BaseEvent.create(
                event_type=EventType.ENGINE_ANALYSIS_REQUESTED,
                payload={"mode": "stop"},
                source="socket",
                trace_id=cmd.trace_id
            ))

        elif action_type == "SYNC_VISION":
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_ACTION,
                payload={"action": "SYNC_VISION"},
                source="socket",
                trace_id=cmd.trace_id
            ))

        elif action_type == "RESET":
            bus.publish(BaseEvent.create(
                event_type=EventType.SYSTEM_RESET,
                payload={},
                source="socket",
                trace_id=cmd.trace_id
            ))
            bus.publish(BaseEvent.create(
                event_type=EventType.GAME_RESET,
                payload={},
                source="socket",
                trace_id=cmd.trace_id
            ))

        elif action_type == "PAUSE":
            bus.publish(BaseEvent.create(
                event_type=EventType.GAME_PAUSE,
                payload={},
                source="socket",
                trace_id=cmd.trace_id
            ))
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Game paused.", "level": "info"},
                source="socket",
                trace_id=cmd.trace_id
            ))

        elif action_type == "UNDO":
            bus.publish(BaseEvent.create(
                event_type=EventType.GAME_UNDO,
                payload={},
                source="socket",
                trace_id=cmd.trace_id
            ))
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Undo applied.", "level": "success"},
                source="socket",
                trace_id=cmd.trace_id
            ))

        elif action_type == "RESUME":
            bus.publish(BaseEvent.create(
                event_type=EventType.ENGINE_ANALYSIS_REQUESTED,
                payload={"mode": "start", **(payload or {})},
                source="socket",
                trace_id=cmd.trace_id
            ))

        else:
            return _socket_error(
                "event_not_supported",
                f"Socket action is allowlisted but has no handler: {action_type}",
                details={"allowed": sorted(allowed_actions)},
            )
        return {"ok": True, "action": action_type}
