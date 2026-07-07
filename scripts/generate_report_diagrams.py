from __future__ import annotations

import json
import math
import textwrap
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont


OUT_ROOT = Path("report_diagrams")
SVG_DIR = OUT_ROOT / "svg"
PNG_DIR = OUT_ROOT / "png"
CONTACT_SHEET = OUT_ROOT / "contact_sheet.png"


PALETTE = {
    "ink": "#172033",
    "muted": "#64748B",
    "line": "#334155",
    "bg": "#F8FAFC",
    "white": "#FFFFFF",
    "blue": "#2563EB",
    "blue_light": "#DBEAFE",
    "teal": "#0F766E",
    "teal_light": "#CCFBF1",
    "green": "#16A34A",
    "green_light": "#DCFCE7",
    "amber": "#D97706",
    "amber_light": "#FEF3C7",
    "red": "#DC2626",
    "red_light": "#FEE2E2",
    "violet": "#7C3AED",
    "violet_light": "#EDE9FE",
    "slate_light": "#E2E8F0",
}


FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msjh.ttc"),
    Path(r"C:\Windows\Fonts\msjhbd.ttc"),
    Path(r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
]


def _font_path() -> str | None:
    for path in FONT_CANDIDATES:
        if path.exists():
            return str(path)
    return None


FONT_PATH = _font_path()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if FONT_PATH:
        # Microsoft JhengHei TTC includes regular/bold faces; index 0 is good enough for both.
        return ImageFont.truetype(FONT_PATH, size=size, index=0)
    return ImageFont.load_default()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def text_size(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=ft)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw in str(text).split("\n"):
        raw = raw.strip()
        if not raw:
            lines.append("")
            continue
        tokens: list[str] = []
        buf = ""
        for ch in raw:
            if ord(ch) < 128 and (ch.isalnum() or ch in ".:/_-"):
                buf += ch
            else:
                if buf:
                    tokens.append(buf)
                    buf = ""
                if ch.isspace():
                    tokens.append(" ")
                else:
                    tokens.append(ch)
        if buf:
            tokens.append(buf)

        current = ""
        for token in tokens:
            candidate = current + token
            if text_size(draw, candidate, ft)[0] <= max_width or not current:
                current = candidate
            else:
                lines.append(current.strip())
                current = token.strip()
        if current:
            lines.append(current.strip())
    return lines


def svg_wrap(text: str, max_chars: int = 17) -> list[str]:
    lines: list[str] = []
    for raw in str(text).split("\n"):
        raw = raw.strip()
        if not raw:
            lines.append("")
            continue
        if len(raw) <= max_chars:
            lines.append(raw)
        else:
            lines.extend(textwrap.wrap(raw, width=max_chars, break_long_words=True, replace_whitespace=False))
    return lines


@dataclass
class Box:
    id: str
    x: int
    y: int
    w: int
    h: int
    label: str
    fill: str = PALETTE["white"]
    stroke: str = PALETTE["line"]
    text: str = PALETTE["ink"]
    radius: int = 22
    font_size: int = 26
    stroke_width: int = 3
    shadow: bool = True


@dataclass
class Group:
    x: int
    y: int
    w: int
    h: int
    label: str
    fill: str = PALETTE["white"]
    stroke: str = PALETTE["slate_light"]


@dataclass
class Arrow:
    start: str | tuple[int, int]
    end: str | tuple[int, int]
    label: str = ""
    start_side: str | None = None
    end_side: str | None = None
    color: str = PALETTE["line"]
    width: int = 4
    dashed: bool = False
    points: list[tuple[int, int]] | None = None


