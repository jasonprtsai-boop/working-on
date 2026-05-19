from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from generate_report_diagrams import Diagram, PALETTE, font, hex_to_rgb


OUT_ROOT = Path("report_diagrams_verified")
PNG_DIR = OUT_ROOT / "png"
SVG_DIR = OUT_ROOT / "svg"
CONTACT_SHEET = OUT_ROOT / "verified_contact_sheet.png"
PACKAGE = OUT_ROOT / "verified_report_diagrams_package.zip"


def add_chain(
    d: Diagram,
    specs: list[tuple[str, str, str, str]],
    *,
    y: int,
    x0: int = 70,
    gap: int = 24,
    h: int = 160,
    font_size: int = 22,
) -> None:
    w = int((d.w - x0 * 2 - gap * (len(specs) - 1)) / len(specs))
    prev: str | None = None
    for idx, (box_id, label, fill, stroke) in enumerate(specs):
        x = x0 + idx * (w + gap)
        d.box(box_id, x, y, w, h, label, fill, stroke, font_size=font_size)
        if prev:
            d.arrow(prev, box_id, start_side="right", end_side="left")
        prev = box_id


def research_process() -> Diagram:
    d = Diagram(
        "research_process_verified",
        "研究流程圖",
        "文獻整理與需求定義 -> 系統建置 -> 初步測試規劃 -> 資料分析與修正",
        "第一章、第三章",
        "對齊第一章 1.4 與第三章 3.1.2；取代原本較舊的研究流程圖。",
    )
    add_chain(
        d,
        [
            ("s1", "1 文獻整理\n高齡陪伴\n棋類活動\n安全規範", PALETTE["amber_light"], PALETTE["amber"]),
            ("s2", "2 需求定義\n互動目標\n安全邊界\n評估指標", PALETTE["green_light"], PALETTE["green"]),
            ("s3", "3 系統架構設計\n感知 / 決策\n執行 / 回饋\n事件架構", PALETTE["blue_light"], PALETTE["blue"]),
            ("s4", "4 影像資料建置\n棋盤拍攝\n資料標註\nYOLOv8 + SAHI", PALETTE["teal_light"], PALETTE["teal"]),
            ("s5", "5 系統模組整合\nVision\nPikafish\nRobotFacade\nDashboard", PALETTE["violet_light"], PALETTE["violet"]),
            ("s6", "6 初步測試規劃\n功能驗證\n問卷訪談\n系統修正", PALETTE["red_light"], PALETTE["red"]),
        ],
        y=300,
        x0=50,
        gap=20,
        h=230,
        font_size=23,
    )
    d.group(225, 675, 1470, 230, "回饋修正循環", "#FFFFFF", "#CBD5E1")
    d.box("f1", 305, 735, 315, 110, "辨識誤差\n光線 / 遮擋 / 反光", "#F8FAFC", "#475569", font_size=21)
    d.box("f2", 800, 735, 315, 110, "互動問題\n難度 / UI / 安全感", "#F8FAFC", "#475569", font_size=21)
    d.box("f3", 1295, 735, 315, 110, "系統修正\n參數調整 / 流程改善", "#F8FAFC", "#475569", font_size=21)
    d.arrow("f1", "f2")
    d.arrow("f2", "f3")
    d.arrow("f3", "s3", "回到設計", dashed=True, points=[(1295, 735), (1230, 635), (845, 635), (845, 530)])
    d.note(70, 950, "校準：目前第四章不寫正式實驗結果，本圖以「初步測試規劃」與後續修正為主。")
    return d


