from typing import Protocol, Dict, Any, Union, Optional
import asyncio

class WorkerProtocol(Protocol):
    """
    [Industrial Architecture] Unified interface for all background workers.
    Ensures that WorkerManager can orchestrate lifecycle uniformly.
    """
    status: str
    last_error: Optional[str]

    def start(self) -> Union[None, asyncio.Task, asyncio.Future, Any]:
        """Start the worker. May return an awaitable for async initialization."""
        ...

    def stop(self) -> Union[None, asyncio.Task, asyncio.Future, Any]:
        """Stop the worker gracefully."""
        ...

    @property
    def is_running(self) -> bool:
        """Return True if the worker is active and healthy."""
        ...

    def stats(self) -> Dict[str, Any]:
        """Return observability metrics for diagnostics."""
        ...
