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
  'dashboard-robot-position',
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
      position: { x: 1.2, y: 3.4, z: 5.6 },
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
  expect(document.getElementById('dashboard-robot-status').textContent).toBe('Connected');
  expect(document.getElementById('dashboard-robot-busy').className).toBe('status-warning');
  expect(document.getElementById('dashboard-robot-position').textContent).toBe('X1.2 Y3.4 Z5.6');
  expect(document.getElementById('dashboard-safety-estop').textContent).toBe('Clear');
  expect(document.getElementById('dashboard-safety-safe-mode').textContent).toBe('Enabled');
  expect(document.getElementById('dashboard-safety-camera-ready').textContent).toBe('Ready');
  expect(document.getElementById('dashboard-exp-participant').textContent).toBe('P-001');
  expect(document.getElementById('dashboard-exp-session-id').textContent).toBe('session_1');
  expect(document.getElementById('dashboard-exp-session-status').textContent).toBe('進行中');
  expect(document.getElementById('dashboard-exp-difficulty').textContent).toBe('12');
  expect(document.getElementById('vision-confidence').textContent).toBe('91% / 72%');
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
  expect(document.getElementById('dashboard-robot-status').textContent).toBe('Offline');
  expect(document.getElementById('dashboard-robot-error').textContent).toBe('axis fault');
  expect(document.getElementById('dashboard-safety-estop').textContent).toBe('Triggered');
  expect(document.getElementById('dashboard-safety-safe-mode').textContent).toBe('未提供');
  expect(document.getElementById('dashboard-safety-camera-ready').textContent).toBe('Not Ready');
  expect(document.getElementById('dashboard-exp-participant').textContent).toBe('未設定');
  expect(document.getElementById('dashboard-exp-session-id').textContent).toBe('--');
  expect(document.getElementById('dashboard-exp-session-status').textContent).toBe('待命');
  expect(document.getElementById('dashboard-exp-difficulty').textContent).toBe('未提供');
});
