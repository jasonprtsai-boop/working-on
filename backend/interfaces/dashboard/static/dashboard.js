(() => {
    const socket = typeof window.io === 'function'
        ? window.io({ timeout: 7000, reconnectionAttempts: 10 })
        : null;
    const logContainer = document.getElementById('log-container');
    const timelineViz = document.getElementById('timeline-viz');
    let eventCount = 0;

    function setText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = String(value);
    }

    function clippedPayload(payload) {
        const text = JSON.stringify(payload ?? {});
        return text.length > 100 ? `${text.substring(0, 100)}...` : text;
    }

    function addLogEntry(type, payload) {
        if (!logContainer) return;
        eventCount += 1;

        const entry = document.createElement('div');
        entry.className = 'log-entry';

        const header = document.createElement('div');
        header.className = 'log-header';

        const typeEl = document.createElement('span');
        typeEl.className = 'log-type';
        typeEl.textContent = String(type || 'UNKNOWN');

        const timeEl = document.createElement('span');
        timeEl.className = 'log-time';
        timeEl.textContent = new Date().toLocaleTimeString();

        const payloadEl = document.createElement('div');
        payloadEl.className = 'log-payload';
        payloadEl.textContent = clippedPayload(payload);

        header.append(typeEl, timeEl);
        entry.append(header, payloadEl);
        logContainer.prepend(entry);

        if (logContainer.childNodes.length > 50) {
            logContainer.removeChild(logContainer.lastChild);
        }
    }

    function updateMetrics(type, payload) {
        if (type !== 'DIAGNOSTICS.UPDATED' || !payload) return;
        if (payload.vision) {
            setText('val-fps', payload.vision.fps?.toFixed?.(1) || '0.0');
            setText('val-latency', (payload.vision.latency_ms || 0).toFixed(0));
        }
        if (payload.health) {
            setText('val-cpu', payload.health.cpu_percent?.toFixed?.(1) || '0');
        }
    }

    function addTimelineMarker() {
        if (!timelineViz) return;
        const marker = document.createElement('div');
        marker.className = 'timeline-marker';
        marker.style.left = '100%';
        timelineViz.appendChild(marker);

        setTimeout(() => {
            marker.style.left = '0%';
        }, 10);

        setTimeout(() => {
            marker.remove();
        }, 10000);
    }

    socket?.on?.('SYSTEM_STATE_UPDATE', (data) => {
        const type = data?.type || 'UNKNOWN';
        const payload = data?.payload || {};
        addLogEntry(type, payload);
        updateMetrics(type, payload);
        addTimelineMarker();
    });

    setInterval(() => {
        setText('val-events', eventCount);
        eventCount = 0;
    }, 1000);
})();
