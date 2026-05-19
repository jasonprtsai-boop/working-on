from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from generate_report_diagrams import Diagram, PALETTE, font, hex_to_rgb


OUT_ROOT = Path("report_diagrams")
PNG_DIR = OUT_ROOT / "function_sequence_cycle_zh_png"
SVG_DIR = OUT_ROOT / "function_sequence_cycle_zh_svg"
CONTACT_SHEET = OUT_ROOT / "function_sequence_cycle_zh_contact_sheet.png"


def function_map() -> Diagram:
    d = Diagram(
        "function_module_map_zh",
        "系統功能圖",
        "使用者功能、後端服務、AI 視覺、手臂與資料功能對應",
        "第三章、第四章",
        "把報告中的功能需求對應到實際程式模組。",
    )
    d.group(55, 145, 360, 830, "使用者可見功能", "#FFFFFF", "#CBD5E1")
    d.group(500, 145, 860, 830, "後端功能核心", "#FFFFFF", "#CBD5E1")
    d.group(1445, 145, 420, 830, "輸出與驗證", "#FFFFFF", "#CBD5E1")

    visible = [
        ("ui", 95, 225, "儀表板介面\n棋盤畫面 / AI 分析\n手臂狀態 / 診斷", PALETTE["blue_light"], PALETTE["blue"]),
        ("control", 95, 405, "控制功能\n登入 / 走子\n開始分析 / 重置", "#E0F2FE", "#0284C7"),
        ("stream", 95, 585, "即時影像\nMJPEG 串流\n邊界框 / FPS / 信心值", PALETTE["teal_light"], PALETTE["teal"]),
        ("safety", 95, 765, "安全功能\n緊急停止 E-Stop\n介面鎖定 / 人工復原", PALETTE["red_light"], PALETTE["red"]),
    ]
    for id_, x, y, label, fill, stroke in visible:
        d.box(id_, x, y, 280, 120, label, fill, stroke, font_size=20)

    core = [
        ("auth", 545, 215, "驗證與防護\nbackend/interfaces/api/auth_*.py\nJWT + 速率限制", "#F8FAFC", "#475569"),
        ("api", 890, 215, "REST / Socket 入口\ncontrol_routes.py\nsocket_handler.py", PALETTE["blue_light"], PALETTE["blue"]),
        ("state", 545, 410, "事件與狀態\nEventBus.publish()\nStateManager.dispatch()\nReducers", PALETTE["violet_light"], PALETTE["violet"]),
        ("vision", 890, 410, "視覺辨識功能\nvision_system.py\nVisionService\nYOLO/SAHI/FEN", PALETTE["teal_light"], PALETTE["teal"]),
        ("engine", 545, 605, "AI 引擎功能\nEngineWorker\nEngineService.compute()\nPikafish UCI", PALETTE["amber_light"], PALETTE["amber"]),
        ("robot", 890, 605, "機械手臂功能\nWorkflowCoordinator\nRobotFacade\nRobotService/FakeRobot", PALETTE["red_light"], PALETTE["red"]),
        ("runtime", 545, 800, "執行環境功能\nAsyncRuntime\n工作者 / 佇列\n監控", "#EDE9FE", PALETTE["violet"]),
        ("persist", 890, 800, "資料保存功能\nPersistenceWorker\nEventStore SQLite\n回放 / 匯出", PALETTE["green_light"], PALETTE["green"]),
    ]
    for id_, x, y, label, fill, stroke in core:
        d.box(id_, x, y, 310, 125, label, fill, stroke, font_size=19)

    outputs = [
        ("contract", 1500, 255, "前端同步\nSYSTEM_STATE_UPDATE\ncontract_schema.py", PALETTE["blue_light"], PALETTE["blue"]),
        ("report", 1500, 475, "研究資料\nSQLite / 回放\nExcel / CSV", PALETTE["green_light"], PALETTE["green"]),
        ("test", 1500, 695, "測試驗證\npytest / Jest\n品質門檻", PALETTE["amber_light"], PALETTE["amber"]),
    ]
    for id_, x, y, label, fill, stroke in outputs:
        d.box(id_, x, y, 310, 130, label, fill, stroke, font_size=20)

    d.arrow("ui", "api", "HTTP / Socket")
    d.arrow("control", "auth", "權杖 / 防護")
    d.arrow("control", "api", "控制指令")
    d.arrow("stream", "vision", "影像幀")
    d.arrow("safety", "robot", "停止閘門")
    d.arrow("api", "state", "BaseEvent")
    d.arrow("vision", "state", "視覺事件")
    d.arrow("state", "engine", "目前 FEN")
    d.arrow("engine", "robot", "bestmove")
    d.arrow("robot", "state", "手臂事件")
    d.arrow("runtime", "vision", "工作者循環")
    d.arrow("runtime", "engine", "輪詢")
    d.arrow("state", "contract", "STATE_UPDATE")
    d.arrow("persist", "report", "查詢 / 匯出")
    d.arrow("state", "persist", "所有事件")
    d.arrow("test", "api", "契約測試", dashed=True)
    return d


