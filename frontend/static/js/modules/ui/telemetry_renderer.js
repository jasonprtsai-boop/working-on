/**
 * telemetry_renderer.js - [UI Layer] Renders real-time industrial event timeline.
 */

import { RenderScheduler } from '../core/render_scheduler.js';

export const TelemetryRenderer = {
    container: null,
    maxLines: 50,

    init(containerId) {
        this.container = document.getElementById(containerId);
    },

    renderEvent(event) {
        if (!this.container) return;

        RenderScheduler.schedule('telemetry-update', () => {
            const line = document.createElement('div');
            const eventType = String(event?.type || 'UNKNOWN');
            line.className = `log-line ${this.toClassToken(eventType.split('.')[0])}`;

            const time = new Date(event.timestamp).toLocaleTimeString([], { hour12: false });

            const timeEl = document.createElement('span');
            timeEl.className = 'log-time';
            timeEl.textContent = `[${time}]`;

            const typeEl = document.createElement('span');
            typeEl.className = 'log-type';
            typeEl.textContent = eventType;

            const payloadEl = document.createElement('span');
            payloadEl.className = 'log-payload';
            payloadEl.textContent = this.formatPayload(event.payload);

            line.append(timeEl, typeEl, payloadEl);

            this.container.prepend(line);

            // Maintain line count
            if (this.container.children.length > this.maxLines) {
                this.container.removeChild(this.container.lastChild);
            }
        });
    },

    formatPayload(payload) {
        if (!payload) return "";
        if (typeof payload === 'string') return payload;

        // Brief summary of payload for telemetry view
        if (payload.board?.last_move) return `走子：${payload.board.last_move}`;
        if (payload.best_move) return `最佳著法：${payload.best_move}（${payload.score}）`;
        if (payload.connected !== undefined) return `狀態：${payload.connected ? '連線中' : '離線'}`;

        return "";
    },

    toClassToken(value) {
        const token = String(value || 'unknown').toLowerCase().replace(/[^a-z0-9_-]/g, '');
        return token || 'unknown';
    }
};
