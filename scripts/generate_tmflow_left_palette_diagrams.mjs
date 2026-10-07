import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { createReadableTmflowDiagram } from "./tmflow_readable_diagram.mjs";

const filename = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(filename), "..");
const docs = path.join(root, "docs");
const model = JSON.parse(fs.readFileSync(path.join(docs, "tmflow_v3_nodes.json"), "utf8"));
const nodes = model.groups.flatMap((group) => group.nodes);
const ids = new Set(nodes.map((node) => node.id));
if (ids.size !== nodes.length) throw new Error("Duplicate node id");
for (const node of nodes) {
  for (const target of Object.values(node.next)) {
    if (!ids.has(target)) throw new Error(`Missing node: ${node.id} -> ${target}`);
  }
}
const visited = new Set();
function visit(id) {
  if (visited.has(id)) return;
  visited.add(id);
  Object.values(nodes.find((node) => node.id === id).next).forEach(visit);
}
visit("A1");
if (visited.size !== ids.size) throw new Error("Unreachable node in design");

function trace(choices) {
  const route = [];
  let id = "B1";
  while (!["L1", "G1"].includes(id)) {
    assert(route.length < nodes.length, "Command route must terminate");
    route.push(id);
    const node = nodes.find((item) => item.id === id);
    id = node.next[choices[id] || "next"];
    assert(id, `Missing branch choice at ${node.id}`);
  }
  return { route, terminal: id };
}
const scan = trace({ B1: "yes", B3: "no" });
const move = trace({ B1: "yes", B3: "yes" });
const rejected = trace({ B1: "no" });
assert.equal(nodes.length, 23, "Minimal design has 23 nodes including Start and Stop");
assert.equal(nodes.filter(n => n.type === "Vision").length, 1);
assert.equal(nodes.filter(n => n.type === "Network").length, 1);
assert.equal(nodes.filter(n => n.type === "If").length, 2);
assert.deepEqual(scan.route, ["B1", "B2", "B3", "M12", "S1", "S2", "S3", "F1"]);
assert.deepEqual(move.route, ["B1", "B2", "B3",
  ...Array.from({ length: 12 }, (_, i) => `M${i + 1}`), "S1", "S2", "S3", "F1"]);
for (const result of [scan, move]) {
  assert.equal(result.terminal, "L1");
  assert.equal(result.route.filter(id => nodes.find(n => n.id === id).type === "Vision").length, 1);
  assert(result.route.indexOf("S3") < result.route.indexOf("F1"), "Image precedes DONE");
}
assert.deepEqual(rejected, { route: ["B1"], terminal: "G1" });
assert.deepEqual(nodes.find(n => n.id === "G1").next, {});
assert.deepEqual(["M2", "M3", "M6", "M7", "M8", "M11"].map(id => nodes.find(n => n.id === id).point),
  ["P_SRC_ABOVE", "P_SRC_PICK", "P_SRC_ABOVE", "P_DST_ABOVE", "P_DST_PLACE", "P_DST_ABOVE"],
  "Pick/place must lift before transfer and before leaving destination");
assert.equal(nodes.find(n => n.id === "M5").type, "Wait for");
assert.equal(nodes.find(n => n.id === "M10").type, "Wait for");
for (const id of ["S3", "F1"]) {
  const failed = trace({ B1: "yes", B3: "yes", [id]: "failure" });
  assert.equal(failed.terminal, "G1");
  if (id === "S3") assert(!failed.route.includes("F1"), "Failed upload cannot report DONE");
}

const escape = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const labels = { next: "下一步", failure: "失敗", pass: "Pass", yes: "是", no: "否", scan: "拍攝", move: "移子", capture: "吃子", normal: "一般" };
const nextText = (node) => Object.entries(node.next).map(([key, value]) => `${labels[key]}: ${value}`).join(" / ") || "停止";

