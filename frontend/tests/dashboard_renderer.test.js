import { DashboardRenderer } from '../static/js/modules/board/dashboard_renderer.js';
import { RenderScheduler } from '../static/js/modules/core/render_scheduler.js';
import { UIRegistry } from '../static/js/modules/ui/ui_registry.js';
import { installFakeDom, setupContainer } from './test_dom.js';

const dashboardIds = [
  'dashboard-board-turn',
  'dashboard-board-fen',
  'dashboard-board-last-move',
  'dashboard-board-move-count',
  'dashboard-engine-depth',
  'dashboard-engine-thinking',
  'dashboard-engine-pv',
  'dashboard-robot-status',
  'dashboard-robot-busy',
  'dashboard-robot-error',
  'dashboard-robot-queue',
  'dashboard-robot-ip',
  'dashboard-robot-position',
  'dashboard-robot-orientation',
  'dashboard-robot-joints',
  'dashboard-robot-speed',
  'dashboard-robot-telemetry-source',
  'dashboard-safety-estop',
  'dashboard-safety-safe-mode',
  'dashboard-safety-camera-ready',
  'dashboard-exp-participant',
  'dashboard-exp-session-id',
  'dashboard-exp-session-status',
  'dashboard-exp-session-time',
  'dashboard-exp-difficulty',
  'vision-detections-count',
  'vision-confidence',
  'vision-calibration-status',
  'vision-calibration-source',
  'vision-calibration-error',
  'vision-calibration-quality',
  'stat-ai',
];

beforeEach(() => {
  installFakeDom();
  RenderScheduler.tasks.clear();
  RenderScheduler.isPending = false;
  dashboardIds.forEach((id) => setupContainer(id));
  UIRegistry.init();
});

afterEach(() => {
  DashboardRenderer.dispose();
});

