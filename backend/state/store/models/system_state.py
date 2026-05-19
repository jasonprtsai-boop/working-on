from dataclasses import asdict, dataclass, field
from datetime import datetime
from backend.state.store.models.game_state import CoreGameState
from backend.state.store.models.engine_state import EngineState
from backend.state.store.models.robot_state import RobotState
from backend.state.store.models.vision_state import VisionState

@dataclass(frozen=True)
class SystemState:
    """The root immutable state object for the entire system."""
    game: CoreGameState = field(default_factory=CoreGameState)
    engine: EngineState = field(default_factory=EngineState)
    robot: RobotState = field(default_factory=RobotState)
    vision: VisionState = field(default_factory=VisionState)

    # System Health
    fps: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0

    trace_id: str = "root"
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self):
        return {
            "game": asdict(self.game),
            "engine": asdict(self.engine),
            "robot": asdict(self.robot),
            "vision": asdict(self.vision),
            "health": {
                "fps": self.fps,
                "cpu_percent": self.cpu_percent,
                "memory_mb": self.memory_mb
            },
            "trace_id": self.trace_id,
            "timestamp": self.timestamp
        }
