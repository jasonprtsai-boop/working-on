/**
 * socket_client.js - [Infrastructure] Low-level Socket.IO wrapper.
 */
const noopSocket = {
    on() {},
    emit(_event, _data, callback) {
        if (typeof callback === 'function') {
            callback({ ok: false, code: 'socket_unavailable', message: 'Socket unavailable.' });
        }
    },
    connect() {},
    disconnect() {}
};

function readStoredToken() {
    try {
        return window.sessionStorage?.getItem('adminToken') || '';
    } catch {
        return '';
    }
}

function socketOptions() {
    return {
        timeout: 7000,
        reconnectionAttempts: 10,
        withCredentials: true,
        auth(callback) {
            const token = readStoredToken();
            callback(token ? { token } : {});
        }
    };
}

export const socket = (typeof window !== 'undefined' && typeof window.io === 'function')
    ? window.io(socketOptions())
    : (typeof globalThis !== 'undefined' && typeof globalThis.io === 'function')
        ? globalThis.io(socketOptions())
        : noopSocket;

export const socketClient = {
    on(event, callback) {
        socket.on?.(event, callback);
        if (['reconnect_attempt', 'reconnect', 'reconnect_error', 'reconnect_failed'].includes(event)) {
            socket.io?.on?.(event, callback);
        }
    },
    emit(event, data, callback) {
        socket.emit?.(event, data, callback);
    },
    emitWithAck(event, data, timeoutMs = 7000) {
        return new Promise((resolve) => {
            let settled = false;
            const done = (error, ack) => {
                if (settled) return;
                settled = true;
                if (error) {
                    resolve({ ok: false, code: 'socket_timeout', message: 'Command timed out.' });
                    return;
                }
                resolve(ack || { ok: false, code: 'missing_ack', message: 'Command returned no acknowledgement.' });
            };

            try {
                if (typeof socket.timeout === 'function') {
                    socket.timeout(timeoutMs).emit(event, data, done);
                    return;
                }
                socket.emit?.(event, data, (ack) => done(null, ack));
            } catch (error) {
                done(error);
            }
        });
    },
    connect() {
        socket.connect?.();
    },
    isConnected() {
        return Boolean(socket.connected);
    }
};
