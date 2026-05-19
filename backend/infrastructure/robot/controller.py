import asyncio
import logging
from typing import Optional, List

from .state_machine import RobotStateMachine, RobotState
from .command_queue import RobotCommandQueue
from .safety_monitor import safety_monitor
from .planner import MotionPlanner
from .executor import RobotExecutor
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType

logger = logging.getLogger("RobotController")

class RobotController:
    """
    Deprecated compatibility controller.

    RobotFacade.execute_move() is the active v1 robot command authority. Keep
    this class out of runtime wiring unless a future migration explicitly
    promotes it back behind RobotFacade.

    [Application/Infrastructure Bridge] High-Level Robot Controller.
    Orchestrates: Queue -> Planner -> Validator -> Executor -> Feedback.
    """
    DEPRECATED_ACTIVE_CONSUMER = False

    def __init__(self, executor: RobotExecutor, planner: MotionPlanner):
        self.executor = executor
        self.planner = planner
        self.state_machine = RobotStateMachine()
        self.queue = RobotCommandQueue()
        self.last_error = None
        self._max_retries = 3

    async def run_loop(self):
        """Main robot execution loop with heartbeat watchdog."""
        # Start heartbeat task
        asyncio.create_task(self._heartbeat())

        while True:
            if self.state_machine.current_state == RobotState.IDLE:
                command = self.queue.dequeue()
                if command:
                    await self._execute_move_sequence(command)
            await asyncio.sleep(0.1)

    async def _heartbeat(self):
        """Monitor hardware connectivity while idle."""
        while True:
            try:
                if self.state_machine.current_state == RobotState.IDLE:
                    # ping the robot
                    pass # adapter.ping()
            except Exception as e:
                logger.warning(f"[Robot] Heartbeat lost: {e}")
            await asyncio.sleep(5.0)

    async def _execute_move_sequence(self, move_str: str):
        attempt = 0
        while attempt < self._max_retries:
            try:
                # 1. Planning
                self._transition(RobotState.PLANNING)
                commands = self.planner.plan_move(move_str)
                if not commands:
                    raise RuntimeError("Path planning failed.")

                # 2. Safety Validation
                if not safety_monitor.validate_sequence(commands):
                    raise RuntimeError("Safety validation failed.")

                # 3. Execution with Timeout
                self._transition(RobotState.MOVING)
                for cmd in commands:
                    try:
                        # Standard industrial timeout: 10s per command
                        success = await asyncio.wait_for(self.executor.execute_command(cmd), timeout=10.0)
                        if not success:
                            raise RuntimeError(f"Hardware execution failed at: {cmd}")
                    except asyncio.TimeoutError:
                        raise RuntimeError(f"Hardware TIMEOUT at: {cmd}")

                    await asyncio.sleep(0.05)

                # 4. Verification
                self._transition(RobotState.VERIFYING)
                self._transition(RobotState.IDLE)
                return

            except Exception as e:
                attempt += 1
                logger.error(f"[Robot] Attempt {attempt} failed: {e}")
                self.last_error = str(e)
                if attempt < self._max_retries:
                    await self._recover()
                else:
                    break

        self._transition(RobotState.ERROR)

    async def _recover(self):
        logger.info("[Robot] Recovering...")
        await self.executor.reset()
        await asyncio.sleep(1.0)

    def _transition(self, new_state: RobotState):
        old_state = self.state_machine.current_state
        if self.state_machine.transition_to(new_state):
            logger.info(f"[Robot] {old_state} -> {new_state}")
            bus.publish(BaseEvent.create(
                event_type=EventType.ROBOT_MOVE_STARTED if new_state == RobotState.MOVING else EventType.DIAGNOSTICS_UPDATED,
                source="robot_controller",
                payload={"robot_state": new_state.value, "error": self.last_error}
            ))

    def enqueue_move(self, move_str: str):
        if not self.queue.enqueue(move_str):
            self.last_error = "Robot command queue is full."
            self._transition(RobotState.ERROR)
