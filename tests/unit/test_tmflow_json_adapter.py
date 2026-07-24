import json
import socket
import threading
import unittest
from unittest.mock import patch

from backend.infrastructure.robot.tmflow_json_adapter import TMflowJsonAdapter
from backend.infrastructure.robot.tmflow_json_protocol import RobotCommand
from backend.utils import config


class FakeTMflowJsonServer:
    def __init__(self):
        self.commands = []
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self.host, self.port = self._sock.getsockname()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        try:
            with socket.create_connection((self.host, self.port), timeout=0.2):
                pass
        except OSError:
            pass
        self._thread.join(timeout=2.0)
        self._sock.close()

    def _serve(self):
        self._sock.listen(1)
        self._sock.settimeout(0.2)
        self._ready.set()
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(0.5)
                self._handle_connection(conn)

    def _handle_connection(self, conn):
        buffer = bytearray()
        while not self._stop.is_set():
            try:
                chunk = conn.recv(1)
            except socket.timeout:
                continue
            if not chunk:
                return
            if chunk != b"\n":
                buffer.extend(chunk)
                continue
            message = json.loads(buffer.decode("utf-8"))
            buffer.clear()
            self.commands.append(message)
            for response in self._responses_for(message):
                conn.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))

    def _responses_for(self, message):
        command_id = message.get("id")
        command = str(message.get("command") or "").upper()
        msg_type = str(message.get("type") or "").upper()
        if msg_type == "PING" or command == "PING":
            return [self._response(command_id, "PONG", "DONE", "IDLE", {"latency_ms": 1})]
        if command == "HELLO":
            return [self._response(command_id, "RESPONSE", "DONE", "IDLE", {"server": "fake_tmflow", "protocol": "1.0"})]
        if command == "GET_STATE":
            return [self._response(command_id, "RESPONSE", "DONE", "READY", {"socket": "CONNECTED", "alarm": False})]
        if command in {"MOVE_L", "GRIPPER"}:
            return [
                self._response(command_id, "RESPONSE", "ACK", "READY", {}),
                self._response(command_id, "RESPONSE", "STARTED", "MOVING", {}),
                self._response(command_id, "RESPONSE", "DONE", "IDLE", {"duration_sec": 0.01}),
            ]
        if command == "STOP":
            return [self._response(command_id, "RESPONSE", "DONE", "IDLE", {})]
        return [self._response(command_id, "RESPONSE", "ERROR", "ERROR", {}, {"code": "CMD_UNKNOWN"})]

    def _response(self, command_id, msg_type, status, state, result, error=None):
        return {
            "version": "1.0",
            "type": msg_type,
            "id": command_id,
            "timestamp": "2026-07-24T00:00:00+08:00",
            "status": status,
            "state": state,
            "result": result,
            "error": error,
        }


class TestTMflowJsonAdapter(unittest.TestCase):
    def test_robot_command_serializes_newline_envelope(self):
        command = RobotCommand(id="CMD_TEST_001", command="GET_STATE", payload={})

        line = command.to_json_line()
        payload = json.loads(line.decode("utf-8"))

        self.assertTrue(line.endswith(b"\n"))
        self.assertEqual(payload["version"], "1.0")
        self.assertEqual(payload["type"], "COMMAND")
        self.assertEqual(payload["id"], "CMD_TEST_001")
        self.assertEqual(payload["command"], "GET_STATE")

    def test_adapter_connect_ping_motion_and_gripper_against_mock_server(self):
        with FakeTMflowJsonServer() as server, patch.object(config, "FAKE_ROBOT", False), patch.object(
            config,
            "ROBOT_TMFLOW_WIRE_FORMAT",
            "envelope",
        ):
            adapter = TMflowJsonAdapter(host=server.host, port=server.port)

            self.assertTrue(adapter.connect())
            self.assertTrue(adapter.ping())
            self.assertTrue(adapter.send_motion([1, 2, 3, 4, 5, 6], speed=20, acceleration=20, timeout=1.0))
            self.assertTrue(adapter.set_gripper(True))
            adapter.disconnect()

        commands = [str(item.get("command") or item.get("type")).upper() for item in server.commands]
        self.assertIn("HELLO", commands)
        self.assertIn("GET_STATE", commands)
        self.assertIn("PING", commands)
        self.assertIn("MOVE_L", commands)
        self.assertIn("GRIPPER", commands)

    def test_adapter_supports_flat_json_wire_format(self):
        with FakeTMflowJsonServer() as server, patch.object(config, "FAKE_ROBOT", False), patch.object(
            config,
            "ROBOT_TMFLOW_WIRE_FORMAT",
            "flat_json",
        ):
            adapter = TMflowJsonAdapter(host=server.host, port=server.port)

            self.assertTrue(adapter.connect())
            self.assertTrue(adapter.send_motion([10, 20, 30, 40, 50, 60], speed=15, acceleration=15, timeout=1.0))
            adapter.disconnect()

        move_command = next(item for item in server.commands if item.get("command") == "MOVE_L")
        self.assertEqual(move_command["x"], 10.0)
        self.assertEqual(move_command["rz"], 60.0)

    def test_adapter_fails_closed_when_server_unavailable(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()
        sock.close()

        with patch.object(config, "FAKE_ROBOT", False), patch.object(config, "ROBOT_CONNECT_TIMEOUT_SEC", 0.1):
            adapter = TMflowJsonAdapter(host="127.0.0.1", port=port)

            self.assertFalse(adapter.connect())
            self.assertFalse(adapter.connected)
            self.assertIsNotNone(adapter.last_error)


if __name__ == "__main__":
    unittest.main()
