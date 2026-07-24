import { BoardRenderer } from './board_renderer.js';
import { renderEngineMetrics } from './engine_renderer.js';
import { renderRobotStatus } from './robot_renderer.js';
import { renderDiagnostics } from './diagnostics_renderer.js';
import { VisionRenderer } from './vision_renderer.js';
import { DashboardRenderer } from './dashboard_renderer.js';
import { subscribe, state } from '../state/state.js';
import { UIRegistry } from '../ui/ui_registry.js';
import { TelemetryRenderer } from '../ui/telemetry_renderer.js';
import { SystemStatusStrip } from '../ui/system_status_strip.js';

const mainBoard = new BoardRenderer('board-pieces');
const adminBoard = new BoardRenderer('console-pieces');
let rendererInitialized = false;
let unsubscribeHandlers = [];

export function initRenderer() {
    if (rendererInitialized) return;
    rendererInitialized = true;

    TelemetryRenderer.init('admin-logs');
    SystemStatusStrip.init();
    VisionRenderer.init();
    DashboardRenderer.init();
    DashboardRenderer.render(state.snapshot);
    updateTurnIndicators();

    unsubscribeHandlers.push(subscribe('board', ({ pieces, oldPieces }) => {
        mainBoard.render(oldPieces, pieces);
        adminBoard.render(oldPieces, pieces);
        updateTurnIndicators();
        DashboardRenderer.render(state.snapshot);
    }));

    unsubscribeHandlers.push(subscribe('events', (event) => {
        TelemetryRenderer.renderEvent(event);
        SystemStatusStrip.handleEvent(event);

        if (event.type === 'RECOVERY_STARTED') {
            window.showAlert?.(`Recovery started: ${event.payload?.strategy || 'unknown'}`, 'warning');
            return;
        }
        if (event.type === 'RECOVERY_COMPLETED') {
            window.showAlert?.(`Recovery complete: ${event.payload?.status || 'ok'}`, 'success');
            return;
        }
        if (event.type === 'TOAST' || event.type === 'UI_TOAST') {
            const text = event.payload?.text || event.payload?.message || '';
            const level = event.payload?.level || 'info';
            if (text) window.showAlert?.(text, level);
        }
    }));

    unsubscribeHandlers.push(subscribe('vision', (visionState) => {
        VisionRenderer.render(visionState);
        renderDiagnostics({ vision: visionState });
        DashboardRenderer.render(state.snapshot);

        const fpsEl = UIRegistry.get('videoFps');
        const tsEl = UIRegistry.get('videoTs');
        if (fpsEl && typeof visionState?.fps === 'number') fpsEl.innerText = `FPS: ${Math.round(visionState.fps)}`;
        if (tsEl) tsEl.innerText = `更新：${new Date().toLocaleTimeString()}`;
    }));

    unsubscribeHandlers.push(subscribe('engine', (engineState) => {
        renderEngineMetrics(engineState);
        DashboardRenderer.render(state.snapshot);
    }));

    unsubscribeHandlers.push(subscribe('sync', (syncState) => {
        UIRegistry.updateTelemetry(syncState);
        renderDiagnostics(syncState);
        DashboardRenderer.render(state.snapshot);
    }));

    unsubscribeHandlers.push(subscribe('robot', (robotState) => {
        renderRobotStatus(robotState);
        DashboardRenderer.render(state.snapshot);
    }));

    unsubscribeHandlers.push(subscribe('ui', (uiState) => {
        updateUIStatus(uiState);
        DashboardRenderer.render(state.snapshot);
    }));
}

export function disposeRenderer() {
    unsubscribeHandlers.forEach((unsubscribe) => unsubscribe());
    unsubscribeHandlers = [];
    VisionRenderer.dispose();
    DashboardRenderer.dispose();
    rendererInitialized = false;
}

export function updateDisplay(_data) {}

function updateUIStatus(uiState) {
    const boardState = state.snapshot.board;
    const statusEl = UIRegistry.get('statusText');
    if (statusEl) statusEl.innerText = `系統：${translatePhaseLabel(uiState?.phase)}`;

    updateTurnIndicators(boardState);

    try {
        const overlay = document.getElementById('pause-overlay');
        if (overlay) {
            const phase = String(uiState?.phase || '').toLowerCase();
            const paused = phase === 'paused' || phase === 'pause';
            const emergency = phase === 'emergency' || Boolean(
                uiState?.estop_triggered || uiState?.e_stop || uiState?.emergency_stop,
            );
            const locked = paused || emergency;
            overlay.classList.toggle('hidden', !locked);
            overlay.classList.toggle('active', locked);
        }
    } catch {
        // Status overlay is non-critical.
    }
}

export function updateTurnIndicators(boardState = state.snapshot.board) {
    const display = getTurnDisplay(boardState);
    const indicators = [
        UIRegistry.get('turnIndicator'),
        UIRegistry.get('playerTurnIndicator'),
    ];

    indicators.forEach((turnEl) => {
        if (!turnEl) return;
        turnEl.innerText = display.label;
        turnEl.className = `turn-indicator-pill ${display.className}`;
        turnEl.setAttribute?.('title', display.description);
        turnEl.setAttribute?.('aria-label', display.description);
    });
}

export function getTurnDisplay(boardState = {}) {
    const turn = normalizeTurn(boardState.turn) || normalizeTurn(turnFromFen(boardState.fen));
    const isBlack = turn === 'black';
    return {
        label: isBlack ? '黑方移動' : '紅方移動',
        className: isBlack ? 'black' : 'red',
        description: isBlack ? '現在輪到黑方移動棋子' : '現在輪到紅方移動棋子',
    };
    return {
        label: isBlack ? '黑方移動' : '紅方移動',
        className: isBlack ? 'black' : 'red',
        description: isBlack ? '現在輪到黑方移動棋子' : '現在輪到紅方移動棋子',
    };
}

function normalizeTurn(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (['black', 'b', 'dark'].includes(normalized)) return 'black';
    if (['red', 'r', 'w', 'white', 'player'].includes(normalized)) return 'red';
    return '';
}

function turnFromFen(fen) {
    const parts = String(fen || '').trim().split(/\s+/);
    return parts.length > 1 ? parts[1] : '';
}

function translatePhaseLabel(phase) {
    const normalized = String(phase || '').trim().toUpperCase();
    const labels = {
        IDLE: '待命',
        READY: '就緒',
        RUNNING: '運行中',
        ACTIVE: '運行中',
        PAUSED: '已暫停',
        PAUSE: '已暫停',
        STOPPED: '已停止',
        RESETTING: '重置中',
        ERROR: '錯誤',
        EMERGENCY: '緊急停止',
    };
    return labels[normalized] || phase || '待命';
}
