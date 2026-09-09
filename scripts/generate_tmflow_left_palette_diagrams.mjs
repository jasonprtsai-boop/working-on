import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const docsDir = path.join(repoRoot, "docs");

const availableNodes = [
  "Start",
  "Set",
  "Point",
  "Wait for",
  "If",
  "Goto",
  "Move",
  "SubFlow",
  "Network",
  "Listen",
  "Stop",
  "Vision",
  "Gateway",
  "Display",
  "Log",
  "Command",
];

const rightOnly = [
  "ModbusDev",
  "Operation Space",
  "Set IO while Project Error",
  "Set IO while Project Stop",
  "Stop Watch",
  "Serial Port",
  "力規設定",
  "檢視",
];

const columns = [
  {
    key: "A",
    title: "A 初始化 / 通訊暫跳",
    tone: "blue",
    nodes: [
      ["A1", "Start", "流程入口；專案速度 3-5%"],
      ["A2", "Set", "初始化 status/error/heartbeat 等變數"],
      ["A3", "Set", "has_piece=false；吸盤 DO 已確認才 OFF"],
      ["A4", "Point", "移到 P_READY_SAFE 安全等待點"],
      ["A5", "Network", "正式送 READY；測試版先跳過"],
      ["Listen1", "Listen", "正式等 Python 指令；測試版先跳過"],
    ],
  },
  {
    key: "B",
    title: "B 測試主線 / 防呆",
    tone: "orange",
    nodes: [
      ["B1", "Set", "heartbeat = heartbeat + 1"],
      ["B2", "Set", "robot_state = 1"],
      ["B3", "Network", "正式送 HB；測試版先跳過"],
      ["B4", "Set", "固定測試命令 active_from/to/action"],
      ["B5", "Network", "正式送 BUSY；測試版先跳過"],
      ["B6", "If", "active_from 範圍；主線通過後加回"],
      ["B7", "If", "active_to 範圍；今日卡關點，重建"],
      ["B8", "If", "active_action 合法；主線通過後加回"],
      ["B9", "Set", "設定 src/dst/cap 的安全 X/Y"],
      ["B10", "If", "active_action==1 走 C；否則走 B11"],
    ],
  },
  {
    key: "M",
    title: "B11-B14 一般假移動",
    tone: "green",
    nodes: [
      ["B11", "Set", "move = src；卡住時先只留 move_x/y"],
      ["B12", "Move", "到來源安全座標；不下降 Z"],
      ["B13", "Set", "move = dst；Z/R 姿態保持 safe"],
      ["B14", "Move", "到目標安全座標；不開吸盤"],
    ],
  },
  {
    key: "C",
    title: "C 吃子假流程",
    tone: "green",
    nodes: [
      ["C1", "Set", "move = dst；到被吃棋位置上方"],
      ["C2", "Move", "到目標格安全高度"],
      ["C3", "Set", "move = cap；死棋盒 X/Y"],
      ["C4", "Move", "到死棋盒安全高度"],
      ["C5", "Set", "dead_slot_index = dead_slot_index + 1"],
      ["Goto", "Goto", "回 B11 搬來源棋"],
    ],
  },
  {
    key: "F",
    title: "F 完成 / 回等待",
    tone: "cyan",
    nodes: [
      ["F1", "Point", "回 P_READY_SAFE"],
      ["F2", "Set", "status=2；completed_cmd_id=active_cmd_id"],
      ["F3", "Network", "正式送 DONE；測試版先跳過"],
      ["F4", "Wait for", "等待 100 ms"],
      ["F5", "Set", "清 status/robot_state/action"],
      ["Goto", "Goto", "測試可 Stop；正式回 Listen1"],
    ],
  },
  {
    key: "G",
    title: "G 後續正式化",
    tone: "red",
    nodes: [
      ["IF", "If", "重建 B6/B7/B8，No 先接 Stop"],
      ["NET", "Network", "Python 9001 開啟後加回 A5/B3/B5/F3"],
      ["LISTEN", "Listen", "確認 Listen1 收命令欄位"],
      ["Z", "Move", "加入 pick_z/place_z/drop_z"],
      ["IO", "Set", "確認 DO 後才做吸盤 ON/OFF"],
      ["ERR", "Set/Stop", "最後補 G 區錯誤流程"],
    ],
  },
];

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function units(text) {
  return Array.from(String(text)).reduce((sum, char) => {
    if (/[\u3000-\u9fff\uff00-\uffef]/u.test(char)) return sum + 1.8;
    if (/[A-Z0-9_./:=-]/.test(char)) return sum + 1.12;
    return sum + 0.95;
  }, 0);
}

