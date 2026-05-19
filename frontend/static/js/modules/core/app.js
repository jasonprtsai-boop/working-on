/**
 * app.js - System Orchestrator
 *
 * Coordinates transport, state, rendering, and top-level UI actions.
 */

import { commit } from '../state/state.js';
import { initRenderer } from '../board/render.js';
import { socketClient } from '../websocket/socket_client.js';
import { setupEventAdapter } from '../websocket/event_adapter.js';
import { setupSocketStatus } from '../websocket/socket_status.js';
import { UIRegistry } from '../ui/ui_registry.js';
import { exportCsvReport, exportExcelReport } from './export_controller.js';
import { apiJson, clearAdminToken, getAdminToken, getStoredRole, hasValidAdminSession, loginAdmin } from './api_client.js';

const ADMIN_ONLY_CONTROL_IDS = [
    'btn-estop-trigger',
    'btn-export-excel',
    'btn-export-csv',
    'btn-snapshot',
    'btn-resume-overlay',
    'btn-session-start',
    'btn-session-end',
];

document.addEventListener('DOMContentLoaded', () => {
    if (window.__SMART_DEBUG__) {
        console.log('System: Industrial Platform Booting...');
    }

    UIRegistry.init();
    installGlobalHelpers();
    setupEventAdapter(socketClient);
    initRenderer();
    setupUI();
    setupSocketStatus(socketClient, UIRegistry);
    loadInitialStateSnapshot();

    socketClient.on('ui_lock', (data) => {
        if (data?.locked === false) {
            hideSystemOverlay();
            commit('DIAGNOSTICS.UPDATED', { ui: { estop_triggered: false, phase: 'READY' } });
            window.showAlert?.(data?.reason || 'Emergency stop cleared.', 'success');
            return;
        }
        showSystemOverlay(data?.reason || 'Emergency stop triggered.');
        commit('DIAGNOSTICS.UPDATED', { ui: { estop_triggered: true, phase: 'EMERGENCY' } });
    });
    socketClient.on('AUTH_ERROR', (payload) => {
        if (payload?.code === 'unauthorized') clearAdminToken();
        refreshAuthorizationUI();
        window.showAlert?.(payload?.message || 'Socket authorization failed.', 'error');
    });

    switchView('view-landing');
});

function installGlobalHelpers() {
    window.showAlert = (message, level = 'info', timeoutMs = 3200) => {
        try {
            const container = document.getElementById('toast-container');
            if (!container) return;

            const mapped =
                level === 'warning' ? 'warn' :
                level === 'danger' ? 'error' :
                level;

            const toast = document.createElement('div');
            toast.className = `toast ${mapped}`;
            toast.innerText = String(message || '');
            container.appendChild(toast);

            const remove = () => {
                try {
                    toast.remove();
                } catch {
                    // Node may already be detached.
                }
            };
            setTimeout(remove, Math.max(800, Number(timeoutMs) || 3200));
            toast.addEventListener('click', remove);
        } catch {
            // Toasts are non-critical UI.
        }
    };

    window.handleVideoError = (imgEl) => {
        if (!hasAdminAccess()) return;
        const pill = document.getElementById('video-status-pill');
        if (pill) {
            pill.classList.remove('live');
            pill.classList.add('standby');
            replacePillContent(pill, 'video reconnecting');
        }
        if (!imgEl) return;

        const src = imgEl.dataset?.src || '/api/video_feed';
        setTimeout(() => {
            imgEl.src = src + (src.includes('?') ? '&' : '?') + 't=' + Date.now();
        }, 800);
    };
}

function setupUI() {
    bindClick('btn-role-player', () => switchView('view-player'));
    bindClick('btn-role-console', requestConsoleAccess);
    bindClick('btn-exit', () => switchView('view-landing'));
    bindClick('btn-console-exit', () => switchView('view-landing'));
    bindClick('btn-toggle-board', () => switchPane('pane-board-view', 'btn-toggle-board'));
    bindClick('btn-toggle-video', () => switchPane('pane-video-view', 'btn-toggle-video'));
    bindClick('btn-toggle-status', () => switchPane('pane-status-view', 'btn-toggle-status'));
    bindClick('btn-reconnect-video', reconnectVideo);
    bindClick('btn-snapshot', snapshotVideo);
    bindClick('btn-estop-trigger', triggerEmergencyStop);
    bindClick('btn-resume-overlay', clearEmergencyStop);
    bindClick('btn-export-excel', exportExcelReport);
    bindClick('btn-export-csv', exportCsvReport);
    bindClick('btn-auth-cancel', hideAuthOverlay);
    bindSubmit('admin-login-form', submitAdminLogin);
    setupEngineDepthControls();
    setupSafeModeControl();
    setupSessionControls();
    setupSidebarTabs();
    installAuthorizationGuards();

    const videoFeed = UIRegistry.get('videoFeed');
    if (videoFeed) {
        videoFeed.dataset.src = '/api/video_feed';
        videoFeed.addEventListener('error', () => window.handleVideoError(videoFeed));
        if (hasAdminAccess()) reconnectVideo();
    }

    commit('UI_TOAST', { text: 'System console ready.', level: 'info' });
    loadRuntimeControlStatus({ quiet: true });
}

