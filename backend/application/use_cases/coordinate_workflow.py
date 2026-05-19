import time
from typing import Dict, Any, Optional
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.application.container import container
from backend.utils import config
from backend.utils.logger import logger

class WorkflowCoordinator:
    """
    [Application Layer] High-Level Orchestrator
    Manages the E2E execution pipeline: Vision -> AI -> Robot.
    Includes telemetry tracking and fault tolerance.
    """

    def __init__(self):
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self._is_enabled = True

    def start(self):
        """Subscribe to core events to drive the automated loop."""
        bus.subscribe(EventType.VISION_MOVE_DETECTED, self.on_vision_move)
        bus.subscribe(EventType.ENGINE_ANALYSIS_COMPLETED, self.on_engine_complete)
        bus.subscribe(EventType.ROBOT_MOVE_COMPLETED, self.on_robot_complete)
        logger.info("[WorkflowCoordinator] Subscribed to automated pipeline events.")

    def on_vision_move(self, event: BaseEvent):
        """Step 1: Vision detected a move. Pipeline starts."""
        if not self._is_enabled: return

        trace_id = event.trace_id
        logger.info(f"[Workflow] Pipeline started. Trace: {trace_id}")

        self.active_workflows[trace_id] = {
            "start_time": time.time(),
            "vision_time": event.timestamp,
            "steps": ["vision"]
        }

        # In a fully automated system, we might trigger engine computation here,
        # but currently EngineWorker polls the state.
        # We'll wait for ENGINE_ANALYSIS_COMPLETED to act.

    def on_engine_complete(self, event: BaseEvent):
        """Step 2: AI analysis finished. Trigger robot if move found."""
        payload = event.payload or {}
        if payload.get("final") is not True:
            logger.info("[Workflow] Ignoring non-final engine analysis event.")
            return

        trace_id = event.trace_id
        if trace_id not in self.active_workflows:
            # Maybe it's a manual move or from a previous session
            self.active_workflows[trace_id] = {"start_time": time.time(), "steps": []}

        wf = self.active_workflows[trace_id]
        wf["engine_time"] = event.timestamp
        wf["steps"].append("engine")

        best_move = payload.get("best_move")
        if best_move and best_move != "none":
            if not getattr(config, "AUTO_EXECUTE_ROBOT", False):
                logger.info(f"[Workflow] AUTO_EXECUTE_ROBOT=false; robot execution skipped for {best_move}.")
                return

            logger.info(f"[Workflow] AI move found: {best_move}. Triggering Robot.")

            robot_service = container.get("robot")
            if robot_service and hasattr(robot_service, "execute_move"):
                is_capture = False
                if not robot_service.execute_move(best_move, is_capture=is_capture):
                    logger.warning("[Workflow] RobotFacade.execute_move returned false.")
            elif robot_service:
                logger.error("[Workflow] Robot service does not expose the active execute_move authority.")
            else:
                logger.warning("[Workflow] Robot service not found.")

    def on_robot_complete(self, event: BaseEvent):
        """Step 3: Robot finished moving. Workflow complete."""
        trace_id = event.trace_id
        if trace_id in self.active_workflows:
            wf = self.active_workflows[trace_id]
            wf["robot_time"] = event.timestamp
            wf["steps"].append("robot")

            duration = time.time() - wf["start_time"]
            logger.info(f"[Workflow] Pipeline COMPLETE. Trace: {trace_id}. Total Latency: {duration:.2f}s")

            # Publish Telemetry Event
            bus.publish(BaseEvent.create(
                event_type="TELEMETRY.PIPELINE_COMPLETE",
                source="workflow_coordinator",
                payload={
                    "total_duration": duration,
                    "steps": wf["steps"],
                    "trace_id": trace_id
                }
            ))

            # Cleanup
            del self.active_workflows[trace_id]

workflow_coordinator = WorkflowCoordinator()
