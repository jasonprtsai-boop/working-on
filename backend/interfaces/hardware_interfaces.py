from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any


class VisionInterface(ABC):
    @abstractmethod
    def detect(self) -> Tuple[Optional[str], float]:
        """Return (fen, confidence) if available."""
        ...


class RobotInterface(ABC):
    @abstractmethod
    def execute_move(self, move: str, is_capture: bool = False) -> bool:
        ...

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        ...