function wrap(value, maxWidth, fontSize) {
  const lines = [];
  let line = "";
  let width = 0;
  for (const char of String(value)) {
    const advance = char.codePointAt(0) > 255 ? fontSize : fontSize * 0.61;
    if (width + advance > maxWidth && line) {
      lines.push(line);
      line = "";
      width = 0;
    }
    line += char;
    width += advance;
  }
  if (line) lines.push(line);
  return lines;
}

function textLines(value, x, y, width, size = 17, color = "#263238") {
  return wrap(value, width, size).map((line, i) => `<text x="${x}" y="${y + i * (size + 7)}" font-size="${size}" fill="${color}">${escape(line)}</text>`).join("");
}

function svg(width, height, title, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(title)}"><style>text{font-family:Microsoft JhengHei,Arial,sans-serif;letter-spacing:0}</style><rect width="100%" height="100%" fill="#f6f8f9"/>${textLines(title, 28, 42, width - 56, 25)}${textLines(`v${model.version} / ${model.date} / 設計規格，尚未整合實機執行`, 28, 74, width - 56, 15, "#526167")}${body}</svg>`;
}

function groupDiagram(groups, title) {
  const columnWidth = 610;
  const columns = Math.min(groups.length, 3);
  const positions = [];
  let top = 108;
  for (let i = 0; i < groups.length; i += columns) {
    const row = groups.slice(i, i + columns);
    const heights = row.map((group) => 65 + group.nodes.reduce((height, node) => height + 54 + wrap(node.task, columnWidth - 66, 17).length * 24 + wrap(nextText(node), columnWidth - 66, 14).length * 21, 0));
    row.forEach((group, j) => positions.push({ group, x: 20 + j * columnWidth, y: top, height: heights[j] }));
    top += Math.max(...heights) + 24;
  }
  let body = "";
  for (const { group, x, y } of positions) {
    body += `<rect x="${x}" y="${y}" width="${columnWidth - 18}" height="40" fill="${group.id === "G" ? "#9b3434" : "#24675d"}"/>`;
    body += textLines(`${group.id}  ${group.title}`, x + 14, y + 28, columnWidth - 50, 20, "#ffffff");
    let cursor = y + 54;
    for (const node of group.nodes) {
      const taskLines = wrap(node.task, columnWidth - 66, 17).length;
      const nextLines = wrap(nextText(node), columnWidth - 66, 14).length;
      const height = 43 + taskLines * 24 + nextLines * 21;
      body += `<rect x="${x}" y="${cursor}" width="${columnWidth - 18}" height="${height}" rx="4" fill="#ffffff" stroke="#c8d0d4"/>`;
      body += textLines(`${node.id}  |  ${node.type}`, x + 14, cursor + 25, columnWidth - 50, 18, "#0b5d52");
      body += textLines(node.task, x + 14, cursor + 51, columnWidth - 66, 17);
      body += textLines(nextText(node), x + 14, cursor + 53 + taskLines * 24, columnWidth - 66, 14, "#5b6269");
      cursor += height + 11;
    }
  }
  return svg(columns * columnWidth + 22, top + 16, title, body);
}

function overview() {
  return createReadableTmflowDiagram(model);
}

function exchange() {
  const rows = [
    ["PC → Listen", "5890 / TMSCT：kind、cmd_id、4 個 Point.Value；完整寫入成功後才 ScriptExit()。"],
    ["TMflow 取放", "SCAN 跳過取放；MOVE 共用來源到目的的流程。吃子由 PC 排兩筆 MOVE。"],
    ["Vision → PC", "JOB_BOARD 只拍一張；HTTP POST /api/vision/tmvision/classify，成功回 frame_received。"],
    ["Network → PC", "沿用 telemetry 接收埠（範例 9001），JSON line 帶 completed_command_id；行尾 CRLF。"],
    ["PC → 下一筆", "收到本筆 DONE 且流程回 Listen 後再派令。逾時結果未知，不自動重送 MOVE。"]
  ];
  const body = rows.map(([title, desc], i) => {
    const y = 112 + i * 130;
    return `<rect x="28" y="${y}" width="1080" height="106" rx="4" fill="#ffffff" stroke="#c8d0d4"/>${textLines(title, 44, y + 30, 250, 20, "#0b5d52")}${textLines(desc, 310, y + 30, 775, 18)}`;
  }).join("");
  return svg(1136, 800, "Python / TMflow / 單張影像資料交換", body);
}

