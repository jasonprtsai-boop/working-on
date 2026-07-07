import { jest } from '@jest/globals';

beforeEach(() => {
  jest.resetModules();
  window.localStorage.clear();
  window.sessionStorage.clear();
  delete window.io;
});

test('socket client sends stored admin token during auth handshake', async () => {
  const socketMock = { on: jest.fn(), emit: jest.fn(), connect: jest.fn(), disconnect: jest.fn(), connected: false };
  window.io = jest.fn(() => socketMock);
  window.sessionStorage.setItem('adminToken', 'socket-token');

  await import('../static/js/modules/websocket/socket_client.js');

  expect(window.io).toHaveBeenCalledTimes(1);
  const options = window.io.mock.calls[0][0];
  expect(options.timeout).toBe(7000);
  expect(options.reconnectionAttempts).toBe(10);
  expect(options.withCredentials).toBe(true);
  const callback = jest.fn();
  options.auth(callback);

  expect(callback).toHaveBeenCalledWith({ token: 'socket-token' });
});

test('socket client falls back to cookie-backed auth when no bearer token is stored', async () => {
  const socketMock = { on: jest.fn(), emit: jest.fn(), connect: jest.fn(), disconnect: jest.fn(), connected: false };
  window.io = jest.fn(() => socketMock);

  await import('../static/js/modules/websocket/socket_client.js');

  const options = window.io.mock.calls[0][0];
  const callback = jest.fn();
  options.auth(callback);

  expect(callback).toHaveBeenCalledWith({});
  expect(options.withCredentials).toBe(true);
});

test('socket client exposes acknowledgement helper', async () => {
  const socketMock = {
    on: jest.fn(),
    emit: jest.fn((_event, _data, callback) => callback({ ok: true, action: 'RESET' })),
    connect: jest.fn(),
    disconnect: jest.fn(),
    connected: true
  };
  window.io = jest.fn(() => socketMock);

  const { socketClient } = await import('../static/js/modules/websocket/socket_client.js');
  const ack = await socketClient.emitWithAck('action', { type: 'RESET' });

  expect(ack).toEqual({ ok: true, action: 'RESET' });
  expect(socketMock.emit).toHaveBeenCalledWith('action', { type: 'RESET' }, expect.any(Function));
});