def code_sequence_player_move() -> Diagram:
    d = Diagram(
        "code_data_sequence_player_move_zh",
        "程式碼資料傳遞順序圖：使用者走子",
        "前端送出 -> socket_handler -> BaseEvent -> EventBus -> StateManager -> 前端更新",
        "第三章、第四章",
        "用實際檔名與函式名稱呈現資料如何在程式碼中傳遞。",
    )
    lanes = [
        ("fe", "前端入口\ncore/app.js", 70),
        ("sockc", "socket_client.js", 270),
        ("handler", "socket_handler.py\non_player_move()", 500),
        ("event", "BaseEvent.create()", 740),
        ("bus", "EventBus.publish()", 970),
        ("sm", "StateManager.dispatch()", 1200),
        ("fw", "socket_handler\n_forward_event()", 1440),
        ("render", "event_adapter.js\ncommit / 畫面更新", 1680),
    ]
    for id_, label, x in lanes:
        d.box(id_, x, 165, 170, 80, label, "#FFFFFF", "#94A3B8", font_size=17, shadow=False)
        d.arrow((x + 85, 260), (x + 85, 935), color="#94A3B8", dashed=True, width=2)

    messages = [
        (155, 335, 355, "送出 player_move 事件"),
        (355, 405, 585, "Socket.IO 事件資料"),
        (585, 475, 825, "SocketPlayerMove.model_validate()"),
        (825, 545, 1055, "GAME_PLAYER_MOVE 負載"),
        (1055, 615, 1285, "全域訂閱者派送"),
        (1285, 685, 1055, "MoveReducer -> 新狀態"),
        (1055, 755, 1525, "STATE_UPDATED"),
        (1525, 825, 1765, "SYSTEM_STATE_UPDATE {type:'STATE_UPDATE'}"),
        (1765, 895, 155, "DOM 更新：棋盤 / 歷史 / 介面",),
    ]
    for x1, y, x2, label in messages:
        d.arrow((x1, y), (x2, y), label, width=3)

    d.box("guard", 470, 285, 300, 90, "驗證路徑\n_require_admin()\n_payload_size_ok()\n_rate_limit_socket()", PALETTE["red_light"], PALETTE["red"], font_size=17)
    d.box("validate", 1120, 505, 300, 90, "狀態驗證\nReducerRegistry\nFENValidator\n無變更防護", PALETTE["green_light"], PALETTE["green"], font_size=17)
    d.note(75, 985, "重點：前端操作不是直接改棋盤，而是送入事件流；唯一狀態改變入口是 StateManager.dispatch()。")
    return d


