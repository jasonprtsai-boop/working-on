/**
 * app.js - System Orchestrator
 *
 * Coordinates transport, state, rendering, and top-level UI actions.
 */

import { commit, state, subscribe } from '../state/state.js';
import { initRenderer } from '../board/render.js';
import { socketClient } from '../websocket/socket_client.js';
import { setupEventAdapter } from '../websocket/event_adapter.js';
import { setupSocketStatus } from '../websocket/socket_status.js';
import { UIRegistry } from '../ui/ui_registry.js';
import { exportCsvReport, exportExcelReport, exportReplayJson } from './export_controller.js';
import {
    apiJson,
    clearAdminToken,
    clearSetupToken,
    getStoredRole,
    hasValidAdminSession,
    hasValidSetupSession,
    loginAdmin,
    loginSetup,
} from './api_client.js';

const REPLAY_ALL_SESSIONS = '__all__';

const ADMIN_ONLY_CONTROL_IDS = [
    'btn-export-excel',
    'btn-export-csv',
    'btn-export-replay',
    'btn-replay-refresh',
    'btn-replay-prev',
    'btn-replay-next',
    'replay-session-select',
    'replay-step-range',
    'btn-resume-overlay',
    'btn-session-start',
    'btn-session-end',
];

let playerGameStarted = false;
let playerStartPreflight = null;
let robotPlayRequestActive = false;
let robotPlayCooldownUntil = 0;
let playerEndRequestActive = false;
let videoReconnectAttempts = 0;
let videoReconnectTimer = null;
let videoStreamActive = false;
let setupStatusTimerId = null;
const setupWizardState = {
    settingsSaved: false,
    preflight: null,
    commissioning: null,
};
const replayState = {
    sessions: [],
    steps: [],
    sessionId: null,
    step: 0,
    currentPayload: null,
    loaded: false,
};
const runtimeControlState = {
    sessionActive: null,
};
const VIDEO_RECONNECT_BASE_MS = 5000;
const VIDEO_RECONNECT_MAX_MS = 30000;
const VISION_STALE_THRESHOLD_MS = 3000;
const ROBOT_PLAY_CONFIRM_MESSAGE = '警告：即將送出機械手臂 Play 訊號，請勿靠近棋盤與手臂工作範圍。確認 TMflow 已在控制器端啟動、所有人員已離開後，才可以繼續。';
const PLAYER_END_CONFIRM_MESSAGE = '確定要結束目前對局嗎？結束後玩家不能再送出棋步或啟動機械手臂；這不是實體急停。';
const PLAYER_END_FINAL_CONFIRM_MESSAGE = '再次確認：你真的要結束對局嗎？若手臂正在動作，請保持距離並由工作人員處理急停。';
const LIVE_HARDWARE_ACTIONS = new Set([
    'gripper_open',
    'gripper_close',
    'write_pose',
    'safe_z',
    'origin',
    'dead_zone',
    'corner_a0',
    'corner_i0',
    'corner_a9',
    'corner_i9',
    'center_e4',
    'grab_z',
    'one_move',
]);
const LIVE_HARDWARE_ACTION_LABELS = {
    gripper_open: '放開夾爪',
    gripper_close: '夾取棋子',
    write_pose: '寫入座標',
    safe_z: '移到安全 Z',
    origin: '移到原點',
    dead_zone: '移到死棋區',
    corner_a0: '移到 a0 安全 Z',
    corner_i0: '移到 i0 安全 Z',
    corner_a9: '移到 a9 安全 Z',
    corner_i9: '移到 i9 安全 Z',
    center_e4: '移到 e4 安全 Z',
    grab_z: '移到 e4 夾取 Z',
    one_move: '執行 a0a1 測試',
};
const LAB_ROBOT_DEFAULTS = {
    'robot.connection.adapter': 'tmflow_json',
    'robot.connection.ip': '192.168.10.10',
    'robot.connection.port': 5890,
    'robot.connection.pc_ip': '192.168.10.50',
    'robot.connection.subnet_mask': '255.255.0.0',
    'robot.tmflow_json.wire_format': 'envelope',
};

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
        videoStreamActive = false;
        markVideoStatus('standby', '重新連線中');
        scheduleVideoReconnect(imgEl);
    };
}

function setupUI() {
    bindClick('btn-role-player', () => switchView('view-player'));
    bindClick('btn-player-start', startPlayerGame);
    bindClick('btn-player-vision-capture', submitPlayerDone);
    bindClick('btn-player-end-game', endPlayerGame);
    bindClick('btn-start-tmflow', startRobotArmFlow);
    bindClick('btn-role-console', requestConsoleAccess);
    bindClick('btn-role-setup', requestSetupAccess);
    bindClick('btn-exit', () => switchView('view-landing'));
    bindClick('btn-setup-exit', () => switchView('view-landing'));
    bindClick('btn-console-exit', () => switchView('view-landing'));
    bindClick('btn-toggle-board', () => switchPane('pane-board-view', 'btn-toggle-board'));
    bindClick('btn-toggle-video', () => switchPane('pane-video-view', 'btn-toggle-video'));
    bindClick('btn-video-reconnect', () => reconnectVideo({ force: true }));
    bindClick('btn-toggle-setup', requestSetupAccess);
    bindClick('btn-toggle-status', () => switchPane('pane-status-view', 'btn-toggle-status'));
    bindClick('btn-resume-overlay', resumeFromOverlay);
    bindClick('btn-export-excel', exportExcelReport);
    bindClick('btn-export-csv', exportCsvReport);
    bindClick('btn-export-replay', () => exportReplayJson(replayState.sessionId));
    bindClick('btn-auth-cancel', hideAuthOverlay);
    bindClick('btn-setup-auth-cancel', hideSetupAuthOverlay);
    bindSubmit('admin-login-form', submitAdminLogin);
    bindSubmit('setup-login-form', submitSetupLogin);
    setupEngineDepthControls();
    setupAiModeControls();
    setupSafeModeControl();
    setupSessionControls();
    setupSettingsControls();
    setupPlayerGuide();
    setupSidebarTabs();
    setupReplayControls();
    setupModeTabsKeyboard();
    installAuthorizationGuards();

    const videoFeed = UIRegistry.get('videoFeed');
    if (videoFeed) {
        videoFeed.dataset.src = '/api/video_feed';
        videoFeed.addEventListener('load', () => handleVideoLoad());
        videoFeed.addEventListener('error', () => window.handleVideoError(videoFeed));
        if (hasAdminAccess()) reconnectVideo();
    }

    commit('UI_TOAST', { text: '主控台已就緒。', level: 'info' });
    loadRuntimeControlStatus({ quiet: true });
    refreshVisionCalibration({ quiet: true });
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

    if (viewId !== 'view-player') {
        playerGameStarted = false;
        playerStartPreflight = null;
    }
    updatePlayerStartPreflightAlert(playerStartPreflight);
    updatePlayerStartGate(viewId === 'view-player');
    if (viewId === 'view-setup') {
        startSetupRobotStatusRefresh();
    } else {
        stopSetupRobotStatusRefresh();
    }
}

function updatePlayerStartGate(isPlayerView) {
    const startPanel = document.getElementById('player-start-panel');
    const arena = document.getElementById('game-arena');
    const showArena = playerGameStarted || isGameEnded(state.snapshot?.board || {});

    if (!isPlayerView) {
        startPanel?.classList.add('hidden');
        arena?.classList.add('hidden');
        return;
    }

    startPanel?.classList.toggle('hidden', showArena);
    arena?.classList.toggle('hidden', !showArena);
}

async function startPlayerGame() {
    if (playerGameStarted) return;

    const button = document.getElementById('btn-player-start');
    if (button) button.disabled = true;
    try {
        const payload = await apiJson('/api/player/start', {
            method: 'POST',
            body: JSON.stringify({ source: 'player_start_button' }),
        });
        playerStartPreflight = normalizePlayerPreflight(payload.preflight);
        updatePlayerStartPreflightAlert(playerStartPreflight);
        if (playerPreflightBlocksStart(playerStartPreflight)) {
            window.showAlert?.(playerPreflightMessage(playerStartPreflight), 'warning', 5200);
            return;
        }

        playerGameStarted = true;
        updatePlayerStartGate(true);
        applyRuntimeControlStatus(payload);
        updatePlayerGuide();
        if (playerPreflightHasWarnings(playerStartPreflight)) {
            window.showAlert?.(playerPreflightMessage(playerStartPreflight), 'warning', 5200);
        } else {
            window.showAlert?.('對局已開始。', 'success');
        }
        await loadInitialStateSnapshot();
    } catch (error) {
        const preflight = normalizePlayerPreflight(error?.payload?.details?.preflight);
        if (preflight) {
            playerStartPreflight = preflight;
            updatePlayerStartPreflightAlert(preflight);
            window.showAlert?.(playerPreflightMessage(preflight), 'warning', 5200);
            return;
        }

        const message = String(error?.message || '');
        if (message.includes('Valid session') || message.includes('unauthorized') || message.includes('401')) {
            // Player mode is public; do not route player-start failures into admin auth.
            window.showAlert?.('請先登入操作權限後再開始玩家模式。', 'warning');
        } else {
            window.showAlert?.(message || '無法開始對局。', 'error');
        }
    } finally {
        if (button) button.disabled = false;
    }
}

function normalizePlayerPreflight(preflight) {
    if (!preflight || typeof preflight !== 'object') return null;
    const failures = Array.isArray(preflight.failures) ? preflight.failures : [];
    const warnings = Array.isArray(preflight.warnings) ? preflight.warnings : [];
    return {
        ...preflight,
        ready: Boolean(preflight.ready ?? preflight.ok),
        failures,
        warnings,
    };
}

function playerPreflightBlocksStart(preflight) {
    return Boolean(preflight && preflight.ready === false && preflight.failures.length > 0);
}

function playerPreflightHasWarnings(preflight) {
    return Boolean(preflight && preflight.warnings.length > 0);
}

function playerPreflightMessage(preflight) {
    const item = preflight?.failures?.[0] || preflight?.warnings?.[0] || null;
    return String(item?.message || '系統預檢尚未通過。');
}

