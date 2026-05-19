import logging
from backend.shared.protocols.event_protocol import EventEnvelope

logger = logging.getLogger(__name__)

class EventMiddleware:
    """[Production Architecture] Base class for event processing middleware."""
    def process(self, envelope: EventEnvelope):
        return envelope

class LoggingMiddleware(EventMiddleware):
    def process(self, envelope: EventEnvelope):
        logger.info(f"[EVENT] {envelope.event_type} | Trace: {envelope.trace_id} | Source: {envelope.source}")

class ValidationMiddleware(EventMiddleware):
    def process(self, envelope: EventEnvelope):
        # Pydantic already validated the structure, but we can add domain validation here
        if not envelope.event_type:
            raise ValueError("Event type cannot be empty")