function bindClick(id, handler) {
    const element = document.getElementById(id);
    if (element) element.addEventListener('click', handler);
}

function bindSubmit(id, handler) {
    const element = document.getElementById(id);
    if (element) element.addEventListener('submit', handler);
}

function switchView(viewId) {
    const sections = document.querySelectorAll('section[id^="view-"]');
    sections.forEach((section) => {
        const isActive = section.id === viewId;
        section.classList.toggle('hidden', !isActive);
        section.classList.toggle('active', isActive);
        section.setAttribute('aria-hidden', isActive ? 'false' : 'true');
    });

    const arena = document.getElementById('game-arena');
    if (arena) arena.classList.toggle('hidden', viewId !== 'view-player');
}

function requestConsoleAccess() {
    if (!hasAdminAccess()) {
        refreshAuthorizationUI();
        showAuthOverlay();
        return;
    }
    hideAuthOverlay();
    switchView('view-console');
    reconnectVideo();
    loadRuntimeControlStatus({ quiet: true });
    refreshAuthorizationUI();
}

function setupSidebarTabs() {
    document.querySelectorAll('.tab-btn[data-tab]').forEach((button, index) => {
        button.addEventListener('click', () => {
            const tab = button.dataset.tab;
            document.querySelectorAll('.tab-btn[data-tab]').forEach((item) => {
                item.classList.toggle('active', item === button);
                item.setAttribute('aria-selected', item === button ? 'true' : 'false');
            });
            document.querySelectorAll('.tab-pane').forEach((pane) => {
                pane.classList.toggle('active', pane.id === `pane-${tab}`);
            });

            const indicator = document.getElementById('tab-indicator');
            if (indicator) indicator.style.transform = `translateX(${index * 100}%)`;
        });
    });
}

