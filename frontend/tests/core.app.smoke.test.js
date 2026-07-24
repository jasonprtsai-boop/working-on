import { jest } from '@jest/globals';

const socketHandlers = {};
const emitMock = jest.fn();
const emitWithAckMock = jest.fn(async () => ({ ok: true }));
const connectMock = jest.fn();
const setupEventAdapterMock = jest.fn();
const initRendererMock = jest.fn();
const flushAsync = () => new Promise((resolve) => setTimeout(resolve, 0));
const jwtWithPayload = (payload) => {
  const encoded = btoa(JSON.stringify(payload)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
  return `header.${encoded}.signature`;
};

jest.unstable_mockModule('../static/js/modules/websocket/socket_client.js', () => ({
  socket: {},
  socketClient: {
    on: jest.fn((event, callback) => {
      socketHandlers[event] = callback;
    }),
    emit: emitMock,
    emitWithAck: emitWithAckMock,
    connect: connectMock,
    isConnected: jest.fn(() => true)
  }
}));

jest.unstable_mockModule('../static/js/modules/websocket/event_adapter.js', () => ({
  setupEventAdapter: setupEventAdapterMock
}));

jest.unstable_mockModule('../static/js/modules/board/render.js', () => ({
  initRenderer: initRendererMock
}));

test('core app enters console directly and resets emergency stop via API', async () => {
  document.body.innerHTML = `
    <section id="view-landing"></section>
    <section id="view-player" class="hidden"></section>
    <section id="view-console" class="hidden"></section>
    <div id="player-start-panel"></div>
    <div id="game-arena" class="hidden"></div>
    <div id="analysis-container"></div>
    <div id="toast-container"></div>
    <div id="pause-overlay" class="hidden"></div>
    <div id="auth-overlay" class="auth-overlay hidden" aria-hidden="true">
      <form id="admin-login-form">
        <input id="admin-password" />
        <button id="btn-auth-cancel" type="button"></button>
        <p id="auth-error"></p>
      </form>
    </div>
    <div id="overlay-title"></div>
    <div id="pause-msg"></div>
    <img id="vision-live-feed" data-src="/api/video_feed" />
    <div id="video-status-pill"></div>
    <span id="video-cam"></span>
    <span id="video-fps"></span>
    <span id="video-ts"></span>
    <div id="system-status-text"></div>
    <div id="state-source-indicator"></div>
    <div id="safety-msg"></div>
    <div id="sync-warning" style="display:none"></div>
    <div id="turn-indicator"></div>
    <span id="mini-fps"></span>
    <span id="mini-latency"></span>
    <span id="cons-fps"></span>
    <span id="cons-last-update"></span>
    <div id="board-pieces"></div>
    <div id="console-pieces"></div>
    <div id="eval-bar-fill"></div>
    <div id="thinking-progress-bar"></div>
    <div id="thinking-container"></div>
    <div id="best-move"></div>
    <div id="eval-score"></div>
    <canvas id="yolo-canvas"></canvas>
    <input id="safe-mode-toggle" type="checkbox" />
    <input id="session-participant-id" />
    <button class="depth-btn" data-depth="5"></button>
    <button class="depth-btn" data-depth="10"></button>
    <div class="tab-pane active" id="pane-status"></div>
    <div class="tab-pane" id="pane-export"></div>
    <button class="tab-btn active" data-tab="status"></button>
    <button class="tab-btn" data-tab="export"></button>
    <div id="tab-indicator"></div>
    <div id="admin-logs">boot log</div>
    ${[
      'btn-role-player', 'btn-player-start', 'btn-role-console', 'btn-exit', 'btn-console-exit',
      'btn-toggle-board', 'btn-toggle-video',
      'btn-estop-trigger', 'btn-resume-overlay', 'btn-export-excel', 'btn-export-csv',
      'btn-session-start', 'btn-session-end'
    ].map((id) => `<button id="${id}"></button>`).join('')}
  `;

  global.fetch = jest.fn(async () => ({
    ok: true,
    status: 200,
    headers: new Headers({ 'content-disposition': 'attachment; filename="game.xlsx"' }),
    json: async () => ({ ok: true }),
    text: async () => '{"ok":true}',
    blob: async () => new Blob(['excel'])
  }));
  window.open = jest.fn();
  URL.createObjectURL = jest.fn(() => 'blob:test');
  URL.revokeObjectURL = jest.fn();
  HTMLAnchorElement.prototype.click = jest.fn();

  await import('../static/js/modules/core/app.js');
  document.dispatchEvent(new Event('DOMContentLoaded'));
  await Promise.resolve();
  await Promise.resolve();

  expect(setupEventAdapterMock).toHaveBeenCalled();
  expect(initRendererMock).toHaveBeenCalled();
  expect(document.getElementById('view-landing').classList.contains('active')).toBe(true);
  expect(document.getElementById('btn-export-excel').disabled).toBe(true);
  expect(document.getElementById('btn-estop-trigger').disabled).toBe(true);
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/player/state');
  expect(global.fetch.mock.calls.map(([url]) => url)).not.toContain('/api/state');

  document.getElementById('btn-role-player').click();
  expect(document.getElementById('view-player').classList.contains('active')).toBe(true);
  expect(document.getElementById('player-start-panel').classList.contains('hidden')).toBe(false);
  expect(document.getElementById('game-arena').classList.contains('hidden')).toBe(true);

  global.fetch.mockClear();
  document.getElementById('btn-player-start').click();
  await flushAsync();
  const playerStartCall = global.fetch.mock.calls.find(([url]) => url === '/api/player/start');
  const playerStateCall = global.fetch.mock.calls.find(([url]) => url === '/api/player/state');
  expect(playerStartCall?.[1]).toEqual(expect.objectContaining({ method: 'POST' }));
  expect(JSON.parse(playerStartCall?.[1]?.body || '{}')).toEqual(expect.objectContaining({ source: 'player_start_button' }));
  expect(playerStartCall?.[1]?.headers.has('Authorization')).toBe(false);
  expect(playerStateCall?.[1]).toEqual(expect.objectContaining({ method: 'GET' }));
  expect(playerStateCall?.[1]?.headers.has('Authorization')).toBe(false);
  expect(document.getElementById('player-start-panel').classList.contains('hidden')).toBe(true);
  expect(document.getElementById('game-arena').classList.contains('hidden')).toBe(false);

  document.getElementById('btn-role-console').click();
  expect(document.getElementById('view-console').classList.contains('active')).toBe(false);
  expect(document.getElementById('auth-overlay').classList.contains('hidden')).toBe(false);

  window.sessionStorage.setItem('adminToken', 'stale-token');
  window.dispatchEvent(new CustomEvent('smart:state-received', { detail: { timestamp: Date.now(), type: 'STATE_UPDATE' } }));
  document.getElementById('btn-role-console').click();
  expect(document.getElementById('view-console').classList.contains('active')).toBe(false);
  expect(window.sessionStorage.getItem('adminToken')).toBe(null);

  window.sessionStorage.setItem('adminToken', jwtWithPayload({ role: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 }));
  window.sessionStorage.setItem('adminRole', 'admin');
  document.getElementById('btn-role-console').click();
  expect(document.getElementById('view-console').classList.contains('active')).toBe(true);
  expect(document.getElementById('vision-live-feed').src).toContain('/api/video_feed?t=');
  expect(document.getElementById('btn-export-excel').disabled).toBe(false);
  expect(document.getElementById('btn-estop-trigger').disabled).toBe(false);

  socketHandlers.disconnect();
  expect(document.body.dataset.connectionStatus).toBe('offline');
  expect(document.body.classList.contains('state-stale')).toBe(true);
  expect(document.getElementById('btn-export-excel').disabled).toBe(true);

  socketHandlers.connect();
  window.dispatchEvent(new CustomEvent('smart:state-received', { detail: { timestamp: Date.now(), type: 'STATE_UPDATE' } }));
  expect(document.body.dataset.connectionStatus).toBe('online');
  expect(document.getElementById('btn-export-excel').disabled).toBe(false);

  global.fetch.mockClear();
  document.getElementById('btn-resume-overlay').click();
  await flushAsync();
  const resetCall = global.fetch.mock.calls.find(([url]) => url === '/api/estop/reset');
  expect(resetCall?.[1]).toEqual(expect.objectContaining({ method: 'POST' }));
  expect(emitWithAckMock).not.toHaveBeenCalledWith('action', { type: 'RESUME', payload: {} });

  document.getElementById('btn-estop-trigger').click();
  await flushAsync();
  const estopCall = global.fetch.mock.calls.find(([url]) => url === '/api/estop/trigger');
  expect(estopCall?.[1]).toEqual(expect.objectContaining({ method: 'POST' }));

  document.getElementById('btn-export-excel').click();
  await Promise.resolve();
  await Promise.resolve();
  await flushAsync();

  const urls = global.fetch.mock.calls.map(([url]) => url);
  expect(urls).toContain('/api/export/excel');
  expect(URL.createObjectURL).toHaveBeenCalled();

  document.getElementById('btn-export-csv').click();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/export/csv');

  expect(global.fetch.mock.calls.find(([url]) => url === '/api/player/move')).toBeUndefined();
});
