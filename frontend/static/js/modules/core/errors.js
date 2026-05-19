/**
 * errors.js - [Domain] Standardized Error Codes.
 * Sync with backend/core/errors/codes.py
 */

export const SystemErrorCode = {
    // Bootstrap & Runtime
    BOOTSTRAP_FAILED: "BOOTSTRAP_FAILED",
    RUNTIME_LOOP_ERROR: "RUNTIME_LOOP_ERROR",

    // Auth & Security
    UNAUTHORIZED: "UNAUTHORIZED",
    FORBIDDEN: "FORBIDDEN",
    INVALID_TOKEN: "INVALID_TOKEN",
    RATE_LIMITED: "RATE_LIMITED",

    // Hardware
    ROBOT_CONNECTION_FAILED: "ROBOT_CONNECTION_FAILED",
    ROBOT_MOTION_ERROR: "ROBOT_MOTION_ERROR",
    VISION_CAMERA_ERROR: "VISION_CAMERA_ERROR",
    VISION_DETECTION_FAILED: "VISION_DETECTION_FAILED",
    ENGINE_PROCESS_CRASHED: "ENGINE_PROCESS_CRASHED",

    // Application Logic
    INVALID_MOVE: "INVALID_MOVE",
    STATE_TRANSITION_ERROR: "STATE_TRANSITION_ERROR",
    PERSISTENCE_FAILURE: "PERSISTENCE_FAILURE",

    // UI / Socket
    INVALID_PAYLOAD: "INVALID_PAYLOAD",
    PAYLOAD_TOO_LARGE: "PAYLOAD_TOO_LARGE",
};

export function getErrorMessage(code) {
    const messages = {
        [SystemErrorCode.UNAUTHORIZED]: "身分驗證失敗，請重新登入。",
        [SystemErrorCode.FORBIDDEN]: "權限不足，無法執行此操作。",
        [SystemErrorCode.RATE_LIMITED]: "操作過於頻繁，請稍候再試。",
        [SystemErrorCode.ROBOT_CONNECTION_FAILED]: "無法連線至機器手臂，請檢查網路與電源。",
        [SystemErrorCode.VISION_CAMERA_ERROR]: "攝影機影像異常，請重新整理頁面。",
        [SystemErrorCode.ENGINE_PROCESS_CRASHED]: "象棋引擎無回應，正在嘗試重新啟動...",
    };
    return messages[code] || "發生未知系統錯誤。";
}
