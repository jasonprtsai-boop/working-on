from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from generate_report_diagrams import Diagram, PALETTE, font, hex_to_rgb


OUT_ROOT = Path("report_diagrams")
PNG_DIR = OUT_ROOT / "advanced_png"
SVG_DIR = OUT_ROOT / "advanced_svg"
CONTACT_SHEET = OUT_ROOT / "advanced_contact_sheet.png"


def chain(d: Diagram, ids: list[str], labels: list[str], y: int, x0: int, w: int, h: int, gap: int, fill: str, stroke: str):
    for i, (id_, label) in enumerate(zip(ids, labels)):
        d.box(id_, x0 + i * (w + gap), y, w, h, label, fill, stroke, font_size=21)
        if i:
            d.arrow(ids[i - 1], id_)


def advanced_dfd() -> Diagram:
    d = Diagram(
        "dfd_level2_system_data_flow",
        "Level-2 DFD 系統資料流圖",
        "外部實體、處理程序、資料儲存與信任邊界",
        "第三章、第四章",
        "比總流程圖更細，適合說明影像、棋局、控制、事件與研究資料如何流動。",
    )
    d.group(55, 150, 360, 820, "External Entities", "#FFFFFF", "#CBD5E1")
    d.group(500, 150, 850, 820, "Processing Boundary: Flask + AsyncRuntime", "#FFFFFF", "#CBD5E1")
    d.group(1435, 150, 430, 820, "Data Stores / Assets", "#FFFFFF", "#CBD5E1")
    d.box("user", 95, 250, 280, 110, "E1 使用者 / 長者\n實體走子\nUI 操作", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("researcher", 95, 430, 280, 110, "E2 研究員\n觀察 / 設定\n匯出資料", PALETTE["green_light"], PALETTE["green"], font_size=21)
    d.box("camera", 95, 610, 280, 110, "E3 Camera\n棋盤影像串流", PALETTE["teal_light"], PALETTE["teal"], font_size=21)
    d.box("tm", 95, 790, 280, 110, "E4 TM5-700\n實體落子 / 狀態", PALETTE["red_light"], PALETTE["red"], font_size=21)

    processes = [
        ("p1", 555, 235, "1.0 Interface Gateway\nREST / Socket / auth\npayload size / rate limit", PALETTE["blue_light"], PALETTE["blue"]),
        ("p2", 920, 235, "2.0 Vision Processing\nwarp / detect / map\nstable FEN", PALETTE["teal_light"], PALETTE["teal"]),
        ("p3", 555, 465, "3.0 Event & State Core\nBaseEvent / EventBus\nReducer / SystemState", PALETTE["violet_light"], PALETTE["violet"]),
        ("p4", 920, 465, "4.0 Engine Decision\ncurrent FEN\nPikafish UCI\nbestmove / PV", PALETTE["amber_light"], PALETTE["amber"]),
        ("p5", 555, 700, "5.0 Robot Execution\nWorkflowCoordinator\nRobotFacade\nE-Stop gate", PALETTE["red_light"], PALETTE["red"]),
        ("p6", 920, 700, "6.0 Observability\nPersistenceWorker\nReplay / Export\nDiagnostics", "#F8FAFC", "#475569"),
    ]
    for id_, x, y, label, fill, stroke in processes:
        d.box(id_, x, y, 320, 145, label, fill, stroke, font_size=20)

    stores = [
        ("d1", 1490, 235, "D1 StateStore\nSystemState snapshot\nFEN / health / trace_id", PALETTE["green_light"], PALETTE["green"]),
        ("d2", 1490, 455, "D2 SQLite app.db\nevents(sequence_id,\nsession_id, trace_id)", "#F8FAFC", "#475569"),
        ("d3", 1490, 675, "D3 Protected Assets\nPikafish.exe / NNUE\nYOLO best.pt", PALETTE["amber_light"], PALETTE["amber"]),
        ("d4", 1490, 835, "D4 Output Artifacts\nReplay / Excel / CSV\nlogs / reports", PALETTE["blue_light"], PALETTE["blue"]),
    ]
    for id_, x, y, label, fill, stroke in stores:
        d.box(id_, x, y, 320, 120, label, fill, stroke, font_size=20)

    d.arrow("user", "p1", "UI command / move")
    d.arrow("researcher", "p1", "admin config")
    d.arrow("camera", "p2", "raw frame")
    d.arrow("p1", "p3", "BaseEvent")
    d.arrow("p2", "p3", "VISION events")
    d.arrow("p3", "p4", "FEN changed")
    d.arrow("p4", "p3", "ENGINE result")
    d.arrow("p3", "p5", "move command")
    d.arrow("p5", "tm", "Modbus / fake execution")
    d.arrow("tm", "p5", "status / error")
    d.arrow("p3", "p6", "all events")
    d.arrow("p3", "d1", "commit snapshot")
    d.arrow("p6", "d2", "batch insert")
    d.arrow("d2", "p6", "", dashed=True, points=[(1490, 515), (1385, 515), (1385, 770), (1240, 770)])
    d.arrow("d3", "p2", "", dashed=True, points=[(1490, 735), (1380, 735), (1380, 305), (1240, 305)])
    d.arrow("d3", "p4", "", dashed=True, points=[(1490, 735), (1360, 735), (1360, 535), (1240, 535)])
    d.arrow("p6", "d4", "files", points=[(1240, 770), (1370, 770), (1370, 895), (1490, 895)])
    d.arrow("p3", "p1", "SYSTEM_STATE_UPDATE", dashed=True, points=[(715, 465), (715, 405), (715, 380)])
    return d


def component_dependency() -> Diagram:
    d = Diagram(
        "uml_component_dependency",
        "UML 元件依賴圖",
        "Factory、Container、EventBus、StateManager、Services、Workers 與 Adapters",
        "第三章、第四章",
        "以近似 UML component/class 方式呈現程式責任與相依關係。",
    )
    d.group(60, 150, 410, 820, "Interface Layer", "#FFFFFF", "#CBD5E1")
    d.group(540, 150, 840, 820, "Application / Domain Core", "#FFFFFF", "#CBD5E1")
    d.group(1450, 150, 410, 820, "Infrastructure Adapters", "#FFFFFF", "#CBD5E1")
    d.box("factory", 105, 220, 320, 105, "<<factory>>\nbackend.main.create_app()", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.box("api", 105, 390, 320, 105, "<<blueprints>>\napi_routes / dashboard", "#E0F2FE", "#0284C7", font_size=20)
    d.box("socket", 105, 560, 320, 120, "<<gateway>>\nsocket_handler.register_socketio\nSYSTEM_STATE_UPDATE", PALETTE["teal_light"], PALETTE["teal"], font_size=19)
    d.box("frontend", 105, 760, 320, 110, "<<browser modules>>\napi_client / socket_client\nstate / renderers", PALETTE["violet_light"], PALETTE["violet"], font_size=19)

    core = [
        ("boot", 600, 220, "<<bootstrap>>\nbootstrap_system()\nruntime -> services -> workers", PALETTE["amber_light"], PALETTE["amber"]),
        ("container", 1010, 220, "<<singleton>>\nServiceContainer\nbus / engine / vision / robot", "#F8FAFC", "#475569"),
        ("bus", 600, 430, "<<event broker>>\nEventBus\npublish / subscribe_all", PALETTE["violet_light"], PALETTE["violet"]),
        ("state", 1010, 430, "<<state authority>>\nStateManager\nreduce / validate / commit", PALETTE["green_light"], PALETTE["green"]),
        ("reducers", 600, 650, "<<reducers>>\nMove / Engine / Robot / System\nfunctional mutation", "#F0FDF4", "#16A34A"),
        ("workers", 1010, 650, "<<runtime workers>>\nEngine / Vision / RobotStatus\nMonitoring / Persistence", "#FEF3C7", "#D97706"),
    ]
    for id_, x, y, label, fill, stroke in core:
        d.box(id_, x, y, 330, 130, label, fill, stroke, font_size=19)

    infra = [
        ("vision", 1495, 220, "<<vision adapter>>\nVisionSystem\nSAHI/Yolo/Grid\nMJPEG overlay", PALETTE["teal_light"], PALETTE["teal"]),
        ("engine", 1495, 410, "<<engine adapter>>\nEngineService\nPikafish UCI\nEngineParser", PALETTE["amber_light"], PALETTE["amber"]),
        ("robot", 1495, 600, "<<robot adapter>>\nRobotFacade\nRobotService / FakeRobot\nE-Stop", PALETTE["red_light"], PALETTE["red"]),
        ("db", 1495, 790, "<<storage adapter>>\nEventStore SQLite\nExcel exporter / Replay", "#F8FAFC", "#475569"),
    ]
    for id_, x, y, label, fill, stroke in infra:
        d.box(id_, x, y, 320, 125, label, fill, stroke, font_size=19)

    d.arrow("factory", "boot", "calls")
    d.arrow("factory", "api", "registers", start_side="bottom", end_side="top")
    d.arrow("factory", "socket", "registers", start_side="bottom", end_side="top")
    d.arrow("frontend", "api", "REST", start_side="top", end_side="bottom")
    d.arrow("frontend", "socket", "Socket.IO", start_side="top", end_side="bottom")
    d.arrow("boot", "container", "register")
    d.arrow("container", "vision", "resolve")
    d.arrow("container", "engine", "resolve")
    d.arrow("container", "robot", "resolve")
    d.arrow("boot", "bus", "wire")
    d.arrow("bus", "state", "dispatch all")
    d.arrow("state", "reducers", "lookup")
    d.arrow("reducers", "state", "new SystemState")
    d.arrow("state", "bus", "STATE_UPDATED", dashed=True, points=[(1175, 430), (1175, 380), (765, 380), (765, 430)])
    d.arrow("workers", "bus", "publish")
    d.arrow("workers", "engine", "compute")
    d.arrow("workers", "vision", "process/stream")
    d.arrow("workers", "db", "persist")
    d.arrow("bus", "socket", "forward contract", points=[(600, 495), (470, 495), (470, 620), (425, 620)])
    return d


def detailed_sequence() -> Diagram:
    d = Diagram(
        "detailed_vision_engine_robot_sequence",
        "Vision -> Engine -> Robot 詳細時序圖",
        "含 trace_id、state commit、contract forward、persistence 與例外分支",
        "第三章、第四章",
        "展示一次完整自動互動從影像到手臂落子的工程細節。",
    )
    lanes = [
        ("cam", "Camera", 70),
        ("vision", "VisionSystem\n/ Worker", 280),
        ("vs", "VisionService", 490),
        ("bus", "EventBus", 700),
        ("sm", "StateManager", 910),
        ("eng", "EngineWorker\nEngineService", 1120),
        ("wf", "Workflow\nRobotFacade", 1330),
        ("front", "Frontend", 1540),
        ("db", "SQLite", 1750),
    ]
    for id_, title, x in lanes:
        d.box(id_, x, 165, 150, 70, title, "#FFFFFF", "#94A3B8", font_size=18, shadow=False)
        d.arrow((x + 75, 250), (x + 75, 940), color="#94A3B8", dashed=True, width=2)

    messages = [
        (145, 355, 355, "frame_buffer.put_raw(frame)"),
        (355, 430, 565, "detections + latency_ms"),
        (565, 505, 775, "BaseEvent(VISION_BOARD_DETECTED)"),
        (775, 580, 985, "dispatch -> MoveReducer"),
        (985, 655, 775, "publish STATE_UPDATED"),
        (775, 730, 1195, "EngineWorker observes FEN"),
        (1195, 805, 1405, "bestmove -> execute_move"),
        (1405, 870, 775, "ROBOT.STATUS_UPDATED"),
        (775, 320, 1615, "SYSTEM_STATE_UPDATE contract"),
        (775, 915, 1825, "PersistenceWorker batch insert"),
    ]
    for x1, y, x2, label in messages:
        d.arrow((x1, y), (x2, y), label, width=3)
    d.box("branch1", 1025, 360, 300, 95, "alt: invalid FEN\nStateManager rejects\nno engine compute", PALETTE["red_light"], PALETTE["red"], font_size=18)
    d.box("branch2", 1265, 520, 300, 95, "alt: AUTO_EXECUTE_ROBOT=false\nbestmove only shown in UI", PALETTE["amber_light"], PALETTE["amber"], font_size=18)
    d.box("branch3", 1475, 690, 300, 95, "alt: E-Stop active\nRobotFacade returns false\nUI locked", PALETTE["red_light"], PALETTE["red"], font_size=18)
    d.note(80, 990, "閱讀重點：trace_id 從 Vision/Socket 事件一路傳到 Engine、Robot、Persistence，可支援 replay 與問題追蹤。")
    return d


def state_machine() -> Diagram:
    d = Diagram(
        "system_state_machine",
        "系統狀態機 State Machine",
        "IDLE、WAIT_MOVE、THINKING、APPLY_MOVE、EXECUTING、ERROR 與復原條件",
        "第三章、第四章",
        "適合放在方法章解釋流程控制與例外處理。",
    )
    states = {
        "idle": (130, 285, "IDLE\n等待操作\nsafe mode ready", PALETTE["green_light"], PALETTE["green"]),
        "wait": (520, 285, "WAIT_MOVE\n使用者走子\n或 Vision sync", PALETTE["blue_light"], PALETTE["blue"]),
        "detect": (910, 285, "DETECTING\nCamera frame\nYOLO/SAHI\nFEN validate", PALETTE["teal_light"], PALETTE["teal"]),
        "think": (1300, 285, "THINKING\nPikafish compute\ndepth / MultiPV", PALETTE["amber_light"], PALETTE["amber"]),
        "apply": (520, 620, "APPLY_MOVE\nMoveReducer\nhistory / turn\nSTATE_UPDATED", PALETTE["violet_light"], PALETTE["violet"]),
        "exec": (910, 620, "EXECUTING\nRobotFacade\npick-and-place\nstatus worker", PALETTE["red_light"], PALETTE["red"]),
        "error": (1300, 620, "ERROR / SAFE_STOP\nE-Stop\ninvalid payload\nhardware failure", PALETTE["red_light"], PALETTE["red"]),
    }
    for id_, (x, y, label, fill, stroke) in states.items():
        d.box(id_, x, y, 300, 150, label, fill, stroke, font_size=22)
    d.arrow("idle", "wait", "GAME_START / player_move")
    d.arrow("wait", "detect", "VISION_FRAME_CAPTURED")
    d.arrow("detect", "apply", "VISION_MOVE_DETECTED")
    d.arrow("apply", "think", "FEN changed", points=[(820, 695), (1450, 695), (1450, 435)])
    d.arrow("think", "exec", "ENGINE_ANALYSIS_COMPLETED\nbestmove")
    d.arrow("exec", "wait", "ROBOT_MOVE_COMPLETED", points=[(910, 695), (670, 695), (670, 435)])
    d.arrow("apply", "wait", "manual mode\nAUTO_EXECUTE_ROBOT=false", dashed=True)
    d.arrow("detect", "error", "invalid FEN / low confidence", dashed=True, points=[(1210, 360), (1450, 360), (1450, 620)])
    d.arrow("think", "error", "engine missing / timeout", dashed=True)
    d.arrow("exec", "error", "E-Stop / robot fail", dashed=True)
    d.arrow("error", "idle", "manual reset\nSYSTEM_RESET", dashed=True, points=[(1300, 695), (100, 695), (100, 360), (130, 360)])
    d.group(85, 815, 1730, 130, "狀態資料來源：CoreGameState.game_status / SystemPhase、EngineState.is_thinking、RobotState.safety_status、VisionState.camera_status。", "#FFFFFF", "#CBD5E1")
    return d


def coordinate_transform() -> Diagram:
    d = Diagram(
        "vision_coordinate_robot_transform",
        "Vision 座標轉換與機械手臂對位圖",
        "pixel -> perspective warp -> 9x10 board cell -> FEN -> robot TCP pose",
        "第三章、第四章",
        "比一般 Vision Pipeline 更細，專門說明座標映射與實體落子依據。",
    )
    chain(
        d,
        ["raw", "warp", "grid", "detect", "fen", "move", "pose"],
        [
            "原始影像\npixel(x,y)",
            "透視校正\nhomography\nwarped plane",
            "棋盤座標\n9 columns x 10 rows\ncell(row,col)",
            "棋子偵測\nbbox center\nclass/confidence",
            "棋局狀態\nboard_state\nFEN string",
            "走法轉換\nbestmove\nfrom -> to",
            "機械手臂座標\nworld frame\nTCP pose",
        ],
        240,
        45,
        245,
        160,
        22,
        PALETTE["teal_light"],
        PALETTE["teal"],
    )
    d.group(120, 600, 760, 260, "Vision geometry", "#FFFFFF", "#CBD5E1")
    d.box("formula1", 170, 675, 300, 105, "pixel_to_cell()\nBoardCoordinateSystem\nGridConfig rows/cols", "#F8FAFC", "#475569", font_size=19)
    d.box("formula2", 540, 675, 300, 105, "TemporalValidator\nwindow_size\nlast_stable_state", "#F8FAFC", "#475569", font_size=19)
    d.group(1040, 600, 760, 260, "Robot geometry", "#FFFFFF", "#CBD5E1")
    d.box("formula3", 1090, 675, 300, 105, "kinematics.grid_to_robot\nsafe approach height\ncapture handling", PALETTE["amber_light"], PALETTE["amber"], font_size=19)
    d.box("formula4", 1460, 675, 300, 105, "RobotSafety.validate_move\nworkspace limits\nE-Stop interlock", PALETTE["red_light"], PALETTE["red"], font_size=19)
    d.arrow("grid", "formula1")
    d.arrow("detect", "formula2")
    d.arrow("move", "formula3")
    d.arrow("pose", "formula4")
    d.note(80, 925, "報告說明建議：用這張圖解釋為什麼需要棋盤校正、棋格映射與安全工作空間，而不只是做物件偵測。")
    return d


def contract_validation() -> Diagram:
    d = Diagram(
        "socket_contract_validation_matrix",
        "Socket Contract 與 Payload 驗證圖",
        "Backend EventType -> serializers/schema -> SYSTEM_STATE_UPDATE -> frontend validation -> renderers",
        "第三章、第四章、測試章節",
        "凸顯前後端不是直接丟任意 JSON，而是有穩定 contract 與測試保護。",
    )
    d.group(70, 165, 520, 805, "Backend internal events", "#FFFFFF", "#CBD5E1")
    d.group(700, 165, 520, 805, "Contract boundary", "#FFFFFF", "#CBD5E1")
    d.group(1330, 165, 520, 805, "Frontend consumer", "#FFFFFF", "#CBD5E1")
    events = [
        ("ev1", "STATE_UPDATED\nSystemState.to_dict()", 235, PALETTE["green_light"], PALETTE["green"]),
        ("ev2", "ENGINE_ANALYSIS_COMPLETED\nbest_move / score / pv", 365, PALETTE["amber_light"], PALETTE["amber"]),
        ("ev3", "VISION.FRAME_PROCESSED\nlatency / detections / FEN", 495, PALETTE["teal_light"], PALETTE["teal"]),
        ("ev4", "ROBOT.STATUS_UPDATED\nconnected / busy / error", 625, PALETTE["red_light"], PALETTE["red"]),
        ("ev5", "DIAGNOSTICS_UPDATED\nengine / robot / vision", 755, PALETTE["blue_light"], PALETTE["blue"]),
    ]
    for id_, label, y, fill, stroke in events:
        d.box(id_, 120, y, 390, 90, label, fill, stroke, font_size=19)
    d.box("serializer", 765, 260, 390, 125, "serializers.py\nStateSerializer\nEngineInfoSerializer\nnormalize_diagnostics_payload", "#F8FAFC", "#475569", font_size=19)
    d.box("schema", 765, 470, 390, 125, "contract_schema.py\nPydantic payload models\noptional CONTRACT_VALIDATE", PALETTE["violet_light"], PALETTE["violet"], font_size=19)
    d.box("envelope", 765, 680, 390, 125, "SYSTEM_STATE_UPDATE\ntype + payload\ncontract_version=1.0", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.box("adapter", 1390, 280, 390, 125, "event_adapter.js\nKNOWN_EVENTS\nvalidateFrontendEventPayload", PALETTE["violet_light"], PALETTE["violet"], font_size=19)
    d.box("state", 1390, 510, 390, 125, "frontend state_manager\nnormalizer.js\nsubscriptions", PALETTE["green_light"], PALETTE["green"], font_size=19)
    d.box("render", 1390, 740, 390, 125, "renderers\nboard / engine / robot\nvision / diagnostics", PALETTE["teal_light"], PALETTE["teal"], font_size=19)
    for id_, *_ in events:
        d.arrow(id_, "serializer")
    d.arrow("serializer", "schema", "validate")
    d.arrow("schema", "envelope", "emit")
    d.arrow("envelope", "adapter", "Socket.IO")
    d.arrow("adapter", "state", "commit")
    d.arrow("state", "render", "subscriptions")
    d.note(90, 925, "測試對應：tests/integration/test_ws_contract_smoke.py、test_contract_payload_schemas.py、frontend socket/state tests。")
    return d


def deployment_network() -> Diagram:
    d = Diagram(
        "deployment_network_runtime",
        "Deployment / Runtime 部署通訊圖",
        "Windows PC、本機瀏覽器、攝影機、TM5-700 控制器、檔案系統與保護資產",
        "第四章 系統實作環境",
        "適合取代簡單架構圖，說明本機部署與各協定連線。",
    )
    d.group(60, 160, 1040, 800, "Windows Host PC", "#FFFFFF", "#CBD5E1")
    d.group(1180, 160, 690, 800, "External devices / files", "#FFFFFF", "#CBD5E1")
    d.box("browser", 120, 240, 280, 120, "Browser\nhttp://127.0.0.1:5000\nDashboard", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("flask", 500, 220, 280, 140, "Flask + Socket.IO\nmain.py\nthreading mode\nAPI blueprints", "#E0F2FE", "#0284C7", font_size=20)
    d.box("runtime", 500, 470, 280, 140, "AsyncRuntime\nbackground loop\nworkers / queues", PALETTE["violet_light"], PALETTE["violet"], font_size=20)
    d.box("state", 820, 340, 230, 120, "EventBus\nStateManager\ncontract forwarder", PALETTE["green_light"], PALETTE["green"], font_size=19)
    d.box("camera", 1240, 230, 260, 115, "USB / IP Camera\nOpenCV capture", PALETTE["teal_light"], PALETTE["teal"], font_size=20)
    d.box("robot", 1240, 430, 260, 115, "TM5-700 Controller\nModbus TCP / fake", PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.box("assets", 1240, 630, 260, 115, "Protected assets\nPikafish.exe\nNNUE / best.pt", PALETTE["amber_light"], PALETTE["amber"], font_size=20)
    d.box("fs", 1570, 360, 250, 150, "Local filesystem\nSQLite app.db\nreplays / logs\nExcel exports", "#F8FAFC", "#475569", font_size=20)
    d.arrow("browser", "flask", "HTTP REST / static")
    d.arrow("flask", "browser", "Socket.IO / MJPEG", start_side="left", end_side="right", dashed=True, points=[(500, 290), (430, 290), (430, 305), (400, 305)])
    d.arrow("flask", "runtime", "schedules work")
    d.arrow("runtime", "state", "events")
    d.arrow("state", "flask", "contract events")
    d.arrow("camera", "runtime", "frames", points=[(1240, 290), (1120, 290), (1120, 540), (780, 540)])
    d.arrow("runtime", "robot", "robot commands")
    d.arrow("assets", "runtime", "models / engine")
    d.arrow("runtime", "fs", "persistence / export")
    d.arrow("fs", "flask", "download / replay", dashed=True)
    return d


def erd_traceability() -> Diagram:
    d = Diagram(
        "event_store_traceability_erd",
        "資料模型與 Traceability 圖",
        "SystemState、EventStore、Replay、Export 與研究資料對應",
        "第四章、第五章、附錄",
        "用資料結構說明每筆互動如何回放、追蹤與匯出。",
    )
    d.group(55, 155, 530, 810, "Runtime objects", "#FFFFFF", "#CBD5E1")
    d.group(695, 155, 530, 810, "SQLite event store", "#FFFFFF", "#CBD5E1")
    d.group(1335, 155, 530, 810, "Research outputs", "#FFFFFF", "#CBD5E1")
    d.box("system", 110, 240, 420, 155, "SystemState\n- game: CoreGameState\n- engine: EngineState\n- robot: RobotState\n- vision: VisionState\n- health / trace_id / timestamp", PALETTE["green_light"], PALETTE["green"], font_size=18)
    d.box("event", 110, 500, 420, 155, "BaseEvent\n- event_id\n- event_type\n- source\n- payload\n- trace_id\n- timestamp", PALETTE["violet_light"], PALETTE["violet"], font_size=18)
    d.box("session", 110, 760, 420, 115, "Runtime session\nactive_session_id\nstart/end\nsafe mode / engine depth", PALETTE["blue_light"], PALETTE["blue"], font_size=18)
    d.box("events_table", 750, 235, 420, 250, "events table\nPK sequence_id\nsession_id\ntrace_id\ntype\npayload JSON\ntimestamp\nIndexes: session+sequence, trace_id, type", "#F8FAFC", "#475569", font_size=18)
    d.box("migration", 750, 610, 420, 115, "schema_migrations\nname='event_store'\nversion=2\napplied_at", PALETTE["amber_light"], PALETTE["amber"], font_size=18)
    d.box("replay", 1395, 235, 420, 135, "Replay API\n/replay/steps\n/replay/step/<index>\nstate reconstruction", PALETTE["blue_light"], PALETTE["blue"], font_size=18)
    d.box("export", 1395, 455, 420, 135, "Excel / CSV export\nmove history\nengine metrics\nvision/robot logs", PALETTE["green_light"], PALETTE["green"], font_size=18)
    d.box("analysis", 1395, 675, 420, 135, "Report analysis\nlatency / FPS\nerror events\nquestionnaire alignment", PALETTE["red_light"], PALETTE["red"], font_size=18)
    d.arrow("system", "event", "STATE_UPDATED snapshot")
    d.arrow("session", "event", "session_id added")
    d.arrow("event", "events_table", "PersistenceWorker.save_events")
    d.arrow("events_table", "replay", "ordered by sequence_id")
    d.arrow("events_table", "export", "query by session/type")
    d.arrow("export", "analysis", "tables / charts")
    d.arrow("events_table", "analysis", "trace_id evidence")
    d.note(710, 900, "這張圖可搭配資料庫 schema 或測試紀錄，說明研究資料不是事後手填，而是由事件來源自動產生。")
    return d


def safety_fault_tree() -> Diagram:
    d = Diagram(
        "safety_fault_tree_and_controls",
        "Safety Fault Tree 與控制措施圖",
        "誤辨識、非法走子、引擎 timeout、手臂失效、使用者安全與資料遺失",
        "第二章安全文獻、第三章、第四章",
        "用風險樹方式說明高齡互動場域的安全設計。",
    )
    d.box("top", 760, 180, 400, 110, "Top Event\n不安全或不可接受的互動", PALETTE["red_light"], PALETTE["red"], font_size=24)
    branches = [
        ("b1", 90, 390, "Vision fault\n低信心 / 遮擋 / 反光\n錯誤 FEN", PALETTE["teal_light"], PALETTE["teal"]),
        ("b2", 460, 390, "Logic fault\n非法棋步\nFEN validation fail\ncontract mismatch", PALETTE["violet_light"], PALETTE["violet"]),
        ("b3", 830, 390, "Engine fault\nmissing executable\nNNUE mismatch\ntimeout", PALETTE["amber_light"], PALETTE["amber"]),
        ("b4", 1200, 390, "Robot fault\n碰撞 / 越界\n抓取失敗\nqueue stuck", PALETTE["red_light"], PALETTE["red"]),
        ("b5", 1570, 390, "Data fault\nqueue full\nDB write failed\ntrace lost", "#F8FAFC", "#475569"),
    ]
    for id_, x, y, label, fill, stroke in branches:
        d.box(id_, x, y, 290, 130, label, fill, stroke, font_size=19)
        d.arrow("top", id_, "cause", start_side="bottom", end_side="top")
    controls = [
        ("c1", 90, 660, "TemporalValidator\nconfidence summary\nmanual sync / fallback", PALETTE["green_light"], PALETTE["green"]),
        ("c2", 460, 660, "Pydantic schemas\nKNOWN_EVENTS\nStateManager validate", PALETTE["green_light"], PALETTE["green"]),
        ("c3", 830, 660, "startup probe\ncompatibility_report\nbackoff diagnostics", PALETTE["green_light"], PALETTE["green"]),
        ("c4", 1200, 660, "E-Stop chain\nRobotFacade gate\nmanual reset", PALETTE["green_light"], PALETTE["green"]),
        ("c5", 1570, 660, "bounded queue\nbatch persistence\nreplay/export checks", PALETTE["green_light"], PALETTE["green"]),
    ]
    for id_, x, y, label, fill, stroke in controls:
        d.box(id_, x, y, 290, 130, label, fill, stroke, font_size=19)
        d.arrow("b" + id_[1:], id_, "mitigation", start_side="bottom", end_side="top", color=PALETTE["green"])
    d.box("out", 760, 875, 400, 100, "Residual risk recorded\nDiagnostics + SQLite + report limitation", "#FFFFFF", "#475569", font_size=21)
    for id_, *_ in controls:
        d.arrow(id_, "out", "", dashed=True)
    return d


def test_coverage_matrix() -> Diagram:
    d = Diagram(
        "test_coverage_traceability_matrix",
        "測試覆蓋與需求追蹤矩陣圖",
        "研究需求 -> 系統模組 -> 測試類型 -> 證據輸出",
        "第四章初步測試、第五章規劃",
        "比一般測試流程圖更適合說明驗證完整性。",
    )
    cols = [
        ("req", 70, "研究需求"),
        ("module", 440, "系統模組"),
        ("test", 810, "測試類型"),
        ("evidence", 1180, "輸出證據"),
        ("chapter", 1550, "報告位置"),
    ]
    for id_, x, title in cols:
        d.box(id_, x, 165, 300, 70, title, "#FFFFFF", "#94A3B8", font_size=22, shadow=False)
    rows = [
        ("高齡互動可用性", "Dashboard / UI state", "frontend Jest\nmanual UI check", "SUS / TAM\n訪談", "第 1/3/4/5 章"),
        ("即時棋盤辨識", "VisionSystem\nYOLO/SAHI/FEN", "vision unit\nsimulation", "FPS / confidence\n錯誤案例", "第 3/4 章"),
        ("AI 對弈決策", "EngineWorker\nEngineService", "unit + integration\nengine status", "bestmove / depth\nscore / PV", "第 3/4 章"),
        ("實體安全落子", "RobotFacade\nE-Stop", "unit + smoke\nmanual safety", "ROBOT.STATUS\nE-Stop log", "第 3/4 章"),
        ("資料可追蹤", "EventBus\nPersistenceWorker", "integration\nDB checks", "SQLite events\nReplay / Excel", "第 4/5 章"),
    ]
    y0 = 300
    for i, row in enumerate(rows):
        y = y0 + i * 130
        fill = "#F8FAFC" if i % 2 else "#EFF6FF"
        ids = []
        for (col_id, x, _), text in zip(cols, row):
            bid = f"{col_id}{i}"
            ids.append(bid)
            d.box(bid, x, y, 300, 95, text, fill, "#CBD5E1", font_size=18, shadow=False)
        for a, b in zip(ids, ids[1:]):
            d.arrow(a, b, "", width=2)
    d.note(80, 980, "這張圖適合放在第四章測試規劃結尾，讓評審看到每一個研究需求都有系統模組與驗證資料對應。")
    return d


BUILDERS = [
    advanced_dfd,
    component_dependency,
    detailed_sequence,
    state_machine,
    coordinate_transform,
    contract_validation,
    deployment_network,
    erd_traceability,
    safety_fault_tree,
    test_coverage_matrix,
]


def build_contact_sheet(png_paths: list[Path]) -> None:
    thumb_w, thumb_h = 430, 242
    cols = 2
    rows = math.ceil(len(png_paths) / cols)
    sheet = Image.new("RGB", (cols * 500, rows * 330 + 85), hex_to_rgb(PALETTE["bg"]))
    draw = ImageDraw.Draw(sheet)
    draw.text((32, 24), "Advanced Report Diagrams", fill=hex_to_rgb(PALETTE["ink"]), font=font(34, True))
    for idx, path in enumerate(png_paths):
        img = Image.open(path).convert("RGB")
        img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col = idx % cols
        row = idx // cols
        x = col * 500 + 35
        y = row * 330 + 90
        draw.rounded_rectangle((x - 10, y - 10, x + thumb_w + 10, y + thumb_h + 50), radius=18, fill=(255, 255, 255), outline=(203, 213, 225))
        sheet.paste(img, (x, y))
        draw.text((x, y + thumb_h + 14), path.stem, fill=hex_to_rgb(PALETTE["ink"]), font=font(18))
    sheet.save(CONTACT_SHEET)


def write_index(diagrams: list[Diagram]) -> None:
    lines = [
        "# Advanced Report Diagrams",
        "",
        "這一組是較複雜的報告圖，適合放在第三章系統設計、第四章系統實作與初步測試規劃。SVG 可匯入 Canva，PNG 可直接插入 Word。",
        "",
        "| 編號 | 圖名 | 建議章節 | 用途 | PNG | SVG |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    manifest = []
    for idx, d in enumerate(diagrams, start=1):
        png = PNG_DIR / f"A{idx:02d}_{d.slug}.png"
        svg = SVG_DIR / f"A{idx:02d}_{d.slug}.svg"
        lines.append(f"| A{idx:02d} | {d.title} | {d.chapter} | {d.description} | `{png}` | `{svg}` |")
        manifest.append(
            {
                "number": f"A{idx:02d}",
                "title": d.title,
                "slug": d.slug,
                "chapter": d.chapter,
                "description": d.description,
                "png": str(png),
                "svg": str(svg),
            }
        )
    (OUT_ROOT / "advanced_diagram_index.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT_ROOT / "advanced_diagram_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    for folder, suffix in ((PNG_DIR, ".png"), (SVG_DIR, ".svg")):
        for old in folder.glob(f"*{suffix}"):
            old.unlink()
    diagrams = [builder() for builder in BUILDERS]
    png_paths: list[Path] = []
    for idx, d in enumerate(diagrams, start=1):
        png = PNG_DIR / f"A{idx:02d}_{d.slug}.png"
        svg = SVG_DIR / f"A{idx:02d}_{d.slug}.svg"
        d.render_png(png)
        d.render_svg(svg)
        png_paths.append(png)
    build_contact_sheet(png_paths)
    write_index(diagrams)
    print(json.dumps({"diagrams": len(diagrams), "png_dir": str(PNG_DIR), "svg_dir": str(SVG_DIR), "contact_sheet": str(CONTACT_SHEET)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
