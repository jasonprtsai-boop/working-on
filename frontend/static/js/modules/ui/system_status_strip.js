import { RenderScheduler } from '../core/render_scheduler.js';

const DEFAULT_LIGHTS = [
    { id: 'frontend', label: 'Frontend', group: 'logic', status: 'running', message: 'UI loaded' },
    { id: 'socket', label: 'Socket.IO', group: 'logic' },
    { id: 'eventbus', label: 'EventBus', group: 'logic' },
    { id: 'state', label: 'State Store', group: 'logic' },
    { id: 'vision', label: 'Vision', group: 'logic' },
    { id: 'yolo', label: 'YOLO', group: 'logic' },
    { id: 'board', label: 'Board', group: 'logic' },
    { id: 'engine', label: 'Pikafish', group: 'logic' },
    { id: 'queue', label: 'Queue', group: 'logic' },
    { id: 'robot', label: 'Robot', group: 'hardware' },
    { id: 'serial', label: 'Serial', group: 'hardware' },
    { id: 'usb', label: 'USB', group: 'hardware' },
    { id: 'storage', label: 'Storage', group: 'hardware' },
    { id: 'cpu', label: 'CPU', group: 'hardware' },
    { id: 'ram', label: 'RAM', group: 'hardware' },
    { id: 'gpu', label: 'GPU', group: 'hardware' },
    { id: 'temperature', label: 'Temp', group: 'hardware' },
];

const STATUS_PRIORITY = {
    error: 6,
    blocked: 5,
    offline: 4,
    warning: 3,
    processing: 2,
    active: 2,
    running: 2,
    success: 1,
    idle: 0,
};

const STATUS_LABELS = {
    idle: 'Idle',
    active: 'Active',
    running: 'Running',
    processing: 'Processing',
    success: 'Success',
    warning: 'Warning',
    blocked: 'Blocked',
    offline: 'Offline',
    error: 'Error',
};

