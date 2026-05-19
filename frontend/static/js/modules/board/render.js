import { BoardRenderer } from './board_renderer.js';
import { renderEngineMetrics } from './engine_renderer.js';
import { renderRobotStatus } from './robot_renderer.js';
import { renderDiagnostics } from './diagnostics_renderer.js';
import { VisionRenderer } from './vision_renderer.js';
import { DashboardRenderer } from './dashboard_renderer.js';
import { subscribe, state } from '../state/state.js';
import { UIRegistry } from '../ui/ui_registry.js';
import { TelemetryRenderer } from '../ui/telemetry_renderer.js';

const mainBoard = new BoardRenderer('board-pieces');
const adminBoard = new BoardRenderer('console-pieces');
let rendererInitialized = false;
let unsubscribeHandlers = [];

export function initRenderer() {
    if (rendererInitialized) return;
    rendererInitialized = true;

    TelemetryRenderer.init('admin-logs');
    VisionRenderer.init();
    DashboardRenderer.init();
    DashboardRenderer.render(state.snapshot);

    unsubscribeHandlers.push(subscribe('board', ({ pieces, oldPieces }) => {
        mainBoard.render(oldPieces, pieces);
        adminBoard.render(oldPieces, pieces);
        DashboardRenderer.render(state.snapshot);
    }));

    unsubscribeHandlers.push(subscribe('events', (event) => {
        TelemetryRenderer.renderEvent(event);

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
        if (tsEl) tsEl.innerText = `Updated: ${new Date().toLocaleTimeString()}`;
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
    if (statusEl) statusEl.innerText = `System: ${translatePhaseLabel(uiState?.phase)}`;

    const turnEl = UIRegistry.get('turnIndicator');
    if (turnEl) {
        const isRed = boardState.turn === 'red';
        turnEl.innerText = isRed ? 'Red turn' : 'Black turn';
        turnEl.className = `turn-indicator-pill ${isRed ? 'red' : 'black'}`;
    }

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

function translatePhaseLabel(phase) {
    const normalized = String(phase || '').trim().toUpperCase();
    const labels = {
        IDLE: 'idle',
        READY: 'ready',
        RUNNING: 'running',
        ACTIVE: 'active',
        PAUSED: 'paused',
        PAUSE: 'paused',
        STOPPED: 'stopped',
        RESETTING: 'resetting',
        ERROR: 'error',
        EMERGENCY: 'emergency',
    };
    return labels[normalized] || phase || 'idle';
}
