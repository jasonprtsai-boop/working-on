import dataclasses
from backend.state.store.models.system_state import SystemState
from backend.state.store.models.game_state import SystemPhase
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType

class SystemReducer:
    """[State Layer] Pure functional reducer for system-level events (resets, diagnostics)."""

    @staticmethod
    def reduce(state: SystemState, event: BaseEvent) -> SystemState:
        payload = event.payload
        health = payload.get("health", {}) if isinstance(payload.get("health"), dict) else {}

        if event.event_type == EventType.SYSTEM_RESET:
            # Return initial state
            return SystemState(trace_id=event.trace_id)

        elif event.event_type == EventType.SYSTEM_ERROR:
            payload_phase = payload.get("phase", SystemPhase.ERROR.value)
            payload_status = payload.get("game_status", "ERROR")
            new_game = dataclasses.replace(
                state.game,
                game_status=payload_status,
                game_phase=payload_phase,
            )
            return dataclasses.replace(state, game=new_game, trace_id=event.trace_id)

        elif event.event_type == EventType.DIAGNOSTICS_UPDATED:
            vision_payload = payload.get("vision", {}) if isinstance(payload.get("vision"), dict) else {}
            new_vision = state.vision
            if vision_payload:
                new_vision = dataclasses.replace(
                    state.vision,
                    camera_status=vision_payload.get("status", state.vision.camera_status),
                    mode=vision_payload.get("mode", state.vision.mode),
                    simulation=bool(vision_payload.get("simulation", state.vision.simulation)),
                    fps=vision_payload.get("fps", state.vision.fps),
                )
            # Update root health fields
            return dataclasses.replace(
                state,
                vision=new_vision,
                fps=payload.get("fps", health.get("fps", state.fps)),
                cpu_percent=payload.get("cpu_percent", health.get("cpu_percent", state.cpu_percent)),
                memory_mb=payload.get("memory_mb", health.get("memory_mb", state.memory_mb)),
                trace_id=event.trace_id
            )

        return state
