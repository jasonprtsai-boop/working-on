from dataclasses import dataclass, field
from typing import List, Optional

@dataclass(frozen=True)
class RobotState:
    current_command: Optional[str] = None
    robot_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    arm_status: str = "IDLE"
    safety_status: str = "SAFE"
    is_connected: bool = False
    queue_size: int = 0
    last_action: str = ""
    connected: bool = False
    busy: bool = False
    error: Optional[str] = None
    position: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
