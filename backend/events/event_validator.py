class EventValidator:
    """[Infrastructure] Enforces schema integrity for all published events."""
    REQUIRED_FIELDS = [
        "domain",
        "type",
        "payload",
        "timestamp",
        "id"
    ]

    @classmethod
    def validate(cls, event):
        """Checks if the event object has all required production fields."""
        for field in cls.REQUIRED_FIELDS:
            if not hasattr(event, field):
                raise ValueError(f"[Event Error] Missing required field: {field}")
        return True
