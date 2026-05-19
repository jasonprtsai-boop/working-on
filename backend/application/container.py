import logging
from typing import Any, Optional

logger = logging.getLogger("ServiceContainer")

from typing import Any, Dict, Type, TypeVar, Optional, Protocol, runtime_checkable

T = TypeVar("T")

@runtime_checkable
class IBus(Protocol):
    def publish(self, event: Any) -> None: ...
    def subscribe(self, event_type: str, handler: Any) -> None: ...

class ServiceContainer:
    """
    [Architectural Authority] Dependency Injection Container.
    The Single Point of Service Resolution.
    Ensures that all modules access dependencies via a central registry.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._services: Dict[str, Any] = {}
        return cls._instance

    def register(self, name: str, service: Any):
        """Register a service instance for global access."""
        self._services[name] = service
        logger.info(f"Service '{name}' registered in authoritative container.")

    def get(self, name: str) -> Any:
        """Resolve a service by name. Raises RuntimeError if not found."""
        if name not in self._services:
            raise RuntimeError(f"Service '{name}' not found. Check system initialization order.")
        return self._services[name]

    def resolve(self, service_type: Type[T], name: str) -> T:
        """Resolve a service with type hinting."""
        instance = self.get(name)
        if not isinstance(instance, service_type):
            logger.warning(f"Service '{name}' is not of type {service_type.__name__}")
        return instance

    @property
    def bus(self) -> IBus: return self.get("bus")

    @property
    def state(self): return self.get("state")

    @property
    def engine(self): return self.get("engine")

    @property
    def robot(self): return self.get("robot")

    @property
    def vision(self): return self.get("vision")

    @property
    def game(self): return self.get("game")

    @property
    def socket(self): return self.get("socket")

# Authoritative Singleton instance
container = ServiceContainer()