def code_sequence_vision_engine_robot() -> Diagram:
    d = Diagram(
        "code_data_sequence_vision_engine_robot_zh",
        "程式碼資料傳遞順序圖：視覺到 AI 與手臂",
        "vision_system -> VisionService -> StateManager -> EngineWorker -> WorkflowCoordinator -> RobotFacade",
        "第三章、第四章",
        "呈現自動辨識、AI 分析與手臂執行的程式碼資料順序。",
    )
    lanes = [
        ("cam", "相機管理\nCameraManager\nframe_buffer", 60),
        ("visys", "vision_system.py\nInferenceWorker", 280),
        ("vsvc", "VisionService\non_board_detected()", 510),
        ("bus", "EventBus", 740),
        ("sm", "StateManager\nMoveReducer", 970),
        ("engw", "EngineWorker\nEngineService", 1200),
        ("wf", "WorkflowCoordinator\nRobotFacade", 1450),
        ("ui", "Socket/介面\nPersistence", 1700),
    ]
    for id_, label, x in lanes:
        d.box(id_, x, 165, 170, 82, label, "#FFFFFF", "#94A3B8", font_size=16, shadow=False)
        d.arrow((x + 85, 260), (x + 85, 940), color="#94A3B8", dashed=True, width=2)

    steps = [
        (145, 320, 365, "原始影像幀"),
        (365, 390, 595, "偵測結果 + 延遲"),
        (595, 460, 825, "VISION_BOARD_DETECTED"),
        (825, 530, 1055, "派送到 MoveReducer"),
        (1055, 600, 825, "STATE_UPDATED 含 FEN"),
        (1055, 670, 1285, "讀取目前棋局 FEN"),
        (1285, 740, 1535, "ENGINE_ANALYSIS_COMPLETED 最佳走法"),
        (1535, 810, 825, "ROBOT_MOVE_STARTED / STATUS"),
        (825, 880, 1785, "前端與 SQLite 接收事件"),
    ]
    for x1, y, x2, label in steps:
        d.arrow((x1, y), (x2, y), label, width=3)
    d.box("fen", 520, 610, 310, 95, "VisionService 輸出\nboard_state\nFEN / UCCI 指令\n信心值 / FPS", PALETTE["teal_light"], PALETTE["teal"], font_size=17)
    d.box("auto", 1330, 520, 330, 95, "分支\nAUTO_EXECUTE_ROBOT=false\n只顯示 AI 建議\n不執行手臂", PALETTE["amber_light"], PALETTE["amber"], font_size=17)
    d.box("stop", 1320, 890, 330, 80, "分支\nE-Stop 啟動 -> RobotFacade 拒絕", PALETTE["red_light"], PALETTE["red"], font_size=17)
    return d