function updatePlayerStartPreflightAlert(preflight) {
    const alert = document.getElementById('player-start-preflight-alert');
    if (!alert) return;
    if (!preflight || (preflight.ready !== false && preflight.warnings.length === 0)) {
        alert.classList.add('hidden');
        alert.textContent = '';
        alert.dataset.state = 'standby';
        return;
    }

    const blocking = playerPreflightBlocksStart(preflight);
    alert.classList.remove('hidden');
    alert.dataset.state = blocking ? 'error' : 'warning';
    alert.textContent = blocking
        ? `無法開始：${playerPreflightMessage(preflight)}`
        : `可開始，但需注意：${playerPreflightMessage(preflight)}`;
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
    refreshVisionCalibration({ quiet: true });
    refreshAuthorizationUI();
    void prepareConsoleStandby({ quiet: true });
}

function requestSetupAccess() {
    if (!hasValidSetupSession()) {
        refreshAuthorizationUI();
        showSetupAuthOverlay();
        return;
    }
    hideSetupAuthOverlay();
    openSetupPane();
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
            if (tab === 'replay') {
                void loadReplayBrowser({ quiet: true });
            }
        });
    });
}

function setupReplayControls() {
    bindClick('btn-replay-refresh', () => loadReplayBrowser({ quiet: false, force: true }));
    bindClick('btn-replay-prev', () => showReplayStep(replayState.step - 1));
    bindClick('btn-replay-next', () => showReplayStep(replayState.step + 1));

    const sessionSelect = document.getElementById('replay-session-select');
    if (sessionSelect) {
        sessionSelect.addEventListener('change', () => {
            replayState.sessionId = sessionSelect.value === REPLAY_ALL_SESSIONS ? null : sessionSelect.value;
            replayState.step = 0;
            void loadReplaySteps({ quiet: false });
        });
    }

    const range = document.getElementById('replay-step-range');
    if (range) {
        range.addEventListener('change', () => showReplayStep(Number(range.value || 0)));
    }

    renderReplayStep();
}

async function loadReplayBrowser({ quiet = false, force = false } = {}) {
    if (!hasAdminAccess()) {
        setReplayStatus('請先解鎖主控台');
        return false;
    }
    if (replayState.loaded && !force) {
        return true;
    }

    setReplayStatus('載入場次中');
    try {
        const payload = await apiJson('/api/replay/sessions?limit=50', { method: 'GET' }, 8000);
        replayState.sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
        replayState.loaded = true;
        if (
            replayState.sessionId !== null
            && !replayState.sessions.some((item) => replaySessionId(item) === replayState.sessionId)
        ) {
            replayState.sessionId = null;
        }
        renderReplaySessions();
        await loadReplaySteps({ quiet: true });
        if (!quiet) window.showAlert?.('回放資料已更新。', 'success');
        return true;
    } catch (error) {
        replayState.loaded = false;
        replayState.steps = [];
        replayState.currentPayload = null;
        renderReplaySessions();
        renderReplayStep();
        setReplayStatus(error?.message || '回放資料無法載入');
        if (!quiet) window.showAlert?.(error?.message || '回放資料無法載入。', 'error');
        return false;
    }
}

function renderReplaySessions() {
    const select = document.getElementById('replay-session-select');
    if (!select) return;
    select.innerHTML = '';

    const allOption = document.createElement('option');
    allOption.value = REPLAY_ALL_SESSIONS;
    allOption.textContent = '所有回放事件';
    select.appendChild(allOption);

    replayState.sessions.forEach((session) => {
        const id = replaySessionId(session);
        const option = document.createElement('option');
        option.value = id;
        option.textContent = `${session.label || id || '未分配回放事件'} (${session.event_count || 0})`;
        select.appendChild(option);
    });
    select.value = replayState.sessionId === null ? REPLAY_ALL_SESSIONS : replayState.sessionId;
}

function replaySessionId(session = {}) {
    if (Object.prototype.hasOwnProperty.call(session, 'session_id')) {
        return String(session.session_id ?? '');
    }
    return String(session.id ?? '');
}

async function loadReplaySteps({ quiet = false } = {}) {
    if (!hasAdminAccess()) {
        setReplayStatus('請先解鎖主控台');
        return false;
    }
    setReplayStatus('載入步驟中');
    try {
        const params = new URLSearchParams({ limit: '500' });
        if (replayState.sessionId !== null) params.set('session', replayState.sessionId);
        const payload = await apiJson(`/api/replay/steps?${params.toString()}`, { method: 'GET' }, 8000);
        replayState.steps = Array.isArray(payload.steps) ? payload.steps : [];
        replayState.step = replayState.steps.length
            ? Math.min(Math.max(Number(replayState.step) || 0, 0), replayState.steps.length - 1)
            : 0;
        replayState.currentPayload = null;
        if (!replayState.steps.length) {
            renderReplayStep();
            setReplayStatus('尚無可回放事件');
            return true;
        }
        await showReplayStep(replayState.step, { quiet: true });
        if (!quiet) window.showAlert?.('回放步驟已載入。', 'success');
        return true;
    } catch (error) {
        replayState.steps = [];
        replayState.currentPayload = null;
        renderReplayStep();
        setReplayStatus(error?.message || '回放步驟無法載入');
        if (!quiet) window.showAlert?.(error?.message || '回放步驟無法載入。', 'error');
        return false;
    }
}

async function showReplayStep(step, { quiet = false } = {}) {
    if (!replayState.steps.length) {
        renderReplayStep();
        return false;
    }
    const index = Math.min(Math.max(Number(step) || 0, 0), replayState.steps.length - 1);
    replayState.step = index;
    renderReplayStep();

    try {
        const params = new URLSearchParams();
        if (replayState.sessionId !== null) params.set('session', replayState.sessionId);
        const suffix = params.toString() ? `?${params.toString()}` : '';
        replayState.currentPayload = await apiJson(`/api/replay/step/${index}${suffix}`, { method: 'GET' }, 8000);
        renderReplayStep();
        setReplayStatus('回放資料已載入');
        return true;
    } catch (error) {
        replayState.currentPayload = null;
        renderReplayStep();
        setReplayStatus(error?.message || '回放步驟無法載入');
        if (!quiet) window.showAlert?.(error?.message || '回放步驟無法載入。', 'error');
        return false;
    }
}

function renderReplayStep() {
    const count = replayState.steps.length;
    const index = count ? Math.min(Math.max(Number(replayState.step) || 0, 0), count - 1) : 0;
    const item = replayState.steps[index] || {};
    const payload = replayState.currentPayload || {};
    const replay = payload._replay || {};
    const board = payload.board || payload.game || {};
    const fen = board.fen || item.fen || '--';

    setTextById('replay-current-step', count ? `${index + 1} / ${count}` : '--');
    setTextById('replay-event-type', replay.type || item.type || '--');
    setTextById('replay-move', replayValue(item.move || board.last_move || board.move));
    setTextById('replay-turn', replayValue(item.turn || board.turn || board.current_turn));
    setTextById('replay-timestamp', replayTime(replay.timestamp || item.timestamp));
    setTextById('replay-fen', fen);

    const range = document.getElementById('replay-step-range');
    if (range) {
        range.max = String(Math.max(count - 1, 0));
        range.value = String(index);
        range.disabled = count === 0;
    }
    const prev = document.getElementById('btn-replay-prev');
    const next = document.getElementById('btn-replay-next');
    if (prev) prev.disabled = count === 0 || index <= 0;
    if (next) next.disabled = count === 0 || index >= count - 1;
    const exportButton = document.getElementById('btn-export-replay');
    if (exportButton && canUseLiveAdminControls()) exportButton.disabled = count === 0;
}

function setReplayStatus(value) {
    setTextById('replay-status', value);
}

function replayValue(value) {
    if (value === undefined || value === null || value === '') return '--';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

function replayTime(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return '--';
    const ms = numeric > 1e12 ? numeric : numeric * 1000;
    return new Date(ms).toLocaleString('zh-TW');
}

async function resumeFromOverlay() {
    if (!requireLiveAdminControls()) return;
    try {
        await apiJson('/api/control', {
            method: 'POST',
            body: JSON.stringify({ action: 'resume', payload: { source: 'overlay' } }),
        });
        hideSystemOverlay();
        commit('DIAGNOSTICS.UPDATED', { ui: { phase: 'READY' } });
    } catch (error) {
        window.showAlert?.(error?.message || '恢復監控失敗。', 'error');
    }
}

function showSystemOverlay(reason) {
    const overlay = document.getElementById('pause-overlay');
    const title = document.getElementById('overlay-title');
    const message = document.getElementById('pause-msg');
    if (title) title.innerText = '系統已停止';
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
        const active = pane.id === paneId;
        pane.classList.toggle('active', active);
        pane.setAttribute('aria-hidden', active ? 'false' : 'true');
    });
    document.querySelectorAll('.mode-btn').forEach((button) => {
        const active = button.id === buttonId;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
}

function setupModeTabsKeyboard() {
    const tabs = Array.from(document.querySelectorAll('.view-mode-toggle .mode-btn'));
    tabs.forEach((tab, index) => {
        tab.addEventListener('keydown', (event) => {
            let nextIndex = null;
            if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                nextIndex = (index + 1) % tabs.length;
            } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                nextIndex = (index - 1 + tabs.length) % tabs.length;
            } else if (event.key === 'Home') {
                nextIndex = 0;
            } else if (event.key === 'End') {
                nextIndex = tabs.length - 1;
            }

            if (nextIndex === null) {
                return;
            }

            event.preventDefault();
            tabs[nextIndex].focus();
            tabs[nextIndex].click();
        });
    });
}

function openSetupPane() {
    switchView('view-setup');
    renderSetupRobotStatus(state.snapshot.robot || {});
    loadSetupCommissioning({ quiet: true });
    loadSetupSettings({ quiet: true });
    refreshSetupCameras({ quiet: true });
    reconnectSetupCamera();
    refreshAuthorizationUI();
}

