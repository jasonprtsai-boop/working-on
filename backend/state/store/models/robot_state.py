from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    orientation: dict = field(default_factory=lambda: {"rx": 0.0, "ry": 0.0, "rz": 0.0})
    joint_angles: dict = field(default_factory=dict)
    speed: float = 0.0
    ip: str = ""
    port: int = 0
    connection: Dict[str, Any] = field(default_factory=dict)
    telemetry: Dict[str, Any] = field(default_factory=dict)
    status_code: Optional[int] = None
    status_label: str = ""
    error_code: Optional[int] = None
    gripper_status_code: Optional[int] = None