export const SystemStatusStrip = {
    container: null,
    detail: null,
    updated: null,
    lights: new Map(),
    selectedId: '',
    initialized: false,

    init() {
        this.container = document.getElementById('system-status-lights');
        this.detail = document.getElementById('system-status-detail');
        this.updated = document.getElementById('system-status-updated');
        this.lights = new Map(DEFAULT_LIGHTS.map((item) => [item.id, normalizeLight(item)]));
        this.selectedId = '';
        this.initialized = Boolean(this.container);
        this.render();
    },

    handleEvent(event) {
        if (!this.initialized || !event) return;
        if (event.type === 'DIAGNOSTICS.UPDATED') {
            this.applyDiagnostics(event.payload || {});
        } else if (event.type === 'ROBOT.STATUS_UPDATED') {
            this.mergeLight('robot', robotLight(event.payload || {}));
        } else if (event.type === 'VISION.FRAME_PROCESSED') {
            this.mergeLight('vision', visionLight(event.payload || {}));
            this.mergeLight('board', boardLight(event.payload || {}));
        } else if (event.type === 'ENGINE.INFO_UPDATED') {
            this.mergeLight('engine', engineLight(event.payload || {}));
        }
        this.render();
    },

    applyDiagnostics(payload) {
        const topology = payload.topology || {};
        const nodes = Array.isArray(topology.nodes) ? topology.nodes : [];
        const edges = Array.isArray(topology.edges) ? topology.edges : [];
        const queue = payload.queue || {};
        const health = payload.health || {};
        const vision = payload.vision || {};
        const robot = payload.robot || {};
        const workers = payload.workers || {};
        const telemetry = payload.telemetry || {};

        for (const node of nodes) {
            const id = mapNodeId(node.id);
            if (!id) continue;
            this.mergeLight(id, {
                label: this.getLabel(id) || node.label,
                status: sanitizeStatus(node.status),
                message: node.message || node.last_event || '',
                lastEvent: node.last_event || '',
                latencyMs: node.latency_ms,
                updatedAt: node.last_event_at,
            });
        }

        const eventBusStatus = telemetry.enabled === false ? 'warning' : 'running';
        this.mergeLight('eventbus', {
            status: eventBusStatus,
            message: `events: ${telemetry.recorded_events ?? '--'}`,
            lastEvent: 'DIAGNOSTICS.UPDATED',
            updatedAt: topology.updated_at,
        });

        this.mergeLight('queue', queueLight(queue, edges));
        this.mergeLight('vision', visionLight(vision));
        this.mergeLight('yolo', yoloLight(vision, workers));
        this.mergeLight('board', boardLight(vision));
        this.mergeLight('robot', robotLight(robot));
        this.mergeLight('serial', linkLight('Serial', robot.serial));
        this.mergeLight('usb', linkLight('USB', robot.usb));
        this.mergeLight('cpu', cpuLight(health));
        this.mergeLight('ram', ramLight(health));
        this.mergeLight('gpu', gpuLight(health.gpu));
        this.mergeLight('temperature', temperatureLight(health.temperature));

        if (this.updated) {
            this.updated.textContent = `updated ${formatTime(topology.updated_at || health.timestamp || Date.now() / 1000)}`;
        }
    },

    mergeLight(id, patch) {
        const current = this.lights.get(id) || normalizeLight({ id, label: id });
        const next = normalizeLight({ ...current, ...patch, id });
        this.lights.set(id, next);
    },

    getLabel(id) {
        return this.lights.get(id)?.label || id;
    },

    render() {
        if (!this.container) return;
        RenderScheduler.schedule('system-status-strip', () => {
            const fragment = document.createDocumentFragment();
            for (const light of this.lights.values()) {
                fragment.appendChild(this.renderLight(light));
            }
            replaceChildren(this.container, fragment);
            if (this.selectedId) {
                this.renderDetail(this.lights.get(this.selectedId));
            }
        });
    },

    renderLight(light) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `system-status-light is-${light.status}`;
        button.dataset.statusId = light.id;
        button.title = detailText(light);
        button.setAttribute('aria-label', `${light.label}: ${STATUS_LABELS[light.status] || light.status}`);

        const dot = document.createElement('span');
        dot.className = 'system-status-light__dot';
        const label = document.createElement('span');
        label.className = 'system-status-light__label';
        label.textContent = light.label;
        const state = document.createElement('span');
        state.className = 'system-status-light__state';
        state.textContent = STATUS_LABELS[light.status] || light.status;

        button.append(dot, label, state);
        button.addEventListener('click', () => {
            this.selectedId = this.selectedId === light.id ? '' : light.id;
            this.renderDetail(this.selectedId ? light : null);
        });
        return button;
    },

    renderDetail(light) {
        if (!this.detail) return;
        if (!light) {
            this.detail.classList.add('hidden');
            this.detail.textContent = '';
            return;
        }
        this.detail.classList.remove('hidden');
        this.detail.textContent = '';

        const title = document.createElement('div');
        title.className = 'system-status-detail__title';
        title.textContent = `${light.label} / ${STATUS_LABELS[light.status] || light.status}`;

        const body = document.createElement('div');
        body.className = 'system-status-detail__body';
        body.textContent = detailText(light);

        const link = document.createElement('a');
        link.href = '/dashboard';
        link.textContent = 'Open diagnostics';
        link.className = 'system-status-detail__link';

        this.detail.append(title, body, link);
    },
};

function normalizeLight(item) {
    return {
        id: String(item.id || ''),
        label: String(item.label || item.id || ''),
        group: item.group || 'logic',
        status: sanitizeStatus(item.status || 'idle'),
        message: item.message || '',
        lastEvent: item.lastEvent || item.last_event || '',
        latencyMs: item.latencyMs ?? item.latency_ms,
        updatedAt: item.updatedAt ?? item.updated_at,
    };
}

