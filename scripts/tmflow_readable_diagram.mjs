import assert from "node:assert/strict";

export function createReadableTmflowDiagram(model) {
  const nodes = model.groups.flatMap(g => g.nodes);
  const represented = [];
  const elements = [];
  const escape = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const colors = { ink: "#243238", muted: "#65747a", green: "#16705c", blue: "#286c9b", red: "#ab4545" };
  function text(x, y, value, size = 18, color = colors.ink, width = 0) {
    elements.push(`<text x="${x}" y="${y}" font-size="${size}" fill="${color}"${width ? ` data-max-width="${width}"` : ""}>${escape(value)}</text>`);
  }
  function arrow(points, color = colors.green, dashed = false) {
    elements.push(`<path d="${points.map(([x,y],i) => `${i ? "L" : "M"}${x} ${y}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2.5"${dashed ? ' stroke-dasharray="6 5"' : ""} marker-end="url(#arrow-${color.slice(1)})"/>`);
  }
  function box(id, x, y, height, title, details = [], color = colors.green, width = 450) {
    const node = nodes.find(n => n.id === id);
    assert(node, `Unknown diagram node ${id}`);
    represented.push(id);
    elements.push(`<g data-flow-box="${id}"><rect x="${x}" y="${y}" width="${width}" height="${height}" rx="7" fill="#fff" stroke="#cedcde"/><rect x="${x}" y="${y}" width="5" height="${height}" rx="2" fill="${color}"/>`);
    text(x+18,y+23,`${id} / ${node.type}`,14,color,width-36);
    text(x+18,y+52,title,22,colors.ink,width-36);
    details.forEach((line,i)=>text(x+18,y+79+i*24,line,17,colors.muted,width-36));
    elements.push("</g>");
  }
  elements.push('<rect width="1800" height="1770" fill="#f4f8f8"/><rect width="1800" height="160" fill="#fff"/>');
  text(70,48,"S.M.A.R.T. CHESS ROBOT  /  TMflow 1.82.51",17,colors.green);
  text(70,103,"單張拍攝・23 個節點",40);
  text(70,139,`v${model.version} / ${model.date}　接收 → 共用取放 → 拍一張 → 傳出 → 等下一筆`,20,colors.muted);
  text(1280,60,"設計規格・尚未實機驗證",22,colors.red);
  text(1280,96,"舊版 55 → 新版 23（含 Start / Stop）",18,colors.muted);
  text(70,191,"01  接收與分流",22,colors.green);
  text(670,191,"02  共用取放（MOVE）",22,colors.green);
  text(1270,191,"03  拍照與向外傳遞",22,colors.blue);

  box("A1",70,210,82,"Start：空載啟動");
  box("A2",70,330,120,"初始化 DO3 與命令變數",["釋放吸盤；ready=false；命令編號歸零","只執行一次，不接回循環"]);
  box("L1",70,490,104,"Listen：等電腦送入命令",["寫入點位成功 → ScriptExit() → Pass"]);
  box("B1",70,634,130,"完整且為新編號？",["ready=true、cmd_id > last_cmd_id","kind 只接受 1 / 2；否則停止"]);
  box("B2",70,804,104,"記住編號，消耗本筆命令",["last_cmd_id=cmd_id；ready=false"]);
  box("B3",70,948,104,"kind == 2？",["是：MOVE　／　否：SCAN"]);
  [[292,330],[450,490],[594,634],[764,804],[908,948]].forEach(([a,b])=>arrow([[295,a],[295,b]]));
  text(315,790,"是",15,colors.green);

  const motion = [
    ["取放起點 P_READY_SAFE","PTP；空載離開拍照姿態"],
    ["來源上方 P_SRC_ABOVE","Line；到來源棋上方"],
    ["下降 P_SRC_PICK","Line；垂直下降，精準到位"],
    ["吸附：DO3 開啟","使用已確認的 SUCTION_LEVEL"],
    ["等待吸附","grip_wait_ms"],
    ["抬升 P_SRC_ABOVE","Line；先升高再橫移"],
    ["移至 P_DST_ABOVE","Line；在轉移高度橫移"],
    ["下降 P_DST_PLACE","Line；垂直下降，精準到位"],
    ["釋放：DO3 釋放","使用已確認的 RELEASE_LEVEL"],
    ["等待釋放","release_wait_ms"],
    ["抬升 P_DST_ABOVE","Line；離開棋子或收納盒"],
    ["回 P_READY_SAFE","Line；空載進入拍照段"]
  ];
  motion.forEach(([title,detail],i)=>{
    const y=210+i*108;
    box(`M${i+1}`,670,y,90,title,[detail]);
    if(i<11) arrow([[895,y+90],[895,y+108]]);
  });
  arrow([[520,1000],[580,1000],[580,255],[670,255]]);
  text(535,979,"是",16,colors.green);
  arrow([[295,1052],[295,1443],[670,1443]]);
  text(320,1113,"否：SCAN 跳過取放",19,colors.green);
  text(320,1145,"直接走 M12 → S1",18,colors.muted);

  box("S1",1270,370,104,"P_PHOTO：單一拍照點",["PTP；整個棋盤入鏡"],colors.blue,460);
  box("S2",1270,514,104,"等影像穩定",["settle_ms"],colors.blue,460);
  box("S3",1270,658,128,"Vision：JOB_BOARD",["新拍一張 → HTTP 上傳至 PC","收到 frame_received 才通過"],colors.blue,460);
  box("F1",1270,826,128,"Network：傳送 DONE",["JSON line + completed_command_id","成功後直接回 Listen"],colors.blue,460);
  arrow([[1120,1443],[1195,1443],[1195,422],[1270,422]]);
  [[474,514],[618,658],[786,826]].forEach(([a,b])=>arrow([[1500,a],[1500,b]],colors.blue));
  arrow([[1730,890],[1780,890],[1780,1550],[40,1550],[40,542],[70,542]]);
  text(810,1535,"回 Listen：留在拍照點等下一筆",19,colors.green);

  text(1288,1030,"PC → L1：TMSCT / 5890",19,colors.blue,420);
  text(1288,1062,"S3 → PC：HTTP 單張影像",19,colors.blue,420);
  text(1288,1094,"F1 → PC：TCP 完成編號",19,colors.blue,420);
  text(1288,1132,"拍照與回報是兩條不同連線。",17,colors.muted,420);
  box("G1",1270,1280,120,"Stop：故障停止",["不自動重搬、不盲目回家或關吸盤","PC 逾時標記結果未知，人工確認"],colors.red,460);
  arrow([[70,699],[20,699],[20,1620],[1500,1620],[1500,1400]],colors.red,true);
  text(78,1610,"B1 否 / L1 Fail → Stop；Point 系統警報由控制器停止",17,colors.red);
  arrow([[1730,722],[1750,722],[1750,1340],[1730,1340]],colors.red,true);
  arrow([[1730,925],[1750,925]],colors.red,true);
  text(1270,1252,"Vision / Network 的可用 Fail 出口",16,colors.red);

  text(70,1680,"吃子：PC 先送「目標棋 → 死棋盒」，DONE 後再送「來源棋 → 目標格」。兩筆共用 M1–M12。",21,colors.ink);
  text(70,1720,"每筆只拍一張；第一筆中間照片不發布棋局。DO3、全盤取景與所有路徑仍需現場核對。",18,colors.muted);
  assert.deepEqual([...represented].sort(),nodes.map(n=>n.id).sort(),"Every node must appear exactly once");
  const defs = Object.values(colors).map(c=>`<marker id="arrow-${c.slice(1)}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M1 1 L7 4 L1 7" fill="none" stroke="${c}" stroke-width="1.3"/></marker>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1770" viewBox="0 0 1800 1770" role="img" aria-labelledby="title desc"><title id="title">TMflow v${model.version} 單張最小流程</title><desc id="desc">完整 23 節點，SCAN 跳過取放、MOVE 共用取放，單張上傳後回報完成。</desc><style>text{font-family:Microsoft JhengHei,Arial,sans-serif}</style><defs>${defs}</defs>${elements.join("")}</svg>`;
}
