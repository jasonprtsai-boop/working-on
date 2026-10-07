from __future__ import annotations

import socket
import unittest
from unittest.mock import MagicMock, patch

from backend.infrastructure.robot.tmflow_json_client import TMflowJsonClient
from backend.infrastructure.robot.tmflow_json_protocol import RobotCommand, TMflowJsonProtocolError


class TestTMflowJsonClientBuffered(unittest.TestCase):
    def test_single_message_read(self):
        client = TMflowJsonClient("127.0.0.1", 5890)
        client.sock = MagicMock()
        client.sock.recv.side_effect = [b'{"id":"cmd_1","status":"DONE"}\n']

        msg = client.read_message(timeout=1.0)
        self.assertEqual(msg["id"], "cmd_1")
        self.assertEqual(msg["status"], "DONE")
        self.assertEqual(len(client._rx_buffer), 0)

    def test_multiple_messages_in_single_chunk(self):
        client = TMflowJsonClient("127.0.0.1", 5890)
        client.sock = MagicMock()
        client.sock.recv.side_effect = [
            b'{"id":"cmd_1","status":"ACK"}\n{"id":"cmd_1","status":"DONE"}\n'
        ]

        msg1 = client.read_message(timeout=1.0)
        self.assertEqual(msg1["status"], "ACK")

        # Second message should be read from internal buffer without socket recv
        msg2 = client.read_message(timeout=1.0)
        self.assertEqual(msg2["status"], "DONE")
        client.sock.recv.assert_called_once()
        self.assertEqual(len(client._rx_buffer), 0)

    def test_message_split_across_chunks(self):
        client = TMflowJsonClient("127.0.0.1", 5890)
        client.sock = MagicMock()
        client.sock.recv.side_effect = [
            b'{"id":"cmd_2",',
            b'"status":',
            b'"DONE"}\n',
        ]

        msg = client.read_message(timeout=1.0)
        self.assertEqual(msg["id"], "cmd_2")
        self.assertEqual(msg["status"], "DONE")
        self.assertEqual(client.sock.recv.call_count, 3)

    def test_max_message_bytes_exceeded_raises_error(self):
        client = TMflowJsonClient("127.0.0.1", 5890, max_message_bytes=20)
        client.sock = MagicMock()
        client.sock.recv.side_effect = [b"1234567890123456789012345"]

        with self.assertRaises(TMflowJsonProtocolError):
            client.read_message(timeout=1.0)

    def test_closed_socket_raises_connection_error(self):
        client = TMflowJsonClient("127.0.0.1", 5890)
        client.sock = MagicMock()
        client.sock.recv.return_value = b""

        with self.assertRaises(ConnectionError):
            client.read_message(timeout=1.0)

    def test_timeout_raises_timeout_error(self):
        client = TMflowJsonClient("127.0.0.1", 5890)
        client.sock = MagicMock()
        client.sock.recv.side_effect = socket.timeout("timed out")

        with self.assertRaises(TimeoutError):
            client.read_message(timeout=0.01)

    def test_connect_and_close_clears_buffer(self):
        client = TMflowJsonClient("127.0.0.1", 5890)
        client._rx_buffer.extend(b"stale_bytes")

        client.close()
        self.assertEqual(len(client._rx_buffer), 0)

        with patch("socket.create_connection") as mock_conn:
            fake_sock = MagicMock()
            mock_conn.return_value = fake_sock
            client._rx_buffer.extend(b"more_stale")
            client.connect()
            self.assertEqual(len(client._rx_buffer), 0)
            self.assertTrue(client.connected)
        client.close()


if __name__ == "__main__":
    unittest.main()
