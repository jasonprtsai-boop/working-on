from dataclasses import dataclass

@dataclass
class RobotCommand:
    """[P1] Encapsulates a movement request for the asynchronous robotic worker."""
    command_id: str
    move: str
    trace_id: str
    status: str = "QUEUED"
    retry_count: int = 0
