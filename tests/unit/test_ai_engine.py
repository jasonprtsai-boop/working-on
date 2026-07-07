import asyncio
import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from backend.application.services.engine_service import EngineService
from backend.events.event_types import EventType
from engine.board import Board
from engine.search import Search


class TestEngineServiceSafety(unittest.TestCase):
    def test_probe_status_has_expected_shape(self):
        service = EngineService()

        status = service.get_probe_status()

        self.assertIn("status", status)
        self.assertIn("engine_path", status)
        self.assertIn("candidates", status)
        self.assertIn("report", status)

    def test_start_aborts_cleanly_when_no_compatible_pair(self):
        service = EngineService()
        service.probe_compatible_pair = AsyncMock(return_value=False)

        asyncio.run(service.start())

        self.assertIsNone(service.process)
        self.assertTrue(service.last_startup_error)

    def test_shutdown_prevents_late_start_and_compute(self):
        service = EngineService()
        service._shutdown_requested = True
        service.probe_compatible_pair = AsyncMock(side_effect=AssertionError("probe should not run"))

        asyncio.run(service.start())
        result = asyncio.run(service.compute("startpos", depth=1))

        self.assertIsNone(service.process)
        self.assertIsNone(result)
        service.probe_compatible_pair.assert_not_called()

    def test_start_aborts_if_shutdown_begins_during_probe(self):
        service = EngineService()
        service.active_nnue_path = "fake.nnue"

        async def fake_probe():
            service._shutdown_requested = True
            return True

        service.probe_compatible_pair = AsyncMock(side_effect=fake_probe)
        service._open_engine = AsyncMock(side_effect=AssertionError("engine should not open"))

        asyncio.run(service.start())

        self.assertIsNone(service.process)
        service._open_engine.assert_not_called()

    def test_compute_handles_process_closed_mid_loop_without_error_log(self):
        service = EngineService()
        service.running = True
        service.process = type("FakeProcess", (), {"returncode": None})()
        service.send = AsyncMock()
        service._wait_for_line = AsyncMock(return_value="readyok")

        async def run_compute():
            async def close_soon():
                await asyncio.sleep(0.01)
                service.process = None

            closer = asyncio.create_task(close_soon())
            result = await service.compute("startpos", depth=1)
            await closer
            return result

        with patch("backend.application.services.engine_service.logger.error") as log_error:
            result = asyncio.run(run_compute())

        self.assertEqual(result.get("best_move"), "none")
        log_error.assert_not_called()

    def test_reader_does_not_publish_completion_for_intermediate_info(self):
        service = EngineService()
        service.running = True

        class FakeStdout:
            def __init__(self):
                self.lines = [
                    b"info depth 4 score cp 12 nodes 100 nps 50 pv a0a1 b9c7\n",
                    b"",
                ]

            async def readline(self):
                return self.lines.pop(0)

        service.process = type(
            "FakeProcess",
            (),
            {"stdout": FakeStdout(), "returncode": None},
        )()
        published = []

        with patch("backend.application.services.engine_service.bus.publish", side_effect=published.append):
            asyncio.run(service._reader())

        event_types = [
            item.get("type") if isinstance(item, dict) else getattr(item, "event_type", None)
            for item in published
        ]
        self.assertIn("ENGINE.INFO_UPDATED", event_types)
        self.assertNotIn(EventType.ENGINE_ANALYSIS_COMPLETED, event_types)
        self.assertNotIn(EventType.ENGINE_ANALYSIS_COMPLETED.value, event_types)

    def test_compute_result_marks_final_analysis(self):
        service = EngineService()
        service.running = True
        service.process = type("FakeProcess", (), {"returncode": None})()
        service.send = AsyncMock()
        service._wait_for_line = AsyncMock(return_value="readyok")
        lines = iter([
            "info depth 1 multipv 1 score cp 15 pv a0a1",
            "bestmove a0a1",
        ])

        async def next_line(timeout=1.0):
            return next(lines)

        service._get_output_line = next_line

        result = asyncio.run(service.compute("startpos", depth=1))

        self.assertTrue(result.get("final"))
        self.assertFalse(result.get("is_thinking"))
        self.assertEqual(result.get("best_move"), "a0a1")

    def test_local_search_exposes_get_best_move_for_uci(self):
        board = Board()
        board.setup_startpos()

        move = Search().get_best_move(board, max_depth=1, time_limit=0.1)

        self.assertIsInstance(move, tuple)
        self.assertEqual(len(move), 4)


if __name__ == "__main__":
    unittest.main()
