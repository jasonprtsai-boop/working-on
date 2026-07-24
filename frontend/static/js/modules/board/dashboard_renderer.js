import { RenderScheduler } from '../core/render_scheduler.js';
import { UIRegistry } from '../ui/ui_registry.js';

const SESSION_STARTED_AT = Date.now();
let sessionTimerId = null;
let latestSnapshot = {};

export const DashboardRenderer = {
    init() {
        this.render({});
        updateSessionTime();
        if (!sessionTimerId && typeof setInterval === 'function') {
            sessionTimerId = setInterval(updateSessionTime, 1000);
        }
    },

    dispose() {
        if (sessionTimerId && typeof clearInterval === 'function') {
            clearInterval(sessionTimerId);
        }
        sessionTimerId = null;
        latestSnapshot = {};
    },

    render(snapshot = {}) {
        latestSnapshot = snapshot || {};
        RenderScheduler.schedule('dashboard-summary', () => {
            renderBoard(latestSnapshot);
            renderVision(latestSnapshot);
            renderEngine(latestSnapshot);
            renderRobot(latestSnapshot);
            renderSafety(latestSnapshot);
            renderExperiment(latestSnapshot);
        });
    },
};

function renderBoard(snapshot) {
    const board = snapshot.board || {};
    const vision = snapshot.vision || {};
    const fen = board.fen || vision.fen_after || vision.fen || '';

    setText('dashboardBoardTurn', translateTurn(board.turn || turnFromFen(fen)));
    setText('dashboardBoardFen', fen || '--');
    setText('dashboardBoardLastMove', formatMove(board.last_move || board.lastMove));
    setText('dashboardBoardMoveCount', hasValue(board.move_count) ? board.move_count : '--');
}

function renderVision(snapshot) {
    const vision = snapshot.vision || {};
    const detections = Array.isArray(vision.detections) ? vision.detections : [];
    const count = vision.detections_count ?? detections.length;
    const confidence = formatConfidence(vision.avg_confidence ?? vision.confidence);
    const minConfidence = formatConfidence(vision.min_confidence ?? vision.confidence);
    const calibration = calibrationSnapshot(vision);
    const quality = calibration.quality || {};

    setText('visionDetectionsCount', hasValue(count) ? count : 0);
    setText('visionConfidence', `${confidence} / ${minConfidence}`);
    setStatus(
        'visionCalibrationStatus',
        calibration.calibrated === undefined ? '--' : (calibration.calibrated ? '已校正' : '尚未校正'),
        calibration.calibrated ? 'status-ok' : 'status-warning',
    );
    setText('visionCalibrationSource', calibration.source || '--');
    setText('visionCalibrationError', formatPx(quality.max_reprojection_error_px));
    setText('visionCalibrationQuality', formatCalibrationQuality(quality));
}

function renderEngine(snapshot) {
    const engine = snapshot.engine || {};
    const ui = snapshot.ui || {};
    const bestMove = engine.best_move || engine.bestMove || engine.bestmove || '';
    const thinking = Boolean(engine.is_thinking || engine.isThinking);
    const aiStatus = UIRegistry.get('statAi');
    const depth = Number(engine.depth || ui.engine_depth || ui.engineDepth);

    setText('dashboardEngineDepth', depth > 0 ? depth : '--');
    setText('dashboardEngineThinking', thinking ? '分析中' : '待命');
    setText('dashboardEnginePv', formatPv(engine.pv, engine.multiPv || engine.multipv));

    if (aiStatus) {
        aiStatus.textContent = thinking ? '分析中' : (bestMove ? '已分析' : '待命中');
        aiStatus.className = thinking ? 'status-warning' : 'status-ok';
    }
}

