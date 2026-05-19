import dataclasses
from backend.state.store.models.system_state import SystemState
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType

class RobotReducer:
    """[State Layer] Pure functional reducer for robot actuation events."""

    @staticmethod
    def _position_dict(value, fallback):
        if isinstance(value, dict):
            return {
                "x": float(value.get("x", fallback.get("x", 0.0)) or 0.0),
                "y": float(value.get("y", fallback.get("y", 0.0)) or 0.0),
                "z": float(value.get("z", fallback.get("z", 0.0)) or 0.0),
            }
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return {"x": float(value[0] or 0.0), "y": float(value[1] or 0.0), "z": float(value[2] or 0.0)}
        return dict(fallback)

    @staticmethod
    def _position_list(position: dict):
        return [
            float(position.get("x", 0.0) or 0.0),
            float(position.get("y", 0.0) or 0.0),
            float(position.get("z", 0.0) or 0.0),
        ]

    @staticmethod
    def _action(payload, fallback="") -> str:
        return str(payload.get("action") or payload.get("command") or payload.get("move") or fallback or "")

    @staticmethod
    def reduce(state: SystemState, event: BaseEvent) -> SystemState:
        payload = event.payload if isinstance(event.payload, dict) else {}

        if event.event_type == EventType.ROBOT_MOVE_STARTED:
            action = RobotReducer._action(payload, state.robot.last_action)
            new_robot = dataclasses.replace(
                state.robot,
                current_command=action or state.robot.current_command,
                last_action=action or state.robot.last_action,
                arm_status="MOVING",
                busy=True,
                error=None,
                queue_size=max(0, int(payload.get("queue_size", state.robot.queue_size) or 0)),
            )
            new_game = dataclasses.replace(
                state.game,
                game_status="EXECUTING"
            )
            return dataclasses.replace(state, game=new_game, robot=new_robot, trace_id=event.trace_id)

        elif event.event_type == EventType.ROBOT_MOVE_COMPLETED:
            new_robot = dataclasses.replace(
                state.robot,
                current_command=None,
                last_action=RobotReducer._action(payload, state.robot.last_action),
                arm_status="IDLE",
                busy=False,
                error=None,
                queue_size=max(0, int(payload.get("queue_size", state.robot.queue_size) or 0)),
            )
            new_game = dataclasses.replace(
                state.game,
                game_status="COMPLETED"
            )
            return dataclasses.replace(state, game=new_game, robot=new_robot, trace_id=event.trace_id)

        elif event.event_type == EventType.ROBOT_STATUS_UPDATED:
            # Direct status update from worker
            position = RobotReducer._position_dict(payload.get("position", payload.get("robot_position")), state.robot.position)
            connected = bool(payload.get("connected", payload.get("is_connected", state.robot.connected)))
            busy = bool(payload.get("busy", state.robot.busy))
            arm_status = str(payload.get("arm_status") or ("MOVING" if busy else "IDLE"))
            new_robot = dataclasses.replace(
                state.robot,
                connected=connected,
                is_connected=connected,
                busy=busy,
                arm_status=arm_status,
                safety_status=payload.get("safety_status", state.robot.safety_status),
                error=payload.get("error", state.robot.error),
                position=position,
                robot_position=RobotReducer._position_list(position),
                queue_size=max(0, int(payload.get("queue_size", state.robot.queue_size) or 0)),
                current_command=payload.get("current_command", state.robot.current_command),
                last_action=RobotReducer._action(payload, state.robot.last_action),
            )
            return dataclasses.replace(state, robot=new_robot, trace_id=event.trace_id)

        return state
