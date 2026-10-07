import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.services.engine_service import EngineService


class EngineServiceSupervisorTest(unittest.IsolatedAsyncioTestCase):
    async def test_compute_recovers_when_process_terminated(self):
        engine = EngineService()
        dead_proc = MagicMock()
        dead_proc.returncode = 1
        engine.process = dead_proc

        alive_proc = MagicMock()
        alive_proc.returncode = None
        alive_proc.stdin = MagicMock()
        alive_proc.stdin.is_closing.return_value = False

        async def fake_start():
            engine.process = alive_proc
            engine.running = True

        engine.start = AsyncMock(side_effect=fake_start)
        engine.close = AsyncMock()
        engine.send = AsyncMock()
        engine._wait_for_line = AsyncMock(return_value="readyok")

        with patch.object(engine, "_get_output_line", AsyncMock(return_value="bestmove b0c2")):
            result = await engine.compute("startpos", depth=4)

        engine.close.assert_awaited_once()
        engine.start.assert_awaited_once()
        self.assertIsNotNone(result)
        self.assertEqual(result.get("best_move"), "b0c2")

    async def test_compute_recovers_when_internal_error_set(self):
        engine = EngineService()
        alive_proc = MagicMock()
        alive_proc.returncode = None
        alive_proc.stdin = MagicMock()
        alive_proc.stdin.is_closing.return_value = False
        engine.process = alive_proc
        engine.last_internal_error = "ERROR: NNUE eval crashed"

        async def fake_close():
            engine.last_internal_error = None
            engine.process = None

        async def fake_start():
            engine.process = alive_proc
            engine.running = True

        engine.close = AsyncMock(side_effect=fake_close)
        engine.start = AsyncMock(side_effect=fake_start)
        engine.send = AsyncMock()
        engine._wait_for_line = AsyncMock(return_value="readyok")

        with patch.object(engine, "_get_output_line", AsyncMock(return_value="bestmove c3c4")):
            result = await engine.compute("startpos", depth=4)

        engine.close.assert_awaited_once()
        engine.start.assert_awaited_once()
        self.assertIsNone(engine.last_internal_error)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("best_move"), "c3c4")


if __name__ == "__main__":
    unittest.main()
