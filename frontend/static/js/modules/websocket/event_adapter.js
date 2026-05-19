/**
 * event_adapter.js - [Transport] Normalizes incoming backend events.
 */
import { commit } from '../state/state.js';
import { KNOWN_EVENTS, validateFrontendEventPayload } from '../state/schemas.js';

export function normalizeSocketEvent(event) {
    if (!event || typeof event !== 'object' || Array.isArray(event)) {
        return null;
    }

    const hasType = typeof event.type === 'string' && event.type.trim();
    if (hasType) {
        return {
            type: event.type.trim(),
            payload: event.payload ?? {}
        };
    }

    // Legacy path: older backend snapshots were sent as the raw state payload.
    return {
        type: 'STATE_UPDATE',
        payload: event
    };
}

export function setupEventAdapter(socket) {
    if (!socket?.on) return;

    socket.on("SYSTEM_STATE_UPDATE", (event) => {
        const normalized = normalizeSocketEvent(event);
        if (!normalized) {
            commit('UI_TOAST', {
                text: 'Ignored malformed socket event.',
                level: 'warning',
                source: 'socket'
            });
            return;
        }
        if (!KNOWN_EVENTS.has(normalized.type)) {
            commit('UI_TOAST', {
                text: `Ignored unknown socket event: ${normalized.type}`,
                level: 'warning',
                source: 'socket'
            });
            return;
        }
        const validation = validateFrontendEventPayload(normalized.type, normalized.payload);
        if (!validation.ok) {
            commit('UI_TOAST', {
                text: `Ignored invalid socket payload: ${normalized.type}`,
                level: 'warning',
                source: 'socket',
                reason: validation.reason
            });
            return;
        }
        commit(normalized.type, normalized.payload);
    });
}
