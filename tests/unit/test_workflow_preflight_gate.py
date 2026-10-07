from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.application.use_cases import coordinate_workflow
from backend.events.event_types import EventType


class FakeEvent:
    trace_id = "trace-preflight"

    def __init__(self):
        now = time.time()
        self.timestamp = now
        self.payload = {
            "final": True,
            "best_move": "a0a1",
            "source_timestamp": now,
        }


class WorkflowPreflightGateTest(unittest.TestCase):
    def test_auto_execute_blocks_robot_command_when_preflight_fails(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        robot = Mock()
        robot.execute_move.return_value = True
        preflight = {
            "ok": False,
            "ready": False,
            "failures": [
                {
                    "key": "robot_mode_confirmed",
                    "label": "Robot Mode",
                    "message": "Real robot mode is selected but robot is not connected.",
                    "severity": "error",
                }
            ],
            "warnings": [],
        }

        with patch.object(coordinate_workflow.config, "AUTO_EXECUTE_ROBOT", True, create=True):
            with patch.object(coordinate_workflow, "build_preflight_report", return_value=preflight):
                coordinator.on_engine_complete(FakeEvent())

        robot.execute_move.assert_not_called()
        workflow = coordinator.active_workflows[FakeEvent.trace_id]
        self.assertEqual(workflow["ai_move"], "a0a1")
        self.assertFalse(workflow["robot_preflight"]["ready"])
        self.assertEqual(workflow["robot_preflight"]["failures"][0]["key"], "robot_mode_confirmed")

    def test_auto_execute_sends_robot_command_after_preflight_passes(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        robot = Mock()
        robot.execute_move.return_value = True
        preflight = {"ok": True, "ready": True, "failures": [], "warnings": []}

        with patch.object(coordinate_workflow.config, "AUTO_EXECUTE_ROBOT", True, create=True):
            with patch.object(coordinate_workflow, "build_preflight_report", return_value=preflight):
                with patch.object(coordinate_workflow.container, "get", return_value=robot):
                    coordinator.on_engine_complete(FakeEvent())
                    coordinator.wait_for_robot()

        robot.execute_move.assert_called_once_with("a0a1", is_capture=False)
        workflow = coordinator.active_workflows[FakeEvent.trace_id]
        self.assertTrue(workflow["robot_preflight"]["ready"])

    def test_robot_verification_does_not_restart_ai_loop(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        event = SimpleNamespace(
            trace_id="trace-verify",
            timestamp=time.time(),
            payload={
                "move": "a0a1",
                "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
            },
        )
        workflow = coordinator._workflow(event.trace_id)
        workflow["verify_pending"] = True
        workflow["ai_move"] = "a0a1"

        with patch.object(
            coordinate_workflow.ChessLogic,
            "game_result",
            return_value={"ended": False, "reason": "in_progress", "winner": None, "legal_moves_count": 12},
        ):
            with patch.object(coordinate_workflow.bus, "publish") as publish:
                coordinator.on_vision_move(event)

        event_types = [call.args[0].event_type for call in publish.call_args_list]
        self.assertNotIn(EventType.ENGINE_ANALYSIS_REQUESTED, event_types)
        self.assertIn(EventType.DIAGNOSTICS_UPDATED, event_types)
        self.assertFalse(workflow["verify_pending"])

    def test_robot_completion_uses_active_command_trace(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        coordinator._active_robot_trace_id = "trace-command"
        event = SimpleNamespace(
            trace_id="trace-random-event",
            timestamp=time.time(),
            payload={"status": "success", "move": "a0a1"},
        )

        with patch.object(coordinator, "is_game_over", return_value=False):
            coordinator.on_robot_complete(event)

        self.assertTrue(coordinator.active_workflows["trace-command"]["verify_pending"])
        self.assertNotIn("trace-random-event", coordinator.active_workflows)
        coordinate_workflow.vision_capture_session.stop(reason="test_cleanup")

    def test_player_move_game_over_stops_before_engine_request(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        event = SimpleNamespace(
            trace_id="trace-game-over",
            timestamp=time.time(),
            payload={
                "move": "a0a1",
                "fen_before": "9/9/9/9/9/9/9/9/9/K3k4 w - - 0 1",
                "fen_after": "9/9/9/9/9/9/9/9/9/4K4 b - - 0 1",
            },
        )

        with patch.object(coordinate_workflow.ChessLogic, "validate_move", return_value=True):
            with patch.object(
                coordinate_workflow.ChessLogic,
                "game_result",
                return_value={"ended": True, "reason": "black_general_missing", "winner": "red", "legal_moves_count": 0},
            ):
                with patch.object(coordinator, "is_game_over", return_value=False):
                    with patch.object(coordinate_workflow.bus, "publish") as publish:
                        coordinator.on_vision_move(event)

        event_types = [call.args[0].event_type for call in publish.call_args_list]
        self.assertIn(EventType.GAME_OVER, event_types)
        self.assertNotIn(EventType.ENGINE_ANALYSIS_REQUESTED, event_types)

    def test_player_end_game_clears_pending_workflow_and_stops_engine(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        workflow = coordinator._workflow("trace-old")
        workflow["verify_pending"] = True

        with patch.object(coordinate_workflow.bus, "publish") as publish:
            result = coordinator.end_game_by_player({"trace_id": "trace-ended", "source": "test"})

        event_types = [call.args[0].event_type for call in publish.call_args_list]
        self.assertIn(EventType.ENGINE_ANALYSIS_REQUESTED, event_types)
        self.assertIn(EventType.GAME_OVER, event_types)
        self.assertFalse(workflow["verify_pending"])
        self.assertTrue(workflow["ended"])
        self.assertEqual(result["game_result"]["reason"], "player_ended")

    def test_robot_execution_is_dispatched_asynchronously(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        robot = Mock()
        robot.execute_move.return_value = True
        preflight = {"ok": True, "ready": True, "failures": [], "warnings": []}

        with patch.object(coordinate_workflow.config, "AUTO_EXECUTE_ROBOT", True, create=True):
            with patch.object(coordinate_workflow, "build_preflight_report", return_value=preflight):
                with patch.object(coordinate_workflow.container, "get", return_value=robot):
                    future = coordinator.on_engine_complete(FakeEvent())
                    self.assertIsNotNone(future)
                    coordinator.wait_for_robot()

        robot.execute_move.assert_called_once_with("a0a1", is_capture=False)

    def test_robot_execution_rejects_duplicate_while_active(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        started = threading.Event()
        release = threading.Event()
        robot = Mock()

        def execute_move(move, is_capture=False):
            started.set()
            release.wait(timeout=2.0)
            return True

        robot.execute_move.side_effect = execute_move

        with patch.object(coordinate_workflow.container, "get", return_value=robot):
            first = coordinator.start_robot_move("trace-one", "a0a1")
            self.assertIsNotNone(first)
            self.assertTrue(started.wait(timeout=1.0))
            second = coordinator.start_robot_move("trace-two", "a0a2")
            self.assertIsNone(second)
            self.assertTrue(coordinator.robot_command_active())
            release.set()
            coordinator.wait_for_robot()

        robot.execute_move.assert_called_once_with("a0a1", is_capture=False)
        self.assertFalse(coordinator.robot_command_active())

    def test_workflow_pruning_caps_active_workflows(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        # Seed 120 workflows
        for i in range(120):
            coordinator.active_workflows[f"trace-{i}"] = {
                "start_time": time.time() - (120 - i) * 10,
                "steps": [],
            }
        self.assertEqual(len(coordinator.active_workflows), 120)
        # Accessing _workflow triggers pruning to max 100
        coordinator._workflow("trace-new")
        self.assertLessEqual(len(coordinator.active_workflows), 101)


if __name__ == "__main__":
    unittest.main()
