from backend.interfaces.shared.schemas import ControlCommandSchema, PlayerMoveSchema, VisionUpdateSchema


SocketAction = ControlCommandSchema
SocketPlayerMove = PlayerMoveSchema
SocketVisionUpdate = VisionUpdateSchema


def normalize_socket_action_payload(data):
    if isinstance(data, str):
        return {"action": data}
    payload = dict(data or {}) if isinstance(data, dict) else {}
    if "action" not in payload and "type" in payload:
        payload["action"] = payload.get("type")
    return payload