function renderRobot(snapshot) {
    const robot = snapshot.robot || {};
    const connected = Boolean(robot.connected || robot.is_connected);
    const busy = Boolean(robot.busy);
    const error = robot.error || '';

    setStatus('dashboardRobotStatus', connected ? '已連線' : '離線', connected ? 'status-ok' : 'status-error');
    setStatus('dashboardRobotBusy', busy ? '忙碌' : '待命', busy ? 'status-warning' : 'status-ok');
    setStatus('dashboardRobotError', error || '--', error ? 'status-error' : 'status-ok');
    setText('dashboardRobotQueue', hasValue(robot.queue_size) ? robot.queue_size : '--');
    setStatus('dashboardRobotIp', formatEndpoint(robot), connected ? 'status-ok' : 'status-error');
    setText('dashboardRobotPosition', formatPosition(robot.position || robot.robot_position));
    setText('dashboardRobotOrientation', formatOrientation(robot.orientation || robot.telemetry?.orientation));
    setText('dashboardRobotJoints', formatJoints(robot.joint_angles || robot.joints || robot.angles || robot.telemetry?.joint_angles));
    setText('dashboardRobotSpeed', formatSpeed(robot.speed ?? robot.telemetry?.speed));
    const telemetry = telemetrySource(robot.telemetry || {});
    setStatus('dashboardRobotTelemetrySource', telemetry.label, telemetry.className);
}

function renderSafety(snapshot) {
    const ui = snapshot.ui || {};
    const robot = snapshot.robot || {};
    const vision = snapshot.vision || {};
    const phase = String(ui.phase || '').toUpperCase();
    const overlayActive = document.getElementById('pause-overlay')?.classList.contains('active') || false;
    const explicitStop = firstDefined(
        ui.estop_triggered,
        ui.e_stop,
        ui.emergency_stop,
        robot.estop_triggered,
        robot.global_stop,
    );
    const isStopped = explicitStop !== undefined ? Boolean(explicitStop) : phase === 'EMERGENCY' || overlayActive;
    const safeMode = firstDefined(ui.safe_mode, ui.safeMode, robot.safe_mode, robot.safeMode, vision.safe_mode, vision.safeMode);
    const camera = classifyCamera(vision);

    setStatus('dashboardSafetyEstop', isStopped ? '已觸發' : '正常', isStopped ? 'status-error' : 'status-ok');
    if (safeMode === undefined) {
        setStatus('dashboardSafetySafeMode', '未提供', 'status-warning');
    } else {
        setStatus('dashboardSafetySafeMode', safeMode ? '已啟用' : '已停用', safeMode ? 'status-ok' : 'status-warning');
    }
    setStatus('dashboardSafetyCameraReady', camera.label, camera.className);
}

function renderExperiment(snapshot) {
    const ui = snapshot.ui || {};
    const engine = snapshot.engine || {};
    const experiment = snapshot.experiment || ui.experiment || {};
    const participant = firstText(
        experiment.participant_id,
        experiment.participantId,
        ui.participant_id,
        ui.participantId,
        readSessionValue('participantId'),
        readSessionValue('participant_id'),
    );
    const difficulty = firstText(
        experiment.ai_difficulty,
        experiment.aiDifficulty,
        ui.ai_mode_label,
        ui.aiModeLabel,
        ui.ai_difficulty,
        ui.aiDifficulty,
        engine.ai_difficulty,
        engine.aiDifficulty,
        engine.skill_level,
        engine.skillLevel,
        hasValue(ui.engine_depth) ? `深度 ${ui.engine_depth}` : '',
    );
    const sessionId = firstText(experiment.session_id, experiment.sessionId, ui.session_id, ui.sessionId);
    const active = firstDefined(experiment.active, ui.session_active, ui.sessionActive);
    const status = active === undefined ? '待命' : (active ? '進行中' : '已結束');

    setText('dashboardExpParticipant', participant || '未設定');
    setText('dashboardExpSessionId', sessionId || '--');
    setStatus('dashboardExpSessionStatus', status, active ? 'status-ok' : 'status-warning');
    setText('dashboardExpDifficulty', difficulty || '未提供');
    updateSessionTime();
}

