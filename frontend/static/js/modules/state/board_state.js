export const boardState = {
    fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
    turn: "red",
    pieces: [],
    move_count: 0,
    last_move: null
};

export function updateBoard(payload) {
    const nextFen = payload.fen || boardState.fen;
    boardState.fen = nextFen;
    boardState.turn = normalizeBoardTurn(payload.turn) || turnFromFen(nextFen) || boardState.turn;
    boardState.pieces = payload.pieces || boardState.pieces;
    boardState.move_count = payload.move_count ?? boardState.move_count;
    boardState.last_move = payload.last_move ?? payload.lastMove ?? boardState.last_move;
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
