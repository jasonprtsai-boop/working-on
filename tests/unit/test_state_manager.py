import unittest

from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.state.store.manager.state_manager import StateManager
from backend.state.store.models.game_state import SystemPhase


class TestStateManager(unittest.TestCase):
    def setUp(self):
        from backend.state.reducers.engine_reducer import EngineReducer
        from backend.state.reducers.move_reducer import MoveReducer
        from backend.state.reducers.robot_reducer import RobotReducer
        from backend.state.reducers.system_reducer import SystemReducer
        from backend.state.store.manager.reducer_registry import reducer_registry

        reducer_registry.register(EventType.VISION_MOVE_DETECTED, MoveReducer)
        reducer_registry.register(EventType.MOVE_APPLIED, MoveReducer)
        reducer_registry.register(EventType.GAME_PLAYER_MOVE, MoveReducer)
        reducer_registry.register(EventType.ENGINE_ANALYSIS_COMPLETED, EngineReducer)
        reducer_registry.register(EventType.ROBOT_MOVE_STARTED, RobotReducer)
        reducer_registry.register(EventType.ROBOT_MOVE_COMPLETED, RobotReducer)
        reducer_registry.register(EventType.ROBOT_STATUS_UPDATED, RobotReducer)
        reducer_registry.register(EventType.SYSTEM_RESET, SystemReducer)
        reducer_registry.register(EventType.SYSTEM_ERROR, SystemReducer)
        reducer_registry.register(EventType.DIAGNOSTICS_UPDATED, SystemReducer)
        self.manager = StateManager()

    def test_diagnostics_update_accepts_flat_payload(self):
        event = BaseEvent.create(
            event_type=EventType.DIAGNOSTICS_UPDATED,
            source="test",
            payload={"fps": 12.5, "cpu_percent": 33.3, "memory_mb": 456.7},
        )

        self.manager.dispatch(event)

        current = self.manager.current
        self.assertEqual(current.fps, 12.5)
        self.assertEqual(current.cpu_percent, 33.3)
        self.assertEqual(current.memory_mb, 456.7)

    def test_diagnostics_update_accepts_nested_health_payload(self):
        event = BaseEvent.create(
            event_type=EventType.DIAGNOSTICS_UPDATED,
            source="test",
            payload={"health": {"fps": 7.0, "cpu_percent": 22.0, "memory_mb": 111.0}},
        )

        self.manager.dispatch(event)

        current = self.manager.current
        self.assertEqual(current.fps, 7.0)
        self.assertEqual(current.cpu_percent, 22.0)
        self.assertEqual(current.memory_mb, 111.0)

    def test_diagnostics_update_tracks_vision_simulation_mode(self):
        event = BaseEvent.create(
            event_type=EventType.DIAGNOSTICS_UPDATED,
            source="test",
            payload={"vision": {"mode": "simulation", "simulation": True, "status": "SIMULATION"}},
        )

        self.manager.dispatch(event)

        current = self.manager.current
        self.assertEqual(current.vision.mode, "simulation")
        self.assertTrue(current.vision.simulation)
        self.assertEqual(current.vision.camera_status, "SIMULATION")

    def test_engine_analysis_completed_updates_engine_state(self):
        event = BaseEvent.create(
            event_type=EventType.ENGINE_ANALYSIS_COMPLETED,
            source="test",
            payload={
                "best_move": "h2e2",
                "score": 128,
                "depth": 16,
                "nodes": 2048,
                "nps": 1024,
                "final": True,
                "pv": ["h2e2", "e9e8"],
                "multi_pv": [{"move": "h2e2", "score": 128, "pv": ["h2e2"]}],
            },
        )

        self.manager.dispatch(event)

        current = self.manager.current
        self.assertEqual(current.engine.bestmove, "h2e2")
        self.assertEqual(current.engine.depth, 16)
        self.assertEqual(current.engine.nodes, 2048)
        self.assertEqual(current.game.game_status, "DECIDED")

    def test_robot_status_and_motion_events_update_robot_state(self):
        status_event = BaseEvent.create(
            event_type=EventType.ROBOT_STATUS_UPDATED,
            source="test",
            payload={
                "connected": True,
                "busy": False,
                "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                "queue_size": 3,
                "last_action": "status-sync",
            },
        )
        move_started = BaseEvent.create(
            event_type=EventType.ROBOT_MOVE_STARTED,
            source="test",
            payload={"move": "a0a1"},
        )
        move_completed = BaseEvent.create(
            event_type=EventType.ROBOT_MOVE_COMPLETED,
            source="test",
            payload={"move": "a0a1"},
        )

        self.manager.dispatch(status_event)
        self.manager.dispatch(move_started)
        self.manager.dispatch(move_completed)

        current = self.manager.current
        self.assertTrue(current.robot.connected)
        self.assertTrue(current.robot.is_connected)
        self.assertFalse(current.robot.busy)
        self.assertEqual(current.robot.arm_status, "IDLE")
        self.assertEqual(current.robot.position, {"x": 1.0, "y": 2.0, "z": 3.0})
        self.assertEqual(current.robot.robot_position, [1.0, 2.0, 3.0])
        self.assertEqual(current.robot.queue_size, 3)
        self.assertEqual(current.robot.last_action, "a0a1")
        self.assertEqual(current.game.game_status, "COMPLETED")

    def test_unknown_legacy_dict_event_is_ignored(self):
        before = self.manager.current
        self.manager.dispatch({"type": "legacy.unknown", "payload": {"foo": "bar"}})
        self.assertIs(self.manager.current, before)

    def test_to_dict_returns_detached_nested_structures(self):
        snapshot = self.manager.current.to_dict()
        snapshot["game"]["move_history"].append("a0a1")
        snapshot["robot"]["position"]["x"] = 99.0

        current = self.manager.current
        self.assertEqual(current.game.move_history, [])
        self.assertEqual(current.robot.position["x"], 0.0)

    def test_player_move_updates_history_and_turn(self):
        before = self.manager.current
        event = BaseEvent.create(
            event_type=EventType.GAME_PLAYER_MOVE,
            source="test",
            payload={"move": "a0a1", "player": "human"},
        )

        self.manager.dispatch(event)

        current = self.manager.current
        self.assertEqual(current.game.move_history[-1], "a0a1")
        self.assertEqual(current.game.current_turn, "b")
        self.assertNotEqual(current.game.fen, before.game.fen)

    def test_illegal_player_move_is_rejected(self):
        before = self.manager.current
        event = BaseEvent.create(
            event_type=EventType.GAME_PLAYER_MOVE,
            source="test",
            payload={"move": "b0d1", "player": "human"},
        )

        self.manager.dispatch(event)

        self.assertIs(self.manager.current, before)

    def test_undo_restores_previous_game_state(self):
        before = self.manager.current
        self.manager.dispatch(
            BaseEvent.create(
                event_type=EventType.GAME_PLAYER_MOVE,
                source="test",
                payload={"move": "a0a1", "player": "human"},
            )
        )
        moved = self.manager.current
        self.assertNotEqual(moved.game.fen, before.game.fen)

        self.manager.dispatch(
            BaseEvent.create(
                event_type=EventType.GAME_UNDO,
                source="test",
                payload={},
            )
        )

        current = self.manager.current
        self.assertEqual(current.game.fen, before.game.fen)
        self.assertEqual(current.game.move_history, before.game.move_history)
        self.assertEqual(current.game.current_turn, before.game.current_turn)

    def test_fen_only_move_event_does_not_flip_turn(self):
        before = self.manager.current
        event = BaseEvent.create(
            event_type=EventType.VISION_MOVE_DETECTED,
            source="test",
            payload={"fen": before.game.fen, "confidence": 1.0},
        )

        self.manager.dispatch(event)

        current = self.manager.current
        self.assertEqual(current.game.current_turn, before.game.current_turn)
        self.assertEqual(current.game.move_history, before.game.move_history)

    def test_system_error_updates_game_status(self):
        event = BaseEvent.create(
            event_type=EventType.SYSTEM_ERROR,
            source="test",
            payload={"game_status": "ERROR", "phase": SystemPhase.ERROR.value},
        )

        self.manager.dispatch(event)

        current = self.manager.current
        self.assertEqual(current.game.game_status, "ERROR")
        self.assertEqual(current.game.game_phase, SystemPhase.ERROR.value)

    def test_system_reset_restores_initial_state(self):
        self.manager.dispatch(
            BaseEvent.create(
                event_type=EventType.SYSTEM_ERROR,
                source="test",
                payload={"game_status": "ERROR", "phase": SystemPhase.ERROR.value},
            )
        )
        self.manager.dispatch(
            BaseEvent.create(
                event_type=EventType.SYSTEM_RESET,
                source="test",
                payload={},
            )
        )

        current = self.manager.current
        self.assertEqual(current.game.game_status, "IDLE")
        self.assertEqual(current.game.current_turn, "w")

    def test_invalid_fen_mutation_is_rejected(self):
        before = self.manager.current
        event = BaseEvent.create(
            event_type=EventType.VISION_MOVE_DETECTED,
            source="test",
            payload={"fen": "invalid-fen", "confidence": 1.0},
        )

        self.manager.dispatch(event)

        self.assertIs(self.manager.current, before)


if __name__ == "__main__":
    unittest.main()