function wrap(text, maxUnits) {
  const chars = Array.from(String(text));
  const lines = [];
  let current = "";
  for (const char of chars) {
    const candidate = current + char;
    if (current && units(candidate) > maxUnits) {
      lines.push(current);
      current = char;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines.length ? lines : [""];
}

function text(lines, x, y, options = {}) {
  const { className = "body", lineHeight = 26, anchor = "start", weight = "" } = options;
  const attrs = [
    `class="${className}"`,
    `text-anchor="${anchor}"`,
    weight ? `font-weight="${weight}"` : "",
  ]
    .filter(Boolean)
    .join(" ");
  return `<text ${attrs}>${lines
    .map((line, index) => `<tspan x="${x}" y="${y + index * lineHeight}">${esc(line)}</tspan>`)
    .join("")}</text>`;
}

function marker(id, color) {
  return `<marker id="${id}" markerWidth="14" markerHeight="14" refX="11" refY="7" orient="auto" markerUnits="strokeWidth"><path d="M 2 2 L 12 7 L 2 12 Z" fill="${color}" /></marker>`;
}

function arrow(x1, y1, x2, y2, options = {}) {
  const { color = "#32455f", dashed = false, label = "", id = "arrow" } = options;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return `<g><path d="M ${x1} ${y1} L ${x2} ${y2}" fill="none" stroke="${color}" stroke-width="4" marker-end="url(#${id})" ${dashed ? 'stroke-dasharray="14 10"' : ""}/>${label ? `<rect class="label-bg" x="${mx - 120}" y="${my - 26}" width="240" height="34" rx="17"/>${text([label], mx, my - 3, { className: "edge-label", anchor: "middle" })}` : ""}</g>`;
}

function node({ x, y, w, h, id, type, body, tone = "blue" }) {
  const bodyLines = wrap(body, Math.max(12, Math.floor(w / 18)));
  return `<g class="node ${tone}">
    <rect class="node-box" x="${x}" y="${y}" width="${w}" height="${h}" rx="12"/>
    <rect class="node-strip" x="${x}" y="${y}" width="12" height="${h}" rx="6"/>
    ${text([id], x + 24, y + 38, { className: "node-id", weight: "600" })}
    <rect class="type-pill" x="${x + w - 138}" y="${y + 15}" width="116" height="30" rx="15"/>
    ${text([type], x + w - 80, y + 37, { className: "type-text", anchor: "middle" })}
    ${text(bodyLines, x + 24, y + 72, { className: "node-body", lineHeight: 24 })}
  </g>`;
}

function lane({ x, y, w, h, title, tone }) {
  return `<g class="lane ${tone}">
    <rect class="lane-box" x="${x}" y="${y}" width="${w}" height="${h}" rx="16"/>
    <rect class="lane-head" x="${x}" y="${y}" width="${w}" height="68" rx="16"/>
    <path class="lane-head-cover" d="M ${x} ${y + 50} H ${x + w} V ${y + 68} H ${x} Z"/>
    ${text([title], x + 22, y + 42, { className: "lane-title", weight: "600" })}
  </g>`;
}

function baseSvg(width, height, title, subtitle, content) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">
  <title id="title">${esc(title)}</title>
  <desc id="desc">${esc(subtitle)}</desc>
  <defs>
    ${marker("arrow", "#32455f")}
    ${marker("arrow-green", "#158a4d")}
    ${marker("arrow-red", "#cf3030")}
    <filter id="shadow" x="-8%" y="-8%" width="116%" height="124%"><feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="#10223f" flood-opacity="0.11"/></filter>
  </defs>
  <style>
    :root{--bg:#f5f7fb;--ink:#142033;--muted:#5b6b83;--border:#c6d3e5;--blue:#2f7cf6;--blue-soft:#e7f1ff;--cyan:#0891b2;--cyan-soft:#e7fbff;--green:#169b55;--green-soft:#e8f8ef;--orange:#ef7b22;--orange-soft:#fff3e3;--red:#d43b3b;--red-soft:#ffe9e9;--purple:#7c3aed;--purple-soft:#f1eaff;--yellow:#c99400;--yellow-soft:#fff7d1}
    .bg{fill:var(--bg)} .title{fill:var(--ink);font:600 44px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}.subtitle{fill:var(--muted);font:400 24px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}.body{fill:var(--ink);font:400 21px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}.small{fill:var(--muted);font:400 18px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}
    .lane-box,.node-box,.panel{fill:#fff;stroke:var(--border);stroke-width:2.2;filter:url(#shadow)}.lane-head,.lane-head-cover{fill:var(--blue-soft)}.lane.orange .lane-head,.lane.orange .lane-head-cover{fill:var(--orange-soft)}.lane.green .lane-head,.lane.green .lane-head-cover{fill:var(--green-soft)}.lane.cyan .lane-head,.lane.cyan .lane-head-cover{fill:var(--cyan-soft)}.lane.red .lane-head,.lane.red .lane-head-cover{fill:var(--red-soft)}.lane-title{fill:var(--ink);font:600 24px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}
    .node-id{fill:var(--ink);font:600 24px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}.node-body{fill:#273853;font:400 19px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}.node-strip{fill:var(--blue)}.node.orange .node-strip{fill:var(--orange)}.node.green .node-strip{fill:var(--green)}.node.cyan .node-strip{fill:var(--cyan)}.node.red .node-strip{fill:var(--red)}.type-pill{fill:#edf3fa;stroke:#d8e2ee;stroke-width:1}.type-text{fill:var(--muted);font:600 15px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}
    .label-bg{fill:var(--bg);stroke:#c7d3e4;stroke-width:1.2}.edge-label{fill:#40506a;font:600 17px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}.warn{fill:#b91c1c;font:600 21px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}.ok{fill:#166534;font:600 21px "Microsoft JhengHei","Noto Sans TC",Arial,sans-serif}
  </style>
  <rect class="bg" width="${width}" height="${height}"/>
  ${text([title], 60, 70, { className: "title", weight: "600" })}
  ${text([subtitle], 60, 110, { className: "subtitle" })}
  ${content}
</svg>`;
}

function expandedDiagram() {
  const width = 3900;
  const height = 2450;
  const laneW = 610;
  const gap = 28;
  const top = 190;
  const content = [
    text(["節點名稱只填 A1、A2...；用途寫在手冊，不寫進 TMflow 名稱。"], 60, 155, { className: "warn" }),
    ...columns.map((col, index) => {
      const x = 60 + index * (laneW + gap);
      const nodeH = col.nodes.length > 8 ? 104 : 128;
      const nodeGap = 18;
      const body = col.nodes
        .map(([id, type, desc], i) => node({ x: x + 24, y: top + 92 + i * (nodeH + nodeGap), w: laneW - 48, h: nodeH, id, type, body: desc, tone: col.tone }))
        .join("");
      return `${lane({ x, y: top, w: laneW, h: 2060, title: col.title, tone: col.tone })}${body}`;
    }),
    arrow(670, 720, 698, 720, { label: "測試：A4 -> B1" }),
    arrow(1308, 1510, 1336, 520, { color: "#158a4d", id: "arrow-green", dashed: true, label: "action=0" }),
    arrow(1308, 1510, 1974, 520, { color: "#158a4d", id: "arrow-green", dashed: true, label: "action=1" }),
    arrow(2584, 990, 1336, 520, { color: "#158a4d", id: "arrow-green", dashed: true, label: "C 後回 B11" }),
    arrow(1946, 1040, 2612, 520, { label: "完成" }),
    arrow(3222, 1050, 380, 2310, { dashed: true, label: "正式回 Listen1" }),
    arrow(1420, 500, 3250, 500, { color: "#cf3030", id: "arrow-red", dashed: true, label: "防呆/錯誤最後補" }),
    node({ x: 760, y: 2275, w: 2420, h: 110, id: "測試規則", type: "Rule", tone: "red", body: "先跳過 A5/Listen1/B3/B5/B6/B7/B8/F3；安全假流程跑通後再逐一加回。" }),
  ].join("");
  return baseSvg(width, height, "TMflow 1.82.51 現場修正版節點展開圖", "依照 2026-09-02 現場卡關結果：先測安全假流程，再加回 If、Network、Listen、真取放。", content);
}

function simpleFlowDiagram() {
  const width = 3000;
  const height = 1900;
  const steps = [
    ["1 初始化", "Start/Set", ["A1 開始", "A2 歸零", "A3 關吸盤"]],
    ["2 安全就位", "Point", ["A4 到 P_READY_SAFE", "跳過通訊與等待"]],
    ["3 測試命令", "Set", ["B1 心跳", "B2 ready", "B4 固定 action"]],
    ["4 安全假移動", "If/Move", ["B10 分支", "B11-B14 搬移", "C1-C5 吃子"]],
    ["5 完成收尾", "Point/Set/Wait", ["F1 回安全點", "F2 完成", "F4/F5 清狀態"]],
    ["6 逐一加回", "If/Net/IO", ["重建 B7", "加回通訊", "最後補 Z/吸盤"]],
  ];
  const boxW = 430;
  const gap = 42;
  const top = 300;
  const boxes = steps
    .map(([title, type, items], index) => {
      const x = 90 + index * (boxW + gap);
      return node({ x, y: top, w: boxW, h: 240, id: title, type, tone: index < 2 ? "blue" : index === 2 ? "orange" : index === 3 ? "green" : index === 4 ? "cyan" : "red", body: items.join(" / ") });
    })
    .join("");
  const arrows = steps.slice(0, -1).map((_, i) => arrow(90 + i * (boxW + gap) + boxW, top + 120, 90 + (i + 1) * (boxW + gap), top + 120)).join("");
  const lists = [
    node({ x: 110, y: 720, w: 780, h: 360, id: "可用流程節點", type: "Allowed", tone: "green", body: "左側可拖進流程：設定、點位、移動、判斷、等待、跳轉、通訊、停止。" }),
    node({ x: 970, y: 720, w: 870, h: 360, id: "不能當流程節點", type: "Right panel", tone: "red", body: "右側工具只作參數設定；不要把 ModbusDev、作業空間、計時、序列埠當節點。" }),
    node({ x: 1920, y: 720, w: 900, h: 360, id: "目前先跳過", type: "Test", tone: "cyan", body: "A5、Listen1、B3、B5、B6、B7、B8、F3 先不放在主測試線。" }),
    node({ x: 110, y: 1220, w: 1280, h: 250, id: "卡關處理", type: "B7", tone: "blue", body: "active_to=1 理應通過；先跳過 B7，主線跑通後刪掉重建 If，再從 ==1 測起。" }),
    node({ x: 1530, y: 1220, w: 1290, h: 250, id: "後續順序", type: "Safe", tone: "orange", body: "先 Move，再 If，再通訊與 Listen，最後才加入下降 Z 與吸盤 ON/OFF。" }),
  ].join("");
  return baseSvg(width, height, "TMflow 1.82.51 清楚流程圖（現場修正版）", "先用安全高度假流程排除問題；右側工具仍只作設定。", `${boxes}${arrows}${lists}`);
}

function exchangeDiagram() {
  const width = 3000;
  const height = 1600;
  const boxes = [
    ["網站", "UI", "玩家按我已下棋"],
    ["Python", "Vision/AI", "YOLO/Pikafish 算出 from/to/action"],
    ["TMflow", "Listen", "Listen1 接收外部命令"],
    ["TMflow", "Motion", "B/C/F 執行，後續補 G"],
    ["Python", "Network 9001", "收 READY/BUSY/DONE/ERR"],
  ];
  const content = boxes
    .map(([id, type, body], i) => node({ x: 120 + i * 560, y: 320, w: 470, h: 210, id, type, body, tone: i === 2 || i === 3 ? "green" : "cyan" }))
    .join("") +
    boxes.slice(0, -1).map((_, i) => arrow(590 + i * 560, 425, 680 + i * 560, 425)).join("") +
    node({ x: 180, y: 760, w: 1200, h: 220, id: "命令方向", type: "Listen", tone: "blue", body: "正式版 Python -> TMflow Listen1。安全假流程測試時先跳過 Listen1，直接從 A4 接 B1。" }) +
    node({ x: 1620, y: 760, w: 1200, h: 220, id: "狀態方向", type: "Network", tone: "cyan", body: "TMflow -> Python 9001。先用純文字 READY、HB、BUSY、DONE，確認後再串 cmd_id。" }) +
    text(["此版本不把 ModbusDev 當節點；Network/Listen 等 Python 端確認後才加回主線。"], 180, 1180, { className: "warn" });
  return baseSvg(width, height, "Python 與 TMflow 資料交換（現場修正版）", "目前測 Move 時先跳過通訊；正式版仍使用 Listen 與 Network。", content);
}

function detailedDiagram() {
  const width = 4300;
  const height = 3550;
  const left = node({ x: 70, y: 220, w: 980, h: 520, id: "初始變數", type: "先建", tone: "blue", body: "status/error_code/completed_cmd_id/heartbeat/robot_state=0；flow_ok=true；has_piece=false；active_to=1；安全測試座標先用目前安全點。" }) +
    node({ x: 70, y: 790, w: 980, h: 430, id: "已知座標", type: "現場", tone: "green", body: "安全點 X363.30 Y13.18 Z532.27 RX-176.41 RY0.69 RZ83.93；死棋盒 X124.04 Y-202.49。" }) +
    node({ x: 70, y: 1270, w: 980, h: 430, id: "卡關處理", type: "B7", tone: "red", body: "B7 在 active_to=1 仍不過，先跳過 B6/B7/B8；主線通過後刪掉 B7 重新拖 If。" }) +
    node({ x: 70, y: 1750, w: 980, h: 520, id: "Network / Listen", type: "後補", tone: "cyan", body: "A5/B3/B5/F3 等 Python 9001 開啟後再測；Listen1 沒資料會停住，正式版才接回。" });
  const laneW = 510;
  const gap = 24;
  const main = columns
    .map((col, index) => {
      const x = 1120 + index * (laneW + gap);
      const nodeH = col.nodes.length > 8 ? 82 : 108;
      const nodeGap = 14;
      return `${lane({ x, y: 220, w: laneW, h: 2910, title: col.title, tone: col.tone })}${col.nodes
        .map(([id, type, desc], i) => node({ x: x + 18, y: 315 + i * (nodeH + nodeGap), w: laneW - 36, h: nodeH, id, type, body: desc, tone: col.tone }))
        .join("")}`;
    })
    .join("");
  return baseSvg(width, height, "TMflow 1.82.51 節點設定工程版（現場修正版）", "左側列當前問題與參數；右側列安全假流程、跳過項目與後續加回順序。", left + main + text(["節點名稱能改才輸入 A1、A2...；不能改名的 Listen/Move/Point 以畫面位置對照手冊。"], 70, 3300, { className: "warn" }));
}

function writeSvg(name, svg) {
  const svgPath = path.join(docsDir, name);
  fs.writeFileSync(svgPath, svg, "utf8");
  return svgPath;
}

async function render(svgPath, pngName, clip = null) {
  const svg = fs.readFileSync(svgPath, "utf8");
  const match = svg.match(/<svg[^>]*width="(\d+)" height="(\d+)"/);
  if (!match) throw new Error(`Cannot read SVG size: ${svgPath}`);
  const width = Number(match[1]);
  const height = Number(match[2]);
  const htmlPath = path.join(docsDir, `${path.basename(svgPath)}.preview.html`);
  fs.writeFileSync(htmlPath, `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;width:${width}px;height:${height}px;background:#f5f7fb}img{display:block;width:${width}px;height:${height}px}</style><img src="${path.basename(svgPath)}">`, "utf8");
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    await page.goto(`file://${htmlPath.replaceAll("\\", "/")}`);
    await page.screenshot({ path: path.join(docsDir, pngName), fullPage: !clip, clip: clip || undefined });
  } finally {
    await browser.close();
    fs.unlinkSync(htmlPath);
  }
}

export async function generateTmflowLeftPaletteDiagrams() {
  const outputs = [
    ["tmflow_1_82_51_node_design.svg", simpleFlowDiagram(), "tmflow_1_82_51_node_design.png"],
    ["tmflow_python_exchange_flowchart.svg", exchangeDiagram(), "tmflow_python_exchange_flowchart.png"],
    ["tmflow_full_python_exchange_flowchart.svg", exchangeDiagram(), "tmflow_full_python_exchange_flowchart.png"],
    ["tmflow_1_82_51_full_node_design.svg", simpleFlowDiagram(), "tmflow_1_82_51_full_node_design.png"],
    ["tmflow_1_82_51_full_node_expanded_ag.svg", expandedDiagram(), "tmflow_1_82_51_full_node_expanded_ag.png"],
    ["tmflow_1_82_51_detailed_node_setup.svg", detailedDiagram(), "tmflow_1_82_51_detailed_node_setup.png"],
    ["tmflow_1_82_51_clear_node_flow.svg", simpleFlowDiagram(), "tmflow_1_82_51_clear_node_flow.png"],
  ];
  for (const [svgName, svg, pngName] of outputs) {
    const svgPath = writeSvg(svgName, svg);
    await render(svgPath, pngName);
    console.log(`Wrote docs/${svgName}`);
    console.log(`Wrote docs/${pngName}`);
  }
  const detailedPath = path.join(docsDir, "tmflow_1_82_51_detailed_node_setup.svg");
  await render(detailedPath, "tmflow_1_82_51_node_setup_params.png", { x: 40, y: 170, width: 1050, height: 2200 });
  await render(detailedPath, "tmflow_1_82_51_node_setup_main_abc.png", { x: 1100, y: 170, width: 1650, height: 1900 });
  await render(detailedPath, "tmflow_1_82_51_node_setup_capture.png", { x: 2150, y: 170, width: 1120, height: 1750 });
  await render(detailedPath, "tmflow_1_82_51_node_setup_move.png", { x: 2680, y: 170, width: 1120, height: 1950 });
  await render(detailedPath, "tmflow_1_82_51_node_setup_done_error.png", { x: 3220, y: 170, width: 1080, height: 1600 });
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  await generateTmflowLeftPaletteDiagrams();
}