@dataclass
class Diagram:
    slug: str
    title: str
    subtitle: str
    chapter: str
    description: str
    w: int = 1920
    h: int = 1080
    groups: list[Group] = field(default_factory=list)
    boxes: dict[str, Box] = field(default_factory=dict)
    arrows: list[Arrow] = field(default_factory=list)
    notes: list[tuple[int, int, str, str]] = field(default_factory=list)

    def group(self, x: int, y: int, w: int, h: int, label: str, fill: str = PALETTE["white"], stroke: str = PALETTE["slate_light"]):
        self.groups.append(Group(x, y, w, h, label, fill, stroke))

    def box(self, id: str, x: int, y: int, w: int, h: int, label: str, fill: str, stroke: str, **kwargs):
        self.boxes[id] = Box(id, x, y, w, h, label, fill, stroke, **kwargs)

    def arrow(self, start, end, label: str = "", start_side: str | None = None, end_side: str | None = None, **kwargs):
        self.arrows.append(Arrow(start, end, label, start_side, end_side, **kwargs))

    def note(self, x: int, y: int, text: str, color: str = PALETTE["muted"]):
        self.notes.append((x, y, text, color))

    def anchor(self, ref: str | tuple[int, int], side: str | None = None) -> tuple[int, int]:
        if isinstance(ref, tuple):
            return ref
        b = self.boxes[ref]
        side = side or "center"
        if side == "left":
            return b.x, b.y + b.h // 2
        if side == "right":
            return b.x + b.w, b.y + b.h // 2
        if side == "top":
            return b.x + b.w // 2, b.y
        if side == "bottom":
            return b.x + b.w // 2, b.y + b.h
        return b.x + b.w // 2, b.y + b.h // 2

    def auto_sides(self, a: Arrow) -> tuple[str, str]:
        if isinstance(a.start, tuple) or isinstance(a.end, tuple):
            return a.start_side or "center", a.end_side or "center"
        s = self.boxes[a.start]
        e = self.boxes[a.end]
        dx = (e.x + e.w / 2) - (s.x + s.w / 2)
        dy = (e.y + e.h / 2) - (s.y + s.h / 2)
        if abs(dx) > abs(dy):
            return ("right", "left") if dx > 0 else ("left", "right")
        return ("bottom", "top") if dy > 0 else ("top", "bottom")

    def render_png(self, path: Path) -> None:
        img = Image.new("RGB", (self.w, self.h), hex_to_rgb(PALETTE["bg"]))
        draw = ImageDraw.Draw(img)
        self._draw_header(draw)
        for g in self.groups:
            self._draw_group_png(draw, g)
        for a in self.arrows:
            self._draw_arrow_png(draw, a)
        for b in self.boxes.values():
            self._draw_box_png(draw, b)
        for x, y, txt, color in self.notes:
            ft = font(22)
            draw.text((x, y), txt, fill=hex_to_rgb(color), font=ft)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)

    def _draw_header(self, draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle((0, 0, self.w, 110), fill=hex_to_rgb("#EEF2F7"))
        draw.line((0, 110, self.w, 110), fill=hex_to_rgb("#CBD5E1"), width=2)
        draw.text((56, 24), self.title, fill=hex_to_rgb(PALETTE["ink"]), font=font(42, True))
        draw.text((58, 74), self.subtitle, fill=hex_to_rgb(PALETTE["muted"]), font=font(22))

    def _draw_group_png(self, draw: ImageDraw.ImageDraw, g: Group) -> None:
        draw.rounded_rectangle((g.x, g.y, g.x + g.w, g.y + g.h), radius=28, fill=hex_to_rgb(g.fill), outline=hex_to_rgb(g.stroke), width=2)
        draw.text((g.x + 22, g.y + 14), g.label, fill=hex_to_rgb(PALETTE["muted"]), font=font(22, True))

    def _draw_box_png(self, draw: ImageDraw.ImageDraw, b: Box) -> None:
        if b.shadow:
            draw.rounded_rectangle((b.x + 8, b.y + 10, b.x + b.w + 8, b.y + b.h + 10), radius=b.radius, fill=(210, 220, 233))
        draw.rounded_rectangle((b.x, b.y, b.x + b.w, b.y + b.h), radius=b.radius, fill=hex_to_rgb(b.fill), outline=hex_to_rgb(b.stroke), width=b.stroke_width)
        ft = font(b.font_size, True)
        lines = wrap_text(draw, b.label, ft, b.w - 34)
        line_heights = [text_size(draw, line, ft)[1] or b.font_size for line in lines]
        total_h = sum(line_heights) + max(0, len(lines) - 1) * 9
        y = b.y + (b.h - total_h) // 2 - 2
        for idx, line in enumerate(lines):
            tw, th = text_size(draw, line, ft)
            draw.text((b.x + (b.w - tw) / 2, y), line, fill=hex_to_rgb(b.text), font=ft)
            y += th + 9

    def _draw_arrow_png(self, draw: ImageDraw.ImageDraw, a: Arrow) -> None:
        if a.points:
            pts = a.points
        else:
            ss, es = self.auto_sides(a)
            ss = a.start_side or ss
            es = a.end_side or es
            p1 = self.anchor(a.start, ss)
            p2 = self.anchor(a.end, es)
            pts = [p1, p2]
        color = hex_to_rgb(a.color)
        if a.dashed:
            self._dashed_line(draw, pts, color, a.width)
        else:
            draw.line(pts, fill=color, width=a.width, joint="curve")
        self._arrow_head(draw, pts[-2], pts[-1], color, a.width)
        if a.label:
            mx = sum(p[0] for p in pts) // len(pts)
            my = sum(p[1] for p in pts) // len(pts)
            ft = font(19)
            tw, th = text_size(draw, a.label, ft)
            pad = 8
            draw.rounded_rectangle((mx - tw / 2 - pad, my - th / 2 - pad, mx + tw / 2 + pad, my + th / 2 + pad), radius=8, fill=(255, 255, 255), outline=(226, 232, 240))
            draw.text((mx - tw / 2, my - th / 2 - 1), a.label, fill=color, font=ft)

    def _dashed_line(self, draw: ImageDraw.ImageDraw, pts: list[tuple[int, int]], color: tuple[int, int, int], width: int):
        for p1, p2 in zip(pts, pts[1:]):
            x1, y1 = p1
            x2, y2 = p2
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist == 0:
                continue
            dash, gap = 16, 12
            t = 0.0
            while t < dist:
                t2 = min(t + dash, dist)
                a = (x1 + (x2 - x1) * t / dist, y1 + (y2 - y1) * t / dist)
                b = (x1 + (x2 - x1) * t2 / dist, y1 + (y2 - y1) * t2 / dist)
                draw.line((a, b), fill=color, width=width)
                t += dash + gap

    def _arrow_head(self, draw: ImageDraw.ImageDraw, p1: tuple[int, int], p2: tuple[int, int], color: tuple[int, int, int], width: int):
        x1, y1 = p1
        x2, y2 = p2
        angle = math.atan2(y2 - y1, x2 - x1)
        size = max(13, width * 4)
        pts = [
            (x2, y2),
            (x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6)),
            (x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6)),
        ]
        draw.polygon(pts, fill=color)

    def render_svg(self, path: Path) -> None:
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">',
            "<defs>",
            '<filter id="shadow" x="-10%" y="-10%" width="130%" height="130%"><feDropShadow dx="4" dy="7" stdDeviation="5" flood-color="#94A3B8" flood-opacity="0.35"/></filter>',
            '<marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M2,2 L10,6 L2,10 Z" fill="#334155"/></marker>',
            '<style>text{font-family:"Microsoft JhengHei","Noto Sans CJK TC",Arial,sans-serif;letter-spacing:0}.title{font-size:42px;font-weight:700;fill:#172033}.sub{font-size:22px;fill:#64748B}.label{font-weight:700;fill:#172033}.note{font-size:22px;fill:#64748B}</style>',
            "</defs>",
            f'<rect width="{self.w}" height="{self.h}" fill="{PALETTE["bg"]}"/>',
            '<rect x="0" y="0" width="1920" height="110" fill="#EEF2F7"/>',
            '<line x1="0" y1="110" x2="1920" y2="110" stroke="#CBD5E1" stroke-width="2"/>',
            f'<text x="56" y="56" class="title">{escape(self.title)}</text>',
            f'<text x="58" y="96" class="sub">{escape(self.subtitle)}</text>',
        ]
        for g in self.groups:
            parts.append(f'<rect x="{g.x}" y="{g.y}" width="{g.w}" height="{g.h}" rx="28" fill="{g.fill}" stroke="{g.stroke}" stroke-width="2"/>')
            parts.append(f'<text x="{g.x + 22}" y="{g.y + 42}" class="note" font-weight="700">{escape(g.label)}</text>')
        for a in self.arrows:
            parts.append(self._arrow_svg(a))
        for b in self.boxes.values():
            filt = ' filter="url(#shadow)"' if b.shadow else ""
            parts.append(f'<rect x="{b.x}" y="{b.y}" width="{b.w}" height="{b.h}" rx="{b.radius}" fill="{b.fill}" stroke="{b.stroke}" stroke-width="{b.stroke_width}"{filt}/>')
            lines = svg_wrap(b.label, max(12, int(b.w / max(16, b.font_size * 0.62))))
            line_h = b.font_size + 9
            y0 = b.y + b.h / 2 - (len(lines) - 1) * line_h / 2 + b.font_size / 3
            parts.append(f'<text x="{b.x + b.w / 2:.1f}" y="{y0:.1f}" text-anchor="middle" class="label" font-size="{b.font_size}px" fill="{b.text}">')
            for i, line in enumerate(lines):
                dy = 0 if i == 0 else line_h
                parts.append(f'<tspan x="{b.x + b.w / 2:.1f}" dy="{dy}">{escape(line)}</tspan>')
            parts.append("</text>")
        for x, y, txt, color in self.notes:
            parts.append(f'<text x="{x}" y="{y}" class="note" fill="{color}">{escape(txt)}</text>')
        parts.append("</svg>")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(parts), encoding="utf-8")

    def _arrow_svg(self, a: Arrow) -> str:
        if a.points:
            pts = a.points
        else:
            ss, es = self.auto_sides(a)
            pts = [self.anchor(a.start, a.start_side or ss), self.anchor(a.end, a.end_side or es)]
        point_str = " ".join(f"{x},{y}" for x, y in pts)
        dash = ' stroke-dasharray="14 10"' if a.dashed else ""
        line = f'<polyline points="{point_str}" fill="none" stroke="{a.color}" stroke-width="{a.width}" stroke-linecap="round" stroke-linejoin="round"{dash} marker-end="url(#arrow)"/>'
        if not a.label:
            return line
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        label = escape(a.label)
        bg_w = max(90, len(a.label) * 18)
        label_svg = (
            f'<rect x="{mx - bg_w / 2:.1f}" y="{my - 18:.1f}" width="{bg_w}" height="36" rx="8" fill="#FFFFFF" stroke="#E2E8F0"/>'
            f'<text x="{mx:.1f}" y="{my + 7:.1f}" text-anchor="middle" font-size="19" fill="{a.color}">{label}</text>'
        )
        return line + label_svg


