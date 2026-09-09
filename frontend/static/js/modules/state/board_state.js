export const boardState = {
    fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
    turn: "red",
    pieces: [],
    move_count: 0,
    last_move: null,
    game_phase: "OPENING",
    game_status: "IDLE",
    game_result: null,
    ended: false
};

export function updateBoard(payload) {
    const nextFen = payload.fen || boardState.fen;
    boardState.fen = nextFen;
    boardState.turn = normalizeBoardTurn(payload.turn) || turnFromFen(nextFen) || boardState.turn;
    boardState.pieces = payload.pieces || boardState.pieces;
    boardState.move_count = payload.move_count ?? boardState.move_count;
    boardState.last_move = payload.last_move ?? payload.lastMove ?? boardState.last_move;
    boardState.game_phase = payload.game_phase || boardState.game_phase;
    boardState.game_status = payload.game_status || boardState.game_status;
    boardState.game_result = payload.game_result === undefined ? boardState.game_result : payload.game_result;
    boardState.ended = Boolean(payload.ended || payload.game_status === "GAME_OVER");
}

function normalizeBoardTurn(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (['black', 'b', 'dark'].includes(normalized)) return 'black';
    if (['red', 'r', 'w', 'white'].includes(normalized)) return 'red';
    return '';
}

function turnFromFen(fen) {
    const side = String(fen || '').trim().split(/\s+/)[1];
    return normalizeBoardTurn(side);
}
