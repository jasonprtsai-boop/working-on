import unittest

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


class TestRobotAuthority(unittest.TestCase):
    def setUp(self):
        self.original_services = dict(container._services)
        self.original_auto_execute = config.AUTO_EXECUTE_ROBOT
        self.original_global_stop = estop.GLOBAL_STOP

    def tearDown(self):
        container._services = self.original_services
        config.AUTO_EXECUTE_ROBOT = self.original_auto_execute
        estop.GLOBAL_STOP = self.original_global_stop

    def _engine_event(self, best_move="a0a1", final=True):
        payload = {"best_move": best_move}
        if final is not None:
            payload["final"] = final
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


if __name__ == "__main__":
    unittest.main()