def add_step_chain(d: Diagram, specs: list[tuple[str, str, str, str]], y: int, x0: int = 70, gap: int = 28, h: int = 150):
    w = int((d.w - x0 * 2 - gap * (len(specs) - 1)) / len(specs))
    prev = None
    for i, (id_, label, fill, stroke) in enumerate(specs):
        x = x0 + i * (w + gap)
        d.box(id_, x, y, w, h, label, fill, stroke, font_size=24)
        if prev:
            d.arrow(prev, id_, start_side="right", end_side="left")
        prev = id_


def d01() -> Diagram:
    d = Diagram("research_context", "研究整體概念架構圖", "從高齡陪伴需求到智慧象棋實體互動系統", "第一章、第二章、第三章", "呈現研究問題、系統解法、互動角色與評估輸出。")
    d.group(70, 150, 1780, 850, "研究主軸與應用情境", "#FFFFFF", "#CBD5E1")
    d.box("need", 110, 230, 350, 180, "研究需求\n高齡化社會\n陪伴不足\n認知刺激需求", PALETTE["amber_light"], PALETTE["amber"])
    d.box("system", 690, 220, 540, 250, "智慧象棋實體互動系統\n實體棋盤 + AI 對弈\n視覺辨識 + 機械手臂\nDashboard 即時回饋", PALETTE["blue_light"], PALETTE["blue"], font_size=27)
    d.box("tech", 1460, 230, 340, 180, "技術核心\nOpenCV / Homography / YOLO\nPikafish\nTM5-700", PALETTE["teal_light"], PALETTE["teal"], font_size=24)
    d.box("role1", 190, 610, 310, 160, "長者 / 使用者\n下棋互動\n理解 AI 回饋", "#F0FDF4", PALETTE["green"], font_size=24)
    d.box("role2", 610, 680, 340, 160, "照護者 / 研究員\n觀察安全\n蒐集問卷訪談", PALETTE["violet_light"], PALETTE["violet"], font_size=24)
    d.box("role3", 1020, 680, 340, 160, "AI 與機械手臂\n分析棋局\n執行實體落子", "#E0F2FE", "#0284C7", font_size=24)
    d.box("eval", 1440, 610, 340, 170, "評估輸出\nSUS / TAM / 訪談\n辨識率 / FPS\n安全事件紀錄", "#F8FAFC", "#475569", font_size=23)
    d.arrow("need", "system", "研究目標")
    d.arrow("tech", "system", "技術整合", start_side="left", end_side="right")
    d.arrow("system", "role1", "互動")
    d.arrow("system", "role2", "實驗")
    d.arrow("system", "role3", "控制")
    d.arrow("role1", "eval", "體驗資料")
    d.arrow("role2", "eval", "觀察紀錄")
    d.arrow("role3", "eval", "系統指標")
    return d


def d02() -> Diagram:
    d = Diagram("research_process", "研究流程圖", "文獻、系統建置、模型訓練、整合測試與使用者評估", "第三章、第四章", "對應報告研究方法與初步測試規劃。")
    add_step_chain(d, [
        ("p1", "1 文獻整理\n高齡陪伴\n棋類活動\n安全規範", PALETTE["amber_light"], PALETTE["amber"]),
        ("p2", "2 需求定義\n互動目標\n安全邊界\n評估指標", "#F0FDF4", PALETTE["green"]),
        ("p3", "3 系統設計\n感知 / 決策\n執行 / 回饋\n事件架構", PALETTE["blue_light"], PALETTE["blue"]),
        ("p4", "4 模型訓練\n影像蒐集\n標註增強\nYOLO", PALETTE["teal_light"], PALETTE["teal"]),
        ("p5", "5 模組整合\nVision\nPikafish\nRobotFacade\nDashboard", PALETTE["violet_light"], PALETTE["violet"]),
        ("p6", "6 初步測試\n功能驗證\n問卷訪談\n系統修正", PALETTE["red_light"], PALETTE["red"]),
    ], 330, x0=50, gap=20, h=210)
    d.group(220, 670, 1480, 230, "回饋修正循環", "#FFFFFF", "#CBD5E1")
    d.box("fb1", 300, 730, 320, 110, "辨識誤差\n光線 / 遮擋 / 反光", "#F8FAFC", "#475569", font_size=22)
    d.box("fb2", 800, 730, 320, 110, "互動問題\n難度 / UI / 安全感", "#F8FAFC", "#475569", font_size=22)
    d.box("fb3", 1300, 730, 320, 110, "系統修正\n參數調整 / 流程改善", "#F8FAFC", "#475569", font_size=22)
    d.arrow("fb1", "fb2", "")
    d.arrow("fb2", "fb3", "")
    d.arrow("fb3", "p3", "回到設計", start_side="top", end_side="bottom", dashed=True)
    return d


def d03() -> Diagram:
    d = Diagram("layered_architecture", "智慧象棋系統分層架構圖", "Frontend、Interface、Application、Event/State、Runtime、Infrastructure 與硬體資產", "第三章、第四章", "以程式目錄與執行責任呈現系統模組分層。")
    xs = [80, 325, 570, 815, 1060, 1305, 1550]
    labels = [
        ("frontend", "Frontend\ntemplates\nJS modules\nCSS", PALETTE["blue_light"], PALETTE["blue"]),
        ("interface", "Interface\nFlask routes\nSocket.IO\nDashboard", "#E0F2FE", "#0284C7"),
        ("app", "Application\nbootstrap\nservices\nuse cases", PALETTE["green_light"], PALETTE["green"]),
        ("state", "Event / State\nEventBus\nReducers\nStateManager", PALETTE["violet_light"], PALETTE["violet"]),
        ("runtime", "Runtime\nAsyncRuntime\nWorkers\nQueues", PALETTE["amber_light"], PALETTE["amber"]),
        ("infra", "Infrastructure\nVision\nRobot\nDatabase", PALETTE["teal_light"], PALETTE["teal"]),
        ("hardware", "Assets / Hardware\nCamera\nPikafish/NNUE\nTM5-700", PALETTE["red_light"], PALETTE["red"]),
    ]
    for x, spec in zip(xs, labels):
        id_, label, fill, stroke = spec
        d.box(id_, x, 220, 210, 600, label, fill, stroke, font_size=23)
    for a, b in zip([s[0] for s in labels], [s[0] for s in labels][1:]):
        d.arrow(a, b, "", start_side="right", end_side="left")
    d.arrow("state", "interface", "STATE_UPDATED", start_side="top", end_side="top", dashed=True, points=[(920, 220), (920, 165), (430, 165), (430, 220)])
    d.arrow("infra", "state", "BaseEvent", start_side="top", end_side="top", dashed=True, points=[(1410, 220), (1410, 140), (920, 140), (920, 220)])
    d.note(78, 900, "核心設計：前端只吃穩定 contract；後端以 EventBus + StateManager 作為唯一狀態同步主幹。")
    return d