function setupSettingsControls() {
    bindClick('btn-setup-load', () => loadSetupSettings());
    bindClick('btn-setup-refresh-cameras', () => refreshSetupCameras());
    bindClick('btn-setup-preview-camera', reconnectSetupCamera);
    bindClick('btn-setup-test-vision-source', testSetupVisionSource);
    bindClick('btn-setup-vision-auto', autoCalibrateSetupVision);
    bindClick('btn-setup-preflight', () => refreshSetupPreflight());
    bindClick('btn-setup-wizard-refresh', () => refreshSetupPreflight());
    bindClick('btn-setup-refresh-robot-status', () => refreshSetupRobotStatus());
    bindClick('btn-setup-lab-defaults', applySetupLabDefaults);
    bindClick('btn-setup-init-test', runSetupInitializationTest);
    bindSubmit('setup-settings-form', saveSetupSettings);
    setupSetupPaneTabs();
    subscribe('robot', (robot) => renderSetupRobotStatus(robot));
    document.querySelectorAll('[data-setup-test]').forEach((button) => {
        button.addEventListener('click', () => runSetupHardwareTest(button.dataset.setupTest));
    });
    document.querySelectorAll('[data-setup-vision-source]').forEach((button) => {
        button.addEventListener('click', () => selectSetupVisionSource(button.dataset.setupVisionSource));
    });

    document.querySelectorAll('[data-setup-field]').forEach((field) => {
        field.addEventListener('input', markSetupDirty);
        field.addEventListener('change', markSetupDirty);
    });
}

