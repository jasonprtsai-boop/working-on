import { installFakeDom, setupContainer } from './test_dom.js';
import { UIRegistry } from '../static/js/modules/ui/ui_registry.js';
import { TelemetryRenderer } from '../static/js/modules/ui/telemetry_renderer.js';
import { renderDiagnostics } from '../static/js/modules/board/diagnostics_renderer.js';

beforeEach(() => {
  installFakeDom();

  setupContainer('system-status-text');
  setupContainer('turn-indicator');
  setupContainer('state-source-indicator');
  setupContainer('mini-fps');
  setupContainer('mini-latency');
  setupContainer('cons-latency');
  setupContainer('cons-fps');
  setupContainer('cons-last-update');
  setupContainer('vision-fen');
  setupContainer('vision-ucci');
  setupContainer('vision-detections-count');
  setupContainer('vision-confidence');
  setupContainer('vision-yolo-latency');
  setupContainer('vision-recognition-time');
  setupContainer('vision-detection-summary');
  setupContainer('board-pieces');
  setupContainer('console-pieces');
  setupContainer('eval-bar-fill');
  setupContainer('thinking-progress-bar');
  setupContainer('thinking-container');
  setupContainer('best-move');
  setupContainer('eval-score');
  setupContainer('vision-live-feed');
  setupContainer('yolo-canvas');
  setupContainer('camera-select');
  setupContainer('video-cam');
  setupContainer('video-fps');
  setupContainer('video-ts');
  setupContainer('stat-camera');
  setupContainer('video-status-pill');

  UIRegistry.init();
});

test('UIRegistry resolves canonical DOM references', () => {
  expect(UIRegistry.get('statusText')).toBe(document.getElementById('system-status-text'));
  expect(UIRegistry.get('videoFeed')).toBe(document.getElementById('vision-live-feed'));
});

test('updateTelemetry writes cross-panel runtime metrics', () => {
  UIRegistry.updateTelemetry({
    latency: 1501,
    fps: 29.6,
  });

  expect(document.getElementById('cons-latency').innerText).toBe('1501ms');
  expect(document.getElementById('cons-latency').className).toBe('value danger');
  expect(String(document.getElementById('cons-fps').innerText)).toBe('30');
  expect(document.getElementById('mini-fps').innerText).toBe('FPS: 30');
});

test('TelemetryRenderer writes event text without injecting markup', () => {
  const logs = setupContainer('admin-logs');
  TelemetryRenderer.init('admin-logs');

  TelemetryRenderer.renderEvent({
    type: 'UI_TOAST<script>',
    timestamp: Date.now(),
    payload: '<img src=x onerror=alert(1)>',
  });

  expect(logs.children.length).toBe(1);
  const line = logs.children[0];
  expect(line.className).toBe('log-line ui_toastscript');
  expect(line.querySelector('.log-type').textContent).toBe('UI_TOAST<script>');
  expect(line.querySelector('.log-payload').textContent).toBe('<img src=x onerror=alert(1)>');
  expect(line.querySelector('img')).toBe(null);
});

test('renderDiagnostics surfaces vision fallback mode', () => {
  renderDiagnostics({ vision: { mode: 'fallback', status: 'FALLBACK' } });

  expect(document.getElementById('stat-camera').innerText).toBe('Fallback');
  expect(document.getElementById('stat-camera').className).toBe('status-warning');
});

test('renderDiagnostics updates YOLO FEN monitor fields', () => {
  renderDiagnostics({
    vision: {
      fen: 'fen-a',
      ucci_position: 'position fen fen-a',
      latency_ms: 42,
      detections_count: 1,
      avg_confidence: 0.91,
      min_confidence: 0.73,
      detections: [
        {
          class_name: 'red_rook',
          confidence: 0.91,
          cell: { key: '0,0' },
        },
      ],
      timestamp: 1770000000,
    },
  });

  expect(document.getElementById('vision-fen').textContent).toBe('fen-a');
  expect(document.getElementById('vision-ucci').textContent).toBe('position fen fen-a');
  expect(document.getElementById('vision-detections-count').textContent).toBe('1');
  expect(document.getElementById('vision-confidence').textContent).toBe('91% / 73%');
  expect(document.getElementById('vision-yolo-latency').textContent).toBe('42ms');
  expect(document.getElementById('vision-detection-summary').textContent).toContain('red_rook@0,0');
});
