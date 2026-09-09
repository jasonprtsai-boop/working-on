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

test('core app enters console directly and resumes overlay via control API', async () => {
  document.body.innerHTML = `
    <section id="view-landing"></section>
    <section id="view-player" class="hidden"></section>
    <section id="view-console" class="hidden"></section>
    <div id="player-start-panel"></div>
    <div id="player-start-preflight-alert" class="hidden"></div>
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
    <div class="tab-pane" id="pane-replay">
      <select id="replay-session-select"></select>
      <button id="btn-replay-refresh"></button>
      <button id="btn-replay-prev"></button>
      <input id="replay-step-range" type="range" />
      <button id="btn-replay-next"></button>
      <div id="replay-status"></div>
      <div id="replay-current-step"></div>
      <div id="replay-event-type"></div>
      <div id="replay-move"></div>
      <div id="replay-turn"></div>
      <div id="replay-timestamp"></div>
      <pre id="replay-fen"></pre>
    </div>
    <button class="tab-btn active" data-tab="status"></button>
    <button class="tab-btn" data-tab="export"></button>
    <button class="tab-btn" data-tab="replay"></button>
    <div id="tab-indicator"></div>
    <div id="admin-logs">boot log</div>
    ${[
      'btn-role-player', 'btn-player-start', 'btn-player-vision-capture', 'btn-player-end-game',
      'btn-start-tmflow', 'btn-role-console', 'btn-exit', 'btn-console-exit',
      'btn-toggle-board', 'btn-toggle-video',
      'btn-resume-overlay', 'btn-export-excel', 'btn-export-csv', 'btn-export-replay',
      'btn-session-start', 'btn-session-end'
    ].map((id) => `<button id="${id}"></button>`).join('')}
  `;

  global.fetch = jest.fn(async (url) => {
    const path = String(url || '');
    if (path.startsWith('/api/replay/sessions')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({
          ok: true,
          sessions: [
            { id: '', session_id: '', label: 'Unassigned session', event_count: 1 },
            { id: 'session-a', session_id: 'session-a', label: 'session-a', event_count: 2 },
          ],
          total: 2,
        }),
        text: async () => '{"ok":true}',
        blob: async () => new Blob(['']),
      };
    }
    if (path.startsWith('/api/replay/steps')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({
          ok: true,
          steps: [
            { step: 0, type: 'STATE_UPDATED', fen: 'fen-0', move: 'a0a1', turn: 'red', timestamp: 1788750000 },
            { step: 1, type: 'STATE_UPDATED', fen: 'fen-1', move: 'b0b1', turn: 'black', timestamp: 1788750001 },
          ],
          total: 2,
        }),
        text: async () => '{"ok":true}',
        blob: async () => new Blob(['']),
      };
    }
    if (path.startsWith('/api/replay/step/')) {
      const step = path.includes('/1') ? 1 : 0;
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({
          ok: true,
          _replay: { step, total: 2, type: 'STATE_UPDATED', timestamp: 1788750000 + step },
          board: { fen: `fen-${step}`, turn: step ? 'black' : 'red' },
        }),
        text: async () => '{"ok":true}',
        blob: async () => new Blob(['']),
      };
    }
    if (path === '/api/runtime/session/start') {
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({
          ok: true,
          safe_mode: true,
          engine_depth: 15,
          session: {
            session_id: 'session-ui',
            participant_id: 'E2E-SESSION',
            active: true,
            started_at: 1788750000,
            ended_at: null,
            duration_sec: 0,
            move_count: 0,
          },
        }),
        text: async () => '{"ok":true}',
        blob: async () => new Blob(['']),
      };
    }
    if (path === '/api/runtime/session/end') {
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({
          ok: true,
          safe_mode: true,
          engine_depth: 15,
          session: {
            session_id: 'session-ui',
            participant_id: 'E2E-SESSION',
            active: false,
            started_at: 1788750000,
            ended_at: 1788750030,
            duration_sec: 30,
            move_count: 0,
          },
        }),
        text: async () => '{"ok":true}',
        blob: async () => new Blob(['']),
      };
    }
    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-disposition': 'attachment; filename="game.xlsx"' }),
      json: async () => ({ ok: true }),
      text: async () => '{"ok":true}',
      blob: async () => new Blob(['excel'])
    };
  });
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
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/player/state');
  expect(global.fetch.mock.calls.map(([url]) => url)).not.toContain('/api/state');

  document.getElementById('btn-role-player').click();
  expect(document.getElementById('view-player').classList.contains('active')).toBe(true);
  expect(document.getElementById('player-start-panel').classList.contains('hidden')).toBe(false);
  expect(document.getElementById('game-arena').classList.contains('hidden')).toBe(true);

  global.fetch.mockClear();
  global.fetch.mockImplementationOnce(async () => ({
    ok: false,
    status: 409,
    headers: new Headers(),
    json: async () => ({
      ok: false,
      message: 'Player mode is not ready to start.',
      details: {
        preflight: {
          ok: false,
          ready: false,
          failures: [{ message: 'Vision is unavailable.' }],
          warnings: [],
        },
      },
    }),
    text: async () => '{"ok":false}',
    blob: async () => new Blob(['']),
  }));
  document.getElementById('btn-player-start').click();
  await flushAsync();
  expect(document.getElementById('player-start-panel').classList.contains('hidden')).toBe(false);
  expect(document.getElementById('game-arena').classList.contains('hidden')).toBe(true);
  expect(document.getElementById('player-start-preflight-alert').classList.contains('hidden')).toBe(false);
  expect(document.getElementById('player-start-preflight-alert').textContent).toContain('Vision is unavailable.');

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

  window.confirm = jest.fn()
    .mockReturnValueOnce(true)
    .mockReturnValueOnce(false)
    .mockReturnValueOnce(true)
    .mockReturnValueOnce(true);
  global.fetch.mockClear();
  document.getElementById('btn-player-end-game').click();
  await flushAsync();
  expect(global.fetch).not.toHaveBeenCalled();

  document.getElementById('btn-player-end-game').click();
  await flushAsync();
  const playerEndCall = global.fetch.mock.calls.find(([url]) => url === '/api/player/end-game');
  expect(playerEndCall?.[1]).toEqual(expect.objectContaining({ method: 'POST' }));
  expect(JSON.parse(playerEndCall?.[1]?.body || '{}')).toEqual(expect.objectContaining({
    source: 'player_end_button',
    confirmed_action: 'end_game',
    final_confirmation: 'END_GAME_CONFIRMED',
  }));

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
  await flushAsync();
  expect(document.getElementById('view-console').classList.contains('active')).toBe(true);
  expect(document.getElementById('vision-live-feed').src).toContain('/api/video_feed?t=');
  expect(document.getElementById('btn-export-excel').disabled).toBe(false);

  socketHandlers.disconnect();
  expect(document.body.dataset.connectionStatus).toBe('offline');
  expect(document.body.classList.contains('state-stale')).toBe(true);
  expect(document.getElementById('btn-export-excel').disabled).toBe(true);

  socketHandlers.connect();
  window.dispatchEvent(new CustomEvent('smart:state-received', { detail: { timestamp: Date.now(), type: 'STATE_UPDATE' } }));
  expect(document.body.dataset.connectionStatus).toBe('online');
  expect(document.getElementById('btn-export-excel').disabled).toBe(false);

  global.fetch.mockClear();
  document.getElementById('session-participant-id').value = 'E2E-SESSION';
  document.getElementById('btn-session-start').click();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/runtime/session/start');
  expect(document.getElementById('btn-session-start').disabled).toBe(true);
  expect(document.getElementById('btn-session-end').disabled).toBe(false);
  expect(document.getElementById('session-participant-id').disabled).toBe(true);

  document.getElementById('btn-session-end').click();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/runtime/session/end');
  expect(document.getElementById('btn-session-start').disabled).toBe(false);
  expect(document.getElementById('btn-session-end').disabled).toBe(true);
  expect(document.getElementById('session-participant-id').disabled).toBe(false);

  global.fetch.mockClear();
  document.getElementById('btn-resume-overlay').click();
  await flushAsync();
  const resumeCall = global.fetch.mock.calls.find(([url]) => url === '/api/control');
  expect(resumeCall?.[1]).toEqual(expect.objectContaining({ method: 'POST' }));
  expect(JSON.parse(resumeCall?.[1]?.body || '{}')).toEqual(expect.objectContaining({ action: 'resume' }));
  expect(emitWithAckMock).not.toHaveBeenCalledWith('action', { type: 'RESUME', payload: {} });

  document.getElementById('btn-export-excel').click();
  await Promise.resolve();
  await Promise.resolve();
  await flushAsync();

  const urls = global.fetch.mock.calls.map(([url]) => url);
  expect(urls.some((url) => String(url).startsWith('/api/export/excel'))).toBe(true);
  expect(urls).toContain('/api/export/excel?profile=field');
  expect(URL.createObjectURL).toHaveBeenCalled();

  document.getElementById('btn-export-csv').click();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/export/csv');

  document.querySelector('.tab-btn[data-tab="replay"]').click();
  await flushAsync();
  await flushAsync();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/sessions?limit=50');
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/steps?limit=500');
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/step/0');
  expect(document.getElementById('replay-current-step').textContent).toBe('1 / 2');
  expect(document.getElementById('replay-fen').textContent).toBe('fen-0');
  const replaySessionSelect = document.getElementById('replay-session-select');
  expect(Array.from(replaySessionSelect.options).map((option) => option.value)).toEqual(
    expect.arrayContaining(['__all__', '', 'session-a'])
  );

  document.getElementById('btn-replay-next').click();
  await flushAsync();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/step/1');
  expect(document.getElementById('replay-current-step').textContent).toBe('2 / 2');
  expect(document.getElementById('replay-fen').textContent).toBe('fen-1');

  document.getElementById('btn-export-replay').click();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/export');

  replaySessionSelect.value = '';
  replaySessionSelect.dispatchEvent(new Event('change'));
  await flushAsync();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/steps?limit=500&session=');
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/step/0?session=');

  document.getElementById('btn-export-replay').click();
  await flushAsync();
  expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/replay/export?session=');

  expect(global.fetch.mock.calls.find(([url]) => url === '/api/player/move')).toBeUndefined();
});
