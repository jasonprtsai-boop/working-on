import { RenderScheduler } from '../core/render_scheduler.js';

const DEFAULT_LIGHTS = [
    { id: 'frontend', label: '前端介面', group: 'logic', status: 'running', message: '介面已載入' },
    { id: 'eventbus', label: 'EventBus', group: 'logic' },
    { id: 'state', label: '狀態儲存', group: 'logic' },
    { id: 'vision', label: '視覺', group: 'logic' },
    { id: 'yolo', label: 'YOLO', group: 'logic' },
    { id: 'board', label: '棋盤', group: 'logic' },
    { id: 'engine', label: 'Pikafish', group: 'logic' },
    { id: 'queue', label: '佇列', group: 'logic' },
    { id: 'robot', label: '機械手臂', group: 'hardware' },
    { id: 'serial', label: '序列埠', group: 'hardware' },
    { id: 'usb', label: 'USB', group: 'hardware' },
    { id: 'cpu', label: 'CPU', group: 'hardware' },
    { id: 'ram', label: 'RAM', group: 'hardware' },
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
    idle: '待命',
    active: '啟用',
    running: '運行中',
    processing: '處理中',
    success: '正常',
    warning: '警告',
    blocked: '阻塞',
    offline: '離線',
    error: '錯誤',
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

        if (this.updated) {
            this.updated.textContent = `更新 ${formatTime(topology.updated_at || health.timestamp || Date.now() / 1000)}`;
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
        link.textContent = '開啟診斷';
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
        label: '佇列',
        status: blocked || edgeBlocked ? 'blocked' : (full ? 'warning' : (size > 0 ? 'processing' : 'success')),
        message: `佇列 ${size} 筆`,
        lastEvent: blocked ? 'QUEUE_BLOCKED' : 'QUEUE_MONITOR',
    };
}

function visionLight(vision) {
    const status = vision.status || (vision.camera_ready ? 'success' : 'idle');
    return {
        label: '視覺',
        status: vision.simulation ? 'warning' : sanitizeStatus(status),
        message: `FPS：${formatNumber(vision.fps)} 相機：${vision.camera ?? '--'}`,
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
        message: `偵測：${detections ?? '--'} 信心值：${formatPercent(vision.avg_confidence ?? vision.confidence)}`,
        lastEvent: 'VISION_DETECTOR',
        latencyMs: vision.latency_ms ?? vision.latency,
    };
}

function boardLight(vision) {
    const hasBoard = Boolean(vision.fen || vision.fen_after || Object.keys(vision.board_state || {}).length);
    return {
        label: '棋盤',
        status: hasBoard ? 'success' : 'idle',
        message: vision.fen_after || vision.fen || '等待棋盤重建',
        lastEvent: hasBoard ? 'BOARD_RECOGNIZED' : 'BOARD_WAITING',
    };
}

function engineLight(engine) {
    return {
        label: 'Pikafish',
        status: engine.is_thinking ? 'processing' : (engine.best_move || engine.bestMove ? 'success' : 'idle'),
        message: `深度：${engine.depth ?? '--'} 最佳步：${engine.best_move || engine.bestMove || '--'}`,
        lastEvent: 'ENGINE.INFO_UPDATED',
    };
}

function robotLight(robot) {
    if (robot.error) {
        return { label: '機械手臂', status: 'error', message: robot.error, lastEvent: 'ROBOT_ERROR' };
    }
    const connection = robot.connection && typeof robot.connection === 'object' ? robot.connection : {};
    const host = robot.ip || connection.ip || connection.host || '';
    const port = robot.port ?? connection.port;
    const endpoint = host ? `${host}${port ? `:${port}` : ''}` : 'IP：--';
    return {
        label: '機械手臂',
        status: robot.busy ? 'running' : (robot.connected || robot.is_connected ? 'success' : 'offline'),
        message: `${endpoint} 佇列：${robot.queue_size ?? '--'} 動作：${robot.last_action || '--'}`,
        lastEvent: 'ROBOT.STATUS_UPDATED',
    };
}

function linkLight(label, link) {
    if (!link || typeof link !== 'object') {
        return { label, status: 'idle', message: '尚無狀態', lastEvent: `${label.toUpperCase()}_WAITING` };
    }
    return {
        label,
        status: link.available ? 'success' : 'offline',
        message: link.status || (link.available ? '可用' : '無法取得'),
        lastEvent: `${label.toUpperCase()}_STATUS`,
    };
}

function cpuLight(health) {
    const value = Number(health.cpu_percent);
    return {
        label: 'CPU',
        status: Number.isFinite(value) ? (value >= 90 ? 'warning' : 'success') : 'idle',
        message: Number.isFinite(value) ? `${value.toFixed(1)}%` : '無法取得',
        lastEvent: 'HEALTH.CPU',
    };
}

function ramLight(health) {
    const value = Number(health.memory_mb);
    return {
        label: 'RAM',
        status: Number.isFinite(value) ? 'success' : 'idle',
        message: Number.isFinite(value) ? `${value.toFixed(0)} MB` : '無法取得',
        lastEvent: 'HEALTH.RAM',
    };
}



function detailText(light) {
    if (!light) return '';
    const parts = [
        `狀態：${STATUS_LABELS[light.status] || light.status}`,
        light.lastEvent ? `事件：${light.lastEvent}` : '',
        Number.isFinite(Number(light.latencyMs)) ? `延遲：${Number(light.latencyMs).toFixed(0)}ms` : '',
        light.message ? `訊息：${light.message}` : '',
        light.updatedAt ? `更新：${formatTime(light.updatedAt)}` : '',
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