function updateSessionTime() {
    const ui = latestSnapshot.ui || {};
    const experiment = latestSnapshot.experiment || ui.experiment || {};
    const startedAt = timestampToMs(firstDefined(experiment.started_at, experiment.session_started_at, ui.session_started_at, ui.sessionStartedAt));
    const endedAt = timestampToMs(firstDefined(experiment.ended_at, experiment.session_ended_at, ui.session_ended_at, ui.sessionEndedAt));
    const durationSec = firstDefined(experiment.duration_sec, ui.session_time_sec, ui.sessionTimeSec);
    const active = Boolean(firstDefined(experiment.active, ui.session_active, ui.sessionActive));

    if (startedAt) {
        const end = active ? Date.now() : (endedAt || Date.now());
        setText('dashboardExpSessionTime', formatDuration(end - startedAt));
        return;
    }
    if (hasValue(durationSec)) {
        setText('dashboardExpSessionTime', formatDuration(Number(durationSec) * 1000));
        return;
    }
    setText('dashboardExpSessionTime', formatDuration(Date.now() - SESSION_STARTED_AT));
}

function setText(key, value) {
    const element = UIRegistry.get(key);
    if (!element) return;
    element.textContent = String(value ?? '--');
}

function setStatus(key, value, className) {
    const element = UIRegistry.get(key);
    if (!element) return;
    element.textContent = String(value ?? '--');
    element.className = className || '';
}

function translateTurn(turn) {
    const normalized = String(turn || '').toLowerCase();
    if (normalized === 'red' || normalized === 'w' || normalized === 'white') return '紅方';
    if (normalized === 'black' || normalized === 'b') return '黑方';
    return turn || '--';
}

function turnFromFen(fen) {
    const parts = String(fen || '').trim().split(/\s+/);
    return parts.length > 1 ? parts[1] : '';
}

function formatMove(move) {
    if (!move) return '--';
    if (typeof move === 'string') return move || '--';
    if (move.notation) return move.notation;
    if (move.uci) return move.uci;
    if (move.from && move.to) return `${move.from}-${move.to}`;
    if (move.source && move.target) return `${move.source}-${move.target}`;
    return '--';
}

function formatPv(pv, multiPv) {
    const direct = normalizePvLine(pv);
    if (direct) return direct;

    const firstLine = Array.isArray(multiPv) ? multiPv[0] : null;
    if (!firstLine) return '--';
    return normalizePvLine(firstLine.pv || firstLine.line || firstLine.moves || firstLine.move || firstLine.best_move);
}

function normalizePvLine(value) {
    if (!value) return '';
    if (typeof value === 'string') return value || '';
    if (!Array.isArray(value)) return formatMove(value);
    return value
        .map((item) => typeof item === 'string' ? item : formatMove(item))
        .filter(Boolean)
        .slice(0, 8)
        .join(' ');
}

function formatConfidence(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return '--';
    return `${Math.round(numeric * 100)}%`;
}

function formatPosition(position) {
    if (!position) return '--';
    if (Array.isArray(position)) {
        const [x = 0, y = 0, z = 0] = position;
        return `X${formatAxis(x)} Y${formatAxis(y)} Z${formatAxis(z)}`;
    }
    return `X${formatAxis(position.x)} Y${formatAxis(position.y)} Z${formatAxis(position.z)}`;
}

function formatOrientation(orientation) {
    if (!orientation || typeof orientation !== 'object') return '--';
    const rx = Number(orientation.rx);
    const ry = Number(orientation.ry);
    const rz = Number(orientation.rz);
    if (![rx, ry, rz].some(Number.isFinite)) return '--';
    return `RX${formatAxis(rx)} RY${formatAxis(ry)} RZ${formatAxis(rz)}`;
}

function formatJoints(joints) {
    if (!joints) return '--';
    if (Array.isArray(joints)) {
        return joints
            .slice(0, 6)
            .map((value, index) => `J${index + 1}:${formatAxis(value)}`)
            .join(' ');
    }
    if (typeof joints !== 'object') return '--';
    const parts = ['j1', 'j2', 'j3', 'j4', 'j5', 'j6']
        .filter((key) => Number.isFinite(Number(joints[key])))
        .map((key) => `${key.toUpperCase()}:${formatAxis(joints[key])}`);
    return parts.join(' ') || '--';
}

