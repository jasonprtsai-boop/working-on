/**
 * normalizer.js - [State Layer] Normalizes backend payloads into consistent frontend schemas.
 */

export const Normalizer = {
    normalize(type, payload) {
        if (!payload) return null;

        switch (type) {
            case "STATE_UPDATE":
            case "GAME.STATE_APPLIED":
                return this.systemState(payload);
            case "ENGINE.INFO_UPDATED":
                return { engine: this.engineInfo(payload) };
            case "DIAGNOSTICS.UPDATED":
                return this.diagnostics(payload);
            case "ROBOT.STATUS_UPDATED":
                return this.robotStatus(payload);
            case "VISION.FRAME_PROCESSED":
                return { vision: this.visionFrame(payload) };
            case "UI_TOAST":
                return this.uiToast(payload);
            default:
                return payload;
        }
    },

    systemState(data) {
        const board = data.board || {};
        const fen = board.fen || "";

        // Ensure standard structure for full state updates
        return {
            board: {
                fen,
                pieces: board.pieces || [],
                turn: normalizeBoardTurn(board.turn) || turnFromFen(fen) || "red",
                move_count: board.move_count || 0,
                last_move: board.last_move || null
            },
            engine: this.engineInfo(data.engine || {}),
            robot: this.robotStatus(data.robot || {}),
            vision: data.vision || {},
            sync: this.syncData(data.sync || {}),
            ui: data.ui || {},
            notation: data.game?.last_notation || data.notation || null
        };
    },

    engineInfo(data) {
        const rawScore = data.score ?? data.score_cp ?? 0;
        const score = Number.isFinite(Number(rawScore)) ? Number(rawScore) : 0;
        const bestMove = data.bestMove || data.best_move || data.bestmove || data.move || "";
        const multiPv = data.multiPv || data.multi_pv || data.multipv || data.suggestions || [];
        return {
            score,
            depth: data.depth || 0,
            nodes: data.nodes || 0,
            nps: data.nps || 0,
            best_move: bestMove,
            bestmove: bestMove,
            bestMove,
            pv: data.pv || [],
            multiPv,
            multipv: multiPv,
            advantage: score > 0 ? "red" : (score < 0 ? "black" : "draw"),
            is_thinking: data.is_thinking || false
        };
    },

    diagnostics(data) {
        const queue = data.queue || data.queues || {};
        const queues = data.queues || data.queue || {};
        const runtime = data.runtime || {};
        // Keep it loose: diagnostics may contain engine/vision status, backoff, errors, etc.
        return {
            ui: data.ui || {},
            sync: data.sync || {},
            engine: data.engine || {},
            robot: data.robot || {},
            vision: data.vision || {},
            health: data.health || {},
            telemetry: data.telemetry || {},
            queue,
            queues,
            pipeline: data.pipeline || {},
            topology: data.topology || {},
            workers: data.workers || {},
            event_bus: data.event_bus || runtime.event_bus || {},
            persistence: data.persistence || runtime.persistence || {},
            async_runtime: data.async_runtime || runtime.async_runtime || {},
            control: data.control || runtime.control || {},
            runtime: {
                ...runtime,
                event_bus: data.event_bus || runtime.event_bus || {},
                persistence: data.persistence || runtime.persistence || {},
                async_runtime: data.async_runtime || runtime.async_runtime || {},
                control: data.control || runtime.control || {},
            },
        };
    },

    robotStatus(data) {
        const connected = data.connected ?? data.is_connected ?? false;
        return {
            connected: Boolean(connected),
            is_connected: Boolean(connected),
            busy: Boolean(data.busy),
            error: data.error || null,
            last_action: data.last_action || "",
            current_command: data.current_command || "",
            queue_size: data.queue_size || 0,
            safety_status: data.safety_status || "UNKNOWN",
            estop_triggered: Boolean(data.estop_triggered || data.global_stop),
            global_stop: Boolean(data.global_stop),
            position: data.position || data.robot_position || { x: 0, y: 0, z: 0 }
        };
    },

    visionFrame(data) {
        const detections = data.detections || [];
        const avgConfidence = data.avg_confidence ?? data.avgConfidence ?? data.confidence ?? 0;
        const minConfidence = data.min_confidence ?? data.minConfidence ?? avgConfidence;
        const timestamp = data.timestamp || Date.now() / 1000;
        const sourceTimestamp = data.source_timestamp ?? data.sourceTimestamp ?? data.stable_timestamp ?? timestamp;
        const processedTimestamp = data.processed_timestamp ?? data.processedTimestamp ?? timestamp;
        const visionAgeMs = firstFiniteNumber(
            data.vision_age_ms,
            data.visionAgeMs,
            ageMsFromTimestamp(sourceTimestamp, processedTimestamp),
        );
        const stale = Boolean(data.stale ?? data.is_stale ?? data.isStale ?? (visionAgeMs > 3000));
        return {
            fps: data.fps || 0,
            latency: data.latency || data.latency_ms || 0,
            latency_ms: data.latency_ms || data.latency || 0,
            detections,
            detections_count: data.detections_count ?? detections.length,
            fen: data.fen || data.fen_after || "",
            fen_after: data.fen_after || data.fen || "",
            fen_valid: data.fen_valid ?? data.fenValid ?? undefined,
            ucci_position: data.ucci_position || "",
            board_state: data.board_state || {},
            avg_confidence: avgConfidence,
            min_confidence: minConfidence,
            confidence: avgConfidence,
            stable: Boolean(data.stable),
            camera_ready: data.camera_ready ?? data.cameraReady ?? undefined,
            safe_mode: data.safe_mode ?? data.safeMode ?? undefined,
            calibration: data.calibration || {},
            calibrated: data.calibrated ?? data.calibration?.calibrated ?? undefined,
            calibration_quality: data.calibration_quality || data.calibrationQuality || data.calibration?.quality || {},
            calibration_source: data.calibration_source || data.calibrationSource || data.calibration?.source || "",
            timestamp,
            source_timestamp: sourceTimestamp,
            processed_timestamp: processedTimestamp,
            vision_age_ms: visionAgeMs,
            stale,
            is_stale: stale,
            status: stale ? (data.status || "STALE") : (data.status || "OK")
        };
    },

    uiToast(data) {
        return {
            text: data.text || "",
            level: data.level || "info",
            source: data.source || "system"
        };
    },

    syncData(data) {
        return {
            version: data.version || 0,
            latency: data.latency || 0,
            fps: data.fps || 0,
            lastReceivedAt: data.lastReceivedAt || 0,
            stale: Boolean(data.stale),
            timeline: data.timeline || {
                vision: { duration: 0 },
                engine: { duration: 0 },
                robot: { duration: 0 }
            }
        };
    }
};

function normalizeBoardTurn(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (['black', 'b', 'dark'].includes(normalized)) return 'black';
    if (['red', 'r', 'w', 'white'].includes(normalized)) return 'red';
    return '';
}

function turnFromFen(fen) {
    const side = String(fen || '').trim().split(/\s+/)[1];
    return normalizeBoardTurn(side);
}

function firstFiniteNumber(...values) {
    for (const value of values) {
        const numeric = Number(value);
        if (Number.isFinite(numeric)) return numeric;
    }
    return 0;
}

function timestampToMs(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return 0;
    return numeric < 100000000000 ? numeric * 1000 : numeric;
}

function ageMsFromTimestamp(sourceTimestamp, processedTimestamp) {
    const sourceMs = timestampToMs(sourceTimestamp);
    const processedMs = timestampToMs(processedTimestamp) || Date.now();
    if (!sourceMs || !processedMs) return 0;
    return Math.max(0, processedMs - sourceMs);
}
