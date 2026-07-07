import unittest
import time
from unittest.mock import patch

from backend.application.container import container
from backend.application.services.estop import estop
from backend.application.services.robot_facade import RobotFacade
from backend.application.use_cases.coordinate_workflow import WorkflowCoordinator
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.utils import config


class FakeRobotAuthority:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def execute_move(self, move, is_capture=False):
        self.calls.append((move, is_capture))
        return self.result


class FakeStateSnapshot:
    def __init__(self, board=None, fen=""):
        self.board = board
        self.fen = fen

    def to_dict(self):
        return {"game": {"board": self.board, "fen": self.fen}}


class FailingRobotAuthority:
    async def move_piece(self, move, is_capture=False):
        raise RuntimeError("motor fault")

    def get_status(self):
        raise RuntimeError("serial offline")


class TestRobotAuthority(unittest.TestCase):
    def setUp(self):
        self.original_services = dict(container._services)
        self.original_auto_execute = config.AUTO_EXECUTE_ROBOT
        self.original_global_stop = estop.GLOBAL_STOP

    def tearDown(self):
        container._services = self.original_services
        config.AUTO_EXECUTE_ROBOT = self.original_auto_execute
        estop.GLOBAL_STOP = self.original_global_stop

    def _engine_event(self, best_move="a0a1", final=True, source_timestamp=None):
        payload = {"best_move": best_move}
        if final is not None:
            payload["final"] = final
        if source_timestamp is not False:
            payload["source_timestamp"] = source_timestamp or time.time()
        return BaseEvent.create(
            event_type=EventType.ENGINE_ANALYSIS_COMPLETED,
            source="test",
            payload=payload,
            trace_id="trace-robot-authority",
        )

    def test_workflow_does_not_execute_robot_when_auto_execute_disabled(self):
        config.AUTO_EXECUTE_ROBOT = False
        robot = FakeRobotAuthority()
        container.register("robot", robot)

        coordinator = WorkflowCoordinator()
        coordinator.on_engine_complete(self._engine_event())

        self.assertEqual(robot.calls, [])

    def test_workflow_uses_execute_move_authority_once_when_enabled(self):
        config.AUTO_EXECUTE_ROBOT = True
        robot = FakeRobotAuthority()
        container.register("robot", robot)

        coordinator = WorkflowCoordinator()
        coordinator.on_engine_complete(self._engine_event())

        self.assertEqual(robot.calls, [("a0a1", False)])

    def test_workflow_refuses_robot_execution_without_vision_timestamp(self):
        config.AUTO_EXECUTE_ROBOT = True
        robot = FakeRobotAuthority()
        container.register("robot", robot)

        coordinator = WorkflowCoordinator()
        coordinator.on_engine_complete(self._engine_event(source_timestamp=False))

        self.assertEqual(robot.calls, [])

    def test_workflow_refuses_robot_execution_for_stale_vision_trace(self):
        config.AUTO_EXECUTE_ROBOT = True
        robot = FakeRobotAuthority()
        container.register("robot", robot)
        coordinator = WorkflowCoordinator()
        trace_id = "trace-stale-vision"
        vision_event = BaseEvent.create(
            event_type=EventType.VISION_MOVE_DETECTED,
            source="test",
            payload={"source_timestamp": time.time() - 10.0},
            trace_id=trace_id,
        )
        engine_event = self._engine_event("a0a1")
        engine_event.trace_id = trace_id

        with patch.object(config, "VISION_RESULT_MAX_AGE_SEC", 0.5):
            coordinator.on_vision_move(vision_event)
            coordinator.on_engine_complete(engine_event)

        self.assertEqual(robot.calls, [])

    def test_workflow_infers_capture_from_destination_occupancy(self):
        config.AUTO_EXECUTE_ROBOT = True
        robot = FakeRobotAuthority()
        board = [[None for _ in range(9)] for _ in range(10)]
        board[8][0] = "P"
        container.register("robot", robot)
        event = self._engine_event("a0a1")
        event.payload["board"] = board

        coordinator = WorkflowCoordinator()
        coordinator.on_engine_complete(event)

        self.assertEqual(robot.calls, [("a0a1", True)])

    def test_workflow_respects_explicit_capture_payload(self):
        config.AUTO_EXECUTE_ROBOT = True
        robot = FakeRobotAuthority()
        container.register("robot", robot)
        event = self._engine_event("a0a1")
        event.payload["is_capture"] = True

        coordinator = WorkflowCoordinator()
        coordinator.on_engine_complete(event)

        self.assertEqual(robot.calls, [("a0a1", True)])

    def test_workflow_respects_explicit_non_capture_payload(self):
        config.AUTO_EXECUTE_ROBOT = True
        robot = FakeRobotAuthority()
        container.register("robot", robot)
        event = self._engine_event("a0a1")
        event.payload["is_capture"] = "false"

        coordinator = WorkflowCoordinator()
        coordinator.on_engine_complete(event)

        self.assertEqual(robot.calls, [("a0a1", False)])

    def test_workflow_ignores_non_final_engine_analysis(self):
        config.AUTO_EXECUTE_ROBOT = True
        robot = FakeRobotAuthority()
        container.register("robot", robot)

        coordinator = WorkflowCoordinator()
        coordinator.on_engine_complete(self._engine_event(final=False))
        coordinator.on_engine_complete(self._engine_event(final=None))

        self.assertEqual(robot.calls, [])

    def test_robot_facade_refuses_execute_move_during_estop(self):
        facade = RobotFacade.__new__(RobotFacade)
        facade._impl = FakeRobotAuthority()
        estop.GLOBAL_STOP = True

        self.assertFalse(facade.execute_move("a0a1"))
        self.assertEqual(facade._impl.calls, [])

    def test_robot_facade_reports_status_and_move_failures(self):
        facade = RobotFacade.__new__(RobotFacade)
        facade._impl = FailingRobotAuthority()
        estop.GLOBAL_STOP = False

        with patch("backend.application.services.robot_facade.publish_error_diagnostic") as publish:
            self.assertFalse(facade.execute_move("a0a1"))
            status = facade.get_status()

        self.assertEqual(status["connected"], False)
        self.assertEqual(status["error"], "serial offline")
        codes = [call.kwargs["code"] for call in publish.call_args_list]
        self.assertIn("robot_execute_move_failed", codes)
        self.assertIn("robot_status_unavailable", codes)


if __name__ == "__main__":
    unittest.main()
