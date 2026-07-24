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
import { exportCsvReport, exportExcelReport } from './export_controller.js';
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

const ADMIN_ONLY_CONTROL_IDS = [
    'btn-estop-trigger',
    'btn-export-excel',
    'btn-export-csv',
    'btn-resume-overlay',
    'btn-session-start',
    'btn-session-end',
];

let playerGameStarted = false;
let videoReconnectAttempts = 0;
let videoReconnectTimer = null;
let videoStreamActive = false;
let setupStatusTimerId = null;
const setupWizardState = {
    settingsSaved: false,
    preflight: null,
    commissioning: null,
};
const VIDEO_RECONNECT_BASE_MS = 800;
const VIDEO_RECONNECT_MAX_MS = 6000;
const VISION_STALE_THRESHOLD_MS = 3000;

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
        videoStreamActive = false;
        markVideoStatus('standby', '重新連線中');
        scheduleVideoReconnect(imgEl);
    };
}

function setupUI() {
    bindClick('btn-role-player', () => switchView('view-player'));
    bindClick('btn-player-start', startPlayerGame);
    bindClick('btn-role-console', requestConsoleAccess);
    bindClick('btn-role-setup', requestSetupAccess);
    bindClick('btn-exit', () => switchView('view-landing'));
    bindClick('btn-setup-exit', () => switchView('view-landing'));
    bindClick('btn-console-exit', () => switchView('view-landing'));
    bindClick('btn-toggle-board', () => switchPane('pane-board-view', 'btn-toggle-board'));
    bindClick('btn-toggle-video', () => switchPane('pane-video-view', 'btn-toggle-video'));
    bindClick('btn-toggle-setup', openSetupPane);
    bindClick('btn-toggle-status', () => switchPane('pane-status-view', 'btn-toggle-status'));
    bindClick('btn-estop-trigger', triggerEmergencyStop);
    bindClick('btn-player-estop', triggerPlayerEmergencyStop);
    bindClick('btn-resume-overlay', clearEmergencyStop);
    bindClick('btn-export-excel', exportExcelReport);
    bindClick('btn-export-csv', exportCsvReport);
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
    installAuthorizationGuards();

    const videoFeed = UIRegistry.get('videoFeed');
    if (videoFeed) {
        videoFeed.dataset.src = '/api/video_feed';
        videoFeed.addEventListener('load', () => handleVideoLoad());
        videoFeed.addEventListener('error', () => window.handleVideoError(videoFeed));
        if (hasAdminAccess()) reconnectVideo();
    }

    commit('UI_TOAST', { text: 'System console ready.', level: 'info' });
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
    }
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

    if (!isPlayerView) {
        startPanel?.classList.add('hidden');
        arena?.classList.add('hidden');
        return;
    }

    startPanel?.classList.toggle('hidden', playerGameStarted);
    arena?.classList.toggle('hidden', !playerGameStarted);
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
        playerGameStarted = true;
        updatePlayerStartGate(true);
        applyRuntimeControlStatus(payload);
        updatePlayerGuide();
        window.showAlert?.('對局已開始。', 'success');
        await loadInitialStateSnapshot();
    } catch (error) {
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

async function triggerPlayerEmergencyStop() {
    showSystemOverlay('Emergency stop triggered from player view.');
    commit('DIAGNOSTICS.UPDATED', { ui: { estop_triggered: true, phase: 'EMERGENCY' } });
    try {
        await apiJson('/api/player/estop', { method: 'POST', body: JSON.stringify({ reason: 'player_view' }) });
        window.showAlert?.('Emergency stop triggered.', 'warning');
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
    bindClick('btn-setup-vision-auto', autoCalibrateSetupVision);
    bindClick('btn-setup-preflight', () => refreshSetupPreflight());
    bindClick('btn-setup-wizard-refresh', () => refreshSetupPreflight());
    bindClick('btn-setup-refresh-robot-status', () => refreshSetupRobotStatus());
    bindSubmit('setup-settings-form', saveSetupSettings);
    subscribe('robot', (robot) => renderSetupRobotStatus(robot));
    document.querySelectorAll('[data-setup-test]').forEach((button) => {
        button.addEventListener('click', () => runSetupHardwareTest(button.dataset.setupTest));
    });

    document.querySelectorAll('[data-setup-field]').forEach((field) => {
        field.addEventListener('input', markSetupDirty);
        field.addEventListener('change', markSetupDirty);
    });
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
        if (!quiet) window.showAlert?.('Settings loaded.', 'success');
    } catch (error) {
        setSetupSaveState('載入失敗');
        if (!quiet) window.showAlert?.(error?.message || 'Settings unavailable.', 'error');
    }
}

async function saveSetupSettings(event) {
    event?.preventDefault?.();
    if (!canUseSetupControls()) {
        window.showAlert?.('Setup is locked.', 'warning');
        refreshAuthorizationUI();
        return;
    }

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
        const warnings = Array.isArray(payload.warnings) ? payload.warnings.filter(Boolean) : [];
        if (warnings.length) {
            window.showAlert?.(warnings[0], 'warning', 5200);
        } else {
            window.showAlert?.('Settings saved.', 'success');
        }
    } catch (error) {
        setSetupSaveState('儲存失敗');
        window.showAlert?.(error?.message || 'Settings save failed.', 'error');
    }
}

