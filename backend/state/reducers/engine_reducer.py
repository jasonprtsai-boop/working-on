import dataclasses
from backend.state.store.models.system_state import SystemState
from backend.events.models.base_event import BaseEvent

class EngineReducer:
    """[State Layer] Pure functional reducer for engine analysis events."""

    @staticmethod
    def reduce(state: SystemState, event: BaseEvent) -> SystemState:
        payload = event.payload

        # 1. Update Engine Sub-state
        new_engine = dataclasses.replace(
            state.engine,
            bestmove=payload.get("bestmove") or payload.get("best_move") or payload.get("move"),
            score=float(payload.get("score", state.engine.score) or 0.0),
            depth=int(payload.get("depth", state.engine.depth) or 0),
            nodes=int(payload.get("nodes", getattr(state.engine, "nodes", 0)) or 0),
            nps=int(payload.get("nps", state.engine.nps) or 0),
            pv=list(payload.get("pv", getattr(state.engine, "pv", [])) or []),
            multipv=list(payload.get("multi_pv", payload.get("multipv", state.engine.multipv)) or []),
            is_thinking=bool(payload.get("is_thinking", state.engine.is_thinking)),
        )

        # 2. Update Game status only when analysis is explicitly final.
        if payload.get("final") is True:
            new_game = dataclasses.replace(state.game, game_status="DECIDED")
        else:
            new_game = state.game

        # 3. Return new root state
        return dataclasses.replace(state, engine=new_engine, game=new_game, trace_id=event.trace_id)
