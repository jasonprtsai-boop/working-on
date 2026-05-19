from __future__ import annotations

class ChessSystemError(Exception):
    """Base class for all chess system exceptions."""
    pass

class FatalBootstrapError(ChessSystemError):
    """Raised when a critical component fails to initialize during bootstrap."""
    pass

class ComponentDegradedError(ChessSystemError):
    """Raised when a non-critical component fails but the system can still run in a limited state."""
    pass
