/**
 * telemetry_renderer.js - [UI Layer] Renders the compact event timeline.
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

            if (this.container.children.length > this.maxLines) {
                this.container.removeChild(this.container.lastChild);
            }
        });
    },

    formatPayload(payload) {
        if (!payload) return "";
        if (typeof payload === 'string') return payload;

        if (payload.board?.last_move) return `last move: ${payload.board.last_move}`;
        if (payload.best_move) return `best move: ${payload.best_move} score: ${payload.score ?? '--'}`;
        if (payload.connected !== undefined) return `connected: ${payload.connected ? 'yes' : 'no'}`;
        if (payload.health?.cpu_percent !== undefined) return `cpu: ${Math.round(payload.health.cpu_percent)}%`;
        if (payload.telemetry?.recorded_events !== undefined) return `events: ${payload.telemetry.recorded_events}`;

        return "";
    },

    toClassToken(value) {
        const token = String(value || 'unknown').toLowerCase().replace(/[^a-z0-9_-]/g, '');
        return token || 'unknown';
    }
};
