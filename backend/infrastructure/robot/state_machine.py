from enum import Enum

class RobotState(Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    MOVING = "MOVING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"

class RobotStateMachine:
    def __init__(self):
        self.current_state = RobotState.IDLE

    def transition_to(self, next_state: RobotState):
        # Add transition validation if needed
        self.current_state = next_state
