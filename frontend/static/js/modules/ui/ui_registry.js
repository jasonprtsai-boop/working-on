/**
 * ui_registry.js - [UI Layer] Centralized reference management for DOM elements.
 * Prevents hardcoded IDs throughout the business logic.
 */

export const UIRegistry = {
    refs: {},

    /**
     * Initialize references.
     * In a more advanced version, this could be dynamic or based on data-ref attributes.
     */
    init() {
        this.refs = {
            // Indicators
            statusText: document.getElementById('system-status-text'),
            turnIndicator: document.getElementById('turn-indicator'),
            playerTurnIndicator: document.getElementById('player-turn-indicator'),
            playerGuideStep: document.getElementById('player-guide-step'),
            playerGuideAction: document.getElementById('player-guide-action'),
            playerGuideDetail: document.getElementById('player-guide-detail'),
            playerGuideTurn: document.getElementById('player-guide-turn'),
            playerGuideVision: document.getElementById('player-guide-vision'),
            playerGuideVisionCard: document.getElementById('player-guide-vision-card'),
            playerGuideRobot: document.getElementById('player-guide-robot'),
            playerGuideRobotCard: document.getElementById('player-guide-robot-card'),
            playerGuideAi: document.getElementById('player-guide-ai'),
            sourceIndicator: document.getElementById('state-source-indicator'),

            // Metrics
            miniFps: document.getElementById('mini-fps'),
            miniLatency: document.getElementById('mini-latency'),
            consLatency: document.getElementById('cons-latency'),
            consFps: document.getElementById('cons-fps'),
            consLastUpdate: document.getElementById('cons-last-update'),
            visionFen: document.getElementById('vision-fen'),
            visionUcci: document.getElementById('vision-ucci'),
            visionDetectionsCount: document.getElementById('vision-detections-count'),
            visionConfidence: document.getElementById('vision-confidence'),
            visionYoloLatency: document.getElementById('vision-yolo-latency'),
            visionRecognitionTime: document.getElementById('vision-recognition-time'),
            visionDetectionSummary: document.getElementById('vision-detection-summary'),
            visionCalibrationStatus: document.getElementById('vision-calibration-status'),
            visionCalibrationSource: document.getElementById('vision-calibration-source'),
            visionCalibrationError: document.getElementById('vision-calibration-error'),
            visionCalibrationQuality: document.getElementById('vision-calibration-quality'),
            dashboardBoardTurn: document.getElementById('dashboard-board-turn'),
            dashboardBoardFen: document.getElementById('dashboard-board-fen'),
            dashboardBoardLastMove: document.getElementById('dashboard-board-last-move'),
            dashboardBoardMoveCount: document.getElementById('dashboard-board-move-count'),
            dashboardEngineDepth: document.getElementById('dashboard-engine-depth'),
            dashboardEngineThinking: document.getElementById('dashboard-engine-thinking'),
            dashboardEnginePv: document.getElementById('dashboard-engine-pv'),
            dashboardRobotStatus: document.getElementById('dashboard-robot-status'),
            dashboardRobotBusy: document.getElementById('dashboard-robot-busy'),
            dashboardRobotError: document.getElementById('dashboard-robot-error'),
            dashboardRobotQueue: document.getElementById('dashboard-robot-queue'),
            dashboardRobotIp: document.getElementById('dashboard-robot-ip'),
            dashboardRobotPosition: document.getElementById('dashboard-robot-position'),
            dashboardRobotOrientation: document.getElementById('dashboard-robot-orientation'),
            dashboardRobotJoints: document.getElementById('dashboard-robot-joints'),
            dashboardRobotSpeed: document.getElementById('dashboard-robot-speed'),
            dashboardRobotTelemetrySource: document.getElementById('dashboard-robot-telemetry-source'),
            dashboardSafetyEstop: document.getElementById('dashboard-safety-estop'),
            dashboardSafetySafeMode: document.getElementById('dashboard-safety-safe-mode'),
            dashboardSafetyCameraReady: document.getElementById('dashboard-safety-camera-ready'),
            dashboardExpParticipant: document.getElementById('dashboard-exp-participant'),
            dashboardExpSessionId: document.getElementById('dashboard-exp-session-id'),
            dashboardExpSessionStatus: document.getElementById('dashboard-exp-session-status'),
            dashboardExpSessionTime: document.getElementById('dashboard-exp-session-time'),
            dashboardExpDifficulty: document.getElementById('dashboard-exp-difficulty'),

            // Boards
            playerBoardPieces: document.getElementById('board-pieces'),
            consoleBoardPieces: document.getElementById('console-pieces'),

            // Engine
            evalBar: document.getElementById('eval-bar-fill'),
            thinkingProgress: document.getElementById('thinking-progress-bar'),
            thinkingContainer: document.getElementById('thinking-container'),
            bestMove: document.getElementById('best-move'),
            evalScore: document.getElementById('eval-score'),
            statAi: document.getElementById('stat-ai'),

            // Video
            videoFeed: document.getElementById('vision-live-feed'),
            yoloCanvas: document.getElementById('yolo-canvas'),
            videoCam: document.getElementById('video-cam'),
            videoFps: document.getElementById('video-fps'),
            videoTs: document.getElementById('video-ts'),
            videoOverlayCoords: document.getElementById('video-overlay-coords'),

            // Panels
            panes: document.querySelectorAll('.view-pane'),
            sections: document.querySelectorAll('section'),
            modeBtns: document.querySelectorAll('.mode-btn')
        };

        if (window.__SMART_DEBUG__) {
            console.log("UI Registry: Initialized with", Object.keys(this.refs).length, "references.");
        }
    },

    get(key) {
        return this.refs[key];
    },

    /**
     * Centralized Telemetry Dispatcher.
     * Updates all associated DOM nodes across different panes.
     */
    updateTelemetry(data) {
        if (!data) return;

        // Update Global LAT/FPS
        if (data.latency !== undefined && this.refs.consLatency) {
            this.refs.consLatency.innerText = `${Math.round(data.latency)}ms`;
            this.refs.consLatency.className = data.latency > 1000 ? 'value danger' : 'value success';
        }

        if (data.fps !== undefined && this.refs.consFps) {
            this.refs.consFps.innerText = Math.round(data.fps);
        }

        if (this.refs.miniFps && data.fps !== undefined) this.refs.miniFps.innerText = `FPS: ${Math.round(data.fps)}`;
        if (this.refs.miniLatency && data.latency !== undefined) this.refs.miniLatency.innerText = `延遲：${Math.round(data.latency)}ms`;
    }
};
