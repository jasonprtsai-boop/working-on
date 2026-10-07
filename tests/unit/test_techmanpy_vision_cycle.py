from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.infrastructure.robot.techmanpy_adapter import TechmanPyAdapter


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Transaction:
    def __init__(self):
        self.calls = []

    def set_base(self, value):
        self.calls.append(("base", value))

    def set_tcp(self, value):
        self.calls.append(("tcp", value))

    def move_to_point_line(self, pose, speed, acceleration):
        self.calls.append(("line", pose, speed, acceleration))

    def move_to_point_ptp(self, pose, speed, acceleration):
        self.calls.append(("ptp", pose, speed, acceleration))

    def set_queue_tag(self, tag, wait_for_completion=False):
        self.calls.append(("queue_tag", tag, wait_for_completion))

    async def submit(self):
        self.calls.append(("submit",))


class TechmanPyVisionCycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_line_motion_applies_base_tcp_and_completion_tag(self):
        adapter = TechmanPyAdapter(host="192.0.2.10", port=5890)
        transaction = _Transaction()
        connection = SimpleNamespace(start_transaction=lambda: transaction)
        fake_techmanpy = SimpleNamespace(
            connect_sct=lambda **_kwargs: _AsyncContext(connection),
        )

        with patch("backend.infrastructure.robot.techmanpy_adapter.techmanpy", fake_techmanpy):
            with patch("backend.infrastructure.robot.techmanpy_adapter.config.ROBOT_TMFLOW_BASE", "ChessBase", create=True):
                with patch("backend.infrastructure.robot.techmanpy_adapter.config.ROBOT_TMFLOW_TCP", "ChessTCP", create=True):
                    await adapter._send_motion_script(
                        [1, 2, 3, 180, 0, 90],
                        0.2,
                        200,
                        motion_mode="line",
                    )

        self.assertEqual(transaction.calls[0:2], [("base", "ChessBase"), ("tcp", "ChessTCP")])
        self.assertEqual(transaction.calls[2][0], "line")
        self.assertEqual(transaction.calls[3][0], "queue_tag")
        self.assertTrue(transaction.calls[3][2])
        self.assertEqual(transaction.calls[4], ("submit",))

    async def test_vision_cycle_exits_listen_and_waits_for_return(self):
        adapter = TechmanPyAdapter(host="192.0.2.10", port=5890)
        connection = SimpleNamespace(exit_listen=AsyncMock())
        states = iter((True, False, True))
        adapter._check_listen_node = AsyncMock(side_effect=lambda: next(states))

        fake_techmanpy = SimpleNamespace(
            connect_sct=lambda **_kwargs: _AsyncContext(connection),
        )
        with patch("backend.infrastructure.robot.techmanpy_adapter.techmanpy", fake_techmanpy):
            with patch("backend.infrastructure.robot.techmanpy_adapter.config.ROBOT_TECHMANPY_VISION_POLL_SEC", 0.01, create=True):
                await adapter._trigger_vision_cycle(timeout=1.0)

        connection.exit_listen.assert_awaited_once()
        self.assertTrue(adapter.last_listen_node_active)

    async def test_vision_cycle_refuses_when_listen_is_not_active(self):
        adapter = TechmanPyAdapter(host="192.0.2.10", port=5890)
        adapter._check_listen_node = AsyncMock(return_value=False)

        with self.assertRaisesRegex(RuntimeError, "not inside the Listen Node"):
            await adapter._trigger_vision_cycle(timeout=0.1)


if __name__ == "__main__":
    unittest.main()