function captureReuse() {
  const steps = [
    ["第一筆 MOVE", "來源＝被吃棋；目的＝死棋盒。共用 M1–M12，拍一張並回 DONE。"],
    ["PC 等待", "確認第一筆 DONE 且已回 Listen。中間照片只供觀察，不發布正式棋局。"],
    ["第二筆 MOVE", "來源＝己方棋；目的＝剛清空的棋格。再用 M1–M12，拍一張並回 DONE。"],
    ["結果", "最終照片用於整手複驗；TMflow 不增加吃子專用節點。PC 分組排程仍待接入。"]
  ];
  return svg(1136, 650, "吃子：兩筆命令重用同一取放段", steps.map(([title, desc], i) => {
    const y = 112 + i * 130;
    return `<rect x="28" y="${y}" width="1080" height="108" fill="#ffffff" stroke="#c8d0d4"/>${textLines(title, 44, y + 30, 230, 20, "#0b5d52")}${textLines(desc, 290, y + 30, 790, 18)}`;
  }).join(""));
}

function guide() {
  const lines = [
    `# ${model.title}：逐節點設定表`, "",
    `版本 ${model.version}；更新 ${model.date}。共 ${nodes.length} 個節點（含 Start / Stop）；設計規格，尚未實機驗證。`, "",
    "本表與圖由同一份 `tmflow_v3_nodes.json` 產生。執行 `scripts/generate_tmflow_left_palette_diagrams.mjs` 同步；`--check` 驗證結構與產物一致性。", "",
    "接線／命令／回報格式見 [設計書](TMFLOW_1_82_51_FULL_NODE_DESIGN.md)，現場填寫見 [操作表](TMFLOW_1_82_51_FIELD_OPERATION_MANUAL.md)。", "",
    "## 共通設定", "", ...model.assumptions.map(item => `- ${item}`),
    "- 所有 Point 精準到位、不混合；Point 的 PTP/Line 是運動模式，不另加 Move 節點。",
    "- Point 系統警報由控制器停止，不假設存在 Fail 接腳；只連現場實際提供的 Listen/Vision/Network Fail 到 G1。",
    "- G1 不保證維持吸附：Stop/Error 的 DO3 行為依控制器設定，需在初始設定記錄。",
    "- 一個 Set 可放多項設定；A2 合併啟動變數與 DO3，B2 合併保存編號與清旗標。", "",
    "## 全流程圖", "", "![單張拍攝與共用取放](tmflow_1_82_51_full_node_design.png)", "",
    "[開啟向量圖](tmflow_1_82_51_full_node_design.svg)。SCAN：B3 否 → M12 → S1；MOVE：B3 是 → M1–M12 → S1；兩者均 S1–S3 → F1 → L1。", ""
  ];
  for (const group of model.groups) {
    lines.push(`## ${group.id}：${group.title}`, "", "| 節點 | 類型 | 設定與動作 | 出口 |", "| --- | --- | --- | --- |");
    for (const node of group.nodes) lines.push(`| ${node.id} | ${node.type} | ${node.task.replaceAll("|", "&#124;")} | ${nextText(node)} |`);
    lines.push("");
  }
  lines.push("## 先接這三條資料路徑", "",
    "1. PC → L1：TMSCT 寫 4 個動態點與命令，成功後 ScriptExit()；TCP 連上本身不代表命令已接受。",
    "2. S3 → PC：JOB_BOARD 每次重新取像，HTTP 上傳單張，收到 frame_received 才通過。",
    "3. F1 → PC：傳送 JSON line 的 completed_command_id；保留現場金鑰，行尾 CRLF；成功出口回 L1。", "",
    "DONE 表示本筆取放／拍攝流程已走完且影像接收成功，不代表辨識成功或棋局已更新。此版只發 DONE；失敗走 Stop，PC 以逾時或斷線偵測，沒有另外的 ERR 回報節點。", "",
    "## 共用吃子流程", "",
    "PC 依序送兩筆不同 cmd_id 的 MOVE：目標棋 → 死棋盒；己方棋 → 目標格。每筆各拍一張，第一筆照片不作正式棋局更新。這是共用流程的取捨；棋局分組與正式 Listen 發送器尚待接入。", "");
  return lines.join("\n");
}