test('DashboardRenderer surfaces board, engine, robot, safety, and experiment data', () => {
  DashboardRenderer.render({
    board: {
      fen: 'fen-main',
      turn: 'black',
      last_move: { from: 'a0', to: 'a1' },
      move_count: 7,
    },
    vision: {
      status: 'READY',
      fps: 29,
      detections_count: 2,
      avg_confidence: 0.91,
      min_confidence: 0.72,
      calibration: {
        calibrated: true,
        source: 'auto',
        quality: {
          max_reprojection_error_px: 0.012345,
          edge_ratio: 1.3154,
          min_angle_deg: 89.5,
          area_ratio: 0.132,
        },
      },
    },
    engine: {
      depth: 13,
      best_move: 'b2b3',
      pv: ['b2b3', 'c7c6'],
      is_thinking: true,
      skill_level: 12,
    },
    robot: {
      connected: true,
      busy: true,
      queue_size: 3,
      ip: '192.168.1.50',
      port: 502,
      position: { x: 1.2, y: 3.4, z: 5.6 },
      orientation: { rx: 10, ry: 20, rz: 30 },
      joint_angles: { j1: 1, j2: 2, j3: 3, j4: 4, j5: 5, j6: 6 },
      speed: 42.5,
      telemetry: { source: 'hardware' },
    },
    ui: {
      safe_mode: true,
      participant_id: 'P-001',
      session_id: 'session_1',
      session_active: true,
      session_started_at: Date.now() / 1000 - 5,
      engine_depth: 15,
    },
  });

  expect(document.getElementById('dashboard-board-turn').textContent).toBe('黑方');
  expect(document.getElementById('dashboard-board-fen').textContent).toBe('fen-main');
  expect(document.getElementById('dashboard-board-last-move').textContent).toBe('a0-a1');
  expect(document.getElementById('dashboard-board-move-count').textContent).toBe('7');
  expect(document.getElementById('dashboard-engine-depth').textContent).toBe('13');
  expect(document.getElementById('dashboard-engine-thinking').textContent).toBe('分析中');
  expect(document.getElementById('dashboard-engine-pv').textContent).toBe('b2b3 c7c6');
  expect(document.getElementById('dashboard-robot-status').textContent).toBe('已連線');
  expect(document.getElementById('dashboard-robot-busy').className).toBe('status-warning');
  expect(document.getElementById('dashboard-robot-ip').textContent).toBe('192.168.1.50:502');
  expect(document.getElementById('dashboard-robot-position').textContent).toBe('X1.2 Y3.4 Z5.6');
  expect(document.getElementById('dashboard-robot-orientation').textContent).toBe('RX10.0 RY20.0 RZ30.0');
  expect(document.getElementById('dashboard-robot-joints').textContent).toBe('J1:1.0 J2:2.0 J3:3.0 J4:4.0 J5:5.0 J6:6.0');
  expect(document.getElementById('dashboard-robot-speed').textContent).toBe('42.5 mm/s');
  expect(document.getElementById('dashboard-robot-telemetry-source').textContent).toBe('硬體');
  expect(document.getElementById('dashboard-safety-estop').textContent).toBe('正常');
  expect(document.getElementById('dashboard-safety-safe-mode').textContent).toBe('已啟用');
  expect(document.getElementById('dashboard-safety-camera-ready').textContent).toBe('已就緒');
  expect(document.getElementById('dashboard-exp-participant').textContent).toBe('P-001');
  expect(document.getElementById('dashboard-exp-session-id').textContent).toBe('session_1');
  expect(document.getElementById('dashboard-exp-session-status').textContent).toBe('進行中');
  expect(document.getElementById('dashboard-exp-difficulty').textContent).toBe('12');
  expect(document.getElementById('vision-confidence').textContent).toBe('91% / 72%');
  expect(document.getElementById('vision-calibration-status').textContent).toBe('已校正');
  expect(document.getElementById('vision-calibration-status').className).toBe('status-ok');
  expect(document.getElementById('vision-calibration-source').textContent).toBe('auto');
  expect(document.getElementById('vision-calibration-error').textContent).toBe('0.012 px');
  expect(document.getElementById('vision-calibration-quality').textContent).toBe('edge 1.32 / angle 89.5deg / area 13.2%');
});

test('DashboardRenderer keeps unsupported fields explicit instead of inventing values', () => {
  DashboardRenderer.render({
    board: {},
    engine: {},
    robot: { connected: false, error: 'axis fault' },
    vision: { status: 'OFFLINE' },
    ui: { phase: 'EMERGENCY' },
  });

  expect(document.getElementById('dashboard-board-turn').textContent).toBe('--');
  expect(document.getElementById('dashboard-board-fen').textContent).toBe('--');
  expect(document.getElementById('dashboard-engine-depth').textContent).toBe('--');
  expect(document.getElementById('dashboard-robot-status').textContent).toBe('離線');
  expect(document.getElementById('dashboard-robot-error').textContent).toBe('axis fault');
  expect(document.getElementById('dashboard-safety-estop').textContent).toBe('已觸發');
  expect(document.getElementById('dashboard-safety-safe-mode').textContent).toBe('未提供');
  expect(document.getElementById('dashboard-safety-camera-ready').textContent).toBe('未就緒');
  expect(document.getElementById('dashboard-exp-participant').textContent).toBe('未設定');
  expect(document.getElementById('dashboard-exp-session-id').textContent).toBe('--');
  expect(document.getElementById('dashboard-exp-session-status').textContent).toBe('待命');
  expect(document.getElementById('dashboard-exp-difficulty').textContent).toBe('未提供');
});

test('DashboardRenderer falls back to FEN side-to-move for board turn', () => {
  DashboardRenderer.render({
    board: {
      fen: 'rnbakabnr/9/9/9/9/9/9/9/9/RNBAKABNR b - - 0 1',
    },
  });

  expect(document.getElementById('dashboard-board-turn').textContent).toBe('黑方');
});
