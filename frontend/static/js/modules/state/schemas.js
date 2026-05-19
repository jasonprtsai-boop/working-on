/**
 * schemas.js - [State Layer] Definition of frontend data schemas.
 * Ensures consistent data types across the application.
 */

export const Schemas = {
    Board: {
        fen: "",
        pieces: [],
        turn: "red",
        move_count: 0,
        last_move: null,
        lastMove: null
    },
    Engine: {
        score: 0,
        depth: 0,
        nodes: 0,
        nps: 0,
        bestMove: "",
        pv: [],
        advantage: "draw",
        isThinking: false
    },
    Robot: {
        connected: false,
        busy: false,
        error: null,
        last_action: "",
        queue_size: 0,
        safety_status: "UNKNOWN",
        position: { x: 0, y: 0, z: 0 }
    },
    Sync: {
        version: 0,
        latency: 0,
        fps: 0,
        timeline: {
            vision: { duration: 0 },
            engine: { duration: 0 },
            robot: { duration: 0 }
        }
    }
};

export const KNOWN_EVENTS = new Set([
    'STATE_UPDATE',
    'GAME.STATE_APPLIED',
    'VISION.FRAME_PROCESSED',
    'ENGINE.INFO_UPDATED',
    'ENGINE_ANALYSIS_COMPLETED',
    'DIAGNOSTICS.UPDATED',
    'DIAGNOSTICS_UPDATED',
    'ROBOT.STATUS_UPDATED',
    'ROBOT_STATUS_UPDATED',
    'UI_TOAST',
]);

export function validateFrontendEventPayload(type, payload) {
    if (!KNOWN_EVENTS.has(type)) {
        return { ok: false, reason: 'unknown_event' };
    }
    if (!isPlainObject(payload)) {
        return { ok: false, reason: 'payload_not_object' };
    }
    return { ok: true };
}

function isPlainObject(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
