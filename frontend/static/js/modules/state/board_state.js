export const boardState = {
    fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
    turn: "red",
    pieces: [],
    move_count: 0,
    last_move: null
};

export function updateBoard(payload) {
    boardState.fen = payload.fen || boardState.fen;
    boardState.turn = payload.turn || boardState.turn;
    boardState.pieces = payload.pieces || boardState.pieces;
    boardState.move_count = payload.move_count ?? boardState.move_count;
    boardState.last_move = payload.last_move ?? payload.lastMove ?? boardState.last_move;
}
