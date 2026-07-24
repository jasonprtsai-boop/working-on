/**
 * state_manager.js - [State Layer] Central SSOT Orchestrator.
 */

import { boardState, updateBoard } from './board_state.js';
import { engineState, updateEngineState } from './engine_state.js';
import { uiState, updateUIState } from './ui_state.js';
import { syncState, updateSyncState } from './sync_state.js';
import { Subscriptions } from './subscriptions.js';
import { EventStore } from './event_store.js';
import { Normalizer } from './normalizer.js';

export const state = {
    snapshot: {
        board: boardState,
        engine: engineState,
        ui: uiState,
        sync: syncState,
        robot: {
            connected: false,
            is_connected: false,
            busy: false,
            error: null,
            last_action: "",
            queue_size: 0,
            safety_status: "UNKNOWN",
            position: { x: 0, y: 0, z: 0 },
            orientation: { rx: 0, ry: 0, rz: 0 },
            joint_angles: {},
            speed: null,
            ip: "",
            port: null,
            connection: {},
            telemetry: {}
        },
        vision: {
            fps: 0,
            latency: 0,
            latency_ms: 0,
            detections: [],
            detections_count: 0,
            fen: "",
            fen_after: "",
            ucci_position: "",
            board_state: {},
            avg_confidence: 0,
            min_confidence: 0,
            status: "OK",
            mode: "unknown",
            simulation: false
        }
    },
    version: 0
};

export function commit(type, payload) {
    // 1. Normalize Payload
    const normalized = Normalizer.normalize(type, payload);

    const event = {
        type,
        payload: normalized,
        timestamp: Date.now(),
        version: ++state.version
    };

    // 2. Store Event for Replay/Telemetry
    EventStore.append(event);

    const oldPieces = [...state.snapshot.board.pieces];

    // 3. Dispatch to Domain Reducers
    const isUpdate = type === "STATE_UPDATE" ||
                     type === "GAME.STATE_APPLIED" ||
                     type === "VISION.FRAME_PROCESSED" ||
                     type.endsWith(".UPDATED") ||
                     type.endsWith("_UPDATED") ||
                     type.endsWith("_COMPLETED");

    if (isUpdate && normalized) {
        const receivedAt = event.timestamp;
        state.snapshot.sync.lastReceivedAt = receivedAt;
        state.snapshot.sync.stale = false;
        dispatchStateReceived(receivedAt, type);

        if (normalized.board) {
            updateBoard(normalized.board);
            Subscriptions.notify('board', { pieces: state.snapshot.board.pieces, oldPieces });
        }
        if (normalized.engine) {
            updateEngineState(normalized.engine);
            Subscriptions.notify('engine', state.snapshot.engine);
        }
        if (normalized.ui) {
            updateUIState(normalized.ui);
            Subscriptions.notify('ui', state.snapshot.ui);
        }
        if (normalized.sync) {
            updateSyncState({ ...normalized.sync, lastReceivedAt: receivedAt, stale: false });
            Subscriptions.notify('sync', state.snapshot.sync);
        } else {
            Subscriptions.notify('sync', state.snapshot.sync);
        }
        if (normalized.robot) {
            state.snapshot.robot = { ...state.snapshot.robot, ...normalized.robot };
            Subscriptions.notify('robot', state.snapshot.robot);
        }
        if (normalized.vision) {
            state.snapshot.vision = { ...state.snapshot.vision, ...normalized.vision };
            Subscriptions.notify('vision', state.snapshot.vision);
        }
        if (normalized.notation) {
            Subscriptions.notify('notation', normalized.notation);
        }
    }

    // Notify any global event listeners (like telemetry UI)
    Subscriptions.notify('events', event);
}

export function markStateStale(reason = 'stale') {
    state.snapshot.sync.stale = true;
    Subscriptions.notify('sync', state.snapshot.sync);
    try {
        window.dispatchEvent(new CustomEvent('smart:state-stale', {
            detail: { reason, lastReceivedAt: state.snapshot.sync.lastReceivedAt },
        }));
    } catch {
        // Browser event bridge is best-effort.
    }
}

function dispatchStateReceived(timestamp, type) {
    try {
        window.dispatchEvent(new CustomEvent('smart:state-received', {
            detail: { timestamp, type },
        }));
    } catch {
        // Browser event bridge is best-effort.
    }
}

// Re-export subscription helper for convenience
export const subscribe = Subscriptions.subscribe;