function mapNodeId(id) {
    const normalized = String(id || '').toLowerCase();
    const aliases = {
        engine: 'engine',
        'ai-engine': 'engine',
        robot: 'robot',
        vision: 'vision',
        state: 'state',
        queue: 'queue',
        socket: 'socket',
        storage: 'storage',
        health: 'cpu',
    };
    return aliases[normalized] || (DEFAULT_LIGHTS.some((item) => item.id === normalized) ? normalized : '');
}

function sanitizeStatus(value) {
    const aliases = {
        ok: 'success',
        ready: 'success',
        connected: 'success',
        enabled: 'running',
        busy: 'running',
        degraded: 'warning',
        simulation: 'warning',
        failed: 'error',
        disconnected: 'offline',
        unavailable: 'offline',
        not_available: 'offline',
    };
    const raw = String(value || 'idle').toLowerCase();
    const status = aliases[raw] || raw;
    return Object.prototype.hasOwnProperty.call(STATUS_PRIORITY, status) ? status : 'idle';
}

function worstStatus(statuses) {
    return statuses.map(sanitizeStatus).sort((a, b) => STATUS_PRIORITY[b] - STATUS_PRIORITY[a])[0] || 'idle';
}

function queueLight(queue, edges) {
    const queues = Object.values(queue || {}).filter((item) => item && typeof item === 'object');
    const size = queues.reduce((sum, item) => sum + Number(item.size || 0), 0);
    const blocked = queues.some((item) => item.blocked);
    const full = queues.some((item) => item.full);
    const edgeBlocked = (edges || []).some((edge) => edge?.status === 'blocked');
    return {
        label: 'Queue',
        status: blocked || edgeBlocked ? 'blocked' : (full ? 'warning' : (size > 0 ? 'processing' : 'success')),
        message: `${size} queued`,
        lastEvent: blocked ? 'QUEUE_BLOCKED' : 'QUEUE_MONITOR',
    };
}

function visionLight(vision) {
    const status = vision.status || (vision.camera_ready ? 'success' : 'idle');
    return {
        label: 'Vision',
        status: vision.simulation ? 'warning' : sanitizeStatus(status),
        message: `fps: ${formatNumber(vision.fps)} camera: ${vision.camera ?? '--'}`,
        lastEvent: 'VISION.STATUS',
        latencyMs: vision.latency_ms ?? vision.latency,
        updatedAt: vision.timestamp,
    };
}

function yoloLight(vision, workers) {
    const detectorWorker = workers?.vision_inference || workers?.camera;
    const detections = vision.detections_count ?? (Array.isArray(vision.detections) ? vision.detections.length : undefined);
    const status = detectorWorker?.last_error ? 'error' : (vision.simulation ? 'warning' : (detections !== undefined ? 'success' : sanitizeStatus(detectorWorker?.status || 'idle')));
    return {
        label: 'YOLO',
        status,
        message: `detections: ${detections ?? '--'} confidence: ${formatPercent(vision.avg_confidence ?? vision.confidence)}`,
        lastEvent: 'VISION_DETECTOR',
        latencyMs: vision.latency_ms ?? vision.latency,
    };
}

function boardLight(vision) {
    const hasBoard = Boolean(vision.fen || vision.fen_after || Object.keys(vision.board_state || {}).length);
    return {
        label: 'Board',
        status: hasBoard ? 'success' : 'idle',
        message: vision.fen_after || vision.fen || 'waiting for board reconstruction',
        lastEvent: hasBoard ? 'BOARD_RECOGNIZED' : 'BOARD_WAITING',
    };
}

function engineLight(engine) {
    return {
        label: 'Pikafish',
        status: engine.is_thinking ? 'processing' : (engine.best_move || engine.bestMove ? 'success' : 'idle'),
        message: `depth: ${engine.depth ?? '--'} best: ${engine.best_move || engine.bestMove || '--'}`,
        lastEvent: 'ENGINE.INFO_UPDATED',
    };
}

