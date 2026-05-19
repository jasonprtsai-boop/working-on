export const engineState = {
    score: 0,
    depth: 0,
    nodes: 0,
    nps: 0,
    best_move: "--",
    pv: [],
    multiPv: [],
    is_thinking: false,
    status: "IDLE"
};

export function updateEngineState(payload) {
    engineState.score = payload.score ?? engineState.score;
    engineState.depth = payload.depth ?? engineState.depth;
    engineState.nodes = payload.nodes ?? engineState.nodes;
    engineState.nps = payload.nps ?? engineState.nps;
    engineState.best_move = payload.best_move ?? payload.move ?? engineState.best_move;
    engineState.pv = payload.pv ?? engineState.pv;
    engineState.multiPv = payload.multiPv ?? payload.multi_pv ?? engineState.multiPv;
    engineState.is_thinking = payload.is_thinking ?? engineState.is_thinking;
    engineState.status = payload.status ?? engineState.status;
}