async function refreshSetupCameras({ quiet = false } = {}) {
    if (!hasSetupAccess()) return;
    try {
        const payload = await apiJson('/api/vision/cameras?refresh=1', { method: 'GET' }, 9000);
        renderCameraOptions(payload.candidates || [], payload.current);
        if (!quiet) window.showAlert?.('Camera list refreshed.', 'success');
    } catch (error) {
        ensureCameraOption(document.getElementById('setup-camera-index')?.value || '0');
        if (!quiet) window.showAlert?.(error?.message || 'Camera scan failed.', 'warning');
    }
}

async function autoCalibrateSetupVision() {
    if (!canUseSetupControls()) {
        window.showAlert?.('Setup is locked.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    try {
        const payload = await apiJson('/api/vision/calibration', {
            method: 'POST',
            body: JSON.stringify({ mode: 'auto', persist: true }),
        }, 12000);
        applyVisionCalibrationStatus(payload);
        await loadSetupSettings({ quiet: true });
        window.showAlert?.('Vision calibration updated.', 'success');
    } catch (error) {
        window.showAlert?.(error?.message || 'Vision calibration failed.', 'error');
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
                payload.ready ? 'Preflight passed.' : 'Preflight needs attention.',
                payload.ready ? 'success' : 'warning'
            );
        }
    } catch (error) {
        setTextById('setup-preflight-status', '檢查失敗');
        if (!quiet) window.showAlert?.(error?.message || 'Preflight unavailable.', 'error');
    }
}

