export const uiState = {
    phase: "IDLE",
    view: "view-landing",
    alerts: [],
    syncLatency: 0,
    estop_triggered: undefined,
    safe_mode: undefined,
    participant_id: "",
    ai_mode: "",
    ai_mode_label: "",
    ai_difficulty: "",
    engine_depth: undefined,
    session_id: "",
    session_active: undefined,
    session_started_at: undefined,
    session_ended_at: undefined,
    session_time_sec: undefined,
    latest_step: null
};

export function updateUIState(payload) {
    uiState.phase = payload.pipeline?.stage || payload.phase || uiState.phase;
    uiState.estop_triggered = payload.estop_triggered ?? payload.e_stop ?? payload.emergency_stop ?? uiState.estop_triggered;
    uiState.safe_mode = payload.safe_mode ?? payload.safeMode ?? uiState.safe_mode;
    uiState.participant_id = payload.participant_id ?? payload.participantId ?? uiState.participant_id;
    uiState.ai_mode = payload.ai_mode ?? payload.aiMode ?? uiState.ai_mode;
    uiState.ai_mode_label = payload.ai_mode_label ?? payload.aiModeLabel ?? uiState.ai_mode_label;
    uiState.ai_difficulty = payload.ai_difficulty ?? payload.aiDifficulty ?? uiState.ai_difficulty;
    uiState.engine_depth = payload.engine_depth ?? payload.engineDepth ?? uiState.engine_depth;
    uiState.session_id = payload.session_id ?? payload.sessionId ?? uiState.session_id;
    uiState.session_active = payload.session_active ?? payload.sessionActive ?? uiState.session_active;
    uiState.session_started_at = payload.session_started_at ?? payload.sessionStartedAt ?? uiState.session_started_at;
    uiState.session_ended_at = payload.session_ended_at ?? payload.sessionEndedAt ?? uiState.session_ended_at;
    uiState.session_time_sec = payload.session_time_sec ?? payload.sessionTimeSec ?? uiState.session_time_sec;
    uiState.latest_step = payload.latest_step ?? payload.latestStep ?? uiState.latest_step;
    // Logic for sync latency tracking can be added here
}