function setupSetupPaneTabs() {
    const form = document.getElementById('setup-settings-form');
    const tabs = Array.from(document.querySelectorAll('[data-setup-pane-target]'));
    if (!form || tabs.length === 0) return;

    const selectPane = (target) => {
        const normalized = target === 'live' ? 'live' : 'essential';
        form.dataset.setupTab = normalized;
        tabs.forEach((tab) => {
            const active = tab.dataset.setupPaneTarget === normalized;
            tab.classList.toggle('active', active);
            tab.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        if (normalized === 'live') {
            refreshSetupRobotStatus({ quiet: true });
        }
    };

    tabs.forEach((tab) => {
        tab.addEventListener('click', () => selectPane(tab.dataset.setupPaneTarget));
    });
    selectPane(form.dataset.setupTab);
}

async function loadSetupSettings({ quiet = false } = {}) {
    if (!hasSetupAccess()) return;
    try {
        const payload = await apiJson('/api/setup/settings', { method: 'GET' }, 6000);
        applySetupSettings(payload.settings || {}, payload.files || {});
        setupWizardState.settingsSaved = true;
        if (payload.commissioning) renderSetupCommissioning(payload.commissioning);
        renderSetupWizard();
        refreshSetupPreflight({ quiet: true });
        if (!quiet) window.showAlert?.('設定已載入。', 'success');
    } catch (error) {
        setSetupSaveState('載入失敗');
        if (!quiet) window.showAlert?.(error?.message || '設定無法取得。', 'error');
    }
}

async function saveSetupSettings(event) {
    event?.preventDefault?.();
    if (!requireSetupControls()) return false;

    try {
        const settings = collectSetupSettings();
        const payload = await apiJson('/api/setup/settings', {
            method: 'POST',
            body: JSON.stringify({ settings }),
        }, 9000);
        applySetupSettings(payload.settings || {}, payload.files || {});
        setupWizardState.settingsSaved = true;
        if (payload.commissioning) renderSetupCommissioning(payload.commissioning);
        renderSetupWizard();
        refreshSetupPreflight({ quiet: true });
        renderSetupInitializationSummary(payload.settings || {}, '已儲存，請執行測試');
        const warnings = Array.isArray(payload.warnings) ? payload.warnings.filter(Boolean) : [];
        if (warnings.length) {
            window.showAlert?.(warnings[0], 'warning', 5200);
        } else {
            window.showAlert?.('設定已儲存。', 'success');
        }
        return true;
    } catch (error) {
        setSetupSaveState('儲存失敗');
        window.showAlert?.(error?.message || '設定儲存失敗。', 'error');
        return false;
    }
}

async function refreshSetupCameras({ quiet = false } = {}) {
    if (!hasSetupAccess()) return;
    try {
        const payload = await apiJson('/api/vision/cameras?refresh=1', { method: 'GET' }, 9000);
        renderCameraOptions(payload.candidates || [], payload.current);
        if (!quiet) window.showAlert?.('相機清單已更新。', 'success');
    } catch (error) {
        ensureCameraOption(document.getElementById('setup-camera-index')?.value || '0');
        if (!quiet) window.showAlert?.(error?.message || '相機掃描失敗。', 'warning');
    }
}

async function autoCalibrateSetupVision() {
    if (!requireSetupControls()) return;
    try {
        const payload = await apiJson('/api/vision/calibration', {
            method: 'POST',
            body: JSON.stringify({ mode: 'auto', persist: true }),
        }, 12000);
        applyVisionCalibrationStatus(payload);
        await loadSetupSettings({ quiet: true });
        window.showAlert?.('視覺校正已更新。', 'success');
    } catch (error) {
        window.showAlert?.(error?.message || '視覺校正失敗。', 'error');
    }
}

async function refreshSetupPreflight({ quiet = false } = {}) {
    if (!hasSetupAccess()) return;
    try {
        const payload = await apiJson('/api/setup/preflight', { method: 'GET' }, 6000);
        if (payload.commissioning) renderSetupCommissioning(payload.commissioning);
        renderSetupPreflight(payload);
        if (!quiet) {
            window.showAlert?.(
                payload.ready ? '預檢已通過。' : '預檢需要處理。',
                payload.ready ? 'success' : 'warning'
            );
        }
    } catch (error) {
        setTextById('setup-preflight-status', '檢查失敗');
        if (!quiet) window.showAlert?.(error?.message || '預檢無法取得。', 'error');
    }
}

async function runSetupInitializationTest() {
    if (!requireSetupControls()) return false;
    setTextById('setup-init-result', '正在儲存設定');
    const saved = await saveSetupSettings();
    if (!saved) return false;
    setTextById('setup-init-result', '正在測試');
    return runSetupHardwareTest('connect');
}

async function runSetupHardwareTest(action) {
    if (!requireSetupControls()) return false;
    if (!action) return false;
    setTextById('setup-hardware-test-status', '測試中');
    if (action === 'connect') setTextById('setup-init-result', '測試中');
    try {
        const liveHardwareTest = document.getElementById('setup-live-hardware-test')?.checked === true;
        const body = { action, dry_run: !liveHardwareTest };
        if (liveHardwareTest && LIVE_HARDWARE_ACTIONS.has(action)) {
            if (!confirmLiveHardwareAction(action)) {
                setTextById('setup-hardware-test-status', `${action}: 已取消`);
                if (action === 'connect') renderSetupInitializationSummary({}, `${action}: 已取消`);
                return false;
            }
            body.confirmed_action = action;
            body.warning_acknowledged = true;
        }
        const payload = await apiJson('/api/setup/hardware-test', {
            method: 'POST',
            body: JSON.stringify(body),
        }, 12000);
        if (payload.status) {
            renderSetupRobotStatus(payload.status);
            commit('ROBOT.STATUS_UPDATED', payload.status);
        }
        if (payload.commissioning) renderSetupCommissioning(payload.commissioning);
        const label = payload.dry_run ? '模擬測試通過' : '測試通過';
        setTextById('setup-hardware-test-status', `${action}: ${label}`);
        if (action === 'connect') renderSetupInitializationSummary({}, `${action}: ${label}`);
        window.showAlert?.(`${action} ${label}`, 'success');
        refreshSetupPreflight({ quiet: true });
        return true;
    } catch (error) {
        setTextById('setup-hardware-test-status', `${action}: 失敗`);
        if (action === 'connect') renderSetupInitializationSummary({}, `${action}: 失敗`);
        window.showAlert?.(error?.message || `${action} 失敗。`, 'error');
        return false;
    }
}

function confirmLiveHardwareAction(action) {
    const label = LIVE_HARDWARE_ACTION_LABELS[action] || action;
    const message = `警告：${label} 會讓機械手臂或夾爪實際動作。請確認所有人員遠離棋盤與手臂工作範圍後再繼續。`;
    return typeof window.confirm === 'function' ? window.confirm(message) : false;
}

function startSetupRobotStatusRefresh() {
    renderSetupRobotStatus(state.snapshot.robot || {});
    refreshSetupRobotStatus({ quiet: true });
    refreshSetupVisionSourceStatus({ quiet: true });
    if (setupStatusTimerId || typeof setInterval !== 'function') return;
    setupStatusTimerId = setInterval(() => {
        const active = document.getElementById('view-setup')?.classList.contains('active');
        if (active) {
            refreshSetupRobotStatus({ quiet: true });
            refreshSetupVisionSourceStatus({ quiet: true });
        }
    }, 1000);
}

function stopSetupRobotStatusRefresh() {
    if (!setupStatusTimerId || typeof clearInterval !== 'function') return;
    clearInterval(setupStatusTimerId);
    setupStatusTimerId = null;
}

async function refreshSetupRobotStatus({ quiet = false } = {}) {
    if (!hasSetupAccess()) return;
    try {
        const payload = await apiJson('/api/setup/hardware-test', {
            method: 'POST',
            body: JSON.stringify({ action: 'status', dry_run: true }),
        }, 5000);
        const robot = payload.status || payload.robot || {};
        renderSetupRobotStatus(robot);
        if (payload.status) commit('ROBOT.STATUS_UPDATED', payload.status);
    } catch (error) {
        renderSetupRobotStatus({ connected: false, error: error?.message || 'status_unavailable' });
        if (!quiet) window.showAlert?.(error?.message || '機械手臂狀態無法取得。', 'warning');
    }
}

function renderSetupRobotStatus(robot = {}) {
    if (!document.getElementById('setup-current-x')) return;

    const telemetry = robot.telemetry && typeof robot.telemetry === 'object' ? robot.telemetry : {};
    const connection = robot.connection && typeof robot.connection === 'object' ? robot.connection : {};
    const position = robot.position || robot.robot_position || telemetry.pose || {};
    const orientation = robot.orientation || telemetry.orientation || {};
    const connected = Boolean(robot.connected || robot.is_connected || connection.connected);
    const busy = Boolean(robot.busy);
    const dot = document.getElementById('setup-robot-live-dot');
    if (dot) dot.dataset.state = busy ? 'busy' : (connected ? 'online' : 'offline');

    const status = robot.error
        ? `錯誤：${robot.error}`
        : (busy ? '移動中' : (connected ? '已連線' : '離線'));
    setTextById('setup-robot-live-status', status);
    setTextById('setup-robot-live-endpoint', setupFormatEndpoint(robot, connection));
    setTextById('setup-current-x', setupFormatNumber(position.x));
    setTextById('setup-current-y', setupFormatNumber(position.y));
    setTextById('setup-current-z', setupFormatNumber(position.z));
    setTextById('setup-current-rx', setupFormatNumber(orientation.rx ?? position.rx));
    setTextById('setup-current-ry', setupFormatNumber(orientation.ry ?? position.ry));
    setTextById('setup-current-rz', setupFormatNumber(orientation.rz ?? position.rz));
    setTextById('setup-current-speed', setupFormatSpeed(robot.speed ?? telemetry.speed));
    setTextById('setup-current-joints', setupFormatJoints(robot.joint_angles || robot.joints || robot.angles || telemetry.joint_angles));
    setTextById('setup-current-telemetry', setupTelemetryLabel(telemetry, robot.fake_robot));
    setTextById('setup-current-updated', new Date().toLocaleTimeString());
}

function setupFormatEndpoint(robot = {}, connection = {}) {
    const host = robot.ip || connection.ip || connection.host || '';
    const port = robot.port ?? connection.port;
    const adapter = robot.adapter || connection.adapter || connection.mode || '';
    if (!host && (port === undefined || port === null || port === '')) return adapter ? String(adapter) : '--';
    const endpoint = port === undefined || port === null || port === '' ? String(host) : `${host || '--'}:${port}`;
    return adapter ? `${adapter} ${endpoint}` : endpoint;
}

function applySetupLabDefaults() {
    if (!requireSetupControls()) return;
    Object.entries(LAB_ROBOT_DEFAULTS).forEach(([path, value]) => setSetupFieldValue(path, value));
    markSetupDirty();
    renderSetupInitializationSummary({}, '尚未儲存');
    window.showAlert?.('已套用實驗室手臂預設值。', 'success');
}

function setSetupFieldValue(path, value) {
    const field = setupFieldByPath(path);
    if (!field) return;
    if (field.tagName === 'SELECT') ensureSelectOption(field, value);
    if (field.type === 'checkbox') {
        field.checked = Boolean(value);
        return;
    }
    field.value = String(value ?? '');
}

function setupFieldByPath(path) {
    for (const field of document.querySelectorAll('[data-setup-field]')) {
        if (field.dataset.setupField === path) return field;
    }
    return null;
}

function setupFieldCurrentValue(path, settings = {}) {
    const field = setupFieldByPath(path);
    if (field) {
        if (field.type === 'checkbox') return Boolean(field.checked);
        return String(field.value || '').trim();
    }
    const value = getNestedValue(settings, path);
    return value === undefined || value === null ? '' : value;
}

function renderSetupInitializationSummary(settings = {}, resultText) {
    const adapter = String(setupFieldCurrentValue('robot.connection.adapter', settings) || '').trim();
    const ip = String(setupFieldCurrentValue('robot.connection.ip', settings) || '').trim();
    const port = setupFieldCurrentValue('robot.connection.port', settings);
    const pcIp = String(setupFieldCurrentValue('robot.connection.pc_ip', settings) || '').trim();
    const subnetMask = String(setupFieldCurrentValue('robot.connection.subnet_mask', settings) || '').trim();
    const wireFormat = String(setupFieldCurrentValue('robot.tmflow_json.wire_format', settings) || '').trim();
    const pcNetwork = pcIp || subnetMask ? `${pcIp || '--'} / ${subnetMask || '--'}` : '--';

    setTextById('setup-init-endpoint', setupFormatEndpoint({}, { adapter, ip, port }));
    setTextById('setup-init-pc-network', pcNetwork);
    setTextById('setup-init-protocol', setupProtocolLabel(adapter, wireFormat));

    const resultElement = document.getElementById('setup-init-result');
    if (resultText !== undefined) {
        setTextById('setup-init-result', resultText);
    } else if (!resultElement?.textContent || resultElement.textContent === '--') {
        setTextById('setup-init-result', '尚未測試');
    }
}

function setupProtocolLabel(adapter, wireFormat) {
    if (adapter === 'tmflow_json') return `TCP JSON / ${wireFormat || 'envelope'}`;
    if (adapter === 'techmanpy') return 'TechmanPy External Script';
    if (adapter === 'modbus') return 'Modbus TCP';
    return adapter || '--';
}

function setupFormatNumber(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    return numeric.toFixed(2);
}

function setupFormatSpeed(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    return `${numeric.toFixed(2)} mm/s`;
}

function setupFormatJoints(joints) {
    if (!joints) return '--';
    if (Array.isArray(joints)) {
        return joints
            .slice(0, 6)
            .map((value, index) => `J${index + 1}:${setupFormatNumber(value)}`)
            .join(' ');
    }
    if (typeof joints !== 'object') return '--';
    const parts = ['j1', 'j2', 'j3', 'j4', 'j5', 'j6']
        .filter((key) => Number.isFinite(Number(joints[key])))
        .map((key) => `${key.toUpperCase()}:${setupFormatNumber(joints[key])}`);
    return parts.join(' ') || '--';
}

function setupTelemetryLabel(telemetry = {}, fakeRobot = false) {
    const source = String(telemetry.source || '').trim();
    if (source) return source;
    return fakeRobot ? '模擬' : '--';
}

async function loadSetupCommissioning({ quiet = false } = {}) {
    if (!hasSetupAccess()) return;
    try {
        const payload = await apiJson('/api/setup/commissioning', { method: 'GET' }, 6000);
        renderSetupCommissioning(payload.commissioning || {});
    } catch (error) {
        if (!quiet) window.showAlert?.(error?.message || 'Commissioning report unavailable.', 'warning');
    }
}

async function reconnectSetupCamera() {
    if (!hasSetupAccess()) return;
    const preview = document.getElementById('setup-camera-preview');
    if (!preview) return;
    const src = preview.dataset?.src || '/api/video_feed';
    const streamSrc = await buildVisionStreamSrc(src);
    preview.src = appendQueryParam(streamSrc, 'setup', Date.now());
}

async function refreshSetupVisionSourceStatus({ quiet = false } = {}) {
    if (!hasSetupAccess()) return null;
    try {
        const payload = await apiJson('/api/vision/source/status', { method: 'GET' }, 5000);
        renderSetupVisionSourceStatus(payload);
        return payload;
    } catch (error) {
        setTextById('setup-vision-source-test-status', '狀態取得失敗');
        if (!quiet) window.showAlert?.(error?.message || '影像來源狀態取得失敗。', 'warning');
        return null;
    }
}

async function testSetupVisionSource() {
    if (!requireSetupControls('設定權限尚未通過。')) return false;
    setTextById('setup-vision-source-test-status', '儲存設定中');
    const saved = await saveSetupSettings();
    if (!saved) return false;
    setTextById('setup-vision-source-test-status', '送出測試影像');
    try {
        const payload = await apiJson('/api/vision/source/test-frame', {
            method: 'POST',
            body: JSON.stringify({ mode: 'synthetic' }),
        }, 9000);
        renderSetupVisionSourceStatus({
            source: payload.source,
            camera: payload.status?.camera,
            test: payload,
        });
        reconnectSetupCamera();
        window.showAlert?.('影像來源測試影像已送出。', 'success');
        return true;
    } catch (error) {
        setTextById('setup-vision-source-test-status', '測試失敗');
        window.showAlert?.(error?.message || '影像來源測試失敗。', 'error');
        return false;
    }
}

function applySetupSettings(settings = {}, files = {}) {
    document.querySelectorAll('[data-setup-field]').forEach((field) => {
        const path = field.dataset.setupField;
        const value = getNestedValue(settings, path);
        if (value === undefined || value === null) return;
        if (field.tagName === 'SELECT') {
            if (path === 'vision.camera_index') {
                ensureCameraOption(value);
            } else {
                ensureSelectOption(field, value);
            }
        }
        if (field.type === 'checkbox') {
            field.checked = Boolean(value);
            return;
        }
        field.value = String(value);
    });

    renderVisionSourceControls(getNestedValue(settings, 'vision.source') || 'opencv');
    const robotCalibration = settings.robot?.calibration || {};
    const visionCalibration = settings.vision?.calibration || {};
    setTextById('setup-robot-calibration-status', formatRobotCalibration(robotCalibration));
    setTextById('setup-vision-status', formatVisionCalibration(visionCalibration));
    setTextById('setup-settings-file', files.setup_settings || '--');
    setTextById('setup-robot-file', files.robot_calibration || robotCalibration.path || '--');
    setTextById('setup-vision-file', files.vision_calibration || '--');
    renderSetupInitializationSummary(settings);
    setSetupSaveState('已載入');
    refreshSetupVisionSourceStatus({ quiet: true });
}

function markSetupDirty() {
    setupWizardState.settingsSaved = false;
    setSetupSaveState('已修改');
    renderSetupInitializationSummary({}, '尚未儲存');
    renderSetupWizard();
}

function collectSetupSettings() {
    const settings = {};
    document.querySelectorAll('[data-setup-field]').forEach((field) => {
        const path = field.dataset.setupField;
        if (!path) return;
        const value = field.type === 'checkbox'
            ? Boolean(field.checked)
            : (numericSetupField(field, path) ? Number(field.value) : String(field.value || '').trim());
        setNestedValue(settings, path, value);
    });
    return settings;
}

function renderSetupPreflight(payload = {}) {
    setupWizardState.preflight = payload || null;
    const checks = Array.isArray(payload.checks) ? payload.checks : [];
    const failures = checks.filter((item) => item && item.ok === false && item.severity === 'error');
    const warnings = checks.filter((item) => item && item.ok === false && item.severity !== 'error');
    const text = failures.length
        ? `未通過 ${failures.length}`
        : (warnings.length ? `警告 ${warnings.length}` : '通過');
    setTextById('setup-preflight-status', text);
    renderSetupWizard();
}

function renderSetupWizard(payload = setupWizardState.preflight) {
    const commissioning = setupWizardState.commissioning || {};
    const commissioningSteps = commissioning.steps || {};
    const checks = new Map((Array.isArray(payload?.checks) ? payload.checks : [])
        .filter(Boolean)
        .map((item) => [item.key, item]));
    const settingsSaved = setupWizardState.settingsSaved || commissioningSteps.settings_saved?.ok === true;
    const hardwareOk = commissioningSteps.hardware?.ok === true;
    const steps = [
        {
            key: 'settings_saved',
            ok: settingsSaved,
            message: settingsSaved ? '已儲存' : '請先儲存',
        },
        setupWizardStepFromCheck(checks, 'vision_ready', '視覺已就緒'),
        setupWizardStepFromCheck(checks, 'motion_profile_safe', '動作範圍安全'),
        setupWizardStepFromCheck(checks, 'board_and_dead_zone_safe', '棋盤範圍安全'),
        setupWizardStepFromCheck(checks, 'robot_communication_probe', '通訊已就緒'),
        {
            key: 'hardware_tests',
            ok: hardwareOk,
            message: hardwareOk ? '硬體已測試' : '請執行硬體測試',
        },
        {
            key: 'preflight_ready',
            ok: Boolean(payload?.ready),
            message: payload ? (payload.ready ? '已通過' : '未通過') : '請執行預檢',
        },
    ];

    let firstBlocked = null;
    steps.forEach((step) => {
        const item = document.querySelector(`[data-setup-step="${step.key}"]`);
        if (!item) return;
        item.dataset.status = step.ok ? 'ok' : (step.warning ? 'warning' : 'blocked');
        const status = item.querySelector('strong');
        if (status) status.textContent = step.message || (step.ok ? '通過' : '待檢查');
        if (!step.ok && !firstBlocked) firstBlocked = step;
    });

    const ready = steps.every((step) => step.ok);
    setTextById('setup-wizard-ready', ready ? '已就緒' : '尚未就緒');
    setTextById('setup-wizard-next', firstBlocked ? firstBlocked.message : '可開始玩家模式');
    setTextById('setup-wizard-preflight-at', formatCommissioningTime(commissioningSteps.preflight?.last_at));
    setTextById('setup-wizard-hardware-at', formatCommissioningTime(commissioningSteps.hardware?.last_at));
}

function renderSetupCommissioning(report = {}) {
    setupWizardState.commissioning = report || {};
    renderSetupWizard();
}

function formatCommissioningTime(value) {
    const timestamp = Number(value);
    if (!Number.isFinite(timestamp) || timestamp <= 0) return '--';
    try {
        return new Date(timestamp * 1000).toLocaleString();
    } catch {
        return '--';
    }
}

function setupWizardStepFromCheck(checks, key, okMessage) {
    const check = checks.get(key);
    if (!check) return { key, ok: false, message: '請執行預檢' };
    return {
        key,
        ok: check.ok === true,
        warning: check.severity !== 'error',
        message: check.ok === true ? okMessage : (check.message || '需要檢查'),
    };
}

function numericSetupField(field, path) {
    return field.type === 'number' || path === 'vision.camera_index';
}

function selectSetupVisionSource(source) {
    if (!requireSetupControls('設定權限尚未通過。')) return;
    const normalized = normalizeSetupVisionSource(source);
    setSetupFieldValue('vision.source', normalized);
    renderVisionSourceControls(normalized);
    markSetupDirty();
}

function normalizeSetupVisionSource(source) {
    const value = String(source || 'opencv').trim().toLowerCase();
    if (['usb', 'usb_camera', 'camera', 'opencv_usb'].includes(value)) return 'opencv';
    if (['tmvision', 'tmvision_http', 'eih', 'eih_http', 'external_detection'].includes(value)) return 'tmvision_http';
    if (['tmflow', 'tmflow_camera', 'tmflow_json_camera'].includes(value)) return 'tmflow_json';
    return value === 'tmflow_json' ? 'tmflow_json' : 'opencv';
}

function renderVisionSourceControls(source) {
    const normalized = normalizeSetupVisionSource(source);
    const field = document.getElementById('setup-vision-source');
    if (field) field.value = normalized;
    document.querySelectorAll('[data-setup-vision-source]').forEach((button) => {
        const active = normalizeSetupVisionSource(button.dataset.setupVisionSource) === normalized;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    const tmflowSettings = document.getElementById('setup-tmflow-vision-settings');
    if (tmflowSettings) tmflowSettings.classList.toggle('hidden', normalized !== 'tmflow_json');
    const sourceLabel = normalized === 'tmvision_http'
        ? 'TMvision HTTP'
        : (normalized === 'tmflow_json' ? 'TMflow JSON' : 'USB / OpenCV');
    setTextById('setup-vision-source-status', sourceLabel);
}

function renderSetupVisionSourceStatus(payload = {}) {
    const camera = payload.camera && typeof payload.camera === 'object' ? payload.camera : {};
    const source = normalizeSetupVisionSource(payload.source || camera.source || 'opencv');
    const diagnostics = payload.diagnostics && typeof payload.diagnostics === 'object' ? payload.diagnostics : {};
    const controlChannel = diagnostics.control_channel && typeof diagnostics.control_channel === 'object'
        ? diagnostics.control_channel
        : {};
    const visionChannel = diagnostics.vision_channel && typeof diagnostics.vision_channel === 'object'
        ? diagnostics.vision_channel
        : camera;
    renderVisionSourceControls(source);
    const connected = camera.opened === true || camera.connected === true;
    const running = camera.running === true;
    const frames = Number(camera.frames_received);
    const lastError = String(camera.last_error || '').trim();
    let text = source === 'tmvision_http'
        ? 'TMvision HTTP'
        : (source === 'tmflow_json' ? 'TMflow JSON' : 'USB / OpenCV');
    if (running || connected) text += connected ? ' 已連線' : ' 啟動中';
    if (Number.isFinite(frames) && frames > 0) text += ` / ${frames} frames`;
    if (payload.test?.frames_injected) text += ` / test ${payload.test.frames_injected}`;
    if (lastError) text += ` / ${lastError}`;
    setTextById('setup-vision-source-test-status', text);
    setTextById('setup-control-channel-status', formatSetupChannel(controlChannel, {
        host: getSetupFieldValue('robot.connection.ip'),
        port: getSetupFieldValue('robot.connection.port') || 5890,
    }));
    setTextById('setup-vision-channel-status', formatSetupChannel(visionChannel, {
        host: getSetupFieldValue('vision.tmflow_json.host'),
        port: getSetupFieldValue('vision.tmflow_json.port') || 5891,
    }));
    setTextById('setup-vision-frame-age', formatSetupFrameAge(visionChannel.last_frame_age_sec ?? camera.last_frame_age_sec));
    setTextById('setup-vision-reconnects', formatSetupCount(visionChannel.reconnects ?? camera.reconnects));
}

function formatSetupChannel(channel = {}, fallback = {}) {
    const status = String(channel.status || '').trim().toLowerCase();
    const connected = channel.connected === true;
    const running = channel.running === true;
    const label = status === 'simulation'
        ? '模擬'
        : (connected ? '已連線' : (running || status === 'starting' ? '啟動中' : '離線'));
    const endpoint = String(channel.endpoint || '').trim() ||
        [channel.host ?? fallback.host, channel.port ?? fallback.port]
            .filter((part) => part !== undefined && part !== null && String(part).trim() !== '')
            .join(':');
    return endpoint ? `${label} / ${endpoint}` : label;
}

function formatSetupFrameAge(value) {
    const age = Number(value);
    if (!Number.isFinite(age) || age < 0) return '--';
    if (age < 1) return `${Math.round(age * 1000)} ms`;
    return `${age.toFixed(1)} s`;
}

function formatSetupCount(value) {
    const count = Number(value);
    return Number.isFinite(count) && count >= 0 ? String(Math.trunc(count)) : '--';
}

function ensureSelectOption(select, value) {
    const normalized = String(value);
    if ([...select.options].some((option) => option.value === normalized)) return;
    const option = document.createElement('option');
    option.value = normalized;
    option.textContent = normalized;
    select.appendChild(option);
}

function renderCameraOptions(candidates, current) {
    const select = document.getElementById('setup-camera-index');
    if (!select) return;
    const selected = current ?? select.value ?? 0;
    select.textContent = '';
    const seen = new Set();
    (candidates || []).forEach((candidate) => {
        const index = Number(candidate.index);
        if (!Number.isFinite(index) || seen.has(index)) return;
        seen.add(index);
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = `相機 ${index}${candidate.available ? ' 線上' : ' 離線'}`;
        select.appendChild(option);
    });
    ensureCameraOption(selected);
    select.value = String(selected);
}

function ensureCameraOption(value) {
    const select = document.getElementById('setup-camera-index');
    if (!select) return;
    const normalized = String(Number(value));
    if ([...select.options].some((option) => option.value === normalized)) return;
    const option = document.createElement('option');
    option.value = normalized;
    option.textContent = `相機 ${normalized}`;
    select.appendChild(option);
}

function getNestedValue(data, path) {
    return String(path || '').split('.').reduce((current, part) => {
        if (current === undefined || current === null) return undefined;
        return current[part];
    }, data);
}

function getSetupFieldValue(path) {
    const field = Array.from(document.querySelectorAll('[data-setup-field]'))
        .find((item) => item.dataset.setupField === path);
    if (!field) return undefined;
    if (field.type === 'checkbox') return Boolean(field.checked);
    return field.value;
}

function setNestedValue(target, path, value) {
    const parts = String(path || '').split('.').filter(Boolean);
    let current = target;
    parts.forEach((part, index) => {
        if (index === parts.length - 1) {
            current[part] = value;
            return;
        }
        current[part] = current[part] && typeof current[part] === 'object' ? current[part] : {};
        current = current[part];
    });
}

function setTextById(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = String(value ?? '--');
}

function setSetupSaveState(value) {
    setTextById('setup-save-state', value);
}

function formatRobotCalibration(calibration) {
    const error = calibration?.calibration_error;
    if (error?.rms !== undefined) return `RMS ${Number(error.rms).toFixed(2)} / MAX ${Number(error.max || 0).toFixed(2)}`;
    return calibration?.path ? '已載入' : '--';
}

function formatVisionCalibration(calibration) {
    if (!calibration || !Object.keys(calibration).length) return '--';
    const quality = calibration.quality || {};
    if (quality.max_error !== undefined) return `誤差 ${Number(quality.max_error).toFixed(2)}`;
    if (calibration.calibrated !== undefined) return calibration.calibrated ? '已校正' : '尚未校正';
    return calibration.source || '已載入';
}

function reconnectVideo({ force = false } = {}) {
    if (!hasAdminAccess()) return;
    clearVideoReconnectTimer();
    videoReconnectAttempts = 0;
    startVideoStream({ force });
}

async function startVideoStream({ force = false } = {}) {
    const videoFeed = UIRegistry.get('videoFeed');
    if (!videoFeed) return;
    const src = videoFeed.dataset?.src || '/api/video_feed';
    const currentSrc = String(videoFeed.currentSrc || videoFeed.src || '');
    if (!force && videoStreamActive && currentSrc.includes(src)) {
        markVideoStatus('live', '已連線');
        return;
    }
    const streamSrc = await buildVisionStreamSrc(src);
    videoFeed.src = appendQueryParam(streamSrc, 't', Date.now());
    videoStreamActive = true;
    markVideoStatus('standby', '連線中');
}

async function buildVisionStreamSrc(src) {
    const base = String(src || '/api/video_feed');
    try {
        const payload = await apiJson('/api/vision/stream-token', { method: 'POST' }, 5000);
        if (payload?.stream_token) {
            return appendQueryParam(base, 'stream_token', payload.stream_token);
        }
    } catch {
        // Keep the original URL as a fallback for cookie-auth or auth-disabled deployments.
    }
    return base;
}

function appendQueryParam(url, key, value) {
    const text = String(url || '');
    const separator = text.includes('?') ? '&' : '?';
    return `${text}${separator}${encodeURIComponent(key)}=${encodeURIComponent(String(value ?? ''))}`;
}

function handleVideoLoad() {
    const videoFeed = UIRegistry.get('videoFeed');
    const src = String(videoFeed?.currentSrc || videoFeed?.src || '');
    if (!src.includes('/api/video_feed') && !src.includes('/api/vision/stream')) return;
    clearVideoReconnectTimer();
    videoReconnectAttempts = 0;
    videoStreamActive = true;
    markVideoStatus('live', '已連線');
}

function scheduleVideoReconnect(videoFeed = UIRegistry.get('videoFeed')) {
    if (!videoFeed || videoReconnectTimer) return;
    const delay = Math.min(VIDEO_RECONNECT_BASE_MS * (2 ** videoReconnectAttempts), VIDEO_RECONNECT_MAX_MS);
    videoReconnectAttempts += 1;
    videoReconnectTimer = setTimeout(() => {
        videoReconnectTimer = null;
        startVideoStream({ force: true });
    }, delay);
}

function clearVideoReconnectTimer() {
    if (!videoReconnectTimer) return;
    clearTimeout(videoReconnectTimer);
    videoReconnectTimer = null;
}

function markVideoStatus(className, label) {
    const pill = document.getElementById('video-status-pill');
    if (!pill) return;
    pill.className = `status-pill ${className}`;
    replacePillContent(pill, label);
}

async function refreshVisionCalibration({ quiet = false } = {}) {
    if (!hasAdminAccess()) return;
    try {
        const payload = await apiJson('/api/vision/calibration', { method: 'GET' }, 5000);
        applyVisionCalibrationStatus(payload);
        if (!quiet) window.showAlert?.('校正狀態已更新。', 'success');
    } catch (error) {
        if (!quiet) window.showAlert?.(error?.message || '校正狀態無法取得。', 'warning');
    }
}

function applyVisionCalibrationStatus(payload = {}) {
    const calibration = payload.calibration && typeof payload.calibration === 'object'
        ? payload.calibration
        : payload;
    commit('DIAGNOSTICS.UPDATED', {
        vision: {
            calibration,
            calibrated: calibration.calibrated,
            calibration_quality: calibration.quality || {},
            calibration_source: calibration.source || '',
        },
    });
}

function installAuthorizationGuards() {
    ADMIN_ONLY_CONTROL_IDS.forEach((id) => {
        const element = document.getElementById(id);
        if (element) {
            element.dataset.requiresAdmin = 'true';
            element.dataset.requiresLive = 'true';
        }
    });
    document.querySelectorAll('.depth-btn, .ai-mode-btn, #safe-mode-toggle, #session-participant-id').forEach((element) => {
        element.dataset.requiresAdmin = 'true';
        element.dataset.requiresLive = 'true';
    });
    document.querySelectorAll('[data-setup-admin="true"], [data-setup-field]').forEach((element) => {
        element.dataset.requiresSetup = 'true';
    });
    window.addEventListener('storage', refreshAuthorizationUI);
    window.addEventListener('smart:connection-status', refreshAuthorizationUI);
    window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            hideAuthOverlay();
            hideSetupAuthOverlay();
        }
    });
    refreshAuthorizationUI();
}

function hasAdminAccess() {
    return getStoredRole() === 'admin' && hasValidAdminSession();
}

function hasSetupAccess() {
    return hasAdminAccess() || hasValidSetupSession();
}

function canUseLiveAdminControls() {
    const status = document.body?.dataset?.connectionStatus || 'offline';
    const stale = document.body?.dataset?.stateStale !== 'false';
    return hasAdminAccess() && status === 'online' && !stale;
}

function canUseSetupControls() {
    return hasSetupAccess();
}

function requireLiveAdminControls(message = '控制通道尚未就緒。') {
    if (canUseLiveAdminControls()) return true;
    window.showAlert?.(message, 'warning');
    refreshAuthorizationUI();
    return false;
}

function requireSetupControls(message = '系統設定尚未解鎖。') {
    if (canUseSetupControls()) return true;
    window.showAlert?.(message, 'warning');
    refreshAuthorizationUI();
    return false;
}

function refreshAuthorizationUI() {
    const isAdmin = hasAdminAccess();
    const hasSetup = hasSetupAccess();
    const live = (document.body?.dataset?.connectionStatus || 'offline') === 'online';
    const fresh = document.body?.dataset?.stateStale === 'false';
    const disabled = !isAdmin || !live || !fresh;
    const setupDisabled = !hasSetup;

    document.body?.classList.toggle('auth-viewer', !isAdmin);
    document.body?.classList.toggle('auth-admin', isAdmin);
    document.body?.classList.toggle('auth-setup', hasSetup);

    document.querySelectorAll('[data-requires-admin="true"]').forEach((element) => {
        element.disabled = disabled;
        element.setAttribute('aria-disabled', disabled ? 'true' : 'false');
        element.dataset.authDisabled = disabled ? 'true' : 'false';
    });
    document.querySelectorAll('[data-requires-setup="true"]').forEach((element) => {
        element.disabled = setupDisabled;
        element.setAttribute('aria-disabled', setupDisabled ? 'true' : 'false');
        element.dataset.authDisabled = setupDisabled ? 'true' : 'false';
    });
    updateSessionControlButtons();
}

async function loadInitialStateSnapshot() {
    try {
        const endpoint = hasAdminAccess() ? '/api/state' : '/api/player/state';
        const payload = await apiJson(endpoint, { method: 'GET' }, 5000);
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
        if (!quiet) window.showAlert?.(error?.message || '執行控制狀態無法取得。', 'warning');
    }
}

function markConsoleStandbyState() {
    const aiStatus = document.getElementById('stat-ai');
    if (aiStatus) {
        aiStatus.textContent = '待機中';
        aiStatus.className = 'status-warning';
    }

    const cameraStatus = document.getElementById('stat-camera');
    if (cameraStatus) {
        cameraStatus.textContent = '待機中';
        cameraStatus.className = 'status-warning';
    }

    setTextById('dashboard-engine-thinking', '待命');
}

async function prepareConsoleStandby({ quiet = true } = {}) {
    if (!hasAdminAccess()) return;
    markConsoleStandbyState();

    const standbyPayload = { source: 'console_login_standby', standby: true };
    const results = await Promise.allSettled([
        apiJson('/api/control', {
            method: 'POST',
            body: JSON.stringify({ action: 'start_engine', payload: standbyPayload }),
        }, 6000),
        apiJson('/api/control', {
            method: 'POST',
            body: JSON.stringify({ action: 'sync_vision', payload: standbyPayload }),
        }, 6000),
        apiJson('/api/engine/status', { method: 'GET' }, 6000),
        apiJson('/api/vision/status', { method: 'GET' }, 6000),
    ]);

    const failed = results.some((result) => result.status === 'rejected');
    if (failed) {
        if (!quiet) window.showAlert?.('Pikafish / YOLO 待機未完全完成，請查看狀態頁。', 'warning');
        return;
    }

    if (!quiet) window.showAlert?.('Pikafish 與 YOLO 已進入待機。', 'success');
    loadRuntimeControlStatus({ quiet: true });
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
        refreshVisionCalibration({ quiet: true });
        refreshAuthorizationUI();
        void prepareConsoleStandby({ quiet: true });
        window.showAlert?.('主控台已解鎖，Pikafish 與 YOLO 正在待機。', 'success');
    } catch (error) {
        if (errorEl) errorEl.textContent = error?.message || '登入失敗。';
        window.showAlert?.('主控台登入失敗。', 'error');
    } finally {
        if (form) form.reset();
    }
}

