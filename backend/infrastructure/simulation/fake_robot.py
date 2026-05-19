import time
from backend.utils.logger import logger

class FakeRobot:
    def __init__(self):
        self.connected = False
        self.pos = [0, 0, 150]

    def connect(self):
        logger.info("FakeRobot: Simulating connection...")
        time.sleep(0.5)
        self.connected = True
        return True

    def execute_chess_move(self, move_ucci):
        logger.info(f"FakeRobot: Executing move {move_ucci}...")
        # Simulate physical movement time
        time.sleep(2.0)
        logger.info(f"FakeRobot: Move {move_ucci} finished.")
        return True

    def stop_all(self):
        logger.warning("FakeRobot: EMERGENCY STOP EXECUTED!")
        return True

    def get_status(self):
        return {"pos": self.pos, "angles": [0]*6, "connected": self.connected}

fake_robot = FakeRobot()