function robotLight(robot) {
    if (robot.error) {
        return { label: 'Robot', status: 'error', message: robot.error, lastEvent: 'ROBOT_ERROR' };
    }
    const connection = robot.connection && typeof robot.connection === 'object' ? robot.connection : {};
    const host = robot.ip || connection.ip || connection.host || '';
    const port = robot.port ?? connection.port;
    const endpoint = host ? `${host}${port ? `:${port}` : ''}` : 'ip: --';
    return {
        label: 'Robot',
        status: robot.busy ? 'running' : (robot.connected || robot.is_connected ? 'success' : 'offline'),
        message: `${endpoint} queue: ${robot.queue_size ?? '--'} action: ${robot.last_action || '--'}`,
        lastEvent: 'ROBOT.STATUS_UPDATED',
    };
}

function linkLight(label, link) {
    if (!link || typeof link !== 'object') {
        return { label, status: 'idle', message: 'no status yet', lastEvent: `${label.toUpperCase()}_WAITING` };
    }
    return {
        label,
        status: link.available ? 'success' : 'offline',
        message: link.status || (link.available ? 'available' : 'unavailable'),
        lastEvent: `${label.toUpperCase()}_STATUS`,
    };
}

function cpuLight(health) {
    const value = Number(health.cpu_percent);
    return {
        label: 'CPU',
        status: Number.isFinite(value) ? (value >= 90 ? 'warning' : 'success') : 'idle',
        message: Number.isFinite(value) ? `${value.toFixed(1)}%` : 'unavailable',
        lastEvent: 'HEALTH.CPU',
    };
}

function ramLight(health) {
    const value = Number(health.memory_mb);
    return {
        label: 'RAM',
        status: Number.isFinite(value) ? 'success' : 'idle',
        message: Number.isFinite(value) ? `${value.toFixed(0)} MB` : 'unavailable',
        lastEvent: 'HEALTH.RAM',
    };
}

function gpuLight(gpu) {
    if (!gpu || gpu.available === false) {
        return { label: 'GPU', status: 'offline', message: gpu?.reason || 'unavailable', lastEvent: 'GPU_UNAVAILABLE' };
    }
    return {
        label: 'GPU',
        status: Number(gpu.load_percent) >= 90 ? 'warning' : 'success',
        message: `${gpu.name || 'GPU'} ${formatNumber(gpu.load_percent)}%`,
        lastEvent: 'GPU_STATUS',
    };
}

function temperatureLight(temp) {
    if (!temp || temp.available === false) {
        return { label: 'Temp', status: 'offline', message: temp?.reason || 'unavailable', lastEvent: 'TEMP_UNAVAILABLE' };
    }
    const value = Number(temp.max_c);
    return {
        label: 'Temp',
        status: Number.isFinite(value) && value >= 80 ? 'warning' : 'success',
        message: Number.isFinite(value) ? `${value.toFixed(1)} C ${temp.label || ''}` : 'available',
        lastEvent: 'TEMPERATURE_STATUS',
    };
}

function detailText(light) {
    if (!light) return '';
    const parts = [
        `status: ${STATUS_LABELS[light.status] || light.status}`,
        light.lastEvent ? `event: ${light.lastEvent}` : '',
        Number.isFinite(Number(light.latencyMs)) ? `latency: ${Number(light.latencyMs).toFixed(0)}ms` : '',
        light.message ? `message: ${light.message}` : '',
        light.updatedAt ? `updated: ${formatTime(light.updatedAt)}` : '',
    ];
    return parts.filter(Boolean).join(' | ');
}

function formatTime(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return '--';
    const millis = numeric < 100000000000 ? numeric * 1000 : numeric;
    return new Date(millis).toLocaleTimeString([], { hour12: false });
}

function formatNumber(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric.toFixed(0) : '--';
}

function formatPercent(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return '--';
    return `${Math.round(numeric * 100)}%`;
}

function replaceChildren(element, child) {
    if (typeof element.replaceChildren === 'function') {
        element.replaceChildren(child);
        return;
    }
    element.textContent = '';
    element.appendChild(child);
}
