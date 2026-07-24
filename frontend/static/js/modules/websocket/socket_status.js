const STATUS_LABELS = {
    online: 'Socket 已連線',
    warning: 'Socket 重新連線中',
    offline: 'Socket 離線',
};

const SAFETY_LABELS = {
    online: '安全通道已連線',
    warning: '安全通道重新連線中',
    offline: '安全通道離線',
};

const STALE_AFTER_MS = 8000;
let staleTimer = null;

function updateConnectionStatus(status, registry) {
    const normalized = STATUS_LABELS[status] ? status : 'offline';
    const source = registry?.get?.('sourceIndicator') ||
        document.getElementById('state-source-indicator');
    const safety = document.getElementById('safety-msg');
    const syncWarning = document.getElementById('sync-warning');

    if (document.body) {
        document.body.dataset.connectionStatus = normalized;
        const stale = normalized !== 'online' || isStateStale();
        document.body.dataset.stateStale = stale ? 'true' : 'false';
        document.body.classList.toggle('state-stale', stale);
        document.body.classList.toggle('backend-offline', normalized === 'offline');
    }

    if (source) {
        source.innerText = STATUS_LABELS[normalized];
        source.dataset.status = normalized;
        source.classList.toggle('danger', normalized === 'offline');
        source.classList.toggle('warning', normalized === 'warning');
    }

    if (safety) {
        safety.innerText = SAFETY_LABELS[normalized];
        safety.dataset.status = normalized;
    }

    if (syncWarning) {
        const stale = normalized !== 'online' || isStateStale();
        syncWarning.style.display = stale ? 'inline-flex' : 'none';
        syncWarning.innerText = normalized === 'warning'
            ? '狀態延遲：重新連線中'
            : (normalized === 'offline' ? '狀態延遲：後端離線' : '狀態延遲：等待最新快照');
    }

    window.dispatchEvent(new CustomEvent('smart:connection-status', {
        detail: { status: normalized, stale: normalized !== 'online' },
    }));
}

export function setupSocketStatus(socketClient, registry) {
    if (!socketClient) return;

    updateConnectionStatus(socketClient.isConnected?.() ? 'online' : 'offline', registry);
    startStaleTimer(registry);
    window.addEventListener('smart:state-received', (event) => {
        const ts = Number(event?.detail?.timestamp || Date.now());
        if (document.body) {
            document.body.dataset.lastReceivedAt = String(ts);
        }
        updateConnectionStatus(socketClient.isConnected?.() ? 'online' : 'offline', registry);
    });
    socketClient.on('connect', () => updateConnectionStatus('online', registry));
    socketClient.on('disconnect', () => updateConnectionStatus('offline', registry));
    socketClient.on('connect_error', () => updateConnectionStatus('offline', registry));
    socketClient.on('reconnect_attempt', () => updateConnectionStatus('warning', registry));
    socketClient.on('reconnect', () => updateConnectionStatus('online', registry));
    socketClient.on('reconnect_failed', () => updateConnectionStatus('offline', registry));
}

function isStateStale(now = Date.now()) {
    const last = Number(document.body?.dataset?.lastReceivedAt || 0);
    if (!last) return true;
    return now - last > STALE_AFTER_MS;
}

function startStaleTimer(registry) {
    if (staleTimer) return;
    staleTimer = setInterval(() => {
        const status = document.body?.dataset?.connectionStatus || 'offline';
        updateConnectionStatus(status, registry);
    }, 1000);
    staleTimer.unref?.();
}
