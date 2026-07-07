import asyncio
import time
from backend.runtime.lifecycle.base_worker import BaseWorker
from backend.runtime.messaging.queues import queue_manager
from backend.infrastructure.vision.camera import Camera
from backend.utils.logger import logger

class CameraWorker(BaseWorker):
    """
    [Runtime Layer] Camera Worker (Industrial Pipeline Step 1).
    Responsible ONLY for reading frames and putting them into the queue.
    """
    def __init__(self, camera: Camera, target_fps: int = 30):
        super().__init__("Camera")
        self.camera = camera
        self.interval = 1.0 / target_fps

    async def run(self):
        logger.info("[CameraWorker] Started.")
        if not self.camera.open():
            logger.error("[CameraWorker] Failed to open camera. Worker stopping.")
            return

        while self.is_running:
            try:
                start_time = time.time()

                frame = self.camera.get_frame()
                if frame is not None:
                    # Put latest frame into queue (Drop oldest if full)
                    await queue_manager.put_latest(queue_manager.frame_queue, frame)

                # FPS Limiter to prevent CPU spikes
                elapsed = time.time() - start_time
                sleep_time = max(0, self.interval - elapsed)
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[CameraWorker] Error: {e}")
                await asyncio.sleep(1.0)

        self.camera.release()
        logger.info("[CameraWorker] Released camera and stopped.")