def d04() -> Diagram:
    d = Diagram("transmission_architecture", "系統傳輸架構圖", "HTTP / Socket.IO / MJPEG / UCI / Modbus TCP / SQLite 的資料通道", "第三章、第四章", "呈現軟硬體之間的資料傳輸與通訊協定。")
    d.group(70, 160, 410, 800, "硬體與模型", "#FFFFFF", "#CBD5E1")
    d.group(560, 160, 780, 800, "後端服務與 runtime", "#FFFFFF", "#CBD5E1")
    d.group(1430, 160, 420, 800, "使用者端與資料輸出", "#FFFFFF", "#CBD5E1")
    d.box("camera", 125, 245, 300, 130, "Camera\n棋盤影像", PALETTE["teal_light"], PALETTE["teal"])
    d.box("robot", 125, 555, 300, 130, "TM5-700\n協作型手臂", PALETTE["red_light"], PALETTE["red"])
    d.box("engineasset", 125, 740, 300, 130, "Pikafish.exe\nNNUE / best.onnx", PALETTE["amber_light"], PALETTE["amber"], font_size=23)
    d.box("api", 610, 250, 300, 120, "Flask API\n/api/*", PALETTE["blue_light"], PALETTE["blue"])
    d.box("socket", 975, 250, 300, 120, "Socket.IO Gateway\nSYSTEM_STATE_UPDATE", "#E0F2FE", "#0284C7", font_size=22)
    d.box("vision", 610, 480, 300, 140, "Vision System\nOpenCV / Homography / YOLO\nMJPEG stream", PALETTE["teal_light"], PALETTE["teal"], font_size=22)
    d.box("event", 975, 480, 300, 140, "EventBus + StateManager\nBaseEvent / Reducer\nSSOT", PALETTE["violet_light"], PALETTE["violet"], font_size=22)
    d.box("enginesvc", 610, 740, 300, 130, "EngineService\nUCI stdin/stdout\nposition fen / go", PALETTE["amber_light"], PALETTE["amber"], font_size=22)
    d.box("robotsvc", 975, 740, 300, 130, "RobotFacade\nRobotService / FakeRobot\nE-Stop gate", PALETTE["red_light"], PALETTE["red"], font_size=22)
    d.box("browser", 1485, 250, 300, 140, "Browser Dashboard\nHTML/CSS/JS\nSocket client", PALETTE["blue_light"], PALETTE["blue"], font_size=22)
    d.box("db", 1485, 565, 300, 130, "SQLite app.db\nReplay / EventStore", "#F8FAFC", "#475569", font_size=22)
    d.box("xlsx", 1485, 760, 300, 110, "Excel / CSV Export\n報告資料", PALETTE["green_light"], PALETTE["green"], font_size=22)
    d.arrow("browser", "api", "REST JSON", start_side="left", end_side="right")
    d.arrow("socket", "browser", "WebSocket", start_side="right", end_side="left")
    d.arrow("vision", "browser", "MJPEG", start_side="right", end_side="left", points=[(910, 550), (1410, 550), (1410, 320), (1485, 320)])
    d.arrow("camera", "vision", "frames")
    d.arrow("engineasset", "enginesvc", "UCI assets")
    d.arrow("enginesvc", "event", "ENGINE events")
    d.arrow("event", "socket", "contract events")
    d.arrow("event", "db", "persistence", points=[(1275, 550), (1390, 550), (1390, 630), (1485, 630)])
    d.arrow("db", "xlsx", "query/export", start_side="bottom", end_side="top")
    d.arrow("robotsvc", "robot", "Modbus TCP / fake", start_side="left", end_side="right")
    d.arrow("event", "robotsvc", "move command", start_side="bottom", end_side="top")
    return d


