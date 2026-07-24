import { UIRegistry } from '../ui/ui_registry.js';
import { RenderScheduler } from '../core/render_scheduler.js';

export function renderDiagnostics(diagnostics = {}) {
    RenderScheduler.schedule('diagnostics-render', () => {
        const vision = diagnostics.vision || diagnostics;
        const latency = Number(diagnostics.latency ?? diagnostics.latency_ms ?? vision.latency ?? vision.latency_ms ?? 0);
        const fps = Number(diagnostics.fps ?? vision.fps ?? 0);

        const latencyEl = UIRegistry.get('consLatency');
        const miniLatEl = UIRegistry.get('miniLatency');
        if (latencyEl) {
            latencyEl.innerText = `${Math.round(latency)}ms`;
            latencyEl.className = latency > 1000 ? 'value danger' : 'value success';
        }
        if (miniLatEl) miniLatEl.innerText = `延遲：${Math.round(latency)}ms`;

        const fpsEl = UIRegistry.get('consFps');
        const miniFpsEl = UIRegistry.get('miniFps');
        if (fpsEl) fpsEl.innerText = Number.isFinite(fps) && fps > 0 ? Math.round(fps) : '--';
        if (miniFpsEl) miniFpsEl.innerText = `FPS: ${Number.isFinite(fps) && fps > 0 ? Math.round(fps) : '--'}`;

        const visionState = mapVisionStatus(vision?.status, vision?.mode);
        const vidPill = document.getElementById('video-status-pill');
        if (vidPill) {
            const dotClass = visionState.isError ? 'error' : (visionState.isWarning ? 'warning' : 'live');
            vidPill.className = `status-pill ${dotClass}`;
            replaceStatusPill(vidPill, visionState.label);
        }

        const vidFps = document.getElementById('video-fps');
        if (vidFps) vidFps.textContent = `FPS: ${vision?.fps || '--'}`;

        const camStatus = document.getElementById('stat-camera');
        if (camStatus) {
            camStatus.innerText = visionState.label;
            camStatus.className = visionState.isError
                ? 'status-error'
                : (visionState.isWarning ? 'status-warning' : 'status-ok');
        }

        const lastUpdateEl = UIRegistry.get('consLastUpdate');
        if (lastUpdateEl) lastUpdateEl.innerText = new Date().toLocaleTimeString();

        renderVisionFenMonitor(vision, latency);
    });
}

function replaceStatusPill(element, labelText) {
    element.textContent = '';
    const dot = document.createElement('span');
    dot.className = 'dot';
    const label = document.createElement('span');
    label.textContent = ` ${labelText}`;
    element.append(dot, label);
}

function renderVisionFenMonitor(vision = {}, latency = 0) {
    const fen = vision.fen_after || vision.fen || '';
    const ucci = vision.ucci_position || (fen ? `position fen ${fen}` : '');
    const detections = Array.isArray(vision.detections) ? vision.detections : [];
    const count = vision.detections_count ?? detections.length;
    const avg = formatConfidence(vision.avg_confidence ?? vision.confidence);
    const min = formatConfidence(vision.min_confidence ?? vision.confidence);

    const fenEl = UIRegistry.get('visionFen');
    const ucciEl = UIRegistry.get('visionUcci');
    const countEl = UIRegistry.get('visionDetectionsCount');
    const confEl = UIRegistry.get('visionConfidence');
    const latencyEl = UIRegistry.get('visionYoloLatency');
    const timeEl = UIRegistry.get('visionRecognitionTime');
    const summaryEl = UIRegistry.get('visionDetectionSummary');

    if (fenEl) fenEl.textContent = fen || '--';
    if (ucciEl) ucciEl.textContent = ucci || '--';
    if (countEl) countEl.textContent = String(count ?? 0);
    if (confEl) confEl.textContent = `${avg} / ${min}`;
    if (latencyEl) latencyEl.textContent = `${Math.round(latency || 0)}ms`;
    if (timeEl) timeEl.textContent = formatTimestamp(vision.timestamp);
    if (summaryEl) summaryEl.textContent = summarizeDetections(detections);
}

function formatConfidence(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return '--';
    return `${Math.round(numeric * 100)}%`;
}

function formatTimestamp(value) {
    if (!value) return new Date().toLocaleTimeString();
    const numeric = Number(value);
    const date = Number.isFinite(numeric)
        ? new Date(numeric < 100000000000 ? numeric * 1000 : numeric)
        : new Date(value);
    if (Number.isNaN(date.getTime())) return new Date().toLocaleTimeString();
    return date.toLocaleTimeString();
}

function summarizeDetections(detections) {
    if (!detections.length) return '--';
    return detections.slice(0, 4).map((det) => {
        const label = det.class_name || det.className || det.label || det.name || 'obj';
        const confidence = formatConfidence(det.confidence ?? det.score);
        const cell = det.cell?.key || (det.cell ? `${det.cell.col},${det.cell.row}` : '');
        return cell ? `${label}@${cell} ${confidence}` : `${label} ${confidence}`;
    }).join(' | ');
}

function mapVisionStatus(status, mode) {
    const normalized = String(status || '').trim().toUpperCase();
    const normalizedMode = String(mode || '').trim().toLowerCase();
    if (normalized === 'STALE') {
        return { label: '資料延遲', isError: false, isWarning: true };
    }
    if (normalizedMode === 'simulation' || normalized === 'SIMULATION') {
        return { label: '模擬模式', isError: false, isWarning: true };
    }

    const labels = {
        OK: 'OK',
        READY: '已就緒',
        LIVE: '即時',
        RUNNING: '運行中',
        SIMULATION: '模擬模式',
        ERROR: '錯誤',
        OFFLINE: '離線',
        UNKNOWN: '未知',
    };
    return {
        label: labels[normalized] || status || 'OK',
        isError: normalized === 'ERROR' || normalized === 'OFFLINE',
        isWarning: false,
    };
}
