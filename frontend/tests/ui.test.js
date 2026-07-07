import { installFakeDom, setupContainer } from './test_dom.js';
import { UIRegistry } from '../static/js/modules/ui/ui_registry.js';
import { TelemetryRenderer } from '../static/js/modules/ui/telemetry_renderer.js';
import { SystemStatusStrip } from '../static/js/modules/ui/system_status_strip.js';
import { renderDiagnostics } from '../static/js/modules/board/diagnostics_renderer.js';
import { getTurnDisplay, updateTurnIndicators } from '../static/js/modules/board/render.js';

beforeEach(() => {
  installFakeDom();

  setupContainer('system-status-text');
  setupContainer('turn-indicator');
  setupContainer('player-turn-indicator');
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
  setupContainer('vision-calibration-status');
  setupContainer('vision-calibration-source');
  setupContainer('vision-calibration-error');
  setupContainer('vision-calibration-quality');
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
  setupContainer('system-status-lights');
  setupContainer('system-status-detail');
  setupContainer('system-status-updated');

  UIRegistry.init();
});

test('UIRegistry resolves canonical DOM references', () => {
  expect(UIRegistry.get('statusText')).toBe(document.getElementById('system-status-text'));
  expect(UIRegistry.get('videoFeed')).toBe(document.getElementById('vision-live-feed'));
  expect(UIRegistry.get('playerTurnIndicator')).toBe(document.getElementById('player-turn-indicator'));
  expect(UIRegistry.get('visionCalibrationStatus')).toBe(document.getElementById('vision-calibration-status'));
});

test('turn indicators update console and player view together', () => {
  updateTurnIndicators({ turn: 'black' });

  expect(document.getElementById('turn-indicator').innerText).toBe('\u9ed1\u65b9\u79fb\u52d5');
  expect(document.getElementById('turn-indicator').className).toBe('turn-indicator-pill black');
  expect(document.getElementById('player-turn-indicator').innerText).toBe('\u9ed1\u65b9\u79fb\u52d5');
  expect(document.getElementById('player-turn-indicator').getAttribute('aria-label')).toBe('\u73fe\u5728\u8f2a\u5230\u9ed1\u65b9\u79fb\u52d5\u68cb\u5b50');
});

test('turn display falls back to FEN side-to-move when turn is missing', () => {
  expect(getTurnDisplay({
    fen: 'rnbakabnr/9/9/9/9/9/9/9/9/RNBAKABNR b - - 0 1',
  })).toMatchObject({
    label: '\u9ed1\u65b9\u79fb\u52d5',
    className: 'black',
  });
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

test('SystemStatusStrip renders telemetry topology and hardware lights', () => {
  const lights = document.getElementById('system-status-lights');
  SystemStatusStrip.init();

  SystemStatusStrip.handleEvent({
    type: 'DIAGNOSTICS.UPDATED',
    payload: {
      health: {
        cpu_percent: 42,
        memory_mb: 512,
        gpu: { available: false, reason: 'not_detected' },
        temperature: { available: false, reason: 'unsupported' },
        timestamp: 1770000000,
      },
      robot: {
        connected: true,
        busy: false,
        queue_size: 1,
        serial: { available: true, status: 'connected' },
        usb: { available: true, status: 'connected' },
      },
      vision: {
        status: 'READY',
        fps: 28,
        detections_count: 2,
        avg_confidence: 0.9,
        fen: 'fen-main',
      },
      queue: {
        robot: { size: 1, maxsize: 10, blocked: true },
      },
      workers: {
        vision_inference: { status: 'RUNNING' },
      },
      telemetry: {
        enabled: true,
        recorded_events: 12,
      },
      topology: {
        updated_at: 1770000000,
        nodes: [
          { id: 'engine', label: 'AI Engine', status: 'running', last_event: 'ENGINE_ANALYSIS_STARTED', latency_ms: 15 },
          { id: 'storage', label: 'Storage', status: 'success', last_event: 'PERSISTED' },
        ],
        edges: [{ id: 'queue_robot', source: 'queue', target: 'robot', status: 'blocked' }],
      },
    },
  });

  expect(lights.children.length).toBeGreaterThan(10);
  expect(lights.textContent).toContain('Queue');
  expect(lights.textContent).toContain('Blocked');
  expect(lights.textContent).toContain('Pikafish');
  expect(lights.textContent).toContain('Running');
  expect(lights.textContent).toContain('GPU');
  expect(lights.textContent).toContain('Offline');
  expect(document.getElementById('system-status-updated').textContent).toContain('updated');
});

test('renderDiagnostics surfaces vision simulation mode', () => {
  renderDiagnostics({ vision: { mode: 'simulation', status: 'SIMULATION' } });

  expect(document.getElementById('stat-camera').innerText).toBe('Simulation');
  expect(document.getElementById('stat-camera').className).toBe('status-warning');
});

test('renderDiagnostics surfaces stale vision as warning', () => {
  renderDiagnostics({ vision: { status: 'STALE' } });

  expect(document.getElementById('stat-camera').innerText).toBe('Stale');
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