function buildDiagrams() {
  return [
    ["tmflow_1_82_51_full_node_design", overview()],
    ["tmflow_python_exchange_flowchart", exchange()],
    ["tmflow_1_82_51_full_node_expanded_ag", groupDiagram(model.groups, "23 個節點與每個出口")],
    ["tmflow_1_82_51_detailed_node_setup", groupDiagram(model.groups, "TMflow v3.1 單張最小流程")],
    ["tmflow_1_82_51_node_setup_params", groupDiagram(model.groups.filter(g => ["A", "B"].includes(g.id)), "啟動與接令")],
    ["tmflow_1_82_51_node_setup_main_abc", groupDiagram(model.groups.filter(g => ["A", "B", "S"].includes(g.id)), "接令與單張拍攝")],
    ["tmflow_1_82_51_node_setup_capture", captureReuse()],
    ["tmflow_1_82_51_node_setup_move", groupDiagram(model.groups.filter(g => g.id === "M"), "共用取放路徑")],
    ["tmflow_1_82_51_node_setup_done_error", groupDiagram(model.groups.filter(g => ["F", "G"].includes(g.id)), "DONE 回報與停止")]
  ];
}

export async function generateTmflowLeftPaletteDiagrams() {
  const diagrams = buildDiagrams();
  if (process.argv.includes("--check")) {
    assert.equal(fs.readFileSync(path.join(docs, "TMFLOW_1_82_51_NODE_SETUP_GUIDE.md"), "utf8"), guide(),
      "Generated guide is stale; regenerate diagrams and guide");
    for (const [name, content] of diagrams) assert.equal(fs.readFileSync(path.join(docs, `${name}.svg`), "utf8"), content, `Stale diagram: ${name}`);
    console.log(`Validated ${nodes.length} nodes, SCAN/MOVE/reject and failure paths, guide and ${diagrams.length} SVGs.`);
    return;
  }
  fs.writeFileSync(path.join(docs, "TMFLOW_1_82_51_NODE_SETUP_GUIDE.md"), guide(), "utf8");
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ deviceScaleFactor: 1 });
    for (const [name, content] of diagrams) {
      fs.writeFileSync(path.join(docs, `${name}.svg`), content, "utf8");
      const [, width, height] = content.match(/width="(\d+)" height="(\d+)"/);
      await page.setViewportSize({ width: Number(width), height: Number(height) });
      await page.setContent(`<!doctype html><meta charset="utf-8"><style>body{margin:0}svg{display:block}</style>${content}`);
      await page.evaluate(() => document.fonts.ready);
      const overflow = await page.evaluate(() => [...document.querySelectorAll("text")].some((element) => {
        const box = element.getBBox();
        const view = element.ownerSVGElement.viewBox.baseVal;
        return box.x < 0 || box.y < 0 || box.x + box.width > view.width || box.y + box.height > view.height;
      }));
      if (overflow) throw new Error(`Text extends outside diagram: ${name}`);
      const overwide = await page.evaluate(() => [...document.querySelectorAll("text[data-max-width]")]
        .filter((element) => element.getBBox().width > Number(element.dataset.maxWidth))
        .map((element) => element.textContent));
      if (overwide.length) throw new Error(`Text exceeds reserved width: ${overwide.join("; ")}`);
      await page.screenshot({ path: path.join(docs, `${name}.png`), fullPage: true });
      console.log(`Generated ${name}`);
    }
  } finally {
    await browser.close();
  }
  console.log(`Validated ${nodes.length} nodes and regenerated guide and ${diagrams.length} diagrams.`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === filename) await generateTmflowLeftPaletteDiagrams();
