import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const REPORT_DIR = path.join(ROOT, 'reports');
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '').replace('T', '-');
const PORT = Number(process.env.HTML_CHECK_PORT || 5123);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const ADMIN_PASSWORD = `html-check-${stamp}`;
const DB_PATH = path.join(REPORT_DIR, `smart-chess-html-check-${stamp}.db`);

const results = [];
const comparisons = [];
const consoleErrors = [];
const consoleWarnings = [];
const serverLines = [];

function addResult(area, item, ok, detail = '') {
  results.push({ area, item, ok: Boolean(ok), detail: String(detail || '') });
}

function addComparison(item, backend, frontend, ok) {
  comparisons.push({
    item,
    backend: String(backend ?? ''),
    frontend: String(frontend ?? ''),
    ok: Boolean(ok),
  });
}

function truncate(value, max = 320) {
  const text = String(value ?? '');
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function isKnownConsoleWarning(message) {
  const text = String(message || '');
  return text.includes('WebSocket connection to')
    && text.includes('/socket.io/')
    && text.includes('Invalid frame header');
}

async function waitForServer(server) {
  const deadline = Date.now() + 30000;
  let lastError = '';
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`Flask exited early with code ${server.exitCode}. ${serverLines.slice(-20).join('\n')}`);
    }
    try {
      const response = await fetch(`${BASE_URL}/api/ready`, { method: 'GET' });
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for Flask server. Last error: ${lastError}`);
}

function startServer() {
  const pythonExe = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
  const env = {
    ...process.env,
    ADMIN_PASSWORD,
    ALLOW_INSECURE_DEFAULTS: 'true',
    APP_ENV: 'development',
    AUTO_EXECUTE_ROBOT: 'false',
    CHESS_SECRET_KEY: `html-check-secret-${stamp}-0123456789abcdef`,
    CONTROL_AUTH_REQUIRED: 'true',
    CORS_ALLOWED_ORIGINS: BASE_URL,
    DB_PATH,
    ENGINE_AUTO_ANALYZE: 'false',
    ENGINE_PROBE_ON_BOOT: 'false',
    FAKE_AI: 'true',
    FAKE_ROBOT: 'true',
    FAKE_VISION: 'true',
    LOG_LEVEL: 'WARNING',
    PORT: String(PORT),
    RATE_LIMITS_ENABLED: 'false',
    SYSTEM_MODE: 'simulation',
    TEST_MODE: 'true',
  };
  const server = spawn(pythonExe, ['main.py'], {
    cwd: ROOT,
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const capture = (chunk) => {
    const text = chunk.toString('utf8');
    text.split(/\r?\n/).filter(Boolean).forEach((line) => {
      if (serverLines.length < 240) serverLines.push(line);
    });
  };
  server.stdout.on('data', capture);
  server.stderr.on('data', capture);
  return server;
}

async function apiJson(pathname, token, options = {}) {
  const response = await fetch(`${BASE_URL}${pathname}`, {
    method: options.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  return { status: response.status, ok: response.ok, payload, bytes: Buffer.byteLength(text) };
}

async function apiBlob(pathname, token) {
  const response = await fetch(`${BASE_URL}${pathname}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const buffer = Buffer.from(await response.arrayBuffer());
  return {
    status: response.status,
    ok: response.ok,
    bytes: buffer.length,
    contentType: response.headers.get('content-type') || '',
  };
}

async function waitForLiveControls(page) {
  await page.waitForFunction(
    () => document.body?.dataset?.connectionStatus === 'online' && document.body?.dataset?.stateStale === 'false',
    { timeout: 15000 },
  );
}

async function text(page, selector) {
  return (await page.locator(selector).textContent({ timeout: 5000 }) || '').trim();
}

async function click(page, selector) {
  const locator = page.locator(selector);
  const count = await locator.count();
  if (count !== 1) throw new Error(`Selector ${selector} matched ${count} elements`);
  await locator.click();
}

async function setSafeMode(page, checked) {
  const toggle = page.locator('#safe-mode-toggle');
  const count = await toggle.count();
  if (count !== 1) throw new Error(`#safe-mode-toggle matched ${count} elements`);
  if ((await toggle.isChecked()) !== checked) {
    await page.locator('label.sidebar-toggle-row').click();
  }
  await page.waitForFunction((expected) => document.querySelector('#safe-mode-toggle')?.checked === expected, checked, {
    timeout: 8000,
  });
}