async function submitSetupLogin(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = form?.querySelector?.('#setup-password')?.value || '';
    const errorEl = document.getElementById('setup-auth-error');
    if (errorEl) errorEl.textContent = '';

    try {
        await loginSetup(password);
        hideSetupAuthOverlay();
        openSetupPane();
        window.showAlert?.('系統設定已解鎖。', 'success');
    } catch (error) {
        clearSetupToken();
        if (errorEl) errorEl.textContent = error?.message || '登入失敗。';
        window.showAlert?.('系統設定登入失敗。', 'error');
    } finally {
        if (form) form.reset();
        refreshAuthorizationUI();
    }
}

function showAuthOverlay() {
    showCredentialOverlay('auth-overlay', 'admin-password');
}

function hideAuthOverlay() {
    hideCredentialOverlay('auth-overlay');
}

function showSetupAuthOverlay() {
    showCredentialOverlay('setup-auth-overlay', 'setup-password');
}

function hideSetupAuthOverlay() {
    hideCredentialOverlay('setup-auth-overlay');
}

function showCredentialOverlay(overlayId, inputId) {
    const overlay = document.getElementById(overlayId);
    if (!overlay) return;
    overlay.classList.remove('hidden');
    overlay.classList.add('active');
    overlay.setAttribute('aria-hidden', 'false');
    const input = document.getElementById(inputId);
    setTimeout(() => input?.focus?.(), 0);
}

