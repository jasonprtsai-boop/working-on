import { state, commit, subscribe } from '../static/js/modules/state/state.js';
import { Normalizer } from '../static/js/modules/state/normalizer.js';

test('ENGINE.INFO_UPDATED updates engine SSOT with move and MultiPV', () => {
  let observed = null;
  subscribe('engine', (engineState) => {
    observed = { ...engineState };
  });

  commit('ENGINE.INFO_UPDATED', {
    score: 128,
    depth: 12,
    best_move: 'a0a1',
    multiPv: [{ move: 'a0a1', score: 128 }],
    is_thinking: true
  });

  expect(state.snapshot.engine.score).toBe(128);
  expect(state.snapshot.engine.best_move).toBe('a0a1');
  expect(state.snapshot.engine.multiPv).toHaveLength(1);
  expect(observed.best_move).toBe('a0a1');
});

test('VISION.FRAME_PROCESSED preserves FEN and UCCI telemetry', () => {
  const normalized = Normalizer.normalize('VISION.FRAME_PROCESSED', {
    fen: 'fen-b',
    ucci_position: 'position fen fen-b',
    latency_ms: 18,
    fps: 55.5,
    fen_valid: true,
    detections: [{ class_name: 'red_rook', confidence: 0.8 }],
    avg_confidence: 0.8,
    min_confidence: 0.8,
    board_state: { '0,0': 'R' },
  });

  expect(normalized.vision.fen).toBe('fen-b');
  expect(normalized.vision.fps).toBe(55.5);
  expect(normalized.vision.fen_valid).toBe(true);
  expect(normalized.vision.ucci_position).toBe('position fen fen-b');
  expect(normalized.vision.detections_count).toBe(1);
  expect(normalized.vision.board_state['0,0']).toBe('R');
});

test('STATE_UPDATE keeps dashboard board and robot contract fields', () => {
  const normalized = Normalizer.normalize('STATE_UPDATE', {
    board: {
      fen: 'fen-c',
      turn: 'black',
      move_count: 9,
      last_move: { from: 'a0', to: 'a1' },
    },
    robot: {
      is_connected: true,
      busy: true,
      error: 'axis fault',
      queue_size: 2,
      safety_status: 'SAFE',
      position: { x: 10, y: 20, z: 30 },
    },
  });

  expect(normalized.board.move_count).toBe(9);
  expect(normalized.board.last_move).toEqual({ from: 'a0', to: 'a1' });
  expect(normalized.robot.connected).toBe(true);
  expect(normalized.robot.is_connected).toBe(true);
  expect(normalized.robot.busy).toBe(true);
  expect(normalized.robot.error).toBe('axis fault');
  expect(normalized.robot.queue_size).toBe(2);
  expect(normalized.robot.safety_status).toBe('SAFE');
  expect(normalized.robot.position).toEqual({ x: 10, y: 20, z: 30 });
});

test('STATE_UPDATE derives board turn from FEN when turn is omitted', () => {
  const normalized = Normalizer.normalize('STATE_UPDATE', {
    board: {
      fen: 'rnbakabnr/9/9/9/9/9/9/9/9/RNBAKABNR b - - 0 1',
    },
  });

  expect(normalized.board.turn).toBe('black');
});

test('DIAGNOSTICS.UPDATED preserves runtime diagnostics and queue aliases', () => {
  const normalized = Normalizer.normalize('DIAGNOSTICS.UPDATED', {
    queues: {
      robot: { size: 1, blocked: true, blocked_reason: 'stale_item' },
    },
    event_bus: { sequence: 12 },
    persistence: { dropped_events: 0 },
    async_runtime: { loop_running: true },
    control: { safe_mode: true },
  });

  expect(normalized.queue.robot.blocked).toBe(true);
  expect(normalized.queues.robot.blocked_reason).toBe('stale_item');
  expect(normalized.event_bus.sequence).toBe(12);
  expect(normalized.runtime.event_bus.sequence).toBe(12);
  expect(normalized.runtime.async_runtime.loop_running).toBe(true);
});
