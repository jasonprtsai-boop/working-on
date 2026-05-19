from backend.shared.protocols.event_protocol import EventEnvelope

class Event(EventEnvelope):
    """
    [Production Architecture] Authoritative Event Model.
    Inherits from industrial standard EventEnvelope.
    """
    domain: str = "system"

    @property
    def name(self):
        return f"{self.domain}.{self.event_type}"
