(() => {
    const MAX_LOCAL_EVENTS = 180;
    const STALE_AFTER_SEC = 12;
    const OFFLINE_AFTER_SEC = 35;
    const DEFAULT_NODES = [
        { id: 'vision', label: 'Vision', status: 'idle' },
        { id: 'engine', label: 'AI Engine', status: 'idle' },
        { id: 'robot', label: 'Robot', status: 'idle' },
        { id: 'state', label: 'Game State', status: 'idle' },
        { id: 'queue', label: 'Queues', status: 'idle' },
        { id: 'socket', label: 'Socket.IO', status: 'idle' },
        { id: 'storage', label: 'Storage', status: 'idle' },
        { id: 'health', label: 'Health', status: 'idle' },
    ];
    const SIGNAL_DEFS = [
        { id: 'vision', label: 'Vision' },
        { id: 'yolo', label: 'YOLO' },
        { id: 'board', label: 'Board' },
        { id: 'engine', label: 'Pikafish' },
        { id: 'queue', label: 'Queue' },
        { id: 'socket', label: 'Socket.IO' },
        { id: 'eventbus', label: 'EventBus' },
        { id: 'robot', label: 'Robot' },
        { id: 'camera', label: 'Camera' },
        { id: 'serial', label: 'Serial' },
        { id: 'storage', label: 'Storage' },
        { id: 'cpu', label: 'CPU' },
        { id: 'memory', label: 'RAM' },
        { id: 'gpu', label: 'GPU' },
        { id: 'temperature', label: 'Temp' },
    ];
    const PIPELINE_STEPS = [
        { id: 'capture', label: 'Capture', node: 'vision' },
        { id: 'detect', label: 'Detect', node: 'vision' },
        { id: 'board', label: 'Board', node: 'state' },
        { id: 'engine', label: 'Pikafish', node: 'engine' },
        { id: 'queue', label: 'Queue', node: 'queue' },
        { id: 'robot', label: 'Robot Arm', node: 'robot' },
    ];
    const PIPELINE_LINKS = [
        { id: 'capture_detect', from: 'capture', to: 'detect', label: 'frame', edge: 'vision_engine' },
        { id: 'detect_board', from: 'detect', to: 'board', label: 'detections', edge: 'vision_engine' },
        { id: 'board_engine', from: 'board', to: 'engine', label: 'FEN', edge: 'vision_engine' },
        { id: 'engine_queue', from: 'engine', to: 'queue', label: 'move', edge: 'engine_robot' },
        { id: 'queue_robot', from: 'queue', to: 'robot', label: 'command', edge: 'queue_robot' },
    ];
    const STATUS_WEIGHT = {
        error: 7,
        blocked: 6,
        offline: 5,
        warning: 4,
        stale: 3,
        processing: 2,
        running: 2,
        active: 2,
        success: 1,
        idle: 0,
    };
    const PIECE_LABELS = {
        K: '\u5e25',
        A: '\u4ed5',
        B: '\u76f8',
        N: '\u99ac',
        R: '\u8eca',
        C: '\u70ae',
        P: '\u5175',
        k: '\u5c07',
        a: '\u58eb',
        b: '\u8c61',
        n: '\u99ac',
        r: '\u8eca',
        c: '\u7832',
        p: '\u5352',
    };

    const state = {
        connected: false,
        eventsThisSecond: 0,
        eventsPerSecond: 0,
        localEvents: [],
        filters: {
            event: 'all',
            module: 'all',
        },
        diagnostics: {
            health: {},
            queue: {},
            workers: {},
            event_bus: {},
            persistence: {},
            async_runtime: {},
            control: {},
            runtime: {},
            telemetry: { recent_events: [], errors: [], recorded_events: 0 },
            pipeline: { status: 'idle', timeline: [] },
            topology: { nodes: DEFAULT_NODES, edges: [], active_trace_id: '' },
        },
        replay: {
            sessions: [],
            steps: [],
            selectedSession: '',
            currentIndex: 0,
            snapshot: null,
            mode: 'live',
            playing: false,
            loading: false,
            error: '',
            total: 0,
        },
    };

    let dirty = true;
    let replayTimer = null;
    let replayRequestId = 0;

    const socket = typeof window.io === 'function'
        ? window.io({ timeout: 7000, reconnectionAttempts: 10, withCredentials: true })
        : null;

    const byId = (id) => document.getElementById(id);
    const setText = (id, value) => {
        const element = byId(id);
        if (element) element.textContent = String(value);
    };

    function setConnection(connected, label) {
        state.connected = Boolean(connected);
        setText('socket-status', label || (connected ? 'Connected' : 'Disconnected'));
        const dot = byId('socket-dot');
        if (dot) {
            dot.className = `dot ${connected ? 'connected' : 'error'}`;
        }
    }

    function normalizeEventEnvelope(data) {
        const type = String(data?.type || 'UNKNOWN');
        const payload = data?.payload && typeof data.payload === 'object' ? data.payload : {};
        return { type, payload, timestamp: Date.now() / 1000 };
    }

    function mergeDiagnostics(payload) {
        const next = state.diagnostics;
        if (!payload.queue && payload.queues && typeof payload.queues === 'object' && !Array.isArray(payload.queues)) {
            payload = { ...payload, queue: payload.queues };
        }
        for (const key of ['health', 'queue', 'workers', 'event_bus', 'persistence', 'async_runtime', 'control', 'runtime', 'telemetry', 'pipeline', 'topology']) {
            if (payload[key] && typeof payload[key] === 'object' && !Array.isArray(payload[key])) {
                next[key] = payload[key];
            }
        }
        if (payload.vision && typeof payload.vision === 'object') {
            next.vision = payload.vision;
        }
        if (payload.robot && typeof payload.robot === 'object') {
            next.robot = payload.robot;
        }
    }

    function appendLocalEvent(event) {
        state.localEvents.push(event);
        if (state.localEvents.length > MAX_LOCAL_EVENTS) {
            state.localEvents.shift();
        }
    }

    function onSocketEvent(data) {
        const event = normalizeEventEnvelope(data);
        state.eventsThisSecond += 1;
        appendLocalEvent(event);
        if (event.type === 'DIAGNOSTICS.UPDATED') {
            mergeDiagnostics(event.payload);
        } else if (event.type === 'ROBOT.STATUS_UPDATED') {
            state.diagnostics.robot = event.payload;
        } else if (event.type === 'VISION.FRAME_PROCESSED') {
            state.diagnostics.vision = event.payload;
        } else if (event.type === 'ENGINE.INFO_UPDATED') {
            state.diagnostics.engine = event.payload;
        }
        dirty = true;
    }

    function render() {
        dirty = false;
        renderSignals();
        renderHealth();
        renderPipelineFlow();
        renderTopology();
        renderEdges();
        renderEvents();
        renderTrace();
        renderQueues();
        renderWorkers();
        renderErrors();
        renderReplay();
    }

    function renderSignals() {
        const container = byId('signal-grid');
        if (!container) return;
        const signals = buildSignals();
        const fragment = document.createDocumentFragment();
        let issues = 0;
        let worst = 'idle';

        for (const signal of signals) {
            const status = sanitizeStatus(signal.status);
            if (STATUS_WEIGHT[status] >= STATUS_WEIGHT.warning) {
                issues += 1;
            }
            if (STATUS_WEIGHT[status] > STATUS_WEIGHT[worst]) {
                worst = status;
            }

            const card = document.createElement('div');
            card.className = `signal status-${status}`;
            card.title = signal.title || `${signal.label}: ${status}`;

            const dot = document.createElement('span');
            dot.className = 'signal-dot';
            const label = document.createElement('span');
            label.className = 'signal-label';
            label.textContent = signal.label;
            const meta = document.createElement('span');
            meta.className = 'signal-meta';
            meta.textContent = signal.meta || status;

            card.append(dot, label, meta);
            fragment.append(card);
        }

        container.replaceChildren(fragment);
        setText('signals-summary', `${signals.length - issues}/${signals.length} nominal · worst: ${worst}`);
    }

    function buildSignals() {
        const health = state.diagnostics.health || {};
        const queue = state.diagnostics.queue || {};
        const robot = state.diagnostics.robot || {};
        const vision = state.diagnostics.vision || {};
        const telemetry = state.diagnostics.telemetry || {};
        const nodeById = topologyNodeMap();
        const queueInfo = queueSummary(queue);

        return SIGNAL_DEFS.map((def) => {
            if (def.id === 'vision') {
                const node = nodeById.get('vision');
                const status = withFreshness(vision.status || node?.status || 'idle', node?.last_event_at || health.timestamp);
                return signal(def, status, `fps ${numberOrDash(vision.fps ?? health.fps)} · ${formatCamera(vision.camera)}`, node?.last_event);
            }
            if (def.id === 'yolo') {
                const detections = detectionCount(vision);
                const node = nodeById.get('vision');
                const status = detections > 0 ? 'success' : withFreshness(node?.status || 'idle', node?.last_event_at);
                return signal(def, status, `detections ${detections || '--'} · ${formatMs(vision.yolo_latency_ms || vision.latency_ms)}`, node?.last_event);
            }
            if (def.id === 'board') {
                const node = nodeById.get('state');
                const fen = vision.fen_after || vision.fen || vision.latest_fen;
                const status = fen ? 'success' : withFreshness(node?.status || 'idle', node?.last_event_at);
                return signal(def, status, fen ? 'FEN ready' : 'waiting reconstruction', node?.last_event);
            }
            if (def.id === 'engine') {
                const node = nodeById.get('engine');
                const engine = state.diagnostics.engine || {};
                const status = engine.is_thinking ? 'processing' : withFreshness(node?.status || engine.status || 'idle', node?.last_event_at);
                return signal(def, status, node?.last_event || engine.best_move || 'waiting', node?.last_event);
            }
            if (def.id === 'queue') {
                return signal(def, queueInfo.status, `${queueInfo.size} queued · ${queueInfo.blocked ? 'blocked' : 'flowing'}`, queueInfo.lastEvent);
            }
            if (def.id === 'socket') {
                return signal(def, state.connected ? 'success' : 'offline', state.connected ? 'connected' : 'disconnected');
            }
            if (def.id === 'eventbus') {
                return signal(def, telemetry.enabled === false ? 'warning' : 'running', `${telemetry.recorded_events || 0} events`);
            }
            if (def.id === 'robot') {
                const node = nodeById.get('robot');
                const status = robot.error ? 'error' : (robot.busy ? 'running' : (robot.connected || robot.is_connected ? 'success' : withFreshness(node?.status || 'offline', node?.last_event_at)));
                return signal(def, status, robot.error || robot.last_action || node?.last_event || 'idle', node?.last_event);
            }
            if (def.id === 'camera') {
                const cameraReady = vision.camera_ready ?? vision.ready ?? vision.camera?.ready;
                const status = vision.status === 'error' ? 'error' : (cameraReady === false ? 'offline' : withFreshness(vision.status || 'idle', health.timestamp));
                return signal(def, status, formatCamera(vision.camera), vision.status);
            }
            if (def.id === 'serial') {
                return linkSignal(def, robot.serial);
            }
            if (def.id === 'usb') {
                return linkSignal(def, robot.usb);
            }
            if (def.id === 'storage') {
                const node = nodeById.get('storage');
                return signal(def, withFreshness(node?.status || 'idle', node?.last_event_at), node?.last_event || node?.message || 'waiting');
            }
            if (def.id === 'cpu') {
                const value = Number(health.cpu_percent);
                return signal(def, Number.isFinite(value) ? (value >= 90 ? 'warning' : 'success') : 'idle', formatPercent(value));
            }
            if (def.id === 'memory') {
                const value = Number(health.memory_mb);
                return signal(def, Number.isFinite(value) ? 'success' : 'idle', formatMb(value));
            }
            if (def.id === 'gpu') {
                return gpuSignal(def, health.gpu);
            }
            if (def.id === 'temperature') {
                return temperatureSignal(def, health.temperature);
            }
            return signal(def, 'idle', '--');
        });
    }

    function renderPipelineFlow() {
        const container = byId('pipeline-flow');
        if (!container) return;
        const nodeById = topologyNodeMap();
        const edgeById = topologyEdgeMap();
        const fragment = document.createDocumentFragment();
        const stepStatus = new Map();
        const linkStatuses = [];

        PIPELINE_STEPS.forEach((step, index) => {
            const node = nodeById.get(step.node);
            const status = pipelineStepStatus(step, node);
            stepStatus.set(step.id, status);
            const card = document.createElement('div');
            card.className = `pipeline-node status-${status}`;
            card.title = `${step.label}: ${status} | ${pipelineStepMeta(step, node)}`;

            const title = document.createElement('div');
            title.className = 'pipeline-node-title';
            title.append(textSpan(step.label), textSpan(status, `pill ${status}`));

            const meta = document.createElement('div');
            meta.className = 'pipeline-node-meta';
            meta.textContent = pipelineStepMeta(step, node);

            const sub = document.createElement('div');
            sub.className = 'pipeline-node-sub';
            sub.textContent = pipelineNodeSubtext(step, node);

            card.append(title, meta, sub);
            fragment.append(card);

            if (index < PIPELINE_STEPS.length - 1) {
                const linkDef = PIPELINE_LINKS[index];
                const edge = edgeById.get(linkDef.edge);
                const linkStatus = pipelineLinkStatus(
                    linkDef,
                    edge,
                    stepStatus.get(linkDef.from),
                    pipelineStepStatus(PIPELINE_STEPS[index + 1], nodeById.get(PIPELINE_STEPS[index + 1].node)),
                );
                linkStatuses.push(linkStatus);
                const link = renderPipelineLink(linkDef, edge, linkStatus);
                fragment.append(link);
            }
        });

        container.replaceChildren(fragment);
        const pipeline = state.diagnostics.pipeline || {};
        const pathStatus = worstStatus([...stepStatus.values(), ...linkStatuses]);
        setText('pipeline-message', `trace ${pipeline.active_trace_id || '--'} · ${formatMs(pipeline.total_latency_ms)} · path ${pathStatus}`);
    }

    function renderHealth() {
        const health = state.diagnostics.health || {};
        const queue = state.diagnostics.queue || {};
        const robot = state.diagnostics.robot || {};
        const vision = state.diagnostics.vision || {};
        const pipeline = state.diagnostics.pipeline || {};
        const topology = state.diagnostics.topology || {};
        const queued = Object.values(queue).reduce((sum, item) => {
            if (!item || typeof item !== 'object') return sum;
            return sum + Number(item.size || 0);
        }, 0);

        setText('metric-cpu', formatPercent(health.cpu_percent));
        setText('metric-memory', formatMb(health.memory_mb));
        setText('metric-threads', numberOrDash(health.threads));
        setText('metric-gpu', formatGpu(health.gpu));
        setText('metric-temp', formatTemp(health.temperature));
        setText('metric-fps', numberOrDash(vision.fps ?? health.fps));
        setText('metric-latency', formatMs(pipeline.total_latency_ms));

        const telemetry = state.diagnostics.telemetry || {};
        setText('metric-error-rate', telemetry.error_rate !== undefined ? formatPercent(telemetry.error_rate) : '--');
        setText('metric-p95-latency', telemetry.p95_latency_ms !== undefined ? formatMs(telemetry.p95_latency_ms) : '--');

        setText('metric-robot', formatRobot(robot));
        setText('metric-serial', formatLink(robot.serial));
        setText('metric-usb', formatLink(robot.usb));
        setText('metric-events', state.eventsPerSecond);
        setText('metric-queue', queued);
        setText('active-trace', `trace: ${topology.active_trace_id || pipeline.active_trace_id || '--'}`);

        const pill = byId('pipeline-status');
        if (pill) {
            const status = sanitizeStatus(pipeline.status || 'idle');
            pill.textContent = status;
            pill.className = `pill ${status}`;
        }
    }

    function renderTopology() {
        const container = byId('topology-nodes');
        if (!container) return;
        const topology = state.diagnostics.topology || {};
        const nodes = Array.isArray(topology.nodes) && topology.nodes.length ? topology.nodes : DEFAULT_NODES;
        const fragment = document.createDocumentFragment();

        for (const node of nodes) {
            const status = withFreshness(node.status, node.last_event_at || node.updated_at);
            const card = document.createElement('div');
            card.className = `node status-${status}`;

            const title = document.createElement('div');
            title.className = 'node-title';

            const label = document.createElement('span');
            label.textContent = node.label || node.id || 'Node';

            const pill = document.createElement('span');
            pill.className = `pill ${status}`;
            pill.textContent = status;

            title.append(label, pill);

            const meta = document.createElement('div');
            meta.className = 'node-meta';
            const event = node.last_event || 'no event';
            const latency = node.latency_ms === null || node.latency_ms === undefined
                ? ''
                : ` | ${formatMs(node.latency_ms)}`;
            meta.textContent = `${event}${latency} · ${formatAge(node.last_event_at || node.updated_at)}`;

            const msg = document.createElement('div');
            msg.className = 'node-meta';
            msg.textContent = node.message || '';

            card.append(title, meta, msg);
            fragment.append(card);
        }

        container.replaceChildren(fragment);
    }

    function renderEdges() {
        const container = byId('edge-list');
        if (!container) return;
        const topology = state.diagnostics.topology || {};
        const edges = Array.isArray(topology.edges) ? topology.edges : [];
        const fragment = document.createDocumentFragment();

        if (!edges.length) {
            fragment.append(emptyLine('Waiting for topology data'));
            container.replaceChildren(fragment);
            return;
        }

        for (const edge of edges) {
            const status = withFreshness(edge.status, edge.last_event_at);
            const latency = formatMs(edge.latency_ms);
            const row = document.createElement('div');
            row.className = 'edge-item';
            row.append(
                textSpan(`${edge.source || '?'} -> ${edge.target || '?'}`, 'mono'),
                textSpan(`${edge.label || edge.last_event || '--'}${latency === '--' ? '' : ` / ${latency}`}`),
                textSpan(status, `pill ${status}`),
            );
            fragment.append(row);
        }
        container.replaceChildren(fragment);
    }

    function renderEvents() {
        const body = byId('event-table');
        if (!body) return;
        const telemetry = state.diagnostics.telemetry || {};
        const backendEvents = Array.isArray(telemetry.recent_events) ? telemetry.recent_events : [];
        const events = backendEvents.length
            ? backendEvents.slice(-120).reverse()
            : state.localEvents.slice(-80).reverse().map((event) => ({
                timestamp: event.timestamp,
                source: 'socket',
                trace_id: '',
                module: 'socket',
                event_type: event.type,
                status: 'processing',
                latency_ms: null,
            }));
        const filteredEvents = filterEvents(events);
        const fragment = document.createDocumentFragment();

        if (!filteredEvents.length) {
            const row = document.createElement('tr');
            const cell = tableCell('No telemetry matches current filters', 'muted');
            cell.colSpan = 7;
            row.append(cell);
            fragment.append(row);
        }

        for (const event of filteredEvents) {
            const row = document.createElement('tr');
            row.append(
                tableCell(formatTime(event.timestamp), 'mono muted'),
                tableCell(event.source || '--', 'mono'),
                tableCell(shortTrace(event.trace_id), 'mono muted'),
                tableCell(event.module || '--'),
                tableCell(event.event_type || event.type || 'UNKNOWN', 'mono'),
                tableCell(sanitizeStatus(event.status), `pill ${sanitizeStatus(event.status)}`),
                tableCell(formatMs(event.latency_ms)),
            );
            fragment.append(row);
        }
        body.replaceChildren(fragment);
        setText('telemetry-count', `${filteredEvents.length}/${telemetry.recorded_events || events.length || 0} shown`);
    }

    function renderTrace() {
        const container = byId('trace-timeline');
        if (!container) return;
        const pipeline = state.diagnostics.pipeline || {};
        const timeline = Array.isArray(pipeline.timeline) ? pipeline.timeline : [];
        const fragment = document.createDocumentFragment();

        if (!timeline.length) {
            fragment.append(emptyLine('No active trace yet'));
            container.replaceChildren(fragment);
            return;
        }

        for (const event of timeline.slice(-24)) {
            const status = withFreshness(event.status, event.timestamp);
            const row = document.createElement('div');
            row.className = 'timeline-item';
            row.append(
                textSpan(formatTime(event.timestamp), 'mono muted'),
                textSpan(`${event.module || '--'} / ${event.event_type || 'UNKNOWN'}`, 'mono'),
                textSpan(status, `pill ${status}`),
            );
            fragment.append(row);
        }
        container.replaceChildren(fragment);
    }

    function renderQueues() {
        const body = byId('queue-table');
        if (!body) return;
        const queue = state.diagnostics.queue || {};
        const fragment = document.createDocumentFragment();
        const entries = Object.entries(queue).filter(([, value]) => value && typeof value === 'object');

        if (!entries.length) {
            const row = document.createElement('tr');
            row.append(tableCell('No queue data'), tableCell('--'), tableCell('--'), tableCell('--'), tableCell('--'), tableCell('--'), tableCell('--'), tableCell('--'));
            fragment.append(row);
            body.replaceChildren(fragment);
            return;
        }

        for (const [name, info] of entries) {
            const row = document.createElement('tr');
            row.append(
                tableCell(name, 'mono'),
                tableCell(numberOrDash(info.size)),
                tableCell(numberOrDash(info.maxsize)),
                tableCell(formatBool(info.full)),
                tableCell(formatBool(info.blocked), info.blocked ? 'pill blocked' : ''),
                tableCell(info.policy || '--'),
                tableCell(numberOrDash(info.dropped_oldest)),
                tableCell(formatSec(info.age_sec)),
            );
            fragment.append(row);
        }
        body.replaceChildren(fragment);
    }

    function renderWorkers() {
        const body = byId('worker-table');
        if (!body) return;
        const workers = state.diagnostics.workers || {};
        const entries = Object.entries(workers).filter(([, value]) => value && typeof value === 'object');
        const fragment = document.createDocumentFragment();

        if (!entries.length) {
            const row = document.createElement('tr');
            row.append(tableCell('No worker data'), tableCell('--'), tableCell('--'), tableCell('--'));
            fragment.append(row);
            body.replaceChildren(fragment);
            return;
        }

        for (const [name, info] of entries) {
            const status = sanitizeStatus(info.status || (info.is_running ? 'running' : 'idle'));
            const row = document.createElement('tr');
            row.append(
                tableCell(name, 'mono'),
                tableCell(status, `pill ${status}`),
                tableCell(formatBool(info.is_running)),
                tableCell(info.last_error || '--'),
            );
            fragment.append(row);
        }
        body.replaceChildren(fragment);
    }

    function renderErrors() {
        const container = byId('error-list');
        if (!container) return;
        const telemetry = state.diagnostics.telemetry || {};
        const errors = Array.isArray(telemetry.errors) ? telemetry.errors.slice(-30).reverse() : [];
        const queue = state.diagnostics.queue || {};
        const robot = state.diagnostics.robot || {};
        const synthetic = [];

        for (const [name, info] of Object.entries(queue)) {
            if (!info || typeof info !== 'object') continue;
            if (info.blocked) {
                synthetic.push({
                    timestamp: Date.now() / 1000,
                    module: 'queue',
                    event_type: 'QUEUE_BLOCKED',
                    message: `${name} queue blocked (${info.size || 0}/${info.maxsize || 0})`,
                    severity: 'warning',
                });
            }
        }
        if (robot.error) {
            synthetic.push({
                timestamp: Date.now() / 1000,
                module: 'robot',
                event_type: 'ROBOT_ERROR',
                message: robot.error,
                severity: 'error',
            });
        }

        const visibleErrors = [...synthetic, ...errors];
        const fragment = document.createDocumentFragment();

        if (!visibleErrors.length) {
            fragment.append(emptyLine('No errors reported'));
            container.replaceChildren(fragment);
            return;
        }

        for (const error of visibleErrors) {
            const row = document.createElement('div');
            row.className = 'error-item';
            row.append(
                textSpan(formatTime(error.timestamp), 'mono muted'),
                textSpan(`${error.module || '--'} / ${error.event_type || 'UNKNOWN'} / ${error.message || ''}`),
                textSpan(error.severity || 'error', `pill ${error.severity || 'error'}`),
            );
            fragment.append(row);
        }
        container.replaceChildren(fragment);
    }

    function renderReplay() {
        renderReplaySessions();
        renderReplayControls();
        renderReplayMeta();
        renderReplayBoard();
        renderReplayStepList();
    }

    function renderReplaySessions() {
        const select = byId('replay-session');
        if (!select) return;
        const replay = state.replay;
        const signature = replay.sessions
            .map((session) => `${session.id || ''}:${session.event_count || 0}:${session.last_timestamp || ''}`)
            .join('|');
        if (select.dataset.signature === signature && select.value === replay.selectedSession) return;

        const fragment = document.createDocumentFragment();
        if (!replay.sessions.length) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = replay.loading ? 'Loading sessions' : 'No replay sessions';
            fragment.append(option);
        } else {
            for (const session of replay.sessions) {
                const option = document.createElement('option');
                option.value = session.id || '';
                option.textContent = `${session.label || session.id || 'Unassigned'} (${session.event_count || 0})`;
                fragment.append(option);
            }
        }
        select.replaceChildren(fragment);
        select.value = replay.selectedSession || '';
        select.dataset.signature = signature;
    }

    function renderReplayControls() {
        const replay = state.replay;
        const hasSteps = replay.steps.length > 0;
        const isReplay = replay.mode === 'replay';
        const status = replayStatus();
        const statusPill = byId('replay-status');
        if (statusPill) {
            statusPill.textContent = status.label;
            statusPill.className = `pill ${status.status}`;
        }

        const live = byId('replay-live');
        if (live) live.classList.toggle('active', !isReplay);
        const play = byId('replay-play');
        if (play) play.textContent = replay.playing ? 'Pause' : 'Play';

        setDisabled('replay-load', replay.loading || !replay.sessions.length);
        setDisabled('replay-export', replay.loading || !hasSteps);
        setDisabled('replay-prev', replay.loading || !hasSteps || replay.currentIndex <= 0);
        setDisabled('replay-next', replay.loading || !hasSteps || replay.currentIndex >= replay.steps.length - 1);
        setDisabled('replay-play', replay.loading || !hasSteps);

        const slider = byId('replay-slider');
        if (slider) {
            slider.max = String(Math.max(0, replay.steps.length - 1));
            slider.value = String(Math.max(0, Math.min(replay.currentIndex, replay.steps.length - 1)));
            slider.disabled = replay.loading || !hasSteps;
        }
    }

    function renderReplayMeta() {
        const replay = state.replay;
        const step = replay.steps[replay.currentIndex] || {};
        const snapshot = replay.snapshot || {};
        const meta = snapshot._replay || {};
        const fen = replayFen(snapshot, step);
        const stepLabel = replay.steps.length
            ? `${replay.currentIndex + 1}/${replay.total || replay.steps.length}`
            : '--';
        const move = step.move || snapshot?.board?.last_move || snapshot?.game?.move_history?.slice?.(-1)?.[0] || '--';
        const trace = meta.trace_id || step.trace_id || '--';
        const timestamp = meta.timestamp || step.timestamp;

        setText('replay-step-label', stepLabel);
        setText('replay-move-label', move || '--');
        setText('replay-time-label', formatTime(timestamp));
        setText('replay-trace-label', shortTrace(trace));
        setText('replay-fen', fen || (replay.error || 'No replay loaded'));
    }

    function renderReplayBoard() {
        const board = byId('replay-board');
        if (!board) return;
        const replay = state.replay;
        const step = replay.steps[replay.currentIndex] || {};
        const fen = replayFen(replay.snapshot || {}, step);
        const rows = parseFenBoard(fen);
        const signature = rows ? rows.map((row) => row.join('')).join('/') : 'empty';
        if (board.dataset.signature === signature) return;

        const fragment = document.createDocumentFragment();
        for (let row = 0; row < 10; row += 1) {
            for (let col = 0; col < 9; col += 1) {
                const cell = document.createElement('div');
                cell.className = 'replay-cell';
                cell.title = `${String.fromCharCode(97 + col)}${9 - row}`;
                const piece = rows?.[row]?.[col];
                if (piece) {
                    const marker = document.createElement('span');
                    marker.className = `replay-piece ${piece === piece.toUpperCase() ? 'red' : 'black'}`;
                    marker.textContent = PIECE_LABELS[piece] || piece;
                    cell.append(marker);
                }
                fragment.append(cell);
            }
        }
        board.replaceChildren(fragment);
        board.dataset.signature = signature;
    }

    function renderReplayStepList() {
        const container = byId('replay-step-list');
        if (!container) return;
        const replay = state.replay;
        const signature = `${replay.steps.length}:${replay.currentIndex}:${replay.steps[0]?.sequence_id || ''}:${replay.steps.at?.(-1)?.sequence_id || ''}`;
        if (container.dataset.signature === signature) return;

        const fragment = document.createDocumentFragment();
        if (!replay.steps.length) {
            fragment.append(emptyLine(replay.loading ? 'Loading replay steps' : 'No replay steps loaded'));
            container.replaceChildren(fragment);
            container.dataset.signature = signature;
            return;
        }

        replay.steps.forEach((step, index) => {
            const row = document.createElement('button');
            row.type = 'button';
            row.className = `replay-step-row ${index === replay.currentIndex ? 'active' : ''}`;
            row.dataset.index = String(index);
            row.append(
                textSpan(`#${index + 1}`, 'mono'),
                textSpan(formatTime(step.timestamp), 'mono muted'),
                textSpan(step.move || step.type || '--', 'mono'),
                textSpan(shortTrace(step.trace_id), 'mono muted'),
            );
            row.addEventListener('click', () => loadReplayStep(index));
            fragment.append(row);
        });
        container.replaceChildren(fragment);
        container.dataset.signature = signature;
    }

    function replayStatus() {
        const replay = state.replay;
        if (replay.error) return { status: 'error', label: 'error' };
        if (replay.loading) return { status: 'processing', label: 'loading' };
        if (replay.playing) return { status: 'running', label: 'playing' };
        if (replay.mode === 'replay' && replay.steps.length) return { status: 'active', label: 'replay' };
        if (replay.sessions.length) return { status: 'success', label: 'ready' };
        return { status: 'idle', label: 'idle' };
    }

    function replayFen(snapshot, step) {
        if (state.replay.mode === 'live') {
            return liveFen() || step?.fen || '';
        }
        return snapshot?.board?.fen || snapshot?.game?.fen || snapshot?.fen || step?.fen || '';
    }

    function liveFen() {
        const vision = state.diagnostics.vision || {};
        return vision.fen_after || vision.fen || vision.latest_fen || '';
    }

    function parseFenBoard(fen) {
        const boardPart = String(fen || '').trim().split(/\s+/)[0];
        const fenRows = boardPart ? boardPart.split('/') : [];
        if (fenRows.length !== 10) return null;
        const rows = [];
        for (const fenRow of fenRows) {
            const row = [];
            for (const char of fenRow) {
                if (/\d/.test(char)) {
                    const count = Number(char);
                    for (let i = 0; i < count; i += 1) row.push('');
                } else {
                    row.push(char);
                }
            }
            if (row.length !== 9) return null;
            rows.push(row);
        }
        return rows;
    }

    function setDisabled(id, disabled) {
        const element = byId(id);
        if (element) element.disabled = Boolean(disabled);
    }

    function topologyNodeMap() {
        const topology = state.diagnostics.topology || {};
        const nodes = Array.isArray(topology.nodes) && topology.nodes.length ? topology.nodes : DEFAULT_NODES;
        return new Map(nodes.map((node) => [node.id, node]));
    }

    function topologyEdgeMap() {
        const topology = state.diagnostics.topology || {};
        const edges = Array.isArray(topology.edges) ? topology.edges : [];
        return new Map(edges.map((edge) => [edge.id, edge]));
    }

    function signal(def, status, meta, event) {
        const cleanStatus = sanitizeStatus(status);
        const detail = event ? `${event} · ${meta || cleanStatus}` : (meta || cleanStatus);
        return {
            id: def.id,
            label: def.label,
            status: cleanStatus,
            meta: detail,
            title: `${def.label}: ${cleanStatus} | ${detail}`,
        };
    }

    function linkSignal(def, link) {
        if (!link || typeof link !== 'object') {
            return signal(def, 'offline', 'unavailable');
        }
        const raw = String(link.status || '').toLowerCase();
        if (raw.includes('error') || raw.includes('fault')) {
            return signal(def, 'error', link.status);
        }
        if (link.available === false || raw.includes('offline') || raw.includes('disconnect') || raw.includes('unavailable')) {
            return signal(def, 'offline', link.status || 'unavailable');
        }
        return signal(def, link.available ? 'success' : 'idle', link.status || 'available');
    }

    function gpuSignal(def, gpu) {
        if (!gpu || gpu.available === false) {
            return signal(def, 'offline', gpu?.reason || 'unavailable');
        }
        const load = Number(gpu.load_percent);
        return signal(def, Number.isFinite(load) && load >= 90 ? 'warning' : 'success', `${gpu.name || 'GPU'} ${formatPercent(load)}`);
    }

    function temperatureSignal(def, temp) {
        if (!temp || temp.available === false) {
            return signal(def, 'offline', temp?.reason || 'unavailable');
        }
        const value = Number(temp.max_c);
        return signal(def, Number.isFinite(value) && value >= 80 ? 'warning' : 'success', Number.isFinite(value) ? `${value.toFixed(1)} C` : 'available');
    }

    function queueSummary(queue) {
        const entries = Object.values(queue || {}).filter((item) => item && typeof item === 'object');
        const size = entries.reduce((sum, item) => sum + Number(item.size || 0), 0);
        const full = entries.some((item) => Boolean(item.full));
        const blocked = entries.some((item) => Boolean(item.blocked));
        const dropped = entries.reduce((sum, item) => sum + Number(item.dropped_oldest || 0), 0);
        return {
            size,
            blocked,
            dropped,
            status: blocked ? 'blocked' : (full || dropped ? 'warning' : (size > 0 ? 'processing' : 'success')),
            lastEvent: blocked ? 'QUEUE_BLOCKED' : '',
        };
    }

    function pipelineStepStatus(step, node) {
        if (step.id === 'detect') {
            return detectionCount(state.diagnostics.vision || {}) > 0
                ? 'success'
                : withFreshness(node?.status || 'idle', node?.last_event_at);
        }
        if (step.id === 'board') {
            const vision = state.diagnostics.vision || {};
            return vision.fen_after || vision.fen || vision.latest_fen
                ? 'success'
                : withFreshness(node?.status || 'idle', node?.last_event_at);
        }
        if (step.id === 'queue') {
            return queueSummary(state.diagnostics.queue || {}).status;
        }
        if (step.id === 'robot') {
            const robot = state.diagnostics.robot || {};
            if (robot.error) return 'error';
            if (robot.busy) return 'running';
        }
        return withFreshness(node?.status || 'idle', node?.last_event_at || node?.updated_at);
    }

    function pipelineStepMeta(step, node) {
        const vision = state.diagnostics.vision || {};
        if (step.id === 'capture') return `fps ${numberOrDash(vision.fps)} · ${formatCamera(vision.camera)}`;
        if (step.id === 'detect') return `detections ${detectionCount(vision) || '--'} · ${formatMs(vision.yolo_latency_ms || vision.latency_ms)}`;
        if (step.id === 'board') return vision.fen_after || vision.fen || vision.latest_fen || node?.last_event || 'waiting';
        if (step.id === 'queue') {
            const queue = queueSummary(state.diagnostics.queue || {});
            return `${queue.size} queued · ${queue.dropped} dropped`;
        }
        if (step.id === 'robot') {
            const robot = state.diagnostics.robot || {};
            return robot.error || robot.last_action || node?.last_event || formatRobot(robot);
        }
        return node?.last_event || node?.message || 'waiting';
    }

    function pipelineNodeSubtext(step, node) {
        if (step.id === 'capture') return formatAge((state.diagnostics.health || {}).timestamp || node?.last_event_at);
        if (step.id === 'detect') return node?.last_event || 'vision detector';
        if (step.id === 'queue') {
            const summary = queueSummary(state.diagnostics.queue || {});
            return summary.blocked ? 'blocked path' : 'queue path';
        }
        if (step.id === 'robot') {
            const robot = state.diagnostics.robot || {};
            return robot.connected || robot.is_connected ? 'hardware online' : 'hardware offline';
        }
        return formatAge(node?.last_event_at || node?.updated_at);
    }

    function renderPipelineLink(linkDef, edge, status) {
        const link = document.createElement('div');
        link.className = `pipeline-edge status-${status}`;
        link.title = `${linkDef.from} -> ${linkDef.to}: ${status}${edge?.last_event ? ` | ${edge.last_event}` : ''}`;

        const line = document.createElement('div');
        line.className = 'pipeline-edge-line';
        const label = document.createElement('div');
        label.className = 'pipeline-edge-label';
        const latency = formatMs(edge?.latency_ms);
        label.textContent = `${linkDef.label}${latency === '--' ? '' : ` · ${latency}`}`;

        link.append(line, label);
        return link;
    }

    function pipelineLinkStatus(linkDef, edge, sourceStatus, targetStatus) {
        const queue = queueSummary(state.diagnostics.queue || {});
        const robot = state.diagnostics.robot || {};
        const edgeStatus = withFreshness(edge?.status || 'idle', edge?.last_event_at);
        const candidates = [edgeStatus, sourceStatus, targetStatus];

        if (queue.blocked && (linkDef.from === 'queue' || linkDef.to === 'queue' || linkDef.to === 'robot')) {
            candidates.push('blocked');
        }
        if (robot.error && (linkDef.from === 'queue' || linkDef.to === 'robot')) {
            candidates.push('error');
        }

        return worstStatus(candidates);
    }

    function worstStatus(statuses) {
        return statuses
            .map((status) => sanitizeStatus(status))
            .reduce((worst, status) => (
                STATUS_WEIGHT[status] > STATUS_WEIGHT[worst] ? status : worst
            ), 'idle');
    }

    function detectionCount(vision) {
        if (Number.isFinite(Number(vision.detections_count))) return Number(vision.detections_count);
        if (Array.isArray(vision.detections)) return vision.detections.length;
        if (Array.isArray(vision.boxes)) return vision.boxes.length;
        return 0;
    }

    function withFreshness(value, lastUpdated) {
        const status = sanitizeStatus(value);
        if (['error', 'blocked', 'offline'].includes(status)) return status;
        const age = ageSeconds(lastUpdated);
        if (!Number.isFinite(age)) return status;
        if (age > OFFLINE_AFTER_SEC) return 'offline';
        if (age > STALE_AFTER_SEC) return 'stale';
        return status;
    }

    function ageSeconds(value) {
        const timestamp = timestampSeconds(value);
        if (!Number.isFinite(timestamp) || timestamp <= 0) return NaN;
        return Date.now() / 1000 - timestamp;
    }

    function timestampSeconds(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric) || numeric <= 0) return NaN;
        return numeric > 100000000000 ? numeric / 1000 : numeric;
    }

    function formatAge(value) {
        const age = ageSeconds(value);
        if (!Number.isFinite(age)) return 'no timestamp';
        if (age < 1) return 'fresh';
        if (age < 60) return `${age.toFixed(0)}s ago`;
        return `${Math.floor(age / 60)}m ago`;
    }

    function formatCamera(camera) {
        if (camera === undefined || camera === null || camera === '') return 'camera --';
        if (typeof camera === 'object') {
            return camera.status || camera.name || camera.id || camera.index || (camera.available === false ? 'unavailable' : 'camera');
        }
        return `camera ${camera}`;
    }

    function filterEvents(events) {
        const activeTrace = (state.diagnostics.pipeline || {}).active_trace_id || (state.diagnostics.telemetry || {}).active_trace_id || '';
        return events.filter((event) => {
            const moduleName = String(event.module || '').toLowerCase();
            const status = sanitizeStatus(event.status);
            const eventType = String(event.event_type || event.type || '').toUpperCase();
            if (state.filters.module !== 'all' && moduleName !== state.filters.module) return false;
            if (state.filters.event === 'errors') {
                return ['error', 'blocked', 'warning'].includes(status)
                    || ['ERROR', 'EXCEPTION', 'TIMEOUT', 'BLOCKED', 'FAILED'].some((token) => eventType.includes(token));
            }
            if (state.filters.event === 'active-trace') {
                return activeTrace && event.trace_id === activeTrace;
            }
            return true;
        });
    }

    function tableCell(value, className) {
        const cell = document.createElement('td');
        cell.textContent = value === undefined || value === null || value === '' ? '--' : String(value);
        if (className) cell.className = className;
        return cell;
    }

    function textSpan(value, className) {
        const span = document.createElement('span');
        span.textContent = value === undefined || value === null || value === '' ? '--' : String(value);
        if (className) span.className = className;
        return span;
    }

    function emptyLine(text) {
        const item = document.createElement('div');
        item.className = 'timeline-item';
        item.append(textSpan(text, 'muted'));
        return item;
    }

    function sanitizeStatus(value) {
        const aliases = {
            enabled: 'running',
            busy: 'running',
            active: 'active',
            stopped: 'offline',
            disabled: 'offline',
            disconnected: 'offline',
            connected: 'success',
            ready: 'success',
            failed: 'error',
            degraded: 'warning',
            stale: 'stale',
        };
        const raw = String(value || 'idle').toLowerCase();
        const status = aliases[raw] || raw;
        return ['idle', 'active', 'running', 'processing', 'success', 'warning', 'stale', 'blocked', 'offline', 'error'].includes(status)
            ? status
            : 'idle';
    }

    function shortTrace(value) {
        const text = String(value || '');
        if (!text) return '--';
        return text.length > 10 ? `${text.slice(0, 8)}...` : text;
    }

    function formatTime(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric) || numeric <= 0) return '--';
        const millis = numeric < 100000000000 ? numeric * 1000 : numeric;
        return new Date(millis).toLocaleTimeString([], { hour12: false });
    }

    function formatPercent(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? `${numeric.toFixed(1)}%` : '--';
    }

    function formatMb(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? `${numeric.toFixed(0)} MB` : '--';
    }

    function formatMs(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? `${numeric.toFixed(0)} ms` : '--';
    }

    function formatSec(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) && numeric > 0 ? `${numeric.toFixed(1)}s` : '--';
    }

    function numberOrDash(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? String(Math.round(numeric)) : '--';
    }

    function formatBool(value) {
        return value === undefined || value === null ? '--' : (value ? 'yes' : 'no');
    }

    function formatGpu(gpu) {
        if (!gpu || gpu.available === false) return 'N/A';
        if (Number.isFinite(Number(gpu.load_percent))) return `${Number(gpu.load_percent).toFixed(0)}%`;
        return gpu.name || 'GPU';
    }

    function formatTemp(temp) {
        if (!temp || temp.available === false) return 'N/A';
        if (Number.isFinite(Number(temp.max_c))) return `${Number(temp.max_c).toFixed(1)} C`;
        return 'N/A';
    }

    function formatRobot(robot) {
        if (!robot || !Object.keys(robot).length) return '--';
        if (robot.error) return 'Error';
        return robot.connected || robot.is_connected ? 'Connected' : 'Offline';
    }

    function formatLink(link) {
        if (!link || typeof link !== 'object') return '--';
        if (link.status) return String(link.status);
        return link.available ? 'available' : 'unavailable';
    }

    function authHeaders() {
        const headers = new Headers();
        try {
            const token = window.sessionStorage?.getItem('adminToken');
            if (token) headers.set('Authorization', `Bearer ${token}`);
        } catch {
            // Dashboard can also rely on same-origin cookie sessions.
        }
        return headers;
    }

    async function replayJson(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: options.headers || authHeaders(),
            credentials: 'same-origin',
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
            throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
        }
        return payload;
    }

    function replaySessionQuery() {
        const params = new URLSearchParams();
        if (state.replay.selectedSession) params.set('session', state.replay.selectedSession);
        return params;
    }

    async function loadReplaySessions() {
        state.replay.loading = true;
        state.replay.error = '';
        dirty = true;
        try {
            const payload = await replayJson('/api/replay/sessions?limit=80');
            state.replay.sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
            if (!state.replay.selectedSession && state.replay.sessions.length) {
                state.replay.selectedSession = state.replay.sessions[0].id || '';
            }
            state.replay.loading = false;
            dirty = true;
            if (state.replay.sessions.length) {
                await loadReplaySteps();
            } else {
                state.replay.steps = [];
                state.replay.snapshot = null;
                state.replay.total = 0;
            }
        } catch (error) {
            state.replay.loading = false;
            state.replay.error = error?.message || 'replay_sessions_failed';
            dirty = true;
        }
    }

    async function loadReplaySteps() {
        stopReplayPlayback();
        state.replay.loading = true;
        state.replay.error = '';
        state.replay.mode = 'replay';
        dirty = true;
        try {
            const params = replaySessionQuery();
            params.set('limit', '2000');
            const payload = await replayJson(`/api/replay/steps?${params.toString()}`);
            state.replay.steps = Array.isArray(payload.steps) ? payload.steps : [];
            state.replay.total = Number(payload.total || state.replay.steps.length || 0);
            state.replay.currentIndex = 0;
            state.replay.snapshot = null;
            state.replay.loading = false;
            dirty = true;
            if (state.replay.steps.length) {
                await loadReplayStep(0);
            }
        } catch (error) {
            state.replay.loading = false;
            state.replay.error = error?.message || 'replay_steps_failed';
            dirty = true;
        }
    }

    async function loadReplayStep(index) {
        const replay = state.replay;
        if (!replay.steps.length) return;
        const nextIndex = Math.max(0, Math.min(Number(index) || 0, replay.steps.length - 1));
        replay.currentIndex = nextIndex;
        replay.mode = 'replay';
        replay.error = '';
        const requestId = ++replayRequestId;
        dirty = true;
        try {
            const params = replaySessionQuery();
            params.set('window', '5000');
            const payload = await replayJson(`/api/replay/step/${nextIndex}?${params.toString()}`);
            if (requestId !== replayRequestId) return;
            replay.snapshot = payload;
            replay.error = '';
            dirty = true;
        } catch (error) {
            if (requestId !== replayRequestId) return;
            replay.error = error?.message || 'replay_step_failed';
            dirty = true;
        }
    }

    function stopReplayPlayback() {
        if (replayTimer) {
            clearInterval(replayTimer);
            replayTimer = null;
        }
        state.replay.playing = false;
    }

    function startReplayPlayback() {
        if (!state.replay.steps.length) return;
        stopReplayPlayback();
        state.replay.playing = true;
        state.replay.mode = 'replay';
        const speed = Math.max(0.25, Number(byId('replay-speed')?.value || 1));
        replayTimer = setInterval(() => {
            const next = state.replay.currentIndex + 1;
            if (next >= state.replay.steps.length) {
                stopReplayPlayback();
                dirty = true;
                return;
            }
            loadReplayStep(next);
        }, Math.max(120, Math.round(1000 / speed)));
        dirty = true;
    }

    function switchReplayLive() {
        stopReplayPlayback();
        state.replay.mode = 'live';
        state.replay.snapshot = null;
        state.replay.error = '';
        dirty = true;
    }

    async function exportReplay() {
        if (!state.replay.steps.length) return;
        state.replay.error = '';
        dirty = true;
        try {
            const params = replaySessionQuery();
            params.set('limit', '20000');
            const response = await fetch(`/api/replay/export?${params.toString()}`, {
                headers: authHeaders(),
                credentials: 'same-origin',
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            const suffix = state.replay.selectedSession || 'all';
            anchor.href = url;
            anchor.download = `replay-${suffix}.json`;
            document.body.append(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            state.replay.error = error?.message || 'replay_export_failed';
        } finally {
            dirty = true;
        }
    }

    function bindReplayControls() {
        byId('replay-refresh')?.addEventListener('click', () => loadReplaySessions());
        byId('replay-load')?.addEventListener('click', () => loadReplaySteps());
        byId('replay-live')?.addEventListener('click', switchReplayLive);
        byId('replay-export')?.addEventListener('click', exportReplay);
        byId('replay-prev')?.addEventListener('click', () => loadReplayStep(state.replay.currentIndex - 1));
        byId('replay-next')?.addEventListener('click', () => loadReplayStep(state.replay.currentIndex + 1));
        byId('replay-play')?.addEventListener('click', () => {
            if (state.replay.playing) {
                stopReplayPlayback();
                dirty = true;
            } else {
                startReplayPlayback();
            }
        });
        byId('replay-speed')?.addEventListener('change', () => {
            if (state.replay.playing) startReplayPlayback();
        });
        byId('replay-session')?.addEventListener('change', (event) => {
            state.replay.selectedSession = event.target.value || '';
            loadReplaySteps();
        });
        const slider = byId('replay-slider');
        slider?.addEventListener('input', () => {
            state.replay.currentIndex = Number(slider.value || 0);
            state.replay.snapshot = null;
            dirty = true;
        });
        slider?.addEventListener('change', () => loadReplayStep(Number(slider.value || 0)));
    }

    function bindTelemetryFilters() {
        document.querySelectorAll('[data-event-filter]').forEach((button) => {
            button.addEventListener('click', () => {
                state.filters.event = button.dataset.eventFilter || 'all';
                document.querySelectorAll('[data-event-filter]').forEach((item) => {
                    item.classList.toggle('active', item === button);
                });
                dirty = true;
            });
        });
        const moduleFilter = byId('module-filter');
        moduleFilter?.addEventListener('change', () => {
            state.filters.module = moduleFilter.value || 'all';
            dirty = true;
        });
    }

    socket?.on?.('connect', () => {
        setConnection(true, 'Connected');
        dirty = true;
    });

    socket?.on?.('disconnect', () => {
        setConnection(false, 'Disconnected');
        dirty = true;
    });

    socket?.on?.('connect_error', () => {
        setConnection(false, 'Connection error');
        dirty = true;
    });

    socket?.on?.('SYSTEM_STATE_UPDATE', onSocketEvent);

    setInterval(() => {
        state.eventsPerSecond = state.eventsThisSecond;
        state.eventsThisSecond = 0;
        dirty = true;
    }, 1000);

    setInterval(() => {
        if (dirty) render();
    }, 500);

    bindTelemetryFilters();
    bindReplayControls();
    loadReplaySessions();
    setConnection(false, socket ? 'Connecting' : 'Socket.IO unavailable');
    render();
})();