async function runBrowserChecks(token) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport: { width: 1440, height: 920 },
  });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const body = message.text();
      if (isKnownConsoleWarning(body)) consoleWarnings.push(body);
      else consoleErrors.push(body);
    }
  });
  page.on('pageerror', (error) => {
    if (isKnownConsoleWarning(error.message)) consoleWarnings.push(error.message);
    else consoleErrors.push(error.message);
  });

  const screenshots = {};
  try {
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
    await page.locator('#view-landing').waitFor({ state: 'visible', timeout: 10000 });
    addResult('前台導覽', 'Landing 頁載入', true, await page.title());
    addResult('前台導覽', '玩家模式按鈕存在', await page.locator('#btn-role-player').isVisible());
    addResult('前台導覽', '主控台模式按鈕存在', await page.locator('#btn-role-console').isVisible());

    await click(page, '#btn-role-player');
    await page.locator('#view-player.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('前台導覽', '玩家模式切換', true, 'view-player.active');
    screenshots.player = path.join(REPORT_DIR, `html-check-${stamp}-player.png`);
    await page.screenshot({ path: screenshots.player, fullPage: true });

    await click(page, '#btn-exit');
    await page.locator('#view-landing.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('前台導覽', '返回首頁', true, 'view-landing.active');

    await click(page, '#btn-role-console');
    await page.locator('#auth-overlay.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('權限流程', '未登入會顯示 Admin unlock', true, 'auth-overlay.active');
    await click(page, '#btn-auth-cancel');
    await page.locator('#view-landing.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('權限流程', '取消登入可返回首頁', true, 'view-landing.active');
    await click(page, '#btn-role-console');
    await page.locator('#auth-overlay.active').waitFor({ state: 'attached', timeout: 8000 });
    await page.locator('#admin-password').fill(ADMIN_PASSWORD);
    await click(page, '#admin-login-form button[type="submit"]');
    await page.locator('#view-console.active').waitFor({ state: 'attached', timeout: 10000 });
    await waitForLiveControls(page);
    addResult('權限流程', 'Admin 登入後進入 Console', true, 'socket online + fresh state');

    await click(page, '#btn-toggle-video');
    await page.locator('#pane-video-view.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('前台主視圖', '切換即時影像 pane', true, 'pane-video-view.active');
    const videoSrc = await page.locator('#vision-live-feed').getAttribute('src');
    addResult('前台主視圖', '即時影像來源已連接', String(videoSrc || '').includes('/api/video_feed'), videoSrc || '');
    addResult('前台主視圖', '影像狀態顯示存在', await page.locator('#video-status-pill').count() === 1);
    addResult('前台主視圖', 'YOLO overlay canvas 存在', await page.locator('#yolo-canvas').count() === 1);
    await click(page, '#btn-toggle-board');
    await page.locator('#pane-board-view.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('前台主視圖', '切回棋盤 pane', true, 'pane-board-view.active');

    await click(page, '#btn-toggle-status');
    await page.locator('#pane-status-view.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('前台主視圖', '狀態 pane 可切換', true, 'pane-status-view.active');

    await click(page, '.depth-btn[data-depth="20"]');
    await page.waitForFunction(() => document.querySelector('#dashboard-engine-depth')?.textContent?.trim() === '20', { timeout: 8000 });
    addResult('AI 控制', 'AI Depth 20 按鈕更新前台', true, await text(page, '#dashboard-engine-depth'));
    const depthBackend = await apiJson('/api/runtime/control', token);
    addResult('AI 控制', 'AI Depth 後台狀態更新', depthBackend.payload.engine_depth === 20, depthBackend.payload.engine_depth);

    await setSafeMode(page, false);
    await page.waitForFunction(() => document.querySelector('#dashboard-safety-safe-mode')?.textContent?.trim() === '已停用', { timeout: 8000 });
    const safeOff = await apiJson('/api/runtime/control', token);
    addResult('Safety 控制', 'Safe Mode toggle OFF 前後端更新', safeOff.payload.safe_mode === false, await text(page, '#dashboard-safety-safe-mode'));
    await setSafeMode(page, true);
    await page.waitForFunction(() => document.querySelector('#dashboard-safety-safe-mode')?.textContent?.trim() === '已啟用', { timeout: 8000 });
    const safeOn = await apiJson('/api/runtime/control', token);
    addResult('Safety 控制', 'Safe Mode toggle ON 前後端更新', safeOn.payload.safe_mode === true, await text(page, '#dashboard-safety-safe-mode'));

    await page.locator('#session-participant-id').fill('E2E-001');
    await click(page, '#btn-session-start');
    await page.waitForFunction(() => document.querySelector('#dashboard-exp-session-status')?.textContent?.trim() === '進行中', { timeout: 8000 });
    const sessionOn = await apiJson('/api/runtime/control', token);
    addResult('Experiment', 'Session Start', sessionOn.payload.session?.active === true, await text(page, '#dashboard-exp-session-id'));
    addResult('Experiment', 'Participant ID 呈現', await text(page, '#dashboard-exp-participant') === 'E2E-001', await text(page, '#dashboard-exp-participant'));
    await click(page, '#btn-session-end');
    await page.waitForFunction(() => document.querySelector('#dashboard-exp-session-status')?.textContent?.trim() === '已結束', { timeout: 8000 });
    const sessionOff = await apiJson('/api/runtime/control', token);
    addResult('Experiment', 'Session End', sessionOff.payload.session?.active === false, await text(page, '#dashboard-exp-session-status'));

    await click(page, '#btn-estop-trigger');
    await page.waitForFunction(
      () => document.querySelector('#pause-overlay')?.classList.contains('active')
        || document.querySelector('#dashboard-safety-estop')?.textContent?.trim() === 'Triggered',
      { timeout: 8000 },
    ).catch(() => {});
    const estopOverlayOn = await page.locator('#pause-overlay.active').count() === 1;
    const estopOn = await apiJson('/api/estop/status', token);
    addResult(
      'Safety 控制',
      'E-Stop trigger 顯示 overlay 並更新後台',
      estopOn.payload.triggered === true && estopOverlayOn,
      `backend=${estopOn.payload.triggered}; overlay=${estopOverlayOn}; frontend=${await text(page, '#dashboard-safety-estop')}`,
    );
    if (estopOverlayOn) {
      await click(page, '#btn-resume-overlay');
    } else {
      await apiJson('/api/estop/reset', token, {
        method: 'POST',
        body: { reason: 'html_check_reset_after_missing_overlay' },
      });
      await page.evaluate(() => {
        const overlay = document.getElementById('pause-overlay');
        overlay?.classList.add('hidden');
        overlay?.classList.remove('active');
      });
    }
    await page.waitForFunction(() => document.querySelector('#pause-overlay')?.classList.contains('active') === false, { timeout: 10000 });
    const estopOff = await apiJson('/api/estop/status', token);
    const estopOverlayOff = await page.locator('#pause-overlay.active').count() === 0;
    addResult(
      'Safety 控制',
      'E-Stop reset 清除 overlay 與後台',
      estopOff.payload.triggered === false && estopOverlayOff,
      `backend=${estopOff.payload.triggered}; overlayActive=${!estopOverlayOff}; frontend=${await text(page, '#dashboard-safety-estop')}`,
    );
    await waitForLiveControls(page);

    await click(page, '.tab-btn[data-tab="export"]');
    await page.locator('#pane-export.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('Sidebar', 'Export tab 可切換', true);
    const csvDownload = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      click(page, '#btn-export-csv'),
    ]).then(([download]) => download);
    const csvPath = await csvDownload.path();
    addResult('匯出功能', 'CSV 按鈕下載', Boolean(csvPath), csvDownload.suggestedFilename());

    const excelDownload = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      click(page, '#btn-export-excel'),
    ]).then(([download]) => download);
    const excelPath = await excelDownload.path();
    addResult('匯出功能', 'Excel 按鈕下載', Boolean(excelPath), excelDownload.suggestedFilename());

    await click(page, '.tab-btn[data-tab="logs"]');
    await page.locator('#pane-logs.active').waitFor({ state: 'attached', timeout: 8000 });
    const logText = await text(page, '#admin-logs');
    addResult('Sidebar', 'Logs tab 有系統事件', logText.length > 0, truncate(logText, 180));

    await click(page, '#btn-toggle-status');
    await page.locator('#pane-status-view.active').waitFor({ state: 'attached', timeout: 8000 });
    screenshots.console = path.join(REPORT_DIR, `html-check-${stamp}-console.png`);
    await page.screenshot({ path: screenshots.console, fullPage: true });
    addResult('前台畫面', 'Console screenshot 已保存', true, screenshots.console);

    const backend = {
      ready: (await apiJson('/api/ready', token)).payload,
      runtime: (await apiJson('/api/runtime/control', token)).payload,
      state: (await apiJson('/api/state', token)).payload,
      estop: (await apiJson('/api/estop/status', token)).payload,
      metrics: (await apiJson('/api/runtime/metrics', token)).payload,
      csv: await apiBlob('/api/export/csv', token),
    };
    const frontend = await page.evaluate(() => ({
      boardFen: document.querySelector('#dashboard-board-fen')?.textContent?.trim() || '',
      engineDepth: document.querySelector('#dashboard-engine-depth')?.textContent?.trim() || '',
      safeMode: document.querySelector('#dashboard-safety-safe-mode')?.textContent?.trim() || '',
      estop: document.querySelector('#dashboard-safety-estop')?.textContent?.trim() || '',
      participant: document.querySelector('#dashboard-exp-participant')?.textContent?.trim() || '',
      sessionStatus: document.querySelector('#dashboard-exp-session-status')?.textContent?.trim() || '',
      robotStatus: document.querySelector('#dashboard-robot-status')?.textContent?.trim() || '',
      logLength: document.querySelector('#admin-logs')?.textContent?.trim()?.length || 0,
      connectionStatus: document.body?.dataset?.connectionStatus || '',
      stateStale: document.body?.dataset?.stateStale || '',
    }));

    addComparison('ready', backend.ready.ready, 'Console loaded', backend.ready.ready === true);
    addComparison('socket/state freshness', 'online / false', `${frontend.connectionStatus} / ${frontend.stateStale}`, frontend.connectionStatus === 'online' && frontend.stateStale === 'false');
    addComparison('engine_depth', backend.runtime.engine_depth, frontend.engineDepth, Number(frontend.engineDepth) === Number(backend.runtime.engine_depth));
    addComparison('safe_mode', backend.runtime.safe_mode ? '已啟用' : '已停用', frontend.safeMode, frontend.safeMode === (backend.runtime.safe_mode ? '已啟用' : '已停用'));
    addComparison('estop', backend.estop.triggered ? '已觸發' : '正常', frontend.estop, frontend.estop === (backend.estop.triggered ? '已觸發' : '正常'));
    addComparison('session_active', backend.runtime.session?.active ? '進行中' : '已結束', frontend.sessionStatus, frontend.sessionStatus === (backend.runtime.session?.active ? '進行中' : '已結束'));
    addComparison('participant_id', backend.runtime.session?.participant_id || '', frontend.participant, frontend.participant === (backend.runtime.session?.participant_id || ''));
    const backendFen = backend.state.board?.fen || backend.state.fen || '';
    addComparison('board_fen', backendFen || '--', frontend.boardFen, frontend.boardFen === (backendFen || '--'));
    addComparison('runtime_metrics', 'timestamp + queues/event_bus', Object.keys(backend.metrics || {}).join(', '), Boolean(backend.metrics?.timestamp && backend.metrics?.queues && backend.metrics?.event_bus));
    addComparison('csv_api_export', '> 0 bytes', `${backend.csv.bytes} bytes`, backend.csv.ok && backend.csv.bytes > 0);

    await click(page, '#btn-console-exit');
    await page.locator('#view-landing.active').waitFor({ state: 'attached', timeout: 8000 });
    addResult('前台導覽', 'Console 返回首頁', true, 'view-landing.active');

    return { screenshots, backend, frontend };
  } finally {
    await context.close();
    await browser.close();
  }
}

function markdownReport({ screenshots, backend, frontend }) {
  const passCount = results.filter((item) => item.ok).length;
  const comparePass = comparisons.filter((item) => item.ok).length;
  const allOk = passCount === results.length && comparePass === comparisons.length && consoleErrors.length === 0;

  const resultRows = results
    .map((item) => `| ${item.ok ? 'OK' : 'FAIL'} | ${item.area} | ${item.item} | ${truncate(item.detail).replaceAll('|', '\\|')} |`)
    .join('\n');
  const comparisonRows = comparisons
    .map((item) => `| ${item.ok ? 'OK' : 'FAIL'} | ${item.item} | ${truncate(item.backend).replaceAll('|', '\\|')} | ${truncate(item.frontend).replaceAll('|', '\\|')} |`)
    .join('\n');
  const errors = consoleErrors.length
    ? consoleErrors.map((item) => `- ${truncate(item, 500)}`).join('\n')
    : '- 無';
  const warnings = consoleWarnings.length
    ? consoleWarnings.map((item) => `- ${truncate(item, 500)}`).join('\n')
    : '- 無';

  return `# HTML 前後端功能檢查紀錄

- 測試時間：${new Date().toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}
- 測試 URL：${BASE_URL}
- 測試模式：FAKE_VISION=true、FAKE_ROBOT=true、FAKE_AI=true、ENGINE_AUTO_ANALYZE=false
- 整體結果：${allOk ? (consoleWarnings.length ? '通過（有警訊）' : '通過') : '需檢查'}
- 前台功能：${passCount}/${results.length} 通過
- 前後端對照：${comparePass}/${comparisons.length} 通過
- Browser console errors：${consoleErrors.length}
- Browser console warnings：${consoleWarnings.length}

## 前台功能操作紀錄

| 結果 | 區塊 | 測項 | 紀錄 |
| --- | --- | --- | --- |
${resultRows}

## 後台資料與前台呈現對照

| 結果 | 欄位 | 後台資料 | 前台呈現 |
| --- | --- | --- | --- |
${comparisonRows}

## 後台摘要

- ready：${backend.ready?.ready}
- bootstrap ready：${backend.ready?.bootstrap?.ready}
- engine registered：${backend.ready?.engine_registered}
- vision registered：${backend.ready?.vision_registered}
- runtime safe_mode：${backend.runtime?.safe_mode}
- runtime engine_depth：${backend.runtime?.engine_depth}
- runtime session active：${backend.runtime?.session?.active}
- estop triggered：${backend.estop?.triggered}
- csv export bytes：${backend.csv?.bytes}

## 前台摘要

\`\`\`json
${JSON.stringify(frontend, null, 2)}
\`\`\`

## 截圖

- Player：${screenshots.player}
- Console：${screenshots.console}

## Console Errors

${errors}

## Console Warnings

${warnings}
`;
}

async function main() {
  await fs.mkdir(REPORT_DIR, { recursive: true });
  await fs.mkdir(path.dirname(DB_PATH), { recursive: true });
  const server = startServer();
  let browserResult = null;
  try {
    await waitForServer(server);
    const login = await apiJson('/api/login', null, {
      method: 'POST',
      body: { username: 'admin', password: ADMIN_PASSWORD },
    });
    if (!login.ok || !login.payload.token) {
      throw new Error(`Admin login failed: HTTP ${login.status}`);
    }
    addResult('後台 API', 'Admin token issued', true, 'token redacted');
    browserResult = await runBrowserChecks(login.payload.token);
    const report = markdownReport(browserResult);
    const reportPath = path.join(REPORT_DIR, `html-function-check-${stamp}.md`);
    await fs.writeFile(reportPath, report, 'utf8');
    console.log(JSON.stringify({
      ok: results.every((item) => item.ok) && comparisons.every((item) => item.ok) && consoleErrors.length === 0,
      reportPath,
      resultCount: results.length,
      comparisonCount: comparisons.length,
      consoleErrors: consoleErrors.length,
      consoleWarnings: consoleWarnings.length,
      screenshots: browserResult.screenshots,
    }, null, 2));
  } finally {
    server.kill();
  }
}

main().catch(async (error) => {
  const reportPath = path.join(REPORT_DIR, `html-function-check-${stamp}-FAILED.md`);
  await fs.mkdir(REPORT_DIR, { recursive: true });
  await fs.writeFile(reportPath, `# HTML 功能檢查失敗\n\n\`\`\`\n${error.stack || error.message}\n\`\`\`\n\n## Server Log\n\n\`\`\`\n${serverLines.slice(-120).join('\n')}\n\`\`\`\n`, 'utf8');
  console.error(error);
  console.error(`Failure report: ${reportPath}`);
  process.exit(1);
});
