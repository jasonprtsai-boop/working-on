import { jest } from '@jest/globals';

const commitMock = jest.fn();

jest.unstable_mockModule('../static/js/modules/state/state.js', () => ({
  commit: commitMock
}));

beforeEach(() => {
  commitMock.mockClear();
});

test('websocket adapter forwards raw payload to the state manager once', async () => {
  const { setupEventAdapter } = await import('../static/js/modules/websocket/event_adapter.js');
  const socket = {
    on: jest.fn((_event, callback) => {
      callback({
        type: 'ENGINE.INFO_UPDATED',
        payload: { score: 42, best_move: 'b0c2' }
      });
    })
  };

  setupEventAdapter(socket);

  expect(socket.on).toHaveBeenCalledWith('SYSTEM_STATE_UPDATE', expect.any(Function));
  expect(commitMock).toHaveBeenCalledWith('ENGINE.INFO_UPDATED', {
    score: 42,
    best_move: 'b0c2'
  });
});

test('websocket adapter preserves legacy raw state snapshots', async () => {
  const { setupEventAdapter } = await import('../static/js/modules/websocket/event_adapter.js');
  const socket = {
    on: jest.fn((_event, callback) => {
      callback({ board: { fen: 'startpos', pieces: [] } });
    })
  };

  setupEventAdapter(socket);

  expect(commitMock).toHaveBeenCalledWith('STATE_UPDATE', {
    board: { fen: 'startpos', pieces: [] }
  });
});

test('websocket adapter reports malformed socket messages without crashing', async () => {
  const { setupEventAdapter } = await import('../static/js/modules/websocket/event_adapter.js');
  const socket = {
    on: jest.fn((_event, callback) => {
      callback(null);
    })
  };

  setupEventAdapter(socket);

  expect(commitMock).toHaveBeenCalledWith('UI_TOAST', {
    text: 'Ignored malformed socket event.',
    level: 'warning',
    source: 'socket'
  });
});

test('websocket adapter rejects unknown event types before state mutation', async () => {
  const { setupEventAdapter } = await import('../static/js/modules/websocket/event_adapter.js');
  const socket = {
    on: jest.fn((_event, callback) => {
      callback({ type: 'UNKNOWN.EVENT', payload: { board: { fen: 'bad' } } });
    })
  };

  setupEventAdapter(socket);

  expect(commitMock).not.toHaveBeenCalledWith('UNKNOWN.EVENT', expect.anything());
  expect(commitMock).toHaveBeenCalledWith('UI_TOAST', expect.objectContaining({
    text: 'Ignored unknown socket event: UNKNOWN.EVENT',
    level: 'warning',
    source: 'socket'
  }));
});

test('websocket adapter rejects invalid known payload shapes', async () => {
  const { setupEventAdapter } = await import('../static/js/modules/websocket/event_adapter.js');
  const socket = {
    on: jest.fn((_event, callback) => {
      callback({ type: 'STATE_UPDATE', payload: 'not-an-object' });
    })
  };

  setupEventAdapter(socket);

  expect(commitMock).not.toHaveBeenCalledWith('STATE_UPDATE', 'not-an-object');
  expect(commitMock).toHaveBeenCalledWith('UI_TOAST', expect.objectContaining({
    text: 'Ignored invalid socket payload: STATE_UPDATE',
    reason: 'payload_not_object'
  }));
});