function formatSpeed(speed) {
    const numeric = Number(speed);
    if (!Number.isFinite(numeric)) return '--';
    return `${numeric.toFixed(1)} mm/s`;
}

function formatEndpoint(robot) {
    const connection = robot.connection && typeof robot.connection === 'object' ? robot.connection : {};
    const host = robot.ip || connection.ip || connection.host || '';
    const port = robot.port ?? connection.port;
    if (!host && !hasValue(port)) return '--';
    return hasValue(port) ? `${host || '--'}:${port}` : String(host);
}

function telemetrySource(telemetry) {
    const source = String(telemetry.source || '').trim().toLowerCase();
    if (source === 'hardware') return { label: '硬體', className: 'status-ok' };
    if (source === 'simulation') return { label: '模擬', className: 'status-warning' };
    if (source === 'unavailable') return { label: '無法取得', className: 'status-error' };
    if (source === 'disabled') return { label: '已停用', className: 'status-warning' };
    if (source === 'software') return { label: '軟體', className: 'status-warning' };
    return { label: '--', className: 'status-warning' };
}

function formatAxis(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    return numeric.toFixed(1);
}

function classifyCamera(vision) {
    const status = String(vision.status || '').trim().toUpperCase();
    const mode = String(vision.mode || '').trim().toLowerCase();
    if (status === 'ERROR' || status === 'OFFLINE') {
        return { label: '未就緒', className: 'status-error' };
    }
    if (mode === 'simulation' || status === 'SIMULATION') {
        return { label: '模擬', className: 'status-warning' };
    }
    if (Number(vision.fps) > 0 || ['OK', 'READY', 'LIVE', 'RUNNING'].includes(status)) {
        return { label: '已就緒', className: 'status-ok' };
    }
    return { label: '--', className: 'status-warning' };
}

function calibrationSnapshot(vision) {
    const calibration = vision.calibration && typeof vision.calibration === 'object' ? vision.calibration : {};
    const quality = firstObject(
        vision.calibration_quality,
        vision.calibrationQuality,
        calibration.quality,
    );
    const calibrated = firstDefined(vision.calibrated, calibration.calibrated);
    const source = firstText(vision.calibration_source, vision.calibrationSource, calibration.source);
    return {
        calibrated,
        source,
        quality,
    };
}

function firstObject(...values) {
    return values.find((value) => value && typeof value === 'object' && !Array.isArray(value)) || {};
}

function formatPx(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    return `${numeric.toFixed(numeric >= 10 ? 1 : 3)} px`;
}

function formatCalibrationQuality(quality) {
    if (!quality || typeof quality !== 'object') return '--';
    const edge = Number(quality.edge_ratio);
    const angle = Number(quality.min_angle_deg);
    const area = Number(quality.area_ratio);
    const parts = [];
    if (Number.isFinite(edge)) parts.push(`edge ${edge.toFixed(2)}`);
    if (Number.isFinite(angle)) parts.push(`angle ${angle.toFixed(1)}deg`);
    if (Number.isFinite(area)) parts.push(`area ${(area * 100).toFixed(1)}%`);
    return parts.join(' / ') || '--';
}

function firstDefined(...values) {
    return values.find((value) => value !== undefined && value !== null);
}

function firstText(...values) {
    const value = values.find((item) => item !== undefined && item !== null && String(item).trim() !== '');
    return value === undefined ? '' : String(value);
}

function hasValue(value) {
    return value !== undefined && value !== null && value !== '';
}

function readSessionValue(key) {
    try {
        return window.sessionStorage?.getItem(key) || '';
    } catch {
        return '';
    }
}

function formatDuration(ms) {
    const totalSeconds = Math.max(0, Math.floor(Number(ms) / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) return `${hours}:${pad2(minutes)}:${pad2(seconds)}`;
    return `${pad2(minutes)}:${pad2(seconds)}`;
}

function timestampToMs(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return 0;
    return numeric < 100000000000 ? numeric * 1000 : numeric;
}

function pad2(value) {
    return String(value).padStart(2, '0');
}