async function clearEmergencyStop() {
    if (!canUseLiveAdminControls()) {
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    try {
        await apiJson('/api/estop/reset', { method: 'POST', body: JSON.stringify({ reason: 'operator_reset' }) });
        hideSystemOverlay();
        commit('DIAGNOSTICS.UPDATED', { ui: { estop_triggered: false, phase: 'READY' } });
    } catch (error) {
        window.showAlert?.(error?.message || 'Failed to clear emergency stop.', 'error');
    }
}

async function triggerEmergencyStop() {
    if (!canUseLiveAdminControls()) {
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    showSystemOverlay('Emergency stop triggered from console.');
    commit('DIAGNOSTICS.UPDATED', { ui: { estop_triggered: true, phase: 'EMERGENCY' } });
    try {
        await apiJson('/api/estop/trigger', { method: 'POST', body: JSON.stringify({ reason: 'frontend_console' }) });
    } catch (error) {
        window.showAlert?.(error?.message || 'Failed to trigger emergency stop.', 'error');
    }
}

function showSystemOverlay(reason) {
    const overlay = document.getElementById('pause-overlay');
    const title = document.getElementById('overlay-title');
    const message = document.getElementById('pause-msg');
    if (title) title.innerText = 'SYSTEM HALTED';
    if (message) message.innerText = reason;
    if (overlay) {
        overlay.classList.remove('hidden');
        overlay.classList.add('active');
    }
}

function hideSystemOverlay() {
    const overlay = document.getElementById('pause-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
        overlay.classList.remove('active');
    }
}

function switchPane(paneId, buttonId) {
    document.querySelectorAll('.view-pane').forEach((pane) => {
        pane.classList.toggle('active', pane.id === paneId);
    });
    document.querySelectorAll('.mode-btn').forEach((button) => {
        button.classList.toggle('active', button.id === buttonId);
    });
}

function reconnectVideo() {
    if (!hasAdminAccess()) return;
    const videoFeed = UIRegistry.get('videoFeed');
    if (!videoFeed) return;
    const src = videoFeed.dataset?.src || '/api/video_feed';
    videoFeed.src = `${src}${src.includes('?') ? '&' : '?'}t=${Date.now()}`;

    const pill = document.getElementById('video-status-pill');
    if (pill) {
        pill.classList.remove('standby');
        pill.classList.add('live');
        replacePillContent(pill, 'live');
    }
}

function snapshotVideo() {
    if (!canUseLiveAdminControls()) {
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    window.open('/api/snapshot', '_blank', 'noopener,noreferrer');
}

function installAuthorizationGuards() {
    ADMIN_ONLY_CONTROL_IDS.forEach((id) => {
        const element = document.getElementById(id);
        if (element) {
            element.dataset.requiresAdmin = 'true';
            element.dataset.requiresLive = 'true';
        }
    });
    document.querySelectorAll('.depth-btn, #safe-mode-toggle, #session-participant-id').forEach((element) => {
        element.dataset.requiresAdmin = 'true';
        element.dataset.requiresLive = 'true';
    });

    window.addEventListener('storage', refreshAuthorizationUI);
    window.addEventListener('smart:connection-status', refreshAuthorizationUI);
    window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') hideAuthOverlay();
    });
    refreshAuthorizationUI();
}

function hasAdminAccess() {
    return Boolean(getAdminToken()) && getStoredRole() === 'admin' && hasValidAdminSession();
}

function canUseLiveAdminControls() {
    const status = document.body?.dataset?.connectionStatus || 'offline';
    const stale = document.body?.dataset?.stateStale !== 'false';
    return hasAdminAccess() && status === 'online' && !stale;
}

function refreshAuthorizationUI() {
    const isAdmin = hasAdminAccess();
    const live = (document.body?.dataset?.connectionStatus || 'offline') === 'online';
    const fresh = document.body?.dataset?.stateStale === 'false';
    const disabled = !isAdmin || !live || !fresh;

    document.body?.classList.toggle('auth-viewer', !isAdmin);
    document.body?.classList.toggle('auth-admin', isAdmin);

    document.querySelectorAll('[data-requires-admin="true"]').forEach((element) => {
        element.disabled = disabled;
        element.setAttribute('aria-disabled', disabled ? 'true' : 'false');
        element.dataset.authDisabled = disabled ? 'true' : 'false';
    });
}

async function loadInitialStateSnapshot() {
    try {
        const payload = await apiJson('/api/state', { method: 'GET' }, 5000);
        commit('STATE_UPDATE', payload);
    } catch {
        document.body?.classList.add('state-fallback-unavailable');
    }
}

async function loadRuntimeControlStatus({ quiet = false } = {}) {
    if (!hasAdminAccess()) return;
    try {
        const payload = await apiJson('/api/runtime/control', { method: 'GET' }, 5000);
        applyRuntimeControlStatus(payload);
    } catch (error) {
        if (!quiet) window.showAlert?.(error?.message || 'Runtime control status unavailable.', 'warning');
    }
}

async function submitAdminLogin(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = form?.querySelector?.('#admin-password')?.value || '';
    const errorEl = document.getElementById('auth-error');
    if (errorEl) errorEl.textContent = '';

    try {
        await loginAdmin(password);
        hideAuthOverlay();
        socketClient.connect();
        switchView('view-console');
        reconnectVideo();
        loadRuntimeControlStatus({ quiet: true });
        refreshAuthorizationUI();
        window.showAlert?.('Admin console unlocked.', 'success');
    } catch (error) {
        if (errorEl) errorEl.textContent = error?.message || 'Login failed.';
        window.showAlert?.('Admin login failed.', 'error');
    } finally {
        if (form) form.reset();
    }
}

function showAuthOverlay() {
    const overlay = document.getElementById('auth-overlay');
    if (!overlay) return;
    overlay.classList.remove('hidden');
    overlay.classList.add('active');
    overlay.setAttribute('aria-hidden', 'false');
    const input = document.getElementById('admin-password');
    setTimeout(() => input?.focus?.(), 0);
}

function hideAuthOverlay() {
    const overlay = document.getElementById('auth-overlay');
    if (!overlay) return;
    overlay.classList.add('hidden');
    overlay.classList.remove('active');
    overlay.setAttribute('aria-hidden', 'true');
}

function replacePillContent(element, labelText) {
    element.textContent = '';
    const dot = document.createElement('span');
    dot.className = 'dot';
    const label = document.createElement('span');
    label.textContent = ` ${labelText}`;
    element.append(dot, label);
}

function setupEngineDepthControls() {
    document.querySelectorAll('.depth-btn[data-depth]').forEach((button) => {
        button.addEventListener('click', () => setEngineDepth(button.dataset.depth));
    });
}

async function setEngineDepth(depth) {
    if (!canUseLiveAdminControls()) {
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    try {
        const payload = await apiJson('/api/runtime/engine-depth', {
            method: 'POST',
            body: JSON.stringify({ depth: Number(depth) }),
        });
        applyRuntimeControlStatus(payload);
    } catch (error) {
        window.showAlert?.(error?.message || 'Failed to update AI depth.', 'error');
    }
}

function setupSafeModeControl() {
    const toggle = document.getElementById('safe-mode-toggle');
    if (!toggle) return;
    toggle.addEventListener('change', () => setSafeMode(Boolean(toggle.checked)));
}

async function setSafeMode(enabled) {
    const toggle = document.getElementById('safe-mode-toggle');
    if (!canUseLiveAdminControls()) {
        if (toggle) toggle.checked = !enabled;
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    try {
        const payload = await apiJson('/api/runtime/safe-mode', {
            method: 'POST',
            body: JSON.stringify({ enabled }),
        });
        applyRuntimeControlStatus(payload);
    } catch (error) {
        if (toggle) toggle.checked = !enabled;
        window.showAlert?.(error?.message || 'Failed to update Safe Mode.', 'error');
    }
}

function setupSessionControls() {
    bindClick('btn-session-start', startExperimentSession);
    bindClick('btn-session-end', endExperimentSession);
}

async function startExperimentSession() {
    if (!canUseLiveAdminControls()) {
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    const input = document.getElementById('session-participant-id');
    const participantId = String(input?.value || '').trim();
    try {
        const payload = await apiJson('/api/runtime/session/start', {
            method: 'POST',
            body: JSON.stringify({ participant_id: participantId }),
        });
        writeSessionValue('participant_id', participantId);
        writeSessionValue('participantId', participantId);
        applyRuntimeControlStatus(payload);
    } catch (error) {
        window.showAlert?.(error?.message || 'Failed to start session.', 'error');
    }
}

async function endExperimentSession() {
    if (!canUseLiveAdminControls()) {
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    try {
        const payload = await apiJson('/api/runtime/session/end', { method: 'POST', body: JSON.stringify({}) });
        applyRuntimeControlStatus(payload);
    } catch (error) {
        window.showAlert?.(error?.message || 'Failed to end session.', 'error');
    }
}

function applyRuntimeControlStatus(payload = {}) {
    const snapshot = payload.runtime_control || payload;
    const session = snapshot.session || payload.session || {};
    const ui = {
        safe_mode: snapshot.safe_mode,
        ai_difficulty: snapshot.ai_difficulty,
        engine_depth: snapshot.engine_depth,
        participant_id: session.participant_id,
        session_id: session.session_id,
        session_active: session.active,
        session_started_at: session.started_at,
        session_ended_at: session.ended_at,
        session_time_sec: session.duration_sec,
        move_count: session.move_count,
        latest_step: session.latest_move,
    };

    const safeToggle = document.getElementById('safe-mode-toggle');
    if (safeToggle && typeof snapshot.safe_mode === 'boolean') safeToggle.checked = snapshot.safe_mode;

    const participantInput = document.getElementById('session-participant-id');
    if (participantInput && session.participant_id) participantInput.value = session.participant_id;
    if (session.participant_id) {
        writeSessionValue('participant_id', session.participant_id);
        writeSessionValue('participantId', session.participant_id);
    }

    if (snapshot.engine_depth !== undefined) setActiveDepthButton(snapshot.engine_depth);
    commit('DIAGNOSTICS.UPDATED', { ui });
}

function setActiveDepthButton(depth) {
    const normalized = String(Number(depth));
    document.querySelectorAll('.depth-btn[data-depth]').forEach((button) => {
        button.classList.toggle('active', String(Number(button.dataset.depth)) === normalized);
    });
}

function writeSessionValue(key, value) {
    try {
        window.sessionStorage?.setItem(key, String(value || ''));
    } catch {
        // Storage is best-effort.
    }
}