def board_to_ai_robot_flow() -> Diagram:
    d = Diagram(
        "board_to_ai_robot_flow_verified",
        "實體棋盤狀態轉換與 AI 落子流程圖",
        "攝影機 -> OpenCV / YOLOv8 / SAHI -> FEN -> Pikafish -> RobotFacade -> 使用者回饋",
        "第二章、第三章",
        "對齊第二章圖 2-1 與第三章 3.2.1；修正圖號與正式流程描述。",
    )
    add_chain(
        d,
        [
            ("b1", "攝影機\n擷取棋盤影像", PALETTE["teal_light"], PALETTE["teal"]),
            ("b2", "OpenCV\n影像前處理\n棋盤校正", "#E0F2FE", "#0284C7"),
            ("b3", "YOLOv8 / SAHI\n棋子偵測\n小目標輔助", PALETTE["violet_light"], PALETTE["violet"]),
            ("b4", "座標映射\n9 x 10 棋盤\n格位判斷", PALETTE["green_light"], PALETTE["green"]),
            ("b5", "FEN Generator\n產生棋局格式\n供引擎分析", PALETTE["red_light"], PALETTE["red"]),
            ("b6", "Pikafish\n局勢分析\n產生走法", PALETTE["amber_light"], PALETTE["amber"]),
            ("b7", "RobotFacade\n落子流程\n狀態回報", PALETTE["blue_light"], PALETTE["blue"]),
        ],
        y=310,
        x0=44,
        gap=16,
        h=175,
        font_size=21,
    )
    d.group(170, 650, 1580, 205, "正式流程與輔助流程區分", "#FFFFFF", "#CBD5E1")
    d.box("note1", 245, 720, 400, 90, "正式流程核心\n校正、偵測、FEN、引擎、落子", PALETTE["green_light"], PALETTE["green"], font_size=20)
    d.box("note2", 760, 720, 400, 90, "ROI 定位\n效能最佳化與比較模組\n不是必要主流程", PALETTE["amber_light"], PALETTE["amber"], font_size=20)
    d.box("note3", 1275, 720, 400, 90, "Dashboard\n顯示棋盤、FEN、AI 分析\n與安全狀態", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.arrow("b3", "note2", "輔助比較", dashed=True)
    d.arrow("b7", "note3", "即時回饋")
    d.note(72, 940, "校準：本圖不宣稱臨床療效，只呈現系統可行性、操作回饋與安全觀察所需資料流。")
    return d


def system_architecture() -> Diagram:
    d = Diagram(
        "system_architecture_verified",
        "系統整體實作架構圖",
        "Flask / Socket.IO / EventBus / StateManager / Workers / Vision / Engine / Robot / Dashboard",
        "第四章 4.2",
        "對齊第四章 4.2 系統整體架構與 4.2.2 後端分層架構。",
    )
    d.group(55, 165, 360, 780, "使用者與介面", "#FFFFFF", "#CBD5E1")
    d.group(500, 165, 880, 780, "後端事件驅動核心", "#FFFFFF", "#CBD5E1")
    d.group(1465, 165, 400, 780, "硬體與資料輸出", "#FFFFFF", "#CBD5E1")

    d.box("ui", 95, 245, 280, 130, "Frontend\n玩家模式 / Console\nDashboard", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("socketclient", 95, 480, 280, 120, "Socket.IO client\nSYSTEM_STATE_UPDATE", "#E0F2FE", "#0284C7", font_size=20)
    d.box("browser", 95, 705, 280, 120, "Browser DOM\n棋盤 / AI / Safety\n即時畫面", PALETTE["teal_light"], PALETTE["teal"], font_size=20)

    d.box("api", 545, 240, 300, 120, "Interfaces\nREST API\nWebSocket Handler", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("app", 920, 240, 300, 120, "Application\nServices\nUse Cases\nBootstrap", PALETTE["green_light"], PALETTE["green"], font_size=21)
    d.box("event", 545, 485, 300, 135, "EventBus\nBaseEvent\ntrace_id / payload", PALETTE["violet_light"], PALETTE["violet"], font_size=21)
    d.box("state", 920, 485, 300, 135, "StateManager\nReducers\nSystemState\nFEN validation", PALETTE["teal_light"], PALETTE["teal"], font_size=20)
    d.box("runtime", 730, 725, 310, 125, "Runtime Workers\nCamera / Vision\nEngine / Persistence\nMonitoring", PALETTE["amber_light"], PALETTE["amber"], font_size=20)

    d.box("vision", 1510, 235, 300, 115, "Vision\nOpenCV / YOLOv8\nSAHI / FEN", PALETTE["teal_light"], PALETTE["teal"], font_size=20)
    d.box("engine", 1510, 420, 300, 115, "Pikafish Engine\nUCI / NNUE\nDepth / MultiPV", PALETTE["amber_light"], PALETTE["amber"], font_size=20)
    d.box("robot", 1510, 605, 300, 115, "TM5-700\nRobotFacade\nModbus / FakeRobot", PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.box("data", 1510, 790, 300, 115, "SQLite / Replay\nExcel / CSV\nlogs / metrics", PALETTE["green_light"], PALETTE["green"], font_size=20)

    d.arrow("ui", "api")
    d.arrow("api", "app")
    d.arrow("app", "event")
    d.arrow("event", "state")
    d.arrow("state", "event", dashed=True, points=[(920, 552), (870, 552), (845, 552)])
    d.arrow("state", "socketclient", points=[(920, 552), (420, 552), (375, 540)])
    d.arrow("socketclient", "browser")
    d.arrow("runtime", "vision")
    d.arrow("runtime", "engine")
    d.arrow("runtime", "robot")
    d.arrow("event", "data")
    d.note(78, 968, "校準：Robot/TM5-700 目前以 RobotFacade 與控制流程為主，TMflow 實機點位教導仍屬後續整合。")
    return d


def event_state_sync() -> Diagram:
    d = Diagram(
        "event_state_sync_verified",
        "EventBus 與狀態同步流程圖",
        "BaseEvent -> EventBus -> StateManager -> Reducer -> SYSTEM_STATE_UPDATE",
        "第三章 3.2.5、第四章 4.3",
        "對齊事件驅動與單一可信狀態來源 SSOT 的文案。",
    )
    d.group(80, 175, 370, 760, "事件來源", "#FFFFFF", "#CBD5E1")
    d.group(540, 175, 845, 760, "狀態更新核心", "#FFFFFF", "#CBD5E1")
    d.group(1475, 175, 355, 760, "訂閱與輸出", "#FFFFFF", "#CBD5E1")

    sources = [
        ("api", "REST API\nmove / reset / estop", 245),
        ("sock", "Socket handlers\nplayer_move / action", 405),
        ("vision", "VisionService\nVISION_MOVE_DETECTED", 565),
        ("engine", "EngineWorker\nENGINE_ANALYSIS\nCOMPLETED", 725),
    ]
    for box_id, label, y in sources:
        d.box(box_id, 120, y, 300, 105, label, PALETTE["blue_light"], PALETTE["blue"], font_size=19)

    d.box("base", 595, 290, 260, 125, "BaseEvent\nid / type\ntrace_id / payload", PALETTE["amber_light"], PALETTE["amber"], font_size=21)
    d.box("bus", 910, 290, 300, 125, "EventBus.publish\nspecific subscribers\nglobal subscribers", PALETTE["violet_light"], PALETTE["violet"], font_size=21)
    d.box("registry", 610, 555, 300, 130, "ReducerRegistry\nMove / Engine\nRobot / System", PALETTE["green_light"], PALETTE["green"], font_size=21)
    d.box("manager", 960, 555, 320, 130, "StateManager\nvalidate FEN\ncommit SystemState", PALETTE["teal_light"], PALETTE["teal"], font_size=21)

    d.box("front", 1510, 285, 280, 115, "Socket forwarder\nSYSTEM_STATE_UPDATE", "#E0F2FE", "#0284C7", font_size=20)
    d.box("persist", 1510, 535, 280, 115, "PersistenceWorker\nqueue -> SQLite", "#F8FAFC", "#475569", font_size=20)
    d.box("toast", 1510, 735, 280, 105, "Diagnostics / UI_TOAST\n錯誤可視化", PALETTE["red_light"], PALETTE["red"], font_size=20)

    for box_id, _, _ in sources:
        d.arrow(box_id, "base")
    d.arrow("base", "bus")
    d.arrow("bus", "registry")
    d.arrow("registry", "manager")
    d.arrow("manager", "bus", dashed=True, points=[(1120, 555), (1120, 500), (1060, 500), (1060, 415)])
    d.arrow("bus", "front")
    d.arrow("bus", "persist")
    d.arrow("bus", "toast")
    d.note(72, 960, "校準：Dashboard 顯示的 FEN、Pikafish 分析的 FEN 與 RobotFacade 執行 move 必須對應同一狀態。")
    return d


def vision_fen_pipeline() -> Diagram:
    d = Diagram(
        "vision_fen_pipeline_verified",
        "Vision Pipeline 與 FEN 轉換實作圖",
        "CameraManager -> OpenCV preprocess -> YOLOv8 / SAHI -> BoardMapper -> FEN Generator",
        "第三章 3.2.2、第四章 4.4",
        "對齊影像辨識主流程，並明確標示 ROI 為輔助最佳化。",
    )
    add_chain(
        d,
        [
            ("v1", "CameraManager\nFrameBuffer\nMJPEG Stream", PALETTE["teal_light"], PALETTE["teal"]),
            ("v2", "OpenCV 前處理\nDenoise\nCLAHE\nSharpening", "#E0F2FE", "#0284C7"),
            ("v3", "Perspective\n四角點\nHomography\n俯視棋盤", PALETTE["blue_light"], PALETTE["blue"]),
            ("v4", "Detector\nYOLOv8 .pt\nSAHI 切片\nGrid fallback", PALETTE["violet_light"], PALETTE["violet"]),
            ("v5", "BoardMapper\nbbox center\n9 x 10 格位\n棋子代碼", PALETTE["green_light"], PALETTE["green"]),
            ("v6", "FENGenerator\nboard_state\nFEN / UCCI\nfen_valid", PALETTE["red_light"], PALETTE["red"]),
        ],
        y=275,
        x0=52,
        gap=22,
        h=195,
        font_size=20,
    )
    d.group(170, 640, 1580, 235, "輸出與驗證", "#FFFFFF", "#CBD5E1")
    d.box("frame", 260, 715, 320, 105, "VISION.FRAME_PROCESSED\nFPS / latency / detections", "#E0F2FE", "#0284C7", font_size=20)
    d.box("move", 800, 715, 320, 105, "VISION_MOVE_DETECTED\n穩定 FEN 更新棋局", PALETTE["green_light"], PALETTE["green"], font_size=20)
    d.box("check", 1340, 715, 320, 105, "人工標記盤面比對\nFEN 正確率\n錯誤來源回溯", PALETTE["amber_light"], PALETTE["amber"], font_size=20)
    d.arrow("v4", "frame", "每幀診斷")
    d.arrow("v6", "move", "stable FEN")
    d.arrow("move", "check", "測試比對")
    d.box("roi", 775, 520, 370, 85, "ROIOptimizer：變動區域偵測\n用於降低重複推論，非正式流程必要條件", "#FFFFFF", "#475569", font_size=18, shadow=False)
    d.arrow("v2", "roi", "輔助", dashed=True)
    d.arrow("roi", "v4", "ROI + YOLO/SAHI", dashed=True)
    return d


def engine_difficulty() -> Diagram:
    d = Diagram(
        "pikafish_difficulty_verified",
        "Pikafish 引擎分析與難度設定圖",
        "FEN -> EngineWorker -> EngineService -> Pikafish UCI -> bestmove / MultiPV / score",
        "第三章 3.2.3、第四章 4.5",
        "對齊 AI 難度設定文案：Depth 為主，Elo 僅作延伸校準參考。",
    )
    d.box("fen", 100, 300, 270, 130, "StateStore\ncurrent FEN\ncurrent_turn", PALETTE["green_light"], PALETTE["green"], font_size=22)
    d.box("worker", 455, 300, 310, 130, "EnginePollingWorker\nFEN 變更 0.2s\nidle 2.0s", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("service", 860, 280, 335, 170, "EngineService\nprobe NNUE\nstart process\ncompute(fen, depth)", PALETTE["amber_light"], PALETTE["amber"], font_size=21)
    d.box("uci", 1290, 280, 285, 170, "Pikafish UCI\nposition fen\ngo depth\nbestmove / info", PALETTE["red_light"], PALETTE["red"], font_size=21)
    d.box("parser", 900, 610, 300, 125, "EngineParser\nscore / pv\nmulti_pv", PALETTE["violet_light"], PALETTE["violet"], font_size=22)
    d.box("event", 500, 610, 315, 125, "ENGINE_ANALYSIS\nCOMPLETED\nbest_move / score / depth", "#E0F2FE", "#0284C7", font_size=18)
    d.box("ui", 1290, 610, 285, 125, "Dashboard\nAI 分析結果\nPV / MultiPV", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.box("robot", 100, 610, 270, 125, "Workflow\nAUTO_EXECUTE_ROBOT\n觸發手臂", PALETTE["teal_light"], PALETTE["teal"], font_size=20)
    d.group(1610, 210, 250, 610, "難度設定", "#FFFFFF", "#CBD5E1")
    d.note(1635, 290, "主要控制")
    d.note(1635, 335, "Depth")
    d.note(1635, 385, "Thinking Time")
    d.note(1635, 455, "輔助控制")
    d.note(1635, 500, "Skill Level")
    d.note(1635, 550, "MultiPV")
    d.note(1635, 640, "延伸校準")
    d.note(1635, 685, "Elo 僅作參考")
    d.arrow("fen", "worker")
    d.arrow("worker", "service")
    d.arrow("service", "uci")
    d.arrow("uci", "service", points=[(1432, 450), (1432, 525), (1028, 525), (1028, 450)])
    d.arrow("service", "parser")
    d.arrow("parser", "event")
    d.arrow("event", "ui")
    d.arrow("event", "robot")
    d.note(80, 960, "校準：AI 難度不以最高棋力為目標，而是配合使用者能力、等待時間與互動一致性。")
    return d


def robot_tmflow_safety() -> Diagram:
    d = Diagram(
        "robot_tmflow_safety_verified",
        "RobotFacade 與 TMflow 後續整合流程圖",
        "AI move -> RobotFacade -> safety gate -> board pose -> TMflow / RobotService -> status feedback",
        "第三章 3.2.4、第四章 4.6",
        "對齊目前實作：RobotFacade 已建立；TMflow 屬後續點位教導與實機整合規劃。",
    )
    add_chain(
        d,
        [
            ("r1", "AI move\n或人工命令", PALETTE["blue_light"], PALETTE["blue"]),
            ("r2", "WorkflowCoordinator\n判斷是否執行\n回合與模式檢查", "#E0F2FE", "#0284C7"),
            ("r3", "RobotFacade\n統一入口\n真機 / 模擬", PALETTE["teal_light"], PALETTE["teal"]),
            ("r4", "Safety Gate\nE-Stop\nSafe Mode\nCamera Ready", PALETTE["red_light"], PALETTE["red"]),
            ("r5", "座標映射\n棋盤格位\nrobot pose\n安全高度", PALETTE["amber_light"], PALETTE["amber"]),
            ("r6", "TMflow 後續整合\n點位教導\n低速 / 工作區域\n安全停止", PALETTE["violet_light"], PALETTE["violet"]),
        ],
        y=270,
        x0=55,
        gap=22,
        h=210,
        font_size=20,
    )
    d.group(230, 665, 1460, 225, "回饋與例外處理", "#FFFFFF", "#CBD5E1")
    d.box("status", 330, 735, 320, 105, "ROBOT.STATUS_UPDATED\nconnected / busy / queue\nposition / error", "#F8FAFC", "#475569", font_size=19)
    d.box("fail", 810, 735, 320, 105, "停止條件\nFEN 不合法 / E-Stop\n手臂未就緒 / 使用者過近", PALETTE["red_light"], PALETTE["red"], font_size=18)
    d.box("dash", 1290, 735, 320, 105, "Dashboard\nRobot / Safety\n清楚顯示狀態", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.arrow("r6", "status")
    d.arrow("r4", "fail", "blocked", dashed=True)
    d.arrow("status", "dash")
    d.arrow("fail", "dash", "警示")
    d.note(70, 960, "校準：本圖避免寫成已完成實機 TMflow 控制，僅呈現後續整合方法與安全檢查。")
    return d


def safety_recovery() -> Diagram:
    d = Diagram(
        "safety_recovery_verified",
        "E-Stop 安全控制與人工復原流程圖",
        "觸發 -> 清佇列 -> 停止手臂 -> 狀態錯誤 -> UI 鎖定 -> 人工 reset",
        "第二章安全文獻、第三章、第四章 4.6.4",
        "對齊安全控制文案，凸顯近距離人機互動的保守停止策略。",
    )
    d.group(70, 175, 420, 750, "觸發來源", "#FFFFFF", "#CBD5E1")
    d.group(560, 175, 800, 750, "E-Stop interlock chain", "#FFFFFF", "#CBD5E1")
    d.group(1430, 175, 420, 750, "輸出與復原", "#FFFFFF", "#CBD5E1")
    for box_id, label, y in [
        ("t1", "Frontend\nE-Stop button", 255),
        ("t2", "安全違規\n碰撞 / 越界\n使用者過近", 455),
        ("t3", "實體急停\n外部訊號", 675),
    ]:
        d.box(box_id, 125, y, 300, 110, label, PALETTE["red_light"], PALETTE["red"], font_size=21)
    chain = [
        ("c1", "EStop.trigger(reason)", 250),
        ("c2", "task_queue.clear()\nrobot_queue.clear()", 395),
        ("c3", "RobotFacade.emergency_stop()\n硬體停止", 540),
        ("c4", "state_store.dispatch\nSYSTEM_ERROR", 685),
    ]
    for box_id, label, y in chain:
        d.box(box_id, 715, y, 470, 95, label, "#FFF7ED", "#EA580C", font_size=21)
    for a, b in zip([x[0] for x in chain], [x[0] for x in chain][1:]):
        d.arrow(a, b, color=PALETTE["red"], start_side="bottom", end_side="top")
    for src in ["t1", "t2", "t3"]:
        d.arrow(src, "c1")
    d.box("o1", 1490, 285, 300, 110, "Socket.IO ui_lock\n前端不可操作", PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.box("o2", 1490, 505, 300, 110, "Dashboard overlay\nERROR / reason", "#E0F2FE", "#0284C7", font_size=20)
    d.box("o3", 1490, 725, 300, 110, "Manual reset\nSYSTEM_RESET\nRECOVERY_COMPLETED", PALETTE["green_light"], PALETTE["green"], font_size=19)
    d.arrow("c4", "o1")
    d.arrow("c4", "o2")
    d.arrow("o3", "c1", dashed=True, points=[(1490, 780), (1370, 780), (1370, 225), (950, 225), (950, 250)])
    return d


def dashboard_layout() -> Diagram:
    d = Diagram(
        "dashboard_layout_verified",
        "前端 Dashboard 功能配置圖",
        "首頁、玩家棋盤、Console、即時影像、YOLO/FEN、AI、Robot/Safety、Experiment、Export",
        "第四章 4.7",
        "依第四章前端功能文案重排；此圖是配置示意，不取代實際系統截圖。",
    )
    d.group(65, 170, 1790, 760, "Dashboard 功能區域", "#FFFFFF", "#CBD5E1")
    d.box("nav", 120, 225, 1680, 80, "模式切換：首頁 / 玩家模式 / Console 模式 / 匯出與日誌", PALETTE["blue_light"], PALETTE["blue"], font_size=24)
    d.box("board", 120, 350, 430, 250, "玩家棋盤顯示區\n棋盤與棋子位置\n目前回合\n同步狀態", "#E0F2FE", "#0284C7", font_size=22)
    d.box("console", 595, 350, 430, 250, "Console 棋盤監控區\n棋局狀態\n紅黑方計時\n局勢評估條", PALETTE["violet_light"], PALETTE["violet"], font_size=22)
    d.box("vision", 1070, 350, 350, 250, "即時影像區\nMJPEG stream\nYOLO bbox\nFPS / snapshot", PALETTE["teal_light"], PALETTE["teal"], font_size=21)
    d.box("side", 1465, 350, 335, 250, "側邊監控\nYOLO / FEN Monitor\nUCCI position\nconfidence / latency", PALETTE["green_light"], PALETTE["green"], font_size=20)
    d.box("ai", 120, 660, 390, 170, "AI 分析結果\nscore / depth\nbestmove / PV\nMultiPV", PALETTE["amber_light"], PALETTE["amber"], font_size=21)
    d.box("robot", 555, 660, 390, 170, "Robot / Safety\nBusy / Error / Queue\nE-Stop / Safe Mode\nCamera Ready", PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.box("experiment", 990, 660, 390, 170, "Experiment session\nParticipant ID\nSession start/end\nAI difficulty", "#F8FAFC", "#475569", font_size=20)
    d.box("export", 1425, 660, 375, 170, "資料匯出與日誌\nExcel / CSV\n系統事件\n錯誤紀錄", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.arrow("vision", "side")
    d.arrow("side", "ai", points=[(1465, 475), (970, 475), (970, 630), (315, 630), (315, 660)])
    d.arrow("ai", "robot")
    d.arrow("robot", "experiment")
    d.arrow("experiment", "export")
    d.note(95, 965, "校準：第四章 4.7 需要實作畫面時，仍建議另外截目前系統畫面；本圖用於說明功能區域與資料關係。")
    return d


def persistence_export() -> Diagram:
    d = Diagram(
        "persistence_replay_export_verified",
        "資料庫、Replay 與 Excel 匯出流程圖",
        "EventBus all events -> PersistenceWorker -> SQLite -> Replay / Excel / CSV / Diagnostics",
        "第四章 4.7.9、4.9.5",
        "對齊資料匯出、Replay 測試與研究資料追蹤文案。",
    )
    d.box("bus", 110, 280, 330, 145, "EventBus\nall BaseEvent\nsession_id / trace_id", PALETTE["violet_light"], PALETTE["violet"], font_size=22)
    d.box("worker", 560, 280, 330, 145, "PersistenceWorker\nqueue maxsize\nbatch flush", PALETTE["amber_light"], PALETTE["amber"], font_size=22)
    d.box("store", 1010, 280, 330, 145, "EventStore\nsave_events()\nWAL mode", PALETTE["teal_light"], PALETTE["teal"], font_size=22)
    d.box("db", 1460, 265, 330, 175, "SQLite app.db\nevents table\nindexes by session / type / trace", "#F8FAFC", "#475569", font_size=21)
    d.arrow("bus", "worker")
    d.arrow("worker", "store")
    d.arrow("store", "db")
    d.group(170, 615, 1580, 240, "資料用途", "#FFFFFF", "#CBD5E1")
    d.box("replay", 260, 685, 300, 105, "Replay routes\nstep / snapshot\n互動回放", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.box("export", 720, 685, 300, 105, "Export routes\nexcel_exporter.py\nExcel / CSV", PALETTE["green_light"], PALETTE["green"], font_size=20)
    d.box("diag", 1180, 685, 300, 105, "Diagnostics\nqueue drops\npersisted events", PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.arrow("db", "replay", points=[(1625, 440), (1625, 570), (410, 570), (410, 685)])
    d.arrow("db", "export", points=[(1625, 440), (1625, 590), (870, 590), (870, 685)])
    d.arrow("worker", "diag", dashed=True, points=[(725, 425), (725, 555), (1330, 555), (1330, 685)])
    d.note(80, 950, "校準：匯出資料包含棋局 FEN、玩家與 AI 棋步、YOLO 指標、機械手臂狀態與系統事件。")
    return d


def testing_quality_plan() -> Diagram:
    d = Diagram(
        "testing_quality_plan_verified",
        "初步測試與品質驗證規劃圖",
        "功能測試、整合測試、前端測試、模擬測試、效能資料與使用者評估規劃",
        "第四章 4.9、第五章規劃",
        "對齊目前尚未正式進入使用者實驗的章節定位。",
    )
    d.group(70, 170, 1780, 770, "測試與研究資料來源", "#FFFFFF", "#CBD5E1")
    boxes = [
        ("unit", 130, 260, "Unit Tests\nreducers / services\nFEN / rate limit", PALETTE["blue_light"], PALETTE["blue"]),
        ("integration", 510, 260, "Integration Tests\nHTTP / Socket\ncontract / runtime", "#E0F2FE", "#0284C7"),
        ("frontend", 890, 260, "Frontend Jest\nsocket client\nrenderers / state", PALETTE["violet_light"], PALETTE["violet"]),
        ("simulation", 1270, 260, "Simulation\nFakeVision\nFakeRobot\nfull game", PALETTE["teal_light"], PALETTE["teal"]),
        ("quality", 320, 570, "Quality Gate\nassets / DB\ncontract / release zip", PALETTE["amber_light"], PALETTE["amber"]),
        ("metrics", 700, 570, "System Metrics\nFPS / latency\nqueue / errors\nrobot success", PALETTE["green_light"], PALETTE["green"]),
        ("survey", 1080, 570, "User Evaluation\nSUS / TAM\n安全感 / 訪談", PALETTE["red_light"], PALETTE["red"]),
        ("analysis", 1460, 570, "Analysis\n描述統計\n問題分類\n系統修正", "#F8FAFC", "#475569"),
    ]
    for box_id, x, y, label, fill, stroke in boxes:
        d.box(box_id, x, y, 300, 145, label, fill, stroke, font_size=21)
    d.arrow("unit", "integration")
    d.arrow("integration", "frontend")
    d.arrow("frontend", "simulation")
    d.arrow("quality", "metrics")
    d.arrow("metrics", "survey")
    d.arrow("survey", "analysis")
    d.arrow("simulation", "metrics", "runtime logs")
    d.arrow("analysis", "quality", "修正後再測", dashed=True, points=[(1460, 640), (260, 640), (260, 642), (320, 642)])
    d.note(120, 875, "校準：第四章使用本圖時，文字應寫「初步系統測試規劃」，不要寫成正式實驗結果。")
    return d


BUILDERS: list[Callable[[], Diagram]] = [
    research_process,
    board_to_ai_robot_flow,
    system_architecture,
    event_state_sync,
    vision_fen_pipeline,
    engine_difficulty,
    robot_tmflow_safety,
    safety_recovery,
    dashboard_layout,
    persistence_export,
    testing_quality_plan,
]


ALIGNMENT_ROWS = [
    (
        "01_research_process_verified",
        "第一章 1.4、第三章 3.1.2",
        "採用「文獻整理與需求定義、系統架構設計、影像資料建置與模型訓練、系統模組整合、使用者互動實驗規劃、資料分析與系統修正」。",
        "OK",
    ),
    (
        "02_board_to_ai_robot_flow_verified",
        "第二章圖 2-1、第三章 3.2.1",
        "修正舊圖圖號不一致問題；ROI 標為輔助最佳化，不列為正式流程必要步驟。",
        "OK",
    ),
    (
        "03_system_architecture_verified",
        "第四章 4.2",
        "對齊 Frontend、Interfaces、Application、EventBus、StateManager、Runtime、Vision、Engine、Robot、SQLite。",
        "OK",
    ),
    (
        "04_event_state_sync_verified",
        "第三章 3.2.5、第四章 4.3",
        "強調單一可信狀態來源、FEN 驗證、SYSTEM_STATE_UPDATE contract。",
        "OK",
    ),
    (
        "05_vision_fen_pipeline_verified",
        "第三章 3.2.2、第四章 4.4",
        "對齊 CameraManager、OpenCV、YOLOv8 .pt、SAHI、BoardMapper、FENGenerator；FEN 正確率以人工標記比對。",
        "OK",
    ),
    (
        "06_pikafish_difficulty_verified",
        "第三章 3.2.3、第四章 4.5",
        "Depth 作為主要控制，Skill Level、Thinking Time、MultiPV 為輔助；Elo 僅延伸校準參考。",
        "OK",
    ),
    (
        "07_robot_tmflow_safety_verified",
        "第三章 3.2.4、第四章 4.6",
        "RobotFacade 已是控制入口；TMflow 標成後續點位教導與實機整合規劃。",
        "OK",
    ),
    (
        "08_safety_recovery_verified",
        "第二章安全文獻、第三章、第四章 4.6.4",
        "對齊 E-Stop、Safe Mode、UI lock、manual reset 與保守停止策略。",
        "OK",
    ),
    (
        "09_dashboard_layout_verified",
        "第四章 4.7",
        "依首頁、玩家棋盤、Console、即時影像、YOLO/FEN Monitor、AI、Robot/Safety、Experiment、Export 重排。",
        "OK",
    ),
    (
        "10_persistence_replay_export_verified",
        "第四章 4.7.9、4.9.5",
        "對齊 SQLite EventStore、Replay、Excel/CSV、Diagnostics 與 session_id/trace_id。",
        "OK",
    ),
    (
        "11_testing_quality_plan_verified",
        "第四章 4.9、第五章規劃",
        "明確寫成初步測試與品質驗證規劃，不寫成正式使用者實驗結果。",
        "OK",
    ),
]


def build_contact_sheet(png_paths: list[Path]) -> None:
    thumb_w, thumb_h = 430, 242
    cols = 3
    rows = math.ceil(len(png_paths) / cols)
    sheet = Image.new("RGB", (cols * 500, rows * 330 + 90), hex_to_rgb(PALETTE["bg"]))
    draw = ImageDraw.Draw(sheet)
    draw.text((32, 24), "Verified Report Diagrams - 新版排版與文案校準", fill=hex_to_rgb(PALETTE["ink"]), font=font(30, True))
    for idx, path in enumerate(png_paths):
        img = Image.open(path).convert("RGB")
        img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col = idx % cols
        row = idx // cols
        x = col * 500 + 35
        y = row * 330 + 90
        draw.rounded_rectangle((x - 10, y - 10, x + thumb_w + 10, y + thumb_h + 52), radius=18, fill=(255, 255, 255), outline=(203, 213, 225))
        sheet.paste(img, (x, y))
        draw.text((x, y + thumb_h + 14), path.stem, fill=hex_to_rgb(PALETTE["ink"]), font=font(16))
    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(CONTACT_SHEET)


def write_index(diagrams: list[Diagram]) -> None:
    lines = [
        "# 新版報告圖包：排版與文案校準版",
        "",
        "這組圖依目前第一到第四章文案重繪，避免沿用舊圖中不一致的圖號、過度超前的實驗說法，或未完成整合的描述。",
        "",
        "| 編號 | 圖名 | 建議章節 | PNG | SVG | 用途 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    manifest = []
    for idx, diagram in enumerate(diagrams, start=1):
        stem = f"{idx:02d}_{diagram.slug}"
        png = PNG_DIR / f"{stem}.png"
        svg = SVG_DIR / f"{stem}.svg"
        lines.append(f"| {idx:02d} | {diagram.title} | {diagram.chapter} | `{png}` | `{svg}` | {diagram.description} |")
        manifest.append(
            {
                "number": idx,
                "slug": diagram.slug,
                "title": diagram.title,
                "subtitle": diagram.subtitle,
                "chapter": diagram.chapter,
                "description": diagram.description,
                "png": str(png),
                "svg": str(svg),
            }
        )
    (OUT_ROOT / "verified_diagram_index.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT_ROOT / "verified_diagram_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def write_alignment_report() -> None:
    lines = [
        "# 圖片內文與目前文案一致性檢查",
        "",
        "檢查原則：",
        "",
        "- 不把第四章寫成正式使用者實驗結果，目前定位為系統實作與初步測試規劃。",
        "- 不把 TMflow 寫成已完成實機整合，僅列為後續點位教導與實機安全參數整合。",
        "- 不把 ROI 寫成正式影像辨識主流程必要條件，僅列為效能最佳化與後續比較模組。",
        "- FEN 正確性以人工標記盤面與系統輸出比對，不直接宣稱已完全正確。",
        "- 第二章原內嵌圖的「圖 2-3」問題已在新版圖包中改為可用於「圖 2-1」的內容。",
        "",
        "| 圖檔 | 對應文案 | 校準內容 | 結論 |",
        "| --- | --- | --- | --- |",
    ]
    for row in ALIGNMENT_ROWS:
        lines.append(f"| `{row[0]}` | {row[1]} | {row[2]} | {row[3]} |")
    (OUT_ROOT / "content_alignment_report.md").write_text("\n".join(lines), encoding="utf-8")


def clean_outputs() -> None:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    for folder, suffix in ((PNG_DIR, ".png"), (SVG_DIR, ".svg")):
        for old in folder.glob(f"*{suffix}"):
            old.unlink()
    for old in [CONTACT_SHEET, PACKAGE, OUT_ROOT / "verified_diagram_index.md", OUT_ROOT / "verified_diagram_manifest.json", OUT_ROOT / "content_alignment_report.md"]:
        if old.exists():
            old.unlink()


def package_outputs() -> None:
    tmp_base = OUT_ROOT.parent / "_verified_report_diagrams_package_tmp"
    tmp_zip = tmp_base.with_suffix(".zip")
    if tmp_zip.exists():
        tmp_zip.unlink()
    if PACKAGE.exists():
        PACKAGE.unlink()
    shutil.make_archive(str(tmp_base), "zip", root_dir=OUT_ROOT, base_dir=".")
    tmp_zip.replace(PACKAGE)


def main() -> int:
    clean_outputs()
    diagrams = [builder() for builder in BUILDERS]
    png_paths: list[Path] = []
    for idx, diagram in enumerate(diagrams, start=1):
        stem = f"{idx:02d}_{diagram.slug}"
        png = PNG_DIR / f"{stem}.png"
        svg = SVG_DIR / f"{stem}.svg"
        diagram.render_png(png)
        diagram.render_svg(svg)
        png_paths.append(png)
    build_contact_sheet(png_paths)
    write_index(diagrams)
    write_alignment_report()
    package_outputs()
    print(
        json.dumps(
            {
                "diagrams": len(diagrams),
                "png_dir": str(PNG_DIR),
                "svg_dir": str(SVG_DIR),
                "index": str(OUT_ROOT / "verified_diagram_index.md"),
                "alignment_report": str(OUT_ROOT / "content_alignment_report.md"),
                "contact_sheet": str(CONTACT_SHEET),
                "package": str(PACKAGE),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
