from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class EngineInterface(ABC):
    """High-level engine interface used by simulation and adapters."""

    @abstractmethod
    def get_move(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return an engine decision payload (implementation-specific)."""
        ...
