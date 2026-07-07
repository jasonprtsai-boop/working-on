import asyncio
import psutil
import time
from backend.runtime.lifecycle.base_worker import BaseWorker
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType
from backend.runtime.contract_schema import normalize_diagnostics_payload
from backend.utils.logger import logger

class MonitoringWorker(BaseWorker):
    """
    [Runtime Layer] System Health & Metrics Monitor.
    Periodically collects CPU, Memory, and Event Throughput metrics.
    """
    def __init__(self, interval_sec: float = 2.0):
        super().__init__("Monitoring")
        self.interval = interval_sec
        self.process = psutil.Process()

    async def run(self):
        logger.info("[MonitoringWorker] Started.")
        while self.is_running:
            try:
                # 1. Collect Hardware Metrics
                cpu_percent = psutil.cpu_percent()
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                thread_count = self.process.num_threads()
                timestamp = time.time()
                gpu_status = self._gpu_status()
                temperature_status = self._temperature_status()
                robot_status = self._robot_status()
                vision_status = self._vision_status()

                try:
                    from backend.runtime.messaging.queues import queue_manager
                    queue_stats = queue_manager.stats()
                except Exception as exc:
                    queue_stats = {"error": str(exc)}

                try:
                    from backend.runtime.workers.worker_manager import worker_manager
                    worker_status = worker_manager.status_snapshot()
                    async_runtime_status = worker_manager.runtime_snapshot()
                except Exception as exc:
                    worker_status = {"error": str(exc)}
                    async_runtime_status = {"error": str(exc)}

                try:
                    event_bus_status = bus.stats()
                except Exception as exc:
                    event_bus_status = {"error": str(exc)}

                try:
                    from backend.runtime.workers.persistence_worker import persistence_worker
                    persistence_status = persistence_worker.stats()
                except Exception as exc:
                    persistence_status = {"error": str(exc)}

                try:
                    from backend.observability.telemetry import telemetry_service
                    telemetry_snapshot = telemetry_service.snapshot(
                        queue_stats=queue_stats,
                        worker_status=worker_status,
                    )
                except Exception as exc:
                    telemetry_snapshot = {
                        "telemetry": {"enabled": False, "error": str(exc)},
                        "pipeline": {},
                        "topology": {},
                    }

                # 2. Publish Diagnostics Event
                diagnostics_payload = normalize_diagnostics_payload({
                    "fps": 0.0,
                    "cpu_percent": cpu_percent,
                    "memory_mb": memory_mb,
                    "threads": thread_count,
                    "health": {
                        "fps": 0.0,
                        "cpu_percent": cpu_percent,
                        "memory_mb": memory_mb,
                        "threads": thread_count,
                        "gpu": gpu_status,
                        "temperature": temperature_status,
                        "timestamp": timestamp,
                        "interval_sec": self.interval,
                    },
                    "robot": robot_status,
                    "vision": vision_status,
                    "queue": queue_stats,
                    "queues": queue_stats,
                    "workers": worker_status,
                    "event_bus": event_bus_status,
                    "persistence": persistence_status,
                    "async_runtime": async_runtime_status,
                    **telemetry_snapshot,
                })
                bus.publish(BaseEvent.create(
                    event_type=EventType.DIAGNOSTICS_UPDATED,
                    source="monitoring_worker",
                    payload=diagnostics_payload
                ))

                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MonitoringWorker] Error: {e}")
                await asyncio.sleep(5.0)

    def _gpu_status(self) -> dict:
        try:
            import GPUtil  # type: ignore

            gpus = GPUtil.getGPUs()
            if not gpus:
                return {"available": False, "reason": "not_detected"}
            gpu = gpus[0]
            return {
                "available": True,
                "name": getattr(gpu, "name", "GPU"),
                "load_percent": round(float(getattr(gpu, "load", 0.0)) * 100.0, 1),
                "memory_used_mb": round(float(getattr(gpu, "memoryUsed", 0.0)), 1),
                "memory_total_mb": round(float(getattr(gpu, "memoryTotal", 0.0)), 1),
                "temperature_c": getattr(gpu, "temperature", None),
            }
        except Exception as exc:
            return {"available": False, "reason": exc.__class__.__name__}

    def _temperature_status(self) -> dict:
        try:
            sensors_fn = getattr(psutil, "sensors_temperatures", None)
            if not sensors_fn:
                return {"available": False, "reason": "unsupported"}
            readings = sensors_fn(fahrenheit=False) or {}
            max_temp = None
            label = ""
            count = 0
            for sensor_name, entries in readings.items():
                for entry in entries or []:
                    current = getattr(entry, "current", None)
                    if current is None:
                        continue
                    count += 1
                    if max_temp is None or current > max_temp:
                        max_temp = float(current)
                        label = f"{sensor_name}:{getattr(entry, 'label', '')}".strip(":")
            if max_temp is None:
                return {"available": False, "reason": "not_detected", "sensors": count}
            return {"available": True, "max_c": round(max_temp, 1), "label": label, "sensors": count}
        except Exception as exc:
            return {"available": False, "reason": exc.__class__.__name__}

    def _robot_status(self) -> dict:
        try:
            from backend.application.container import container

            robot = container.get("robot")
            if robot and hasattr(robot, "get_status"):
                status = robot.get_status() or {}
                if isinstance(status, dict):
                    connected = bool(status.get("connected") or status.get("is_connected"))
                    status.setdefault("serial", {"available": connected, "status": "connected" if connected else "unavailable"})
                    status.setdefault("usb", {"available": connected, "status": "connected" if connected else "unavailable"})
                    return status
        except Exception as exc:
            return {"connected": False, "error": str(exc), "serial": {"available": False}, "usb": {"available": False}}
        return {"connected": False, "serial": {"available": False}, "usb": {"available": False}}

    def _vision_status(self) -> dict:
        try:
            from backend.infrastructure.vision.vision_system import vision_system

            if hasattr(vision_system, "get_status"):
                status = vision_system.get_status() or {}
                if isinstance(status, dict):
                    calibration = status.get("calibration") if isinstance(status.get("calibration"), dict) else {}
                    return {
                        "status": status.get("status", status.get("camera_status", "unknown")),
                        "fps": status.get("fps", 0.0),
                        "mode": status.get("mode", "unknown"),
                        "fallback": status.get("fallback", False),
                        "camera": status.get("camera", status.get("camera_index")),
                        "calibration": calibration,
                        "calibrated": calibration.get("calibrated"),
                        "calibration_quality": calibration.get("quality"),
                        "calibration_source": calibration.get("source"),
                    }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "camera": None}
        return {"status": "unknown", "fps": 0.0, "camera": None}

monitoring_worker = MonitoringWorker()