async function runSetupHardwareTest(action) {
    if (!canUseSetupControls()) {
        window.showAlert?.('Setup is locked.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    if (!action) return;
    setTextById('setup-hardware-test-status', 'Testing');
    try {
        const liveHardwareTest = document.getElementById('setup-live-hardware-test')?.checked === true;
        const payload = await apiJson('/api/setup/hardware-test', {
            method: 'POST',
            body: JSON.stringify({ action, dry_run: !liveHardwareTest }),
        }, 12000);
        if (payload.status) {
            renderSetupRobotStatus(payload.status);
            commit('ROBOT.STATUS_UPDATED', payload.status);
        }
        if (payload.commissioning) renderSetupCommissioning(payload.commissioning);
        const label = payload.dry_run ? 'Dry-run passed' : 'Passed';
        setTextById('setup-hardware-test-status', `${action}: ${label}`);
        window.showAlert?.(`${action} ${label}`, 'success');
        refreshSetupPreflight({ quiet: true });
    } catch (error) {
        setTextById('setup-hardware-test-status', `${action}: Failed`);
        window.showAlert?.(error?.message || `${action} failed.`, 'error');
    }
}

function startSetupRobotStatusRefresh() {
    renderSetupRobotStatus(state.snapshot.robot || {});
    refreshSetupRobotStatus({ quiet: true });
    if (setupStatusTimerId || typeof setInterval !== 'function') return;
    setupStatusTimerId = setInterval(() => {
        const active = document.getElementById('view-setup')?.classList.contains('active');
        if (active) refreshSetupRobotStatus({ quiet: true });
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
        if (!quiet) window.showAlert?.(error?.message || 'Robot status unavailable.', 'warning');
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
        ? `Error: ${robot.error}`
        : (busy ? 'Moving' : (connected ? 'Connected' : 'Offline'));
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
    if (!host && (port === undefined || port === null || port === '')) return '--';
    return port === undefined || port === null || port === '' ? String(host) : `${host || '--'}:${port}`;
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
    return fakeRobot ? 'simulation' : '--';
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

function reconnectSetupCamera() {
    if (!hasSetupAccess()) return;
    const preview = document.getElementById('setup-camera-preview');
    if (!preview) return;
    const src = preview.dataset?.src || '/api/video_feed';
    preview.src = `${src}${src.includes('?') ? '&' : '?'}setup=${Date.now()}`;
}

function applySetupSettings(settings = {}, files = {}) {
    document.querySelectorAll('[data-setup-field]').forEach((field) => {
        const path = field.dataset.setupField;
        const value = getNestedValue(settings, path);
        if (value === undefined || value === null) return;
        if (field.tagName === 'SELECT') ensureCameraOption(value);
        if (field.type === 'checkbox') {
            field.checked = Boolean(value);
            return;
        }
        field.value = String(value);
    });

    const robotCalibration = settings.robot?.calibration || {};
    const visionCalibration = settings.vision?.calibration || {};
    setTextById('setup-robot-calibration-status', formatRobotCalibration(robotCalibration));
    setTextById('setup-vision-status', formatVisionCalibration(visionCalibration));
    setTextById('setup-settings-file', files.setup_settings || '--');
    setTextById('setup-robot-file', files.robot_calibration || robotCalibration.path || '--');
    setTextById('setup-vision-file', files.vision_calibration || '--');
    setSetupSaveState('已載入');
}

function markSetupDirty() {
    setupWizardState.settingsSaved = false;
    setSetupSaveState('已修改');
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
            message: settingsSaved ? 'Saved' : 'Save required',
        },
        setupWizardStepFromCheck(checks, 'vision_ready', 'Vision ready'),
        setupWizardStepFromCheck(checks, 'motion_profile_safe', 'Motion safe'),
        setupWizardStepFromCheck(checks, 'board_and_dead_zone_safe', 'Area safe'),
        setupWizardStepFromCheck(checks, 'robot_register_probe', 'Register verified'),
        {
            key: 'hardware_tests',
            ok: hardwareOk,
            message: hardwareOk ? 'Hardware tested' : 'Run hardware test',
        },
        {
            key: 'preflight_ready',
            ok: Boolean(payload?.ready),
            message: payload ? (payload.ready ? 'Passed' : 'Blocked') : 'Run preflight',
        },
    ];

    let firstBlocked = null;
    steps.forEach((step) => {
        const item = document.querySelector(`[data-setup-step="${step.key}"]`);
        if (!item) return;
        item.dataset.status = step.ok ? 'ok' : (step.warning ? 'warning' : 'blocked');
        const status = item.querySelector('strong');
        if (status) status.textContent = step.message || (step.ok ? 'OK' : 'Check');
        if (!step.ok && !firstBlocked) firstBlocked = step;
    });

    const ready = steps.every((step) => step.ok);
    setTextById('setup-wizard-ready', ready ? 'Ready' : 'Not ready');
    setTextById('setup-wizard-next', firstBlocked ? firstBlocked.message : 'Start player mode');
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
    if (!check) return { key, ok: false, message: 'Run preflight' };
    return {
        key,
        ok: check.ok === true,
        warning: check.severity !== 'error',
        message: check.ok === true ? okMessage : (check.message || 'Check required'),
    };
}

function numericSetupField(field, path) {
    return field.type === 'number' || path === 'vision.camera_index';
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
        option.textContent = `Camera ${index}${candidate.available ? ' online' : ' offline'}`;
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
    option.textContent = `Camera ${normalized}`;
    select.appendChild(option);
}

function getNestedValue(data, path) {
    return String(path || '').split('.').reduce((current, part) => {
        if (current === undefined || current === null) return undefined;
        return current[part];
    }, data);
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
    return calibration?.path ? 'Loaded' : '--';
}

function formatVisionCalibration(calibration) {
    if (!calibration || !Object.keys(calibration).length) return '--';
    const quality = calibration.quality || {};
    if (quality.max_error !== undefined) return `Error ${Number(quality.max_error).toFixed(2)}`;
    if (calibration.calibrated !== undefined) return calibration.calibrated ? 'Calibrated' : 'Not calibrated';
    return calibration.source || 'Loaded';
}

function reconnectVideo({ force = false } = {}) {
    if (!hasAdminAccess()) return;
    clearVideoReconnectTimer();
    videoReconnectAttempts = 0;
    startVideoStream({ force });
}

function startVideoStream({ force = false } = {}) {
    const videoFeed = UIRegistry.get('videoFeed');
    if (!videoFeed) return;
    const src = videoFeed.dataset?.src || '/api/video_feed';
    const currentSrc = String(videoFeed.currentSrc || videoFeed.src || '');
    if (!force && videoStreamActive && currentSrc.includes(src)) {
        markVideoStatus('live', '已連線');
        return;
    }
    videoFeed.src = `${src}${src.includes('?') ? '&' : '?'}t=${Date.now()}`;
    videoStreamActive = true;
    markVideoStatus('standby', '連線中');
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
        if (!quiet) window.showAlert?.('Calibration status refreshed.', 'success');
    } catch (error) {
        if (!quiet) window.showAlert?.(error?.message || 'Calibration status unavailable.', 'warning');
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
        refreshVisionCalibration({ quiet: true });
        refreshAuthorizationUI();
        window.showAlert?.('Admin console unlocked.', 'success');
    } catch (error) {
        if (errorEl) errorEl.textContent = error?.message || 'Login failed.';
        window.showAlert?.('Admin login failed.', 'error');
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
        window.showAlert?.('Setup unlocked.', 'success');
    } catch (error) {
        clearSetupToken();
        if (errorEl) errorEl.textContent = error?.message || 'Login failed.';
        window.showAlert?.('Setup login failed.', 'error');
    } finally {
        if (form) form.reset();
        refreshAuthorizationUI();
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

function showSetupAuthOverlay() {
    const overlay = document.getElementById('setup-auth-overlay');
    if (!overlay) return;
    overlay.classList.remove('hidden');
    overlay.classList.add('active');
    overlay.setAttribute('aria-hidden', 'false');
    const input = document.getElementById('setup-password');
    setTimeout(() => input?.focus?.(), 0);
}

function hideSetupAuthOverlay() {
    const overlay = document.getElementById('setup-auth-overlay');
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
    const aiLabel = ui.ai_mode_label || ui.ai_difficulty || '陪伴模式';

    setTextById('player-guide-turn', turnLabel);
    setTextById('player-guide-ai', aiLabel);

    const visionStatus = playerVisionStatus(vision);
    const robotStatus = playerRobotStatus(robot, engine, turn);
    setTextById('player-guide-vision', visionStatus.text);
    setGuideState('player-guide-vision-card', visionStatus.state);
    setTextById('player-guide-robot', robotStatus.text);
    setGuideState('player-guide-robot-card', robotStatus.state);

    if (!playerGameStarted) {
        setPlayerGuideCopy('等待開始', '請按下開始對局', '開始後，系統會提示輪到哪一方、辨識是否成功，以及機械手臂是否準備動作。');
        return;
    }
    if (robot.estop_triggered || robot.global_stop || ui.estop_triggered) {
        setPlayerGuideCopy('緊急停止', '系統已停止，請等待工作人員處理', '請勿移動棋盤或伸手靠近機械手臂。');
        return;
    }
    if (robot.busy) {
        setPlayerGuideCopy('機械手臂動作中', '請保持雙手離開棋盤', '等待機械手臂完成後，再依畫面提示繼續。');
        return;
    }
    if (robotStatus.state === 'warning') {
        setPlayerGuideCopy('機械手臂即將動作', '請保持雙手離開棋盤', 'AI 已產生走法，系統準備執行機械手臂動作。');
        return;
    }
    if (engine.is_thinking) {
        setPlayerGuideCopy('AI 思考中', '請稍候，不需要移動棋子', '系統正在計算下一步。');
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
    setPlayerGuideCopy('玩家回合', '請移動紅方棋子', '移動後請把手離開棋盤，等待系統顯示辨識成功。');
}

function setPlayerGuideCopy(step, action, detail) {
    setTextById('player-guide-step', step);
    setTextById('player-guide-action', action);
    setTextById('player-guide-detail', detail);
}

function playerVisionStatus(vision = {}) {
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

function playerRobotStatus(robot = {}, engine = {}, turn = 'red') {
    if (robot.error) return { state: 'error', text: '需要工作人員確認' };
    if (robot.estop_triggered || robot.global_stop) return { state: 'error', text: '緊急停止中' };
    if (robot.busy) return { state: 'warning', text: '動作中，請勿靠近' };
    if (turn === 'black' && (engine.best_move || engine.bestMove || engine.bestmove)) {
        return { state: 'warning', text: '即將動作' };
    }
    return { state: 'standby', text: '尚未動作' };
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

async function setAiMode(mode) {
    if (!canUseLiveAdminControls()) {
        window.showAlert?.('Control channel is not ready.', 'warning');
        refreshAuthorizationUI();
        return;
    }
    try {
        const payload = await apiJson('/api/runtime/ai-mode', {
            method: 'POST',
            body: JSON.stringify({ mode }),
        });
        applyRuntimeControlStatus(payload);
    } catch (error) {
        window.showAlert?.(error?.message || 'Failed to update AI mode.', 'error');
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
    commit('DIAGNOSTICS.UPDATED', { ui });
    updatePlayerGuide();
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
