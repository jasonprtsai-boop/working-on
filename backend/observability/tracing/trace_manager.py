import uuid

class TraceManager:
    """Manages unique trace IDs for cross-module pipeline tracking."""
    @staticmethod
    def create_trace_id():
        return str(uuid.uuid4())
