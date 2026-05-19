import { jest } from '@jest/globals';
import {
  apiFetch,
  apiJson,
  clearAdminToken,
  getStoredRole,
  hasValidAdminSession,
  isTokenExpired,
  loginAdmin,
  setAdminToken
} from '../static/js/modules/core/api_client.js';

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  global.fetch = jest.fn(async () => ({
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ ok: true }),
  }));
});

test('apiFetch attaches admin token and JSON content type', async () => {
  setAdminToken('t123');

  await apiFetch('/api/move', {
    method: 'POST',
    body: JSON.stringify({ move: 'a0a1', type: 'MANUAL' }),
  });

  expect(global.fetch).toHaveBeenCalledTimes(1);
  const [url, options] = global.fetch.mock.calls[0];

  expect(url).toBe('/api/move');
  expect(options.method).toBe('POST');
  expect(options.headers.get('Authorization')).toBe('Bearer t123');
  expect(options.headers.get('Content-Type')).toBe('application/json');
});

test('clearAdminToken removes stored console credentials', () => {
  setAdminToken('t123');
  clearAdminToken();

  expect(window.sessionStorage.getItem('adminToken')).toBe(null);
  expect(window.localStorage.getItem('token')).toBe(null);
  expect(window.sessionStorage.getItem('adminRole')).toBe(null);
  expect(window.localStorage.getItem('role')).toBe(null);
  expect(getStoredRole()).toBe('viewer');
});

test('setAdminToken stores the console role used by UI guards', () => {
  window.localStorage.setItem('token', 'old-persistent-token');
  window.localStorage.setItem('role', 'admin');
  setAdminToken('t123', 'admin');

  expect(window.sessionStorage.getItem('adminToken')).toBe('t123');
  expect(window.sessionStorage.getItem('adminRole')).toBe('admin');
  expect(window.localStorage.getItem('token')).toBe(null);
  expect(window.localStorage.getItem('role')).toBe(null);
  expect(getStoredRole()).toBe('admin');
});

test('loginAdmin stores returned token and role', async () => {
  global.fetch = jest.fn(async () => ({
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({ ok: true, token: 'jwt-token', role: 'admin' }),
  }));

  await loginAdmin('secret');

  expect(window.sessionStorage.getItem('adminToken')).toBe('jwt-token');
  expect(window.sessionStorage.getItem('adminRole')).toBe('admin');
});

test('hasValidAdminSession clears expired JWT tokens', () => {
  const expiredPayload = btoa(JSON.stringify({ role: 'admin', exp: 1 })).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
  const token = `header.${expiredPayload}.signature`;
  setAdminToken(token, 'admin');

  expect(isTokenExpired(token, 2000)).toBe(true);
  expect(hasValidAdminSession()).toBe(false);
  expect(window.sessionStorage.getItem('adminToken')).toBe(null);
});

test('hasValidAdminSession rejects malformed console tokens', () => {
  setAdminToken('stale-token', 'admin');

  expect(isTokenExpired('stale-token')).toBe(true);
  expect(hasValidAdminSession()).toBe(false);
  expect(window.sessionStorage.getItem('adminToken')).toBe(null);
});

test('apiJson returns parsed payload on successful response', async () => {
  global.fetch = jest.fn(async () => ({
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({ ok: true, status: 'accepted' }),
  }));

  const payload = await apiJson('/api/state');
  expect(payload).toEqual({ ok: true, status: 'accepted' });
});

test('apiJson raises a useful error on failed response payload', async () => {
  global.fetch = jest.fn(async () => ({
    ok: false,
    status: 401,
    headers: new Headers(),
    json: async () => ({ message: 'unauthorized' }),
  }));

  await expect(apiJson('/api/state')).rejects.toThrow('unauthorized');
});

test('apiFetch maps aborts to request_timeout', async () => {
  global.fetch = jest.fn(async () => {
    const error = new Error('aborted');
    error.name = 'AbortError';
    throw error;
  });

  await expect(apiFetch('/api/state')).rejects.toThrow('request_timeout');
});
