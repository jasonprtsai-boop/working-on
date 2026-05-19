import time

class SyncState:
    """Manages system synchronization, timeline analytics, and pipeline status."""
    def __init__(self):
        self.frame_analytics = {}
        self.timeline = {
            "vision": {"duration": 0},
            "engine": {"duration": 0},
            "robot": {"duration": 0}
        }
        self.current_frame_id = None

    def start_frame(self):
        frame_id = int(time.time() * 1000)
        self.frame_analytics[frame_id] = {
            "start": time.time(),
            "stages": {}
        }
        self.current_frame_id = frame_id
        return frame_id

    def log_stage_end(self, stage):
        if self.current_frame_id and self.current_frame_id in self.frame_analytics:
            now = time.time()
            start = self.frame_analytics[self.current_frame_id]["start"]
            duration = (now - start) * 1000
            self.frame_analytics[self.current_frame_id]["stages"][stage] = duration
            self.timeline[stage]["duration"] = int(duration)
            return duration
        return 0

    def to_dict(self):
        return {
            "timeline": self.timeline
        }
