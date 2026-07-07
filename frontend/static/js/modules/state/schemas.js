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
    if (type === 'STATE_UPDATE' || type === 'GAME.STATE_APPLIED') {
        return validateStateUpdate(payload);
    }
    if (type === 'ENGINE.INFO_UPDATED' || type === 'ENGINE_ANALYSIS_COMPLETED') {
        return validateEngineInfo(payload);
    }
    if (type === 'DIAGNOSTICS.UPDATED' || type === 'DIAGNOSTICS_UPDATED') {
        return validateDiagnostics(payload);
    }
    if (type === 'VISION.FRAME_PROCESSED') {
        return validateVisionFrame(payload);
    }
    if (type === 'ROBOT.STATUS_UPDATED' || type === 'ROBOT_STATUS_UPDATED') {
        return validateRobotStatus(payload);
    }
    return { ok: true };
}

function isPlainObject(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isNumberLike(value) {
    return value === undefined || (typeof value === 'number' && Number.isFinite(value));
}

function isBooleanLike(value) {
    return value === undefined || typeof value === 'boolean';
}

function isStringLike(value) {
    return value === undefined || value === null || typeof value === 'string';
}

function validateStateUpdate(payload) {
    const roots = ['board', 'game', 'state', 'engine', 'robot', 'sync'];
    if (!roots.some((key) => key in payload)) {
        return { ok: false, reason: 'state_update_missing_root' };
    }
    for (const key of ['board', 'engine', 'robot', 'sync', 'ui', 'vision', 'game']) {
        if (payload[key] !== undefined && !isPlainObject(payload[key])) {
            return { ok: false, reason: `${key}_not_object` };
        }
    }
    if (payload.board?.pieces !== undefined && !Array.isArray(payload.board.pieces)) {
        return { ok: false, reason: 'board_pieces_not_array' };
    }
    return { ok: true };
}

function validateEngineInfo(payload) {
    for (const key of ['score', 'depth', 'nodes', 'nps']) {
        if (!isNumberLike(payload[key])) {
            return { ok: false, reason: `${key}_not_number` };
        }
    }
    if (payload.pv !== undefined && !Array.isArray(payload.pv)) {
        return { ok: false, reason: 'pv_not_array' };
    }
    if (payload.multiPv !== undefined && !Array.isArray(payload.multiPv)) {
        return { ok: false, reason: 'multiPv_not_array' };
    }
    if (!isStringLike(payload.best_move) || !isStringLike(payload.bestMove)) {
        return { ok: false, reason: 'best_move_not_string' };
    }
    if (!isBooleanLike(payload.is_thinking)) {
        return { ok: false, reason: 'is_thinking_not_boolean' };
    }
    return { ok: true };
}

function validateDiagnostics(payload) {
    for (const key of [
        'ui',
        'sync',
        'engine',
        'robot',
        'vision',
        'health',
        'telemetry',
        'queue',
        'queues',
        'pipeline',
        'topology',
        'workers',
        'event_bus',
        'persistence',
        'async_runtime',
        'control',
        'runtime'
    ]) {
        if (payload[key] !== undefined && !isPlainObject(payload[key])) {
            return { ok: false, reason: `${key}_not_object` };
        }
    }
    return { ok: true };
}

function validateVisionFrame(payload) {
    for (const key of ['timestamp', 'latency_ms', 'detections_count', 'avg_confidence', 'min_confidence', 'confidence']) {
        if (!isNumberLike(payload[key])) {
            return { ok: false, reason: `${key}_not_number` };
        }
    }
    if (payload.detections !== undefined && !Array.isArray(payload.detections)) {
        return { ok: false, reason: 'detections_not_array' };
    }
    if (payload.board_state !== undefined && !isPlainObject(payload.board_state)) {
        return { ok: false, reason: 'board_state_not_object' };
    }
    return { ok: true };
}

function validateRobotStatus(payload) {
    if (!isBooleanLike(payload.connected) || !isBooleanLike(payload.busy)) {
        return { ok: false, reason: 'robot_boolean_field_invalid' };
    }
    if (!isNumberLike(payload.queue_size)) {
        return { ok: false, reason: 'queue_size_not_number' };
    }
    if (payload.position !== undefined && !isPlainObject(payload.position)) {
        return { ok: false, reason: 'position_not_object' };
    }
    return { ok: true };
}