function hideCredentialOverlay(overlayId) {
    const overlay = document.getElementById(overlayId);
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

function setupPlayerGuide() {
    ['board', 'vision', 'engine', 'robot', 'ui'].forEach((domain) => {
        subscribe(domain, () => updatePlayerGuide());
    });
    updatePlayerGuide();
}

function updatePlayerGuide() {
    const snap = state.snapshot || {};
    const board = snap.board || {};
    const vision = snap.vision || {};
    const engine = snap.engine || {};
    const robot = snap.robot || {};
    const ui = snap.ui || {};
    const turn = normalizePlayerTurn(board.turn || board.fen);
    const turnLabel = turn === 'black' ? '黑方移動' : '紅方移動';
    const aiLabel = ui.ai_mode_label || ui.ai_difficulty || '陪伴預設';
    const gameEnded = isGameEnded(board);

    setTextById('player-guide-turn', turnLabel);
    setTextById('player-guide-ai', aiLabel);

    const visionStatus = playerVisionStatus(vision);
    const robotStatus = playerRobotStatus(robot, engine, turn);
    updateVisionCaptureButton(vision, board);
    updateRobotStartButton(robot, board, engine);
    updatePlayerEndButton(board);
    setTextById('player-guide-vision', visionStatus.text);
    setGuideState('player-guide-vision-card', visionStatus.state);
    setTextById('player-guide-robot', robotStatus.text);
    setGuideState('player-guide-robot-card', robotStatus.state);

    if (gameEnded) {
        const result = board.game_result || {};
        setPlayerGuideCopy('棋局結束', gameEndActionText(result), '請勿再移動棋子；這不是實體急停，如需重新開始或處理手臂，請由工作人員操作。');
        return;
    }
    if (!playerGameStarted) {
        setPlayerGuideCopy('等待開始', '請按下開始對局', '開始後，系統會提示輪到哪一方、辨識是否成功，以及機械手臂是否準備動作。');
        return;
    }
    if (robot.busy) {
        setPlayerGuideCopy('機械手臂動作中', '請保持雙手離開棋盤', '等待機械手臂完成後，再依畫面提示繼續。');
        return;
    }
    if (robotStatus.reason === 'ready_to_start') {
        setPlayerGuideCopy('等待啟動手臂', '請按下啟動機械手臂流程', '啟動前請確認所有人員遠離棋盤與手臂工作範圍。');
        return;
    }
    if (engine.is_thinking) {
        setPlayerGuideCopy('AI 思考中', '請稍候，不需要移動棋子', '系統正在計算下一步。');
        return;
    }
    if (visionStatus.reason === 'capture_active') {
        setPlayerGuideCopy('辨識中', '請保持雙手離開棋盤', '系統每 2 秒擷取一次最新畫面，辨識成功後會自動停止。');
        return;
    }
    if (visionStatus.state === 'error') {
        setPlayerGuideCopy('辨識失敗', '請重新擺正棋子', '確認棋子放在格線交點附近，手離開棋盤後等待系統重新辨識。');
        return;
    }
    if (visionStatus.state === 'warning') {
        setPlayerGuideCopy('等待影像更新', '請先不要移動棋子', '目前影像資料延遲或尚未穩定，請把手離開棋盤並等待辨識成功。');
        return;
    }
    if (turn === 'black') {
        setPlayerGuideCopy('等待 AI', '現在輪到黑方', '請稍候系統計算，機械手臂動作前畫面會再次提示。');
        return;
    }
    setPlayerGuideCopy('玩家回合', '請移動紅方棋子', '移動後請把手離開棋盤，按下我已下棋。');
}

function setPlayerGuideCopy(step, action, detail) {
    setTextById('player-guide-step', step);
    setTextById('player-guide-action', action);
    setTextById('player-guide-detail', detail);
}

function playerVisionStatus(vision = {}) {
    const capture = vision.capture_session && typeof vision.capture_session === 'object' ? vision.capture_session : {};
    const captureActive = isVisionCaptureActive(vision);
    const captureReason = String(capture.last_reason || '').toLowerCase();
    if (captureActive) {
        return { state: 'warning', text: '辨識中', reason: 'capture_active' };
    }
    if (captureReason === 'stable_vision_result') {
        return { state: 'ok', text: '辨識成功', reason: 'capture_complete' };
    }
    if (captureReason === 'timeout') {
        return { state: 'error', text: '辨識逾時', reason: 'capture_timeout' };
    }
    const status = String(vision.status || '').toLowerCase();
    const ageMs = Number(vision.vision_age_ms ?? vision.visionAgeMs ?? 0);
    const stale = Boolean(vision.stale || vision.is_stale || vision.isStale || ageMs > VISION_STALE_THRESHOLD_MS);
    if (vision.fen_valid === false || status.includes('error') || status.includes('fail')) {
        return { state: 'error', text: '辨識失敗' };
    }
    if (stale || status.includes('stale')) {
        return { state: 'warning', text: '影像延遲' };
    }
    if (vision.stable || vision.fen || vision.fen_after) {
        return { state: 'ok', text: '辨識成功' };
    }
    if (vision.camera_ready === false) {
        return { state: 'error', text: '相機未就緒' };
    }
    return { state: 'standby', text: '等待棋子移動' };
}

function isVisionCaptureActive(vision = {}) {
    const capture = vision.capture_session && typeof vision.capture_session === 'object' ? vision.capture_session : {};
    return Boolean(vision.capture_active || capture.active);
}

function updateVisionCaptureButton(vision = {}, board = {}) {
    const button = document.getElementById('btn-player-vision-capture');
    if (!button) return;
    const active = isVisionCaptureActive(vision);
    const ended = isGameEnded(board);
    button.classList.toggle('active', active);
    button.textContent = ended ? '棋局已結束' : (active ? '辨識中...' : '我已下棋');
    button.disabled = !playerGameStarted || active || ended;
}

function updatePlayerEndButton(board = {}) {
    const button = document.getElementById('btn-player-end-game');
    if (!button) return;
    const ended = isGameEnded(board);
    button.disabled = !playerGameStarted || ended || playerEndRequestActive;
    if (playerEndRequestActive) {
        button.textContent = '結束中...';
    } else if (ended) {
        button.textContent = '對局已結束';
    } else {
        button.textContent = '結束對局';
    }
}

async function submitPlayerDone() {
    if (!playerGameStarted) {
        window.showAlert?.('請先開始對局。', 'warning');
        return;
    }
    const button = document.getElementById('btn-player-vision-capture');
    if (button) button.disabled = true;
    try {
        const payload = await apiJson('/api/player-done', {
            method: 'POST',
            body: JSON.stringify({
                source: 'player_done_button',
            }),
        }, 6000);
        if (payload.vision) {
            commit('DIAGNOSTICS.UPDATED', { vision: payload.vision });
        }
        updatePlayerGuide();
        window.showAlert?.('已通知系統開始辨識。', 'success');
    } catch (error) {
        window.showAlert?.(error?.message || '送出玩家完成狀態失敗。', 'error');
    } finally {
        if (button) button.disabled = false;
        updateVisionCaptureButton(state.snapshot.vision || {}, state.snapshot.board || {});
    }
}

function playerRobotStatus(robot = {}, engine = {}, turn = 'red') {
    const simulation = Boolean(robot.fake_robot || robot.simulation);
    if (robot.error) return { state: 'error', text: '需要工作人員確認' };
    if (robot.busy) return { state: 'warning', text: simulation ? '模擬動作中' : '動作中，請勿靠近' };
    if (isRobotMoveReady(engine, { turn })) {
        return { state: 'warning', text: simulation ? '模擬待啟動' : '等待啟動', reason: 'ready_to_start' };
    }
    return { state: 'standby', text: simulation ? '模擬模式' : '尚未動作' };
}

function updateRobotStartButton(robot = {}, board = {}, engine = {}) {
    const button = document.getElementById('btn-start-tmflow');
    if (!button) return;
    const ended = isGameEnded(board);
    const busy = Boolean(robot.busy);
    const coolingDown = Date.now() < robotPlayCooldownUntil;
    const moveReady = isRobotMoveReady(engine, board);
    button.disabled = !playerGameStarted || ended || busy || !moveReady || robotPlayRequestActive || coolingDown;
    if (robotPlayRequestActive) {
        button.textContent = '送出啟動中...';
    } else if (busy) {
        button.textContent = '手臂動作中...';
    } else if (coolingDown) {
        button.textContent = '啟動訊號已送出';
    } else if (ended) {
        button.textContent = '棋局已結束';
    } else if (!moveReady) {
        button.textContent = '等待 AI 招法';
    } else {
        button.textContent = '啟動機械手臂流程';
    }
}

async function startRobotArmFlow() {
    if (!playerGameStarted) {
        window.showAlert?.('請先開始對局。', 'warning');
        return;
    }
    if (isGameEnded(state.snapshot.board || {})) {
        window.showAlert?.('棋局已結束，請勿再啟動機械手臂。', 'warning');
        return;
    }
    if (!isRobotMoveReady(state.snapshot.engine || {}, state.snapshot.board || {})) {
        window.showAlert?.('AI 尚未產生可執行招法，請等畫面提示後再啟動。', 'warning');
        updateRobotStartButton(state.snapshot.robot || {}, state.snapshot.board || {}, state.snapshot.engine || {});
        return;
    }
    if (!hasSetupAccess()) {
        window.showAlert?.('請先由工作人員解鎖系統設定權限。', 'warning');
        showSetupAuthOverlay();
        return;
    }
    if (typeof window.confirm === 'function' && !window.confirm(ROBOT_PLAY_CONFIRM_MESSAGE)) {
        window.showAlert?.('已取消啟動機械手臂。', 'info');
        return;
    }

    robotPlayRequestActive = true;
    updateRobotStartButton(state.snapshot.robot || {}, state.snapshot.board || {}, state.snapshot.engine || {});
    try {
        await apiJson('/api/robot/play', {
            method: 'POST',
            body: JSON.stringify({
                source: 'player_web_robot_start_button',
                confirmed_action: 'robot_play',
                warning_acknowledged: true,
            }),
        }, 9000);
        robotPlayCooldownUntil = Date.now() + 5000;
        setTimeout(() => updateRobotStartButton(state.snapshot.robot || {}, state.snapshot.board || {}, state.snapshot.engine || {}), 5200);
        commit('DIAGNOSTICS.UPDATED', {
            ui: {
                robot_play_requested_at: Date.now(),
                robot_play_warning_acknowledged: true,
            },
        });
        updatePlayerGuide();
        window.showAlert?.('已送出機械手臂啟動訊號，請勿靠近。', 'warning', 5200);
    } catch (error) {
        window.showAlert?.(error?.message || '機械手臂啟動失敗。', 'error', 5200);
    } finally {
        robotPlayRequestActive = false;
        updateRobotStartButton(state.snapshot.robot || {}, state.snapshot.board || {}, state.snapshot.engine || {});
    }
}

async function endPlayerGame() {
    if (!playerGameStarted && !isGameEnded(state.snapshot.board || {})) {
        window.showAlert?.('尚未開始對局。', 'warning');
        return;
    }
    if (isGameEnded(state.snapshot.board || {})) {
        window.showAlert?.('對局已經結束。', 'info');
        updatePlayerEndButton(state.snapshot.board || {});
        return;
    }
    if (!confirmPlayerEndGame()) {
        window.showAlert?.('已取消結束對局。', 'info');
        return;
    }

    playerEndRequestActive = true;
    updatePlayerEndButton(state.snapshot.board || {});
    updateVisionCaptureButton(state.snapshot.vision || {}, state.snapshot.board || {});
    updateRobotStartButton(state.snapshot.robot || {}, state.snapshot.board || {}, state.snapshot.engine || {});
    try {
        const payload = await apiJson('/api/player/end-game', {
            method: 'POST',
            body: JSON.stringify({
                source: 'player_end_button',
                confirmed_action: 'end_game',
                final_confirmation: 'END_GAME_CONFIRMED',
            }),
        }, 7000);
        if (payload.state) {
            commit('GAME.STATE_APPLIED', payload.state);
        } else {
            const gameResult = payload.game_result || { ended: true, reason: 'player_ended', winner: null };
            commit('GAME.STATE_APPLIED', {
                board: {
                    ...(state.snapshot.board || {}),
                    game_status: 'GAME_OVER',
                    game_phase: 'ENDED',
                    game_result: gameResult,
                    ended: true,
                },
                game: {
                    ...(state.snapshot.game || {}),
                    game_status: 'GAME_OVER',
                    game_phase: 'ENDED',
                    game_result: gameResult,
                },
                state: 'GAME_OVER',
            });
        }
        updatePlayerStartGate(true);
        updatePlayerGuide();
        window.showAlert?.('對局已結束，請勿再移動棋子；這不是實體急停。', 'success', 5200);
    } catch (error) {
        window.showAlert?.(error?.message || '結束對局失敗。', 'error', 5200);
    } finally {
        playerEndRequestActive = false;
        updatePlayerEndButton(state.snapshot.board || {});
        updateVisionCaptureButton(state.snapshot.vision || {}, state.snapshot.board || {});
        updateRobotStartButton(state.snapshot.robot || {}, state.snapshot.board || {}, state.snapshot.engine || {});
    }
}

function confirmPlayerEndGame() {
    if (typeof window.confirm !== 'function') return false;
    if (!window.confirm(PLAYER_END_CONFIRM_MESSAGE)) return false;
    return window.confirm(PLAYER_END_FINAL_CONFIRM_MESSAGE);
}

function isRobotMoveReady(engine = {}, board = {}) {
    const turn = normalizePlayerTurn(board.turn || board.fen);
    return turn === 'black' && Boolean(engine.best_move || engine.bestMove || engine.bestmove);
}

function isGameEnded(board = {}) {
    const status = String(board.game_status || '').toUpperCase();
    return Boolean(board.ended || status === 'GAME_OVER' || board.game_result?.ended);
}

function gameWinnerLabel(winner) {
    const normalized = String(winner || '').toLowerCase();
    if (normalized === 'red') return '紅方';
    if (normalized === 'black') return '黑方';
    return '棋局';
}

function gameEndActionText(result = {}) {
    const reason = String(result.reason || '').toLowerCase();
    if (reason === 'player_ended') return '玩家已結束對局';
    const winner = String(result.winner || '').toLowerCase();
    if (winner === 'red' || winner === 'black') return `${gameWinnerLabel(winner)}獲勝`;
    return '對局已結束';
}

function setGuideState(id, stateName) {
    const element = document.getElementById(id);
    if (element) element.dataset.state = stateName || 'standby';
}

function normalizePlayerTurn(value) {
    const text = String(value || '').trim().toLowerCase();
    if (text.includes(' b ') || text === 'b' || text === 'black' || text === 'dark') return 'black';
    if (text.includes(' w ') || text === 'w' || text === 'red' || text === 'white') return 'red';
    return 'red';
}

function setupEngineDepthControls() {
    document.querySelectorAll('.depth-btn[data-depth]').forEach((button) => {
        button.addEventListener('click', () => setEngineDepth(button.dataset.depth));
    });
}

function setupAiModeControls() {
    document.querySelectorAll('.ai-mode-btn[data-ai-mode]').forEach((button) => {
        button.addEventListener('click', () => setAiMode(button.dataset.aiMode));
    });
}

async function setEngineDepth(depth) {
    await postRuntimeControl('/api/runtime/engine-depth', { depth: Number(depth) }, '更新 AI 深度失敗。');
}

async function setAiMode(mode) {
    await postRuntimeControl('/api/runtime/ai-mode', { mode }, '更新 AI 難度預設失敗。');
}

function setupSafeModeControl() {
    const toggle = document.getElementById('safe-mode-toggle');
    if (!toggle) return;
    toggle.addEventListener('change', () => setSafeMode(Boolean(toggle.checked)));
}

async function setSafeMode(enabled) {
    const toggle = document.getElementById('safe-mode-toggle');
    const revertToggle = () => {
        if (toggle) toggle.checked = !enabled;
    };
    await postRuntimeControl('/api/runtime/safe-mode', { enabled }, '更新安全模式失敗。', {
        onDenied: revertToggle,
        onError: revertToggle,
    });
}

function setupSessionControls() {
    bindClick('btn-session-start', startExperimentSession);
    bindClick('btn-session-end', endExperimentSession);
}

async function startExperimentSession() {
    const input = document.getElementById('session-participant-id');
    const participantId = String(input?.value || '').trim();
    await postRuntimeControl('/api/runtime/session/start', { participant_id: participantId }, '開始場次失敗。', {
        onSuccess: () => {
            writeSessionValue('participant_id', participantId);
            writeSessionValue('participantId', participantId);
        },
    });
}

async function endExperimentSession() {
    await postRuntimeControl('/api/runtime/session/end', {}, '結束場次失敗。');
}

async function postRuntimeControl(endpoint, payload, failureMessage, hooks = {}) {
    if (!requireLiveAdminControls()) {
        hooks.onDenied?.();
        return null;
    }
    try {
        const response = await apiJson(endpoint, {
            method: 'POST',
            body: JSON.stringify(payload || {}),
        });
        hooks.onSuccess?.(response);
        applyRuntimeControlStatus(response);
        return response;
    } catch (error) {
        hooks.onError?.(error);
        window.showAlert?.(error?.message || failureMessage, 'error');
        return null;
    }
}

function applyRuntimeControlStatus(payload = {}) {
    const snapshot = payload.runtime_control || payload;
    const session = snapshot.session || payload.session || {};
    const ui = {
        safe_mode: snapshot.safe_mode,
        ai_mode: snapshot.ai_mode,
        ai_mode_label: snapshot.ai_mode_label,
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
    if (snapshot.ai_mode) setActiveAiModeButton(snapshot.ai_mode);
    if (typeof session.active === 'boolean') {
        runtimeControlState.sessionActive = session.active;
        updateSessionControlButtons();
    }
    commit('DIAGNOSTICS.UPDATED', { ui });
    updatePlayerGuide();
}

function updateSessionControlButtons() {
    const canUse = canUseLiveAdminControls();
    const active = runtimeControlState.sessionActive === true;
    const known = typeof runtimeControlState.sessionActive === 'boolean';
    const startDisabled = !canUse || (known && active);
    const endDisabled = !canUse || !active;
    const participantDisabled = !canUse || active;

    setControlDisabled('btn-session-start', startDisabled);
    setControlDisabled('btn-session-end', endDisabled);
    setControlDisabled('session-participant-id', participantDisabled);
}

function setControlDisabled(id, disabled) {
    const element = document.getElementById(id);
    if (!element) return;
    element.disabled = Boolean(disabled);
    element.setAttribute('aria-disabled', disabled ? 'true' : 'false');
}

function setActiveDepthButton(depth) {
    const normalized = String(Number(depth));
    document.querySelectorAll('.depth-btn[data-depth]').forEach((button) => {
        button.classList.toggle('active', String(Number(button.dataset.depth)) === normalized);
    });
}

function setActiveAiModeButton(mode) {
    const normalized = String(mode || '').trim().toLowerCase();
    document.querySelectorAll('.ai-mode-btn[data-ai-mode]').forEach((button) => {
        button.classList.toggle('active', String(button.dataset.aiMode || '').toLowerCase() === normalized);
    });
}

function writeSessionValue(key, value) {
    try {
        window.sessionStorage?.setItem(key, String(value || ''));
    } catch {
        // Storage is best-effort.
    }
}