def d05() -> Diagram:
    d = Diagram("event_state_flow", "EventBus 與狀態同步流程圖", "BaseEvent -> EventBus -> Reducer -> SystemState -> Socket contract", "第三章、第四章", "說明事件驅動與唯一狀態來源 SSOT。")
    d.group(80, 175, 370, 770, "事件來源", "#FFFFFF", "#CBD5E1")
    d.group(540, 175, 840, 770, "事件處理核心", "#FFFFFF", "#CBD5E1")
    d.group(1470, 175, 360, 770, "訂閱與輸出", "#FFFFFF", "#CBD5E1")
    sources = [
        ("s1", "API routes\nmove / reset / estop", 245),
        ("s2", "Socket handlers\nplayer_move / action", 405),
        ("s3", "VisionService\nVISION_MOVE_DETECTED", 565),
        ("s4", "EngineWorker\nENGINE_ANALYSIS_COMPLETED", 725),
    ]
    for id_, label, y in sources:
        d.box(id_, 120, y, 290, 105, label, PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("base", 595, 290, 250, 130, "BaseEvent\nid / type\ntrace_id / payload", PALETTE["amber_light"], PALETTE["amber"], font_size=22)
    d.box("bus", 890, 290, 300, 130, "EventBus.publish\nspecific subscribers\nglobal subscribers", PALETTE["violet_light"], PALETTE["violet"], font_size=22)
    d.box("reducer", 610, 560, 280, 130, "ReducerRegistry\nMove / Engine\nRobot / System", PALETTE["green_light"], PALETTE["green"], font_size=22)
    d.box("state", 945, 560, 300, 130, "StateManager\nvalidate FEN\ncommit SystemState", PALETTE["teal_light"], PALETTE["teal"], font_size=22)
    d.box("frontend", 1510, 280, 280, 120, "Socket forwarder\nSYSTEM_STATE_UPDATE", "#E0F2FE", "#0284C7", font_size=21)
    d.box("persist", 1510, 540, 280, 120, "PersistenceWorker\nqueue -> SQLite", "#F8FAFC", "#475569", font_size=21)
    d.box("diag", 1510, 740, 280, 105, "Diagnostics / UI_TOAST\nerror visibility", PALETTE["red_light"], PALETTE["red"], font_size=20)
    for id_, _, _ in sources:
        d.arrow(id_, "base", "")
    d.arrow("base", "bus", "")
    d.arrow("bus", "reducer", "dispatch")
    d.arrow("reducer", "state", "new state")
    d.arrow("state", "bus", "STATE_UPDATED", start_side="top", end_side="bottom", dashed=True, points=[(1095, 560), (1095, 500), (1040, 500), (1040, 420)])
    d.arrow("bus", "frontend", "contract")
    d.arrow("bus", "persist", "all events")
    d.arrow("bus", "diag", "errors")
    return d


def d06() -> Diagram:
    d = Diagram("move_sequence", "一步棋完整時序圖", "User / Frontend / Backend / Vision / Engine / Robot / DB 的端到端互動", "第三章、第四章", "適合說明一次對弈循環如何完成。")
    lanes = [
        ("user", "使用者", 90),
        ("front", "Frontend", 330),
        ("back", "Backend\nAPI / Socket", 570),
        ("state", "EventBus\nStateManager", 810),
        ("ai", "Vision / Engine", 1050),
        ("robot", "RobotFacade", 1290),
        ("db", "SQLite / Export", 1530),
    ]
    for id_, title, x in lanes:
        d.box(id_, x, 175, 190, 80, title, "#FFFFFF", "#94A3B8", font_size=22, shadow=False)
        d.arrow((x + 95, 270), (x + 95, 920), color="#94A3B8", dashed=True, width=2)
    steps = [
        ((185, 325), (425, 325), "1 點擊走子 / 拍攝棋盤"),
        ((425, 390), (665, 390), "2 REST 或 Socket 發送命令"),
        ((665, 455), (905, 455), "3 建立 BaseEvent"),
        ((905, 520), (1145, 520), "4 reducer 更新 FEN"),
        ((1145, 585), (905, 585), "5 Pikafish 回傳 bestmove"),
        ((905, 650), (1385, 650), "6 workflow 觸發落子"),
        ((1385, 715), (905, 715), "7 ROBOT.STATUS_UPDATED"),
        ((905, 780), (425, 780), "8 SYSTEM_STATE_UPDATE"),
        ((905, 850), (1625, 850), "9 事件批次寫入"),
    ]
    for p1, p2, label in steps:
        d.arrow(p1, p2, label, color=PALETTE["line"], width=4)
    d.note(92, 960, "trace_id 貫穿整個流程，讓 Replay、log、診斷與後續報告資料能對回同一次互動。")
    return d


def d07() -> Diagram:
    d = Diagram("vision_pipeline", "Vision Pipeline 與 FEN 生成流程圖", "Camera frame -> OpenCV/Homography/YOLO -> Board state -> FEN -> EventBus", "第三章、第四章", "細化影像辨識與棋局轉換流程。")
    add_step_chain(d, [
        ("v1", "Camera\nraw frame", PALETTE["teal_light"], PALETTE["teal"]),
        ("v2", "Perspective\nwarp 棋盤俯視", "#E0F2FE", "#0284C7"),
        ("v3", "Preprocess\n色彩增強\n去雜訊", PALETTE["blue_light"], PALETTE["blue"]),
        ("v4", "Detector\nYOLO\nYOLO only", PALETTE["violet_light"], PALETTE["violet"]),
        ("v5", "BoardMapper\nbbox -> 9x10\n棋格座標", PALETTE["green_light"], PALETTE["green"]),
        ("v6", "TemporalValidator\n穩定判斷\n信心摘要", PALETTE["amber_light"], PALETTE["amber"]),
        ("v7", "FENGenerator\nboard_state\n-> FEN", PALETTE["red_light"], PALETTE["red"]),
    ], 260, x0=40, gap=16, h=175)
    d.group(190, 610, 1540, 250, "輸出與回饋", "#FFFFFF", "#CBD5E1")
    d.box("event", 285, 680, 320, 110, "VISION_MOVE_DETECTED\n更新棋局狀態", PALETTE["green_light"], PALETTE["green"], font_size=21)
    d.box("frame", 785, 680, 320, 110, "VISION.FRAME_PROCESSED\nFPS / latency / detections", "#E0F2FE", "#0284C7", font_size=21)
    d.box("mjpeg", 1285, 680, 320, 110, "MJPEG + Overlay\n影像串流 / bbox", PALETTE["teal_light"], PALETTE["teal"], font_size=21)
    d.arrow("v7", "event", "stable FEN")
    d.arrow("v4", "frame", "每幀診斷")
    d.arrow("v2", "mjpeg", "視覺回饋")
    d.note(70, 930, "程式對應：backend/infrastructure/vision/*、vision_system.py、VisionService.on_board_detected()。")
    return d


def d08() -> Diagram:
    d = Diagram("engine_pipeline", "Pikafish AI 引擎與難度控制流程圖", "FEN -> EngineWorker -> EngineService -> UCI -> EngineParser -> UI / Robot", "第三章、第四章", "呈現 AI 分析與深度/多變化輸出的資料流。")
    d.box("state", 90, 280, 270, 140, "StateStore\ncurrent FEN\ncurrent_turn", PALETTE["green_light"], PALETTE["green"])
    d.box("worker", 455, 280, 310, 140, "EnginePollingWorker\nFEN 變更 0.2s\nidle 2.0s", PALETTE["blue_light"], PALETTE["blue"], font_size=22)
    d.box("svc", 860, 260, 330, 180, "EngineService\nprobe NNUE\nstart process\ncompute(fen, depth)", PALETTE["amber_light"], PALETTE["amber"], font_size=22)
    d.box("uci", 1285, 260, 280, 180, "Pikafish UCI\nposition fen\ngo depth\nbestmove/info", PALETTE["red_light"], PALETTE["red"], font_size=22)
    d.box("parser", 885, 590, 300, 130, "EngineParser\nscore / pv\nmulti_pv", PALETTE["violet_light"], PALETTE["violet"], font_size=23)
    d.box("event", 505, 590, 300, 130, "ENGINE_ANALYSIS_COMPLETED\nbest_move / score / depth", "#E0F2FE", "#0284C7", font_size=21)
    d.box("out1", 1265, 590, 280, 130, "Frontend\nengine_renderer.js\nAI 建議", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("out2", 90, 590, 280, 130, "Workflow\nAUTO_EXECUTE_ROBOT\n觸發手臂", PALETTE["teal_light"], PALETTE["teal"], font_size=21)
    d.arrow("state", "worker", "讀取 FEN")
    d.arrow("worker", "svc", "compute")
    d.arrow("svc", "uci", "UCI stdin")
    d.arrow("uci", "svc", "stdout", start_side="bottom", end_side="bottom", points=[(1425, 440), (1425, 525), (1025, 525), (1025, 440)])
    d.arrow("svc", "parser", "info lines")
    d.arrow("parser", "event", "publish")
    d.arrow("event", "out1", "Socket contract")
    d.arrow("event", "out2", "bestmove")
    d.group(1580, 210, 280, 620, "可調參數", "#FFFFFF", "#CBD5E1")
    d.note(1610, 290, "Skill Level")
    d.note(1610, 340, "Depth")
    d.note(1610, 390, "Hash / Threads")
    d.note(1610, 440, "MultiPV")
    d.note(1610, 520, "可延伸為：\nMMSE 或使用者程度\n對應難度控制表")
    return d


def d09() -> Diagram:
    d = Diagram("robot_motion_safety", "機械手臂 Pick-and-Place 控制流程圖", "Best move -> RobotFacade -> E-Stop gate -> RobotService/FakeRobot -> TM5-700", "第三章、第四章", "說明實體落子路徑、模擬切換與安全門檻。")
    add_step_chain(d, [
        ("r1", "AI bestmove\n或人工命令", PALETTE["blue_light"], PALETTE["blue"]),
        ("r2", "WorkflowCoordinator\n決定是否執行", "#E0F2FE", "#0284C7"),
        ("r3", "RobotFacade\n統一真機/模擬", PALETTE["teal_light"], PALETTE["teal"]),
        ("r4", "E-Stop Gate\nGLOBAL_STOP 檢查", PALETTE["red_light"], PALETTE["red"]),
        ("r5", "Kinematics\n棋格 -> robot pose\n安全路徑", PALETTE["amber_light"], PALETTE["amber"]),
        ("r6", "RobotService\nModbus / FakeRobot\nmove_piece", PALETTE["violet_light"], PALETTE["violet"]),
        ("r7", "TM5-700\nPick -> Place\nstatus feedback", PALETTE["green_light"], PALETTE["green"]),
    ], 270, x0=40, gap=16, h=190)
    d.group(250, 665, 1420, 220, "狀態回饋與例外處理", "#FFFFFF", "#CBD5E1")
    d.box("status", 350, 735, 300, 100, "ROBOT.STATUS_UPDATED\nconnected / busy / queue", "#F8FAFC", "#475569", font_size=20)
    d.box("fail", 810, 735, 300, 100, "執行失敗\nfalse / error\n人工介入", PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.box("front", 1270, 735, 300, 100, "Dashboard\nrobot_renderer.js\n即時顯示", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.arrow("r7", "status")
    d.arrow("r4", "fail", "blocked", dashed=True)
    d.arrow("status", "front")
    return d


def d10() -> Diagram:
    d = Diagram("estop_chain", "E-Stop 安全控制鏈圖", "觸發、清佇列、硬體停止、狀態錯誤、UI 鎖定與人工復原", "第三章、第四章", "凸顯高齡互動場域中的安全閉鎖機制。")
    d.group(70, 170, 420, 760, "觸發來源", "#FFFFFF", "#CBD5E1")
    d.group(560, 170, 800, 760, "E-Stop interlock chain", "#FFFFFF", "#CBD5E1")
    d.group(1430, 170, 420, 760, "輸出與復原", "#FFFFFF", "#CBD5E1")
    for id_, label, y in [
        ("t1", "Frontend 長按\nE-Stop button", 260),
        ("t2", "安全違規\n碰撞 / 越界", 460),
        ("t3", "實體急停\n外部訊號", 660),
    ]:
        d.box(id_, 125, y, 300, 110, label, PALETTE["red_light"], PALETTE["red"], font_size=22)
    chain = [
        ("c1", "EStop.trigger(reason)", 255),
        ("c2", "task_queue.clear()\nrobot_queue.clear()", 405),
        ("c3", "RobotFacade.emergency_stop()\n硬體停止", 555),
        ("c4", "state_store.dispatch\nSYSTEM_ERROR", 705),
    ]
    for id_, label, y in chain:
        d.box(id_, 715, y, 470, 100, label, "#FFF7ED", "#EA580C", font_size=22)
    for a, b in zip([x[0] for x in chain], [x[0] for x in chain][1:]):
        d.arrow(a, b, start_side="bottom", end_side="top", color=PALETTE["red"])
    d.box("o1", 1490, 290, 300, 120, "Socket.IO ui_lock\n前端不可操作", PALETTE["red_light"], PALETTE["red"], font_size=22)
    d.box("o2", 1490, 510, 300, 120, "Dashboard overlay\nERROR / reason", "#E0F2FE", "#0284C7", font_size=22)
    d.box("o3", 1490, 730, 300, 120, "Manual reset\nSYSTEM_RESET\nRECOVERY_COMPLETED", PALETTE["green_light"], PALETTE["green"], font_size=21)
    for src in ["t1", "t2", "t3"]:
        d.arrow(src, "c1")
    d.arrow("c4", "o1")
    d.arrow("c4", "o2")
    d.arrow("o3", "c1", "解除後重新啟動", dashed=True, points=[(1490, 790), (1360, 790), (1360, 225), (950, 225), (950, 255)])
    return d


def d11() -> Diagram:
    d = Diagram("persistence_replay_export", "資料庫、Replay 與 Excel 匯出流程圖", "EventBus all events -> Persistence queue -> SQLite -> replay/export/report", "第四章、測試與資料分析", "說明研究資料如何被記錄、回放與輸出。")
    d.box("bus", 110, 275, 330, 150, "EventBus\nall BaseEvent\nsession_id / trace_id", PALETTE["violet_light"], PALETTE["violet"])
    d.box("queue", 560, 275, 330, 150, "PersistenceWorker\nqueue maxsize\nbatch flush", PALETTE["amber_light"], PALETTE["amber"])
    d.box("store", 1010, 275, 330, 150, "EventStore\nsave_events()\nWAL mode", PALETTE["teal_light"], PALETTE["teal"])
    d.box("db", 1460, 265, 330, 170, "SQLite app.db\nevents table\nindexes by session / type / trace", "#F8FAFC", "#475569", font_size=22)
    d.arrow("bus", "queue", "subscribe_all")
    d.arrow("queue", "store", "batch")
    d.arrow("store", "db", "INSERT")
    d.group(170, 605, 1580, 250, "資料用途", "#FFFFFF", "#CBD5E1")
    d.box("replay", 260, 675, 300, 110, "Replay routes\nstep / snapshot\n互動回放", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("export", 720, 675, 300, 110, "Export routes\nexcel_exporter.py\nExcel / CSV", PALETTE["green_light"], PALETTE["green"], font_size=21)
    d.box("diag", 1180, 675, 300, 110, "Diagnostics\nqueue drops\npersisted events", PALETTE["red_light"], PALETTE["red"], font_size=21)
    d.arrow("db", "replay", "query", points=[(1625, 435), (1625, 565), (410, 565), (410, 675)])
    d.arrow("db", "export", "query", points=[(1625, 435), (1625, 585), (870, 585), (870, 675)])
    d.arrow("queue", "diag", "stats / drops", dashed=True, points=[(725, 425), (725, 550), (1330, 550), (1330, 675)])
    return d


def d12() -> Diagram:
    d = Diagram("frontend_contract_sync", "前後端同步與 Dashboard 資料流圖", "SYSTEM_STATE_UPDATE contract -> normalizer -> state_manager -> renderers", "第三章、第四章", "呈現前端如何穩定消費後端狀態。")
    d.group(70, 180, 520, 760, "Frontend modules", "#FFFFFF", "#CBD5E1")
    d.group(700, 180, 520, 760, "Backend contract", "#FFFFFF", "#CBD5E1")
    d.group(1330, 180, 520, 760, "UI render outputs", "#FFFFFF", "#CBD5E1")
    d.box("entry", 130, 260, 360, 90, "app.js / core/app.js\n啟動 UI registry", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.box("api", 130, 420, 360, 90, "api_client.js\nREST /api/state\nlogin / export", "#E0F2FE", "#0284C7", font_size=20)
    d.box("sock", 130, 580, 360, 90, "socket_client.js\nSocket.IO connect\naction / player_move", PALETTE["teal_light"], PALETTE["teal"], font_size=20)
    d.box("adapter", 130, 740, 360, 90, "event_adapter.js\nvalidate KNOWN_EVENTS\ncommit()", PALETTE["violet_light"], PALETTE["violet"], font_size=20)
    d.box("gateway", 760, 315, 400, 110, "socket_handler.py\n_emit SYSTEM_STATE_UPDATE\ncontract_version 1.0", PALETTE["amber_light"], PALETTE["amber"], font_size=21)
    d.box("contract", 760, 525, 400, 120, "contract.py\nSTATE_UPDATE\nENGINE.INFO_UPDATED\nVISION.FRAME_PROCESSED", PALETTE["green_light"], PALETTE["green"], font_size=20)
    d.box("state", 760, 735, 400, 110, "StateSerializer\nEngineInfoSerializer\npayload normalization", "#F8FAFC", "#475569", font_size=20)
    d.box("renderer", 1390, 305, 360, 120, "render.js\nboard / engine / robot\nvision / diagnostics", PALETTE["blue_light"], PALETTE["blue"], font_size=20)
    d.box("dom", 1390, 525, 360, 120, "Browser DOM\n棋盤 / AI 分析\n狀態燈 / logs", "#E0F2FE", "#0284C7", font_size=20)
    d.box("overlay", 1390, 745, 360, 100, "Vision overlay\nBounding box\nFPS / confidence", PALETTE["teal_light"], PALETTE["teal"], font_size=20)
    d.arrow("entry", "api")
    d.arrow("entry", "sock")
    d.arrow("sock", "gateway", "Socket.IO")
    d.arrow("gateway", "adapter", "SYSTEM_STATE_UPDATE", points=[(760, 370), (620, 370), (620, 785), (490, 785)])
    d.arrow("contract", "gateway", "allowed events")
    d.arrow("state", "gateway", "serialize")
    d.arrow("adapter", "renderer", "commit -> subscriptions", points=[(490, 785), (1275, 785), (1275, 365), (1390, 365)])
    d.arrow("renderer", "dom")
    d.arrow("renderer", "overlay")
    return d


def d13() -> Diagram:
    d = Diagram("runtime_worker_queue", "Runtime Worker 與 Queue 拓樸圖", "AsyncRuntime 背景執行緒、workers、frame/detect/robot queue 與 diagnostics", "第四章、測試章節", "說明多工作者與非同步佇列如何支撐即時互動。")
    d.box("runtime", 760, 210, 400, 130, "AsyncRuntime\nbackground event loop\nruntime.run_task()", PALETTE["violet_light"], PALETTE["violet"], font_size=24)
    d.box("wm", 760, 430, 400, 120, "WorkerManager\ninitialize_workers()\nshutdown hooks", "#F8FAFC", "#475569", font_size=22)
    d.arrow("runtime", "wm")
    workers = [
        ("camera", 120, 250, "CameraWorker\nframe capture", PALETTE["teal_light"], PALETTE["teal"]),
        ("vision", 120, 525, "VisionInferenceWorker\npipeline.process()", PALETTE["teal_light"], PALETTE["teal"]),
        ("engine", 760, 700, "EngineWorker\npoll current FEN\nbackoff", PALETTE["amber_light"], PALETTE["amber"]),
        ("robot", 1400, 250, "RobotStatusWorker\nrobot status heartbeat", PALETTE["red_light"], PALETTE["red"]),
        ("persist", 1400, 525, "PersistenceWorker\nbatch queue -> DB", PALETTE["green_light"], PALETTE["green"]),
    ]
    for id_, x, y, label, fill, stroke in workers:
        d.box(id_, x, y, 360, 130, label, fill, stroke, font_size=22)
        d.arrow("wm", id_, "start", dashed=True)
    d.box("q1", 470, 335, 220, 90, "frame_queue", "#FFFFFF", "#94A3B8", font_size=22)
    d.box("q2", 1230, 610, 220, 90, "event queue", "#FFFFFF", "#94A3B8", font_size=22)
    d.arrow("camera", "q1", "frames")
    d.arrow("q1", "vision", "latest frame")
    d.arrow("vision", "engine", "FEN events", points=[(300, 655), (300, 820), (760, 820)])
    d.arrow("engine", "persist", "ENGINE events")
    d.arrow("robot", "persist", "ROBOT events")
    d.arrow("persist", "q2", "batch", start_side="left", end_side="right")
    d.note(92, 930, "設計重點：耗時工作不阻塞 Flask/Socket.IO；失敗時以 backoff、diagnostics、queue drop stats 呈現。")
    return d


def d14() -> Diagram:
    d = Diagram("testing_quality_plan", "初步測試與品質驗證規劃圖", "功能、整合、前端、模擬、效能與使用者問卷訪談", "第四章、第五章規劃", "對應目前測試目錄與報告中的實驗規劃。")
    d.group(70, 170, 1780, 770, "測試與研究資料來源", "#FFFFFF", "#CBD5E1")
    rows = [
        ("unit", 130, 260, "Unit Tests\nreducers / services\nFEN / rate limit", PALETTE["blue_light"], PALETTE["blue"]),
        ("integration", 510, 260, "Integration Tests\nHTTP / Socket\ncontract / runtime", "#E0F2FE", "#0284C7"),
        ("frontend", 890, 260, "Frontend Jest\nsocket client\nrenderers / state", PALETTE["violet_light"], PALETTE["violet"]),
        ("simulation", 1270, 260, "Simulation\nFakeVision\nFakeRobot\nfull game", PALETTE["teal_light"], PALETTE["teal"]),
        ("quality", 320, 565, "Quality Gate\nassets / DB\ncontract / release zip", PALETTE["amber_light"], PALETTE["amber"]),
        ("metrics", 700, 565, "System Metrics\nFPS / latency\nqueue / errors\nrobot success", PALETTE["green_light"], PALETTE["green"]),
        ("survey", 1080, 565, "User Evaluation\nSUS / TAM\n安全感 / 訪談", PALETTE["red_light"], PALETTE["red"]),
        ("analysis", 1460, 565, "Analysis\n描述統計\n問題分類\n系統修正", "#F8FAFC", "#475569"),
    ]
    for id_, x, y, label, fill, stroke in rows:
        d.box(id_, x, y, 300, 145, label, fill, stroke, font_size=22)
    d.arrow("unit", "integration")
    d.arrow("integration", "frontend")
    d.arrow("frontend", "simulation")
    d.arrow("quality", "metrics")
    d.arrow("metrics", "survey")
    d.arrow("survey", "analysis")
    d.arrow("simulation", "metrics", "runtime logs")
    d.note(120, 870, "建議放入報告：以此圖銜接第四章「初步系統測試規劃」與後續第五章資料分析。")
    return d


def d15() -> Diagram:
    d = Diagram("model_training_evaluation", "影像模型訓練與效能分析流程圖", "資料蒐集、標註、YOLO26 訓練、驗證、部署與指標", "第二章、第三章、第四章", "支撐視覺辨識模型建置與限制討論。")
    add_step_chain(d, [
        ("m1", "資料蒐集\n不同光線\n角度 / 遮擋", PALETTE["teal_light"], PALETTE["teal"]),
        ("m2", "標註\n棋子類別\nbbox / board", PALETTE["blue_light"], PALETTE["blue"]),
        ("m3", "資料增強\n旋轉 / 對比\n小目標切片", PALETTE["violet_light"], PALETTE["violet"]),
        ("m4", "YOLO26 訓練\nbest.onnx\nvalidation set", PALETTE["amber_light"], PALETTE["amber"]),
        ("m5", "YOLO 推論\nbbox / confidence\nNMS 合併", PALETTE["green_light"], PALETTE["green"]),
        ("m6", "部署\nvision_system.py\nYOLO only", PALETTE["red_light"], PALETTE["red"]),
    ], 260, x0=70, gap=24, h=190)
    d.group(230, 620, 1460, 240, "效能與錯誤分析", "#FFFFFF", "#CBD5E1")
    d.box("k1", 315, 690, 280, 110, "Detection metrics\nPrecision / Recall\nmAP / confusion", "#F8FAFC", "#475569", font_size=20)
    d.box("k2", 690, 690, 280, 110, "Runtime metrics\nFPS / latency\nconfidence", "#F8FAFC", "#475569", font_size=20)
    d.box("k3", 1065, 690, 280, 110, "Failure cases\n反光 / 遮擋\n棋子重疊", "#F8FAFC", "#475569", font_size=20)
    d.box("k4", 1440, 690, 200, 110, "改進\n光源 / Homography\n再訓練", PALETTE["green_light"], PALETTE["green"], font_size=20)
    d.arrow("m6", "k1", "驗證")
    d.arrow("k1", "k2")
    d.arrow("k2", "k3")
    d.arrow("k3", "k4")
    d.arrow("k4", "m1", "回收樣本", dashed=True, points=[(1540, 690), (1540, 570), (185, 570), (185, 450)])
    return d


def d16() -> Diagram:
    d = Diagram("fault_recovery_traceability", "Fault Recovery 與 Traceability 圖", "異常來源 -> 診斷事件 -> 安全/復原策略 -> trace_id/replay", "第四章、測試章節", "補強系統可靠度、錯誤追蹤與安全復原說明。")
    d.group(70, 170, 450, 760, "異常來源", "#FFFFFF", "#CBD5E1")
    d.group(620, 170, 680, 760, "偵測與處置", "#FFFFFF", "#CBD5E1")
    d.group(1400, 170, 450, 760, "追蹤與報告", "#FFFFFF", "#CBD5E1")
    faults = [
        ("f1", "Camera / Vision\n無影像 / 低信心", 245),
        ("f2", "Engine\nmissing / timeout\nNNUE incompatible", 405),
        ("f3", "Robot\nqueue stuck\n抓取失敗", 565),
        ("f4", "Contract / Socket\ninvalid payload\nrate limited", 725),
    ]
    for id_, label, y in faults:
        d.box(id_, 125, y, 330, 100, label, PALETTE["red_light"], PALETTE["red"], font_size=20)
    d.box("detect", 705, 260, 300, 120, "Diagnostics events\nDIAGNOSTICS_UPDATED\nhealth / ready", PALETTE["amber_light"], PALETTE["amber"], font_size=21)
    d.box("policy", 930, 470, 300, 120, "Recovery policy\nerror / retry\nbackoff / stop", PALETTE["blue_light"], PALETTE["blue"], font_size=21)
    d.box("safe", 705, 680, 300, 120, "Safety action\nE-Stop / UI lock\nmanual reset", PALETTE["red_light"], PALETTE["red"], font_size=21)
    d.box("trace", 1460, 285, 320, 120, "trace_id\n從 UI 到 worker\n全流程標記", PALETTE["violet_light"], PALETTE["violet"], font_size=21)
    d.box("replay", 1460, 500, 320, 120, "Replay / SQLite\n事件序列\n問題重現", "#F8FAFC", "#475569", font_size=21)
    d.box("report", 1460, 715, 320, 120, "Report evidence\nlog / metrics\n修正依據", PALETTE["green_light"], PALETTE["green"], font_size=21)
    for id_, _, _ in faults:
        d.arrow(id_, "detect")
    d.arrow("detect", "policy")
    d.arrow("policy", "safe")
    d.arrow("detect", "trace")
    d.arrow("policy", "replay")
    d.arrow("safe", "report")
    d.arrow("replay", "report")
    return d


BUILDERS: list[Callable[[], Diagram]] = [
    d01,
    d02,
    d03,
    d04,
    d05,
    d06,
    d07,
    d08,
    d09,
    d10,
    d11,
    d12,
    d13,
    d14,
    d15,
    d16,
]


def build_contact_sheet(png_paths: list[Path]) -> None:
    thumb_w, thumb_h = 430, 242
    cols = 4
    rows = math.ceil(len(png_paths) / cols)
    sheet = Image.new("RGB", (cols * 480, rows * 330 + 80), hex_to_rgb(PALETTE["bg"]))
    draw = ImageDraw.Draw(sheet)
    draw.text((32, 24), "S.M.A.R.T. Chess Robot Report Diagrams", fill=hex_to_rgb(PALETTE["ink"]), font=font(34, True))
    for idx, path in enumerate(png_paths):
        img = Image.open(path).convert("RGB")
        img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col = idx % cols
        row = idx // cols
        x = col * 480 + 25
        y = row * 330 + 85
        draw.rounded_rectangle((x - 10, y - 10, x + thumb_w + 10, y + thumb_h + 54), radius=18, fill=(255, 255, 255), outline=(203, 213, 225))
        sheet.paste(img, (x, y))
        draw.text((x, y + thumb_h + 14), path.stem, fill=hex_to_rgb(PALETTE["ink"]), font=font(18))
    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(CONTACT_SHEET)


def write_index(diagrams: list[Diagram]) -> None:
    manifest = []
    lines = [
        "# S.M.A.R.T. Chess Robot 報告圖示包",
        "",
        "所有圖示同時輸出為 SVG 與 PNG。SVG 適合匯入 Canva 後再排版與微調；PNG 適合直接插入 Word 報告。",
        "",
        "| 編號 | 圖名 | 建議章節 | 檔案 | 用途 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for idx, d in enumerate(diagrams, start=1):
        svg = SVG_DIR / f"{idx:02d}_{d.slug}.svg"
        png = PNG_DIR / f"{idx:02d}_{d.slug}.png"
        manifest.append(
            {
                "number": idx,
                "slug": d.slug,
                "title": d.title,
                "subtitle": d.subtitle,
                "chapter": d.chapter,
                "description": d.description,
                "svg": str(svg),
                "png": str(png),
            }
        )
        lines.append(f"| {idx:02d} | {d.title} | {d.chapter} | `{png}` / `{svg}` | {d.description} |")
    (OUT_ROOT / "diagram_index.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT_ROOT / "diagram_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    for directory, suffix in ((SVG_DIR, ".svg"), (PNG_DIR, ".png")):
        for old_file in directory.glob(f"*{suffix}"):
            old_file.unlink()
    diagrams = [builder() for builder in BUILDERS]
    png_paths: list[Path] = []
    for idx, diagram in enumerate(diagrams, start=1):
        svg_path = SVG_DIR / f"{idx:02d}_{diagram.slug}.svg"
        png_path = PNG_DIR / f"{idx:02d}_{diagram.slug}.png"
        diagram.render_svg(svg_path)
        diagram.render_png(png_path)
        png_paths.append(png_path)
    write_index(diagrams)
    build_contact_sheet(png_paths)
    print(json.dumps({"diagrams": len(diagrams), "png_dir": str(PNG_DIR), "svg_dir": str(SVG_DIR), "contact_sheet": str(CONTACT_SHEET)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
