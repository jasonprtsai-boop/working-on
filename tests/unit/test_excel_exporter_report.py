import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from backend.utils.serialization.excel_exporter import ExcelExporter


class ExcelExporterReportTest(unittest.TestCase):
    def test_report_adds_action_items_and_filters_snapshot_noise(self) -> None:
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        events = [
            {
                "sequence_id": 1,
                "event_id": "11111111-1111-4111-8111-111111111111",
                "session_id": "session-a",
                "trace_id": "trace-a",
                "timestamp": 1788766600.0,
                "type": "STATE_UPDATED",
                "source": "state_manager",
                "payload": {
                    "vision": {
                        "detections_count": 0,
                        "avg_confidence": 0.0,
                        "min_confidence": 0.0,
                        "latency_ms": 5,
                        "fen": fen,
                    },
                    "engine": {"bestmove": "b0c2", "score": 0.3, "depth": 8},
                    "robot": {"connected": False, "error": "snapshot only"},
                },
            },
            {
                "sequence_id": 2,
                "event_id": "22222222-2222-4222-8222-222222222222",
                "session_id": "session-a",
                "trace_id": "trace-a",
                "timestamp": 1788766601.0,
                "type": "VISION_FRAME_PROCESSED",
                "source": "vision_service",
                "payload": {
                    "detections_count": 1,
                    "avg_confidence": 0.91,
                    "min_confidence": 0.91,
                    "latency_ms": 42,
                    "camera_status": "ready",
                    "fen": fen,
                },
            },
            {
                "sequence_id": 3,
                "event_id": "33333333-3333-4333-8333-333333333333",
                "session_id": "session-a",
                "trace_id": "trace-a",
                "timestamp": 1788766602.0,
                "type": "ROBOT_STATUS_UPDATED",
                "source": "robot_status_worker",
                "payload": {
                    "connected": False,
                    "is_connected": False,
                    "error": "link failed",
                    "ip": "192.168.10.10",
                    "port": 502,
                    "connection": {"adapter": "modbus", "connected": False},
                    "robot_status": "disconnected",
                },
            },
            {
                "sequence_id": 4,
                "event_id": "44444444-4444-4444-8444-444444444444",
                "session_id": "session-a",
                "trace_id": "trace-a",
                "timestamp": 1788766603.0,
                "type": "ENGINE_INFO_UPDATED",
                "source": "AI_ENGINE",
                "payload": {"bestmove": "h2e2", "score": 12, "depth": 10, "engine_ms": 24},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.xlsx"
            exporter = ExcelExporter(filename=str(Path(tmp) / "runtime.xlsx"), subscribe=False)
            exporter.export_events(events, str(output), session_id="session-a")

            wb = load_workbook(output, data_only=True)
            self.addCleanup(wb.close)

            self.assertIn("Action Items", wb.sheetnames)
            overview = {
                row[0]: row[1]
                for row in wb["Overview"].iter_rows(min_row=4, max_col=2, values_only=True)
                if row[0]
            }
            self.assertEqual(overview["Report Verdict"], "NOT READY - robot disconnected")
            self.assertEqual(overview["Game Moves"], 0)
            self.assertEqual(overview["Vision Events"], 1)
            self.assertEqual(overview["YOLO Min Confidence"], 0.91)

            action_rows = list(wb["Action Items"].iter_rows(min_row=2, values_only=True))
            self.assertEqual(action_rows[0][0], "P0")
            self.assertEqual(action_rows[0][1], "Robot")
            self.assertIn("endpoint=192.168.10.10:502", action_rows[0][3])
            self.assertIn("adapter=modbus", action_rows[0][3])
            self.assertIn("error=link failed", action_rows[0][3])
            self.assertEqual([row[1] for row in action_rows].count("Robot"), 1)

            self.assertEqual(wb["Vision YOLO"].max_row, 2)
            self.assertEqual(wb["Game Moves"].max_row, 1)
            self.assertEqual(wb["Engine AI"].max_row, 2)
            self.assertEqual(wb["UCCI Trace"].max_row, 2)

            warnings = list(wb["Errors & Warnings"].iter_rows(min_row=2, values_only=True))
            reasons = [row[1] for row in warnings]
            self.assertNotIn("Low YOLO confidence", reasons)
            self.assertIn("link failed", " ".join(str(row[1]) for row in warnings))

    def test_field_profile_focuses_report_and_excludes_raw_sheets(self) -> None:
        events = [
            {
                "sequence_id": 1,
                "event_id": "55555555-5555-4555-8555-555555555555",
                "session_id": "session-field",
                "trace_id": "trace-field",
                "timestamp": 1788766700.0,
                "type": "GAME_PLAYER_MOVE",
                "source": "player",
                "payload": {"move": "a0a1", "fen_after": "fen-after"},
            },
            {
                "sequence_id": 2,
                "event_id": "66666666-6666-4666-8666-666666666666",
                "session_id": "session-field",
                "trace_id": "trace-field",
                "timestamp": 1788766701.0,
                "type": "ROBOT_STATUS_UPDATED",
                "source": "robot",
                "payload": {"connected": True, "robot_status": "ready", "message": "field test ok"},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "field-report.xlsx"
            exporter = ExcelExporter(filename=str(Path(tmp) / "runtime.xlsx"), subscribe=False)
            exporter.export_events(events, str(output), session_id="session-field", profile="field")

            wb = load_workbook(output, data_only=True)
            self.addCleanup(wb.close)

            self.assertEqual(wb["Overview"]["A1"].value, "S.M.A.R.T Chess Robot Field Report")
            self.assertIn("Field Test Report", wb.sheetnames)
            self.assertIn("Game Moves", wb.sheetnames)
            self.assertIn("Errors & Warnings", wb.sheetnames)
            self.assertNotIn("Pipeline_Log", wb.sheetnames)
            self.assertNotIn("Raw Payload", wb.sheetnames)
            self.assertNotIn("Vision Detections", wb.sheetnames)

    def test_game_moves_enriched_parameters_and_timing(self) -> None:
        initial_fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        fen_after_m1 = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 0 1"
        fen_after_m2 = "r1bakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR w - - 0 2"
        fen_after_m3 = "r1bakabnr/9/1c2C1c1/p1p3p1p/9/9/P1P1P1P1P/1C7/9/RNBAKABNR b - - 0 2"

        events = [
            {
                "sequence_id": 1,
                "event_id": "10000000-0000-0000-0000-000000000001",
                "session_id": "session-game",
                "trace_id": "trace-1",
                "timestamp": 1788767000.0,
                "type": "GAME_PLAYER_MOVE",
                "source": "player",
                "payload": {
                    "move": "h2e2",
                    "actor": "player",
                    "fen_before": initial_fen,
                    "fen_after": fen_after_m1,
                    "yolo_latency_ms": 35.5,
                },
            },
            {
                "sequence_id": 2,
                "event_id": "10000000-0000-0000-0000-000000000002",
                "session_id": "session-game",
                "trace_id": "trace-2",
                "timestamp": 1788767005.0,
                "type": "ROBOT_MOVE_COMPLETED",
                "source": "robot_service",
                "payload": {
                    "move": "b9c7",
                    "actor": "ai",
                    "ai_move": "b9c7",
                    "fen_before": fen_after_m1,
                    "fen_after": fen_after_m2,
                    "robot_status": "success",
                    "robot_ms": 1200.0,
                    "engine_ms": 85.0,
                    "score": 15,
                    "depth": 8,
                },
            },
            {
                "sequence_id": 3,
                "event_id": "10000000-0000-0000-0000-000000000003",
                "session_id": "session-game",
                "trace_id": "trace-3",
                "timestamp": 1788767012.0,
                "type": "GAME_PLAYER_MOVE",
                "source": "player",
                "payload": {
                    "move": "e2e6",
                    "actor": "player",
                    "fen_before": fen_after_m2,
                    "fen_after": fen_after_m3,
                    "yolo_latency_ms": 40.0,
                },
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "game-report.xlsx"
            exporter = ExcelExporter(filename=str(Path(tmp) / "runtime.xlsx"), subscribe=False)
            exporter.export_events(events, str(output), session_id="session-game")

            wb = load_workbook(output, data_only=True)
            self.addCleanup(wb.close)

            ws = wb["Game Moves"]
            headers = [cell.value for cell in ws[1]]
            self.assertIn("round_number", headers)
            self.assertIn("move_number", headers)
            self.assertIn("turn_side", headers)
            self.assertIn("actor", headers)
            self.assertIn("move_chinese", headers)
            self.assertIn("piece_name", headers)
            self.assertIn("action_type", headers)
            self.assertIn("captured_piece", headers)
            self.assertIn("from_square", headers)
            self.assertIn("to_square", headers)
            self.assertIn("from_board_coord", headers)
            self.assertIn("to_board_coord", headers)
            self.assertIn("from_robot_xy", headers)
            self.assertIn("to_robot_xy", headers)
            self.assertIn("turn_duration_sec", headers)
            self.assertIn("round_duration_sec", headers)

            rows = [dict(zip(headers, [cell.value for cell in row])) for row in ws.iter_rows(min_row=2)]

            self.assertEqual(len(rows), 3)

            # Move 1: Red Player h2e2
            m1 = rows[0]
            self.assertEqual(m1["round_number"], 1)
            self.assertEqual(m1["move_number"], 1)
            self.assertEqual(m1["turn_side"], "紅方")
            self.assertIn("玩家", str(m1["actor"]))
            self.assertEqual(m1["move"], "h2e2")
            self.assertEqual(m1["move_chinese"], "炮二平五")
            self.assertEqual(m1["piece_name"], "紅炮")
            self.assertEqual(m1["action_type"], "移動")
            self.assertEqual(m1["captured_piece"], "無")
            self.assertEqual(m1["from_square"], "h2")
            self.assertEqual(m1["to_square"], "e2")
            self.assertEqual(m1["from_board_coord"], "[7, 2]")
            self.assertEqual(m1["to_board_coord"], "[4, 2]")
            self.assertTrue(bool(m1["from_robot_xy"]))
            self.assertTrue(bool(m1["to_robot_xy"]))
            self.assertIn(m1["turn_duration_sec"], ("", None))
            self.assertEqual(m1["round_duration_sec"], 0.0)

            # Move 2: Black AI b9c7
            m2 = rows[1]
            self.assertEqual(m2["round_number"], 1)
            self.assertEqual(m2["move_number"], 2)
            self.assertEqual(m2["turn_side"], "黑方")
            self.assertIn("AI", str(m2["actor"]))
            self.assertEqual(m2["move"], "b9c7")
            self.assertEqual(m2["move_chinese"], "馬2進3")
            self.assertEqual(m2["piece_name"], "黑馬")
            self.assertEqual(m2["turn_duration_sec"], 5.0)
            self.assertEqual(m2["round_duration_sec"], 5.0)
            self.assertEqual(m2["robot_ms"], 1200.0)
            self.assertEqual(m2["thinking_ms"], 85.0)

            # Move 3: Red Player e2e6 (captures black pawn on e6)
            m3 = rows[2]
            self.assertEqual(m3["round_number"], 2)
            self.assertEqual(m3["move_number"], 3)
            self.assertEqual(m3["turn_side"], "紅方")
            self.assertEqual(m3["action_type"], "吃子")
            self.assertEqual(m3["captured_piece"], "黑卒")
            self.assertEqual(m3["turn_duration_sec"], 7.0)
            self.assertEqual(m3["round_duration_sec"], 0.0)

            # Check Robot Control sheet
            rc_ws = wb["Robot Control"]
            rc_headers = [cell.value for cell in rc_ws[1]]
            self.assertIn("move_chinese", rc_headers)
            self.assertIn("from_robot_xy", rc_headers)
            self.assertIn("to_robot_xy", rc_headers)

            # Check Session Summary sheet
            ss_ws = wb["Session Summary"]
            ss_headers = [cell.value for cell in ss_ws[1]]
            self.assertIn("avg_turn_sec", ss_headers)
            ss_row = dict(zip(ss_headers, [cell.value for cell in list(ss_ws.iter_rows(min_row=2))[0]]))
            self.assertEqual(ss_row["game_moves"], 3)
            self.assertEqual(ss_row["avg_turn_sec"], 6.0)

    def test_log_events_batch_and_queue_draining(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "batch_test.xlsx"
            exporter = ExcelExporter(filename=str(file_path), subscribe=False)
            items = [
                (
                    None,
                    {
                        "event_id": f"evt-{i}",
                        "session_id": "sess-batch",
                        "trace_id": "trace-batch",
                        "timestamp": 1788766600.0 + i,
                        "type": "DIAGNOSTICS_UPDATED",
                        "source": "test",
                        "payload": {"status": f"batch-{i}"},
                    },
                )
                for i in range(10)
            ]
            exporter.log_events_batch(items)

            wb = load_workbook(str(file_path), data_only=True)
            ws = wb[ExcelExporter.PIPELINE_SHEET]
            # Header + 10 rows = 11 rows
            self.assertEqual(ws.max_row, 11)
            wb.close()


if __name__ == "__main__":
    unittest.main()
