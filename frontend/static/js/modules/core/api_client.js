const DEFAULT_TIMEOUT_MS = 7000;

function readStorage(storageName, key) {
    try {
        return window?.[storageName]?.getItem(key) || '';
    } catch {
        return '';
    }
}

function writeStorage(storageName, key, value) {
    try {
        window?.[storageName]?.setItem(key, value);
    } catch {
        // Storage can be disabled in private windows or tests.
    }
}

function removeStorage(storageName, key) {
    try {
        window?.[storageName]?.removeItem(key);
    } catch {
        // Storage can be disabled in private windows or tests.
    }
}

export function getAdminToken() {
    return readStorage('sessionStorage', 'adminToken');
}

export function getStoredRole() {
    const role = readStorage('sessionStorage', 'adminRole');
    if (role) return role;
    return getAdminToken() ? 'admin' : 'viewer';
}

export function setAdminToken(token, role = 'admin') {
    if (!token) return;
    writeStorage('sessionStorage', 'adminToken', token);
    writeStorage('sessionStorage', 'adminRole', role || 'admin');
    // Clear legacy persistent tokens so admin credentials do not survive browser restarts.
    removeStorage('localStorage', 'token');
    removeStorage('localStorage', 'role');
}

export function clearAdminToken() {
    removeStorage('sessionStorage', 'adminToken');
    removeStorage('localStorage', 'token');
    removeStorage('sessionStorage', 'adminRole');
    removeStorage('localStorage', 'role');
}

export function isTokenExpired(token = getAdminToken(), nowMs = Date.now()) {
    const payload = decodeJwtPayload(token);
    if (!payload || typeof payload.exp !== 'number') return true;
    return payload.exp * 1000 <= nowMs;
}

export function hasValidAdminSession() {
    const token = getAdminToken();
    if (!token) return false;
    const claims = decodeJwtPayload(token);
    if (!claims || claims.role !== 'admin' || typeof claims.exp !== 'number' || isTokenExpired(token)) {
        clearAdminToken();
        return false;
    }
    return getStoredRole() === 'admin';
}

export async function loginAdmin(password) {
    const payload = await apiJson('/api/login', {
        method: 'POST',
        body: JSON.stringify({ password: String(password || '') }),
    });
    if (!payload?.token) {
        throw new Error(payload?.message || 'login_failed');
    }
    setAdminToken(payload.token, payload.role || 'admin');
    return payload;
}

function decodeJwtPayload(token) {
    try {
        const parts = String(token || '').split('.');
        if (parts.length < 2) return null;
        const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
        return JSON.parse(globalThis.atob(padded));
    } catch {
        return null;
    }
}

export async function apiFetch(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Number(timeoutMs) || DEFAULT_TIMEOUT_MS);
    const headers = new Headers(options.headers || {});
    const hasBody = options.body !== undefined && options.body !== null;

    if (hasBody && !headers.has('Content-Type') && typeof options.body === 'string') {
        headers.set('Content-Type', 'application/json');
    }

    const token = getAdminToken();
    if (token && !headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
    }

    try {
        return await fetch(url, {
            ...options,
            headers,
            signal: controller.signal,
        });
    } catch (error) {
        if (error?.name === 'AbortError') {
            throw new Error('request_timeout');
        }
        throw error;
    } finally {
        clearTimeout(timer);
    }
}

export async function apiJson(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const response = await apiFetch(url, options, timeoutMs);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
        throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
    }
    return payload;
}
