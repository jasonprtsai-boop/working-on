from backend.interfaces.shared.schemas import ControlCommandSchema, PlayerMoveSchema


class ControlRequest(ControlCommandSchema):
    """[Production Architecture] Validated API control request."""


class MoveRequest(PlayerMoveSchema):
    """Validated player move request shared with Socket.IO."""
