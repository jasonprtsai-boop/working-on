from __future__ import annotations

import time
import unittest
from unittest.mock import Mock, patch

from backend.application.use_cases import coordinate_workflow


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
    def test_auto_execute_sends_robot_command_without_preflight_gate(self):
        coordinator = coordinate_workflow.WorkflowCoordinator()
        robot = Mock()
        robot.execute_move.return_value = True

        with patch.object(coordinate_workflow.config, "AUTO_EXECUTE_ROBOT", True, create=True):
            with patch.object(coordinate_workflow.container, "get", return_value=robot):
                coordinator.on_engine_complete(FakeEvent())

        robot.execute_move.assert_called_once_with("a0a1", is_capture=False)
        workflow = coordinator.active_workflows[FakeEvent.trace_id]
        self.assertEqual(workflow["ai_move"], "a0a1")


if __name__ == "__main__":
    unittest.main()