def closed_loop_cycle() -> Diagram:
    d = Diagram(
        "closed_loop_interaction_cycle_zh",
        "智慧象棋閉環互動循環圖",
        "感知 -> 狀態同步 -> AI 決策 -> 手臂執行 -> 回饋 -> 紀錄 -> 修正",
        "第三章、第四章、第五章",
        "說明系統不是單次流程，而是持續閉環互動。",
    )
    center = (960, 545)
    nodes = [
        ("sense", 820, 170, "1 感知\n相機 / 視覺辨識\nYOLO/SAHI/FEN", PALETTE["teal_light"], PALETTE["teal"]),
        ("state", 1310, 315, "2 狀態同步\nEventBus\nStateManager\nSYSTEM_STATE_UPDATE", PALETTE["violet_light"], PALETTE["violet"]),
        ("think", 1310, 690, "3 AI 決策\nEngineWorker\nPikafish\n最佳走法", PALETTE["amber_light"], PALETTE["amber"]),
        ("act", 820, 835, "4 實體執行\nRobotFacade\n取放流程\n狀態回報", PALETTE["red_light"], PALETTE["red"]),
        ("feedback", 330, 690, "5 前端回饋\n儀表板\n疊圖顯示\n提示訊息", PALETTE["blue_light"], PALETTE["blue"]),
        ("persist", 330, 315, "6 資料紀錄\nSQLite\n回放\nExcel/CSV", PALETTE["green_light"], PALETTE["green"]),
    ]
    for id_, x, y, label, fill, stroke in nodes:
        d.box(id_, x, y, 300, 145, label, fill, stroke, font_size=21)
    order = ["sense", "state", "think", "act", "feedback", "persist", "sense"]
    for a, b in zip(order, order[1:]):
        d.arrow(a, b, "")
    d.box("core", 760, 470, 400, 140, "核心閉環\ntrace_id 串接\n事件驅動\n安全控制", "#FFFFFF", "#475569", font_size=25)
    d.arrow("core", "state", "狀態權威", dashed=True)
    d.arrow("core", "persist", "可追蹤性", dashed=True)
    d.box("safe", 760, 660, 400, 95, "例外循環\n低信心 / 逾時 / E-Stop\n-> 診斷 -> 人工復原", PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.arrow("safe", "feedback", "警示")
    d.arrow("safe", "persist", "紀錄")
    return d


def event_reducer_cycle() -> Diagram:
    d = Diagram(
        "event_reducer_state_cycle_zh",
        "EventBus / Reducer 狀態循環圖",
        "BaseEvent -> EventBus -> StateManager -> Reducer -> SystemState -> STATE_UPDATED -> 訂閱者",
        "第三章、第四章",
        "細化系統內部事件循環與狀態更新規則。",
    )
    nodes = [
        ("producer", 110, 245, "事件來源\nAPI / Socket\n視覺 / 引擎\n手臂 / 工作者", PALETTE["blue_light"], PALETTE["blue"]),
        ("event", 515, 245, "BaseEvent\n事件類型\n來源 / 負載\ntrace_id", PALETTE["amber_light"], PALETTE["amber"]),
        ("bus", 920, 245, "EventBus.publish()\n特定訂閱者\n全域訂閱者", PALETTE["violet_light"], PALETTE["violet"]),
        ("manager", 1325, 245, "StateManager.dispatch()\n鎖定\n無變更防護\n驗證", PALETTE["green_light"], PALETTE["green"]),
        ("registry", 1325, 600, "ReducerRegistry\nMoveReducer\nEngineReducer\nRobotReducer\nSystemReducer", "#F0FDF4", "#16A34A"),
        ("state", 920, 600, "新 SystemState\n不可變快照\n歷史上限 50", PALETTE["teal_light"], PALETTE["teal"]),
        ("sub", 515, 600, "訂閱者\nSocket 轉發\nPersistenceWorker\nTimelineTracer", "#F8FAFC", "#475569"),
        ("front", 110, 600, "輸出\n前端畫面更新\nSQLite 回放\n診斷資訊", PALETTE["blue_light"], PALETTE["blue"]),
    ]
    for id_, x, y, label, fill, stroke in nodes:
        d.box(id_, x, y, 300, 140, label, fill, stroke, font_size=20)
    order = ["producer", "event", "bus", "manager", "registry", "state", "sub", "front"]
    for a, b in zip(order, order[1:]):
        d.arrow(a, b)
    d.arrow("state", "bus", "發布 STATE_UPDATED", dashed=True, points=[(920, 670), (740, 670), (740, 425), (1070, 425), (1070, 385)])
    d.arrow("front", "producer", "新的操作 / 下一幀影像", dashed=True, points=[(260, 600), (260, 520), (260, 385)])
    d.note(85, 915, "內文可寫：這個循環保證所有模組透過事件改變狀態，避免前後端各自維護不一致棋局。")
    return d


def experiment_improvement_cycle() -> Diagram:
    d = Diagram(
        "experiment_improvement_cycle_zh",
        "系統測試與改善循環圖",
        "測試資料 -> 指標分析 -> 問題定位 -> 參數/程式修正 -> 再測試",
        "第四章初步測試、第五章規劃",
        "用於說明系統如何根據測試與研究資料持續改善。",
    )
    nodes = [
        ("test", 815, 165, "1 初步測試\n功能 / 整合\n視覺 / 手臂\n前端", PALETTE["blue_light"], PALETTE["blue"]),
        ("collect", 1280, 325, "2 資料蒐集\nSQLite 事件\n記錄 / 截圖\nSUS / TAM", PALETTE["green_light"], PALETTE["green"]),
        ("metric", 1280, 665, "3 指標分析\nFPS / 延遲\n信心值\n成功率", PALETTE["teal_light"], PALETTE["teal"]),
        ("diagnose", 815, 825, "4 問題定位\ntrace_id\n回放步驟\n錯誤類別", PALETTE["violet_light"], PALETTE["violet"]),
        ("fix", 350, 665, "5 修正策略\n閾值\n引擎深度\n介面 / 安全", PALETTE["amber_light"], PALETTE["amber"]),
        ("rerun", 350, 325, "6 再測試\n品質門檻\npytest / Jest\n人工執行", PALETTE["red_light"], PALETTE["red"]),
    ]
    for id_, x, y, label, fill, stroke in nodes:
        d.box(id_, x, y, 300, 140, label, fill, stroke, font_size=21)
    cycle = ["test", "collect", "metric", "diagnose", "fix", "rerun", "test"]
    for a, b in zip(cycle, cycle[1:]):
        d.arrow(a, b)
    d.box("center", 760, 480, 400, 140, "研究驗證核心\n可用性 + 系統穩定性\n安全性 + 可追蹤性", "#FFFFFF", "#475569", font_size=24)
    d.arrow("center", "metric", "指標")
    d.arrow("center", "diagnose", "證據")
    d.note(100, 950, "這張可放在第四章尾端：目前是初步測試規劃，後續第五章可用同一循環呈現正式實驗修正。")
    return d


BUILDERS = [
    function_map,
    code_sequence_player_move,
    code_sequence_vision_engine_robot,
    closed_loop_cycle,
    event_reducer_cycle,
    experiment_improvement_cycle,
]


def build_contact_sheet(png_paths: list[Path]) -> None:
    thumb_w, thumb_h = 430, 242
    cols = 2
    rows = math.ceil(len(png_paths) / cols)
    sheet = Image.new("RGB", (cols * 500, rows * 330 + 85), hex_to_rgb(PALETTE["bg"]))
    draw = ImageDraw.Draw(sheet)
    draw.text((32, 24), "功能圖 / 順序圖 / 循環圖（繁中標註版）", fill=hex_to_rgb(PALETTE["ink"]), font=font(32, True))
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
        "# 功能圖、程式碼資料傳遞順序圖與循環圖（繁中標註版）",
        "",
        "這批圖已將說明文字改為繁體中文；程式檔名、函式名稱、事件名稱與協定名稱保留原文，方便對照程式碼。SVG 可匯入 Canva 編輯；PNG 可直接插入 Word。",
        "",
        "| 編號 | 圖名 | 類型 | 建議章節 | PNG | SVG |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    manifest = []
    for idx, d in enumerate(diagrams, start=1):
        kind = "功能圖" if idx == 1 else "順序圖" if idx in (2, 3) else "循環圖"
        png = PNG_DIR / f"FSCZH{idx:02d}_{d.slug}.png"
        svg = SVG_DIR / f"FSCZH{idx:02d}_{d.slug}.svg"
        lines.append(f"| FSCZH{idx:02d} | {d.title} | {kind} | {d.chapter} | `{png}` | `{svg}` |")
        manifest.append(
            {
                "number": f"FSCZH{idx:02d}",
                "title": d.title,
                "kind": kind,
                "chapter": d.chapter,
                "description": d.description,
                "png": str(png),
                "svg": str(svg),
            }
        )
    (OUT_ROOT / "function_sequence_cycle_zh_index.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT_ROOT / "function_sequence_cycle_zh_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    for folder, suffix in ((PNG_DIR, ".png"), (SVG_DIR, ".svg")):
        for old in folder.glob(f"*{suffix}"):
            old.unlink()
    diagrams = [builder() for builder in BUILDERS]
    png_paths: list[Path] = []
    for idx, diagram in enumerate(diagrams, start=1):
        png = PNG_DIR / f"FSCZH{idx:02d}_{diagram.slug}.png"
        svg = SVG_DIR / f"FSCZH{idx:02d}_{diagram.slug}.svg"
        diagram.render_png(png)
        diagram.render_svg(svg)
        png_paths.append(png)
    build_contact_sheet(png_paths)
    write_index(diagrams)
    print(json.dumps({"diagrams": len(diagrams), "png_dir": str(PNG_DIR), "svg_dir": str(SVG_DIR), "contact_sheet": str(CONTACT_SHEET)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
