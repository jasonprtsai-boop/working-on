import os
import unittest

from tests.helpers import socket_auth


class TestRobotStatusContract(unittest.TestCase):
    def test_robot_status_updated_emits_and_validates(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.events.bus.event_bus import bus
        from backend.runtime.contract_schema import validate_contract_payload

        app, socketio = create_app()
        client = socketio.test_client(app, flask_test_client=app.test_client(), auth=socket_auth())
        try:
            client.get_received()

            payload = {
                "connected": False,
                "busy": False,
                "error": None,
                "last_action": "",
                "queue_size": 0,
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
            validate_contract_payload("ROBOT.STATUS_UPDATED", payload)
            from backend.events.event_types import EventType
            from backend.events.models.base_event import BaseEvent
            bus.publish(BaseEvent.create(
                event_type=EventType.ROBOT_STATUS_UPDATED,
                source="test",
                payload=payload,
            ))
            socketio.sleep(0.05)

            received = client.get_received()
        finally:
            client.disconnect()

        msgs = [m for m in received if m.get("name") == "SYSTEM_STATE_UPDATE"]
        args0 = [m.get("args", [{}])[0] for m in msgs if m.get("args")]
        robot_msgs = [a for a in args0 if a.get("type") == "ROBOT.STATUS_UPDATED"]
        self.assertTrue(robot_msgs, "Expected ROBOT.STATUS_UPDATED emission")

        # Validate received payload schema
        validate_contract_payload("ROBOT.STATUS_UPDATED", robot_msgs[-1].get("payload") or {})
