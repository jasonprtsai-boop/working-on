import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';
import { jest } from '@jest/globals';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');

test('dashboard exposes replay controls and API wiring', () => {
  const html = readFileSync(resolve(root, '../backend/interfaces/dashboard/static/index.html'), 'utf8');
  const js = readFileSync(resolve(root, '../backend/interfaces/dashboard/static/dashboard.js'), 'utf8');

  for (const id of [
    'replay-session',
    'replay-live',
    'replay-load',
    'replay-play',
    'replay-prev',
    'replay-next',
    'replay-slider',
    'replay-board',
    'replay-export',
  ]) {
    expect(html).toContain(`id="${id}"`);
  }

  expect(js).toContain('/api/replay/sessions');
  expect(js).toContain('/api/replay/steps');
  expect(js).toContain('/api/replay/step/');
  expect(js).toContain('/api/replay/export');
});

test('dashboard replay script initializes controls from API data', async () => {
  jest.useFakeTimers();
  document.body.innerHTML = `
    <span id="socket-status"></span>
    <span id="socket-dot"></span>
    <span id="replay-status"></span>
    <select id="replay-session"></select>
    <button id="replay-refresh"></button>
    <button id="replay-live"></button>
    <button id="replay-load"></button>
    <button id="replay-export"></button>
    <button id="replay-prev"></button>
    <button id="replay-play"></button>
    <button id="replay-next"></button>
    <select id="replay-speed"><option value="1">1x</option></select>
    <input id="replay-slider" type="range">
    <div id="replay-step-label"></div>
    <div id="replay-move-label"></div>
    <div id="replay-time-label"></div>
    <div id="replay-trace-label"></div>
    <div id="replay-fen"></div>
    <div id="replay-board"></div>
    <div id="replay-step-list"></div>
  `;
  global.fetch = jest.fn(async (url) => {
    const text = String(url);
    if (text.includes('/api/replay/sessions')) {
      return { ok: true, json: async () => ({ ok: true, sessions: [{ id: 's1', label: 'Session 1', event_count: 1 }] }) };
    }
    if (text.includes('/api/replay/steps')) {
      return {
        ok: true,
        json: async () => ({
          ok: true,
          total: 1,
          steps: [{
            step: 0,
            session_id: 's1',
            trace_id: 'trace-1',
            type: 'STATE_UPDATED',
            timestamp: 1234,
            fen: '9/9/9/9/9/9/9/9/9/4K4 w - - 0 1',
            move: 'b2b5',
          }],
        }),
      };
    }
    return {
      ok: true,
      json: async () => ({
        board: { fen: '9/9/9/9/9/9/9/9/9/4K4 w - - 0 1' },
        _replay: { step: 0, total: 1, trace_id: 'trace-1', timestamp: 1234 },
      }),
    };
  });

  const dashboardUrl = `${pathToFileURL(resolve(root, '../backend/interfaces/dashboard/static/dashboard.js')).href}?test=${Date.now()}`;
  await import(dashboardUrl);
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  jest.advanceTimersByTime(500);
  await Promise.resolve();
  await Promise.resolve();

  expect(global.fetch).toHaveBeenCalledWith('/api/replay/sessions?limit=80', expect.any(Object));
  expect(document.getElementById('replay-session').value).toBe('s1');
  expect(document.getElementById('replay-move-label').textContent).toBe('b2b5');
  expect(document.getElementById('replay-board').querySelectorAll('.replay-cell').length).toBe(90);

  jest.clearAllTimers();
  jest.useRealTimers();
});
