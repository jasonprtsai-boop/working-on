/**
 * vision_renderer.js - [UI Layer] Industrial Vision Monitoring with Canvas Overlays.
 */

import { RenderScheduler } from '../core/render_scheduler.js';
import { UIRegistry } from '../ui/ui_registry.js';

export const VisionRenderer = {
    canvas: null,
    ctx: null,
    video: null,
    controller: null,
    calibrationGridVisible: false,
    lastVisionData: null,

    init() {
        if (this.controller && this.canvas) return;
        this.video = UIRegistry.get('videoFeed');
        this.canvas = UIRegistry.get('yoloCanvas');
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext('2d');
        this.resize();
        this.controller = new AbortController();
        window.addEventListener('resize', () => this.resize(), { signal: this.controller.signal });
        if (this.video) {
            this.video.addEventListener('load', () => this.resize(), { signal: this.controller.signal });
        }
    },

    dispose() {
        this.controller?.abort?.();
        this.controller = null;
    },

    resize() {
        if (!this.canvas || !this.video) return;
        const width = Math.max(1, Math.round(this.video.clientWidth || this.video.getBoundingClientRect?.().width || 0));
        const height = Math.max(1, Math.round(this.video.clientHeight || this.video.getBoundingClientRect?.().height || 0));
        if (this.canvas.width !== width) this.canvas.width = width;
        if (this.canvas.height !== height) this.canvas.height = height;
    },

    render(visionData) {
        if (!this.ctx || !visionData) return;
        this.lastVisionData = visionData;

        RenderScheduler.schedule('vision-overlay', () => {
            this.resize();
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

            this.drawCalibrationGrid(visionData);
            const detections = Array.isArray(visionData.detections) ? visionData.detections : [];
            detections.forEach(det => this.drawDetection(det));
            this.drawTelemetry(visionData);
            this.renderDetectionSummary(detections);
        });
    },

    setCalibrationGridVisible(visible) {
        this.calibrationGridVisible = Boolean(visible);
        if (this.lastVisionData) this.render(this.lastVisionData);
    },

    drawCalibrationGrid(visionData) {
        if (!this.calibrationGridVisible || !this.ctx || !this.canvas) return;

        const calibration = visionData?.calibration || {};
        const calibrated = visionData?.calibrated ?? calibration.calibrated;
        if (!calibrated) return;

        const outputSize = Array.isArray(calibration.output_size) ? calibration.output_size : [];
        const sourceWidth = Math.max(1, Number(outputSize[0] || this.video?.naturalWidth || this.canvas.width || 1));
        const sourceHeight = Math.max(1, Number(outputSize[1] || this.video?.naturalHeight || this.canvas.height || 1));
        const rect = this.containedImageRect(sourceWidth, sourceHeight);
        const cols = Math.max(2, Number(visionData?.board_cols || calibration.cols || 9));
        const rows = Math.max(2, Number(visionData?.board_rows || calibration.rows || 10));

        this.ctx.save?.();
        this.ctx.strokeStyle = 'rgba(14, 165, 233, 0.72)';
        this.ctx.lineWidth = 1;
        for (let c = 0; c < cols; c += 1) {
            const x = rect.left + (rect.width * c) / (cols - 1);
            this.ctx.beginPath();
            this.ctx.moveTo(x, rect.top);
            this.ctx.lineTo(x, rect.top + rect.height);
            this.ctx.stroke();
        }
        for (let r = 0; r < rows; r += 1) {
            const y = rect.top + (rect.height * r) / (rows - 1);
            this.ctx.beginPath();
            this.ctx.moveTo(rect.left, y);
            this.ctx.lineTo(rect.left + rect.width, y);
            this.ctx.stroke();
        }

        this.ctx.fillStyle = 'rgba(14, 165, 233, 0.95)';
        [
            [rect.left, rect.top],
            [rect.left + rect.width, rect.top],
            [rect.left + rect.width, rect.top + rect.height],
            [rect.left, rect.top + rect.height],
        ].forEach(([x, y]) => {
            this.ctx.beginPath();
            this.ctx.arc(x, y, 4, 0, Math.PI * 2);
            this.ctx.fill();
        });
        this.ctx.restore?.();
    },

    drawDetection(det) {
        const box = this.normalizeBox(det);
        if (!box || box.w <= 0 || box.h <= 0) return;

        const confidence = Number(det.confidence ?? det.score ?? 0);
        const label = det.label ?? det.class_name ?? det.className ?? det.name ?? 'obj';
        const color = this.cssColor('--accent-green', '#10b981');
        const labelText = `${label} ${Math.round(confidence * 100)}%`;

        this.ctx.strokeStyle = color;
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(box.x, box.y, box.w, box.h);

        this.ctx.font = '10px JetBrains Mono, monospace';
        const textWidth = Math.ceil(this.ctx.measureText(labelText).width);
        const labelY = Math.max(2, box.y - 16);
        this.ctx.fillStyle = 'rgba(2, 6, 23, 0.78)';
        this.ctx.fillRect(box.x, labelY, textWidth + 8, 14);
        this.ctx.fillStyle = color;
        this.ctx.fillText(labelText, box.x + 4, labelY + 10);
    },

    normalizeBox(det) {
        const raw = this.readRawBox(det);
        if (!raw) return null;

        const source = this.sourceSize(det, raw);
        const isNormalized = Math.max(raw.x, raw.y, raw.w, raw.h) <= 1.5;
        const sourceBox = {
            x: isNormalized ? raw.x * source.width : raw.x,
            y: isNormalized ? raw.y * source.height : raw.y,
            w: isNormalized ? raw.w * source.width : raw.w,
            h: isNormalized ? raw.h * source.height : raw.h,
        };

        const fitted = this.containedImageRect(source.width, source.height);
        const scaleX = fitted.width / source.width;
        const scaleY = fitted.height / source.height;

        return {
            x: fitted.left + sourceBox.x * scaleX,
            y: fitted.top + sourceBox.y * scaleY,
            w: sourceBox.w * scaleX,
            h: sourceBox.h * scaleY,
        };
    },

    readRawBox(det) {
        const bbox = det?.bbox;
        if (Array.isArray(bbox) && bbox.length === 4) {
            const [a, b, c, d] = bbox.map(Number);
            if (![a, b, c, d].every(Number.isFinite)) return null;
            if (c >= a && d >= b) return { x: a, y: b, w: c - a, h: d - b };
            return { x: a, y: b, w: c, h: d };
        }
        if (bbox && typeof bbox === 'object') {
            const x1 = Number(bbox.x1 ?? bbox.x ?? 0);
            const y1 = Number(bbox.y1 ?? bbox.y ?? 0);
            const x2 = Number(bbox.x2 ?? x1 + Number(bbox.w ?? bbox.width ?? 0));
            const y2 = Number(bbox.y2 ?? y1 + Number(bbox.h ?? bbox.height ?? 0));
            if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
            return { x: x1, y: y1, w: Math.max(0, x2 - x1), h: Math.max(0, y2 - y1) };
        }
        return null;
    },

    sourceSize(det, raw) {
        const width = Number(
            det?.image_width ??
            det?.source_width ??
            det?.frame_width ??
            this.video?.naturalWidth ??
            this.canvas?.width ??
            1
        );
        const height = Number(
            det?.image_height ??
            det?.source_height ??
            det?.frame_height ??
            this.video?.naturalHeight ??
            this.canvas?.height ??
            1
        );

        return {
            width: Math.max(width, raw.x + raw.w, 1),
            height: Math.max(height, raw.y + raw.h, 1),
        };
    },

    containedImageRect(sourceWidth, sourceHeight) {
        const canvasWidth = Math.max(1, this.canvas?.width || 1);
        const canvasHeight = Math.max(1, this.canvas?.height || 1);
        const scale = Math.min(canvasWidth / sourceWidth, canvasHeight / sourceHeight);
        const width = sourceWidth * scale;
        const height = sourceHeight * scale;

        return {
            left: (canvasWidth - width) / 2,
            top: (canvasHeight - height) / 2,
            width,
            height,
        };
    },

    cssColor(name, fallback) {
        try {
            return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
        } catch {
            return fallback;
        }
    },

    drawTelemetry(data) {
        const fps = data.fps || 0;
        const latency = data.latency || data.latency_ms || 0;
        const text = `${Math.round(fps)} FPS / ${Math.round(latency)}ms`;

        this.ctx.font = '11px JetBrains Mono, monospace';
        this.ctx.fillStyle = 'rgba(2, 6, 23, 0.72)';
        this.ctx.fillRect(8, Math.max(8, this.canvas.height - 28), 118, 20);
        this.ctx.fillStyle = this.cssColor('--accent-green', '#10b981');
        this.ctx.fillText(text, 14, Math.max(22, this.canvas.height - 14));
    },

    renderDetectionSummary(detections) {
        const el = UIRegistry.get('videoOverlayCoords');
        if (!el) return;
        if (!detections.length) {
            el.textContent = 'Detections: no data';
            return;
        }

        el.textContent = detections.slice(0, 5).map((det) => {
            const label = det.class_name || det.className || det.label || det.name || 'obj';
            const confidence = Number(det.confidence ?? det.score ?? 0);
            const box = this.readRawBox(det);
            const bboxText = box
                ? `[${Math.round(box.x)}, ${Math.round(box.y)}, ${Math.round(box.x + box.w)}, ${Math.round(box.y + box.h)}]`
                : '[bbox n/a]';
            return `${label} ${Math.round(confidence * 100)}% ${bboxText}`;
        }).join(' | ');
    }
};
