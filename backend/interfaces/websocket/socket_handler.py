import threading
import asyncio
from flask import request
from pydantic import ValidationError
from backend.events.bus.event_bus import bus
from backend.application.container import container
from backend.state.store.state_store import state_store
from backend.runtime.contract import CONTRACT_VERSION
from backend.interfaces.websocket.event_forwarder import SocketEventForwarder
from backend.interfaces.websocket.request_models import SocketAction, SocketPlayerMove, SocketVisionUpdate, normalize_socket_action_payload
from backend.interfaces.websocket.socket_context import SocketSessionContext, viewer_claims
from backend.utils.auth import verify_socket_token
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

    socket_context = SocketSessionContext(socketio)
    _set_socket_claims = socket_context.set_claims
    _drop_socket_claims = socket_context.drop_claims
    _get_socket_claims = socket_context.get_claims
    _socket_error = socket_context.socket_error
    _require_admin = socket_context.require_admin
    _validation_error = socket_context.validation_error
    _payload_too_large_error = socket_context.payload_too_large_error
    _payload_size_ok = socket_context.payload_size_ok
    _rate_limit_socket = socket_context.rate_limit_socket
    _viewer_claims = viewer_claims

    # Outbound: forward EventBus events to frontend adapter
    _forward_event = SocketEventForwarder(_emit).forward

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
