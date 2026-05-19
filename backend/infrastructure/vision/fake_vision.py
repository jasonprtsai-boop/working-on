import time
from backend.utils.logger import logger

class FakeVision:
    def __init__(self):
        self._cap = None

    def detect(self):
        logger.info("FakeVision: Simulating board detection...")
        time.sleep(1.0)
        # Return a sample FEN
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        return fen, 0.99

    def save_debug_frame(self, path):
        logger.info(f"FakeVision: Saving mock frame to {path}")
        return True

fake_vision = FakeVision()
