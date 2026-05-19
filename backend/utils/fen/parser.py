def fen_to_board(fen):
    """FEN pieces part -> 10x9 2D array (row-major)"""
    rows = fen.split()[0].split('/')
    board = []
    for row in rows:
        board_row = []
        for char in row:
            if char.isdigit():
                board_row.extend([None] * int(char))
            else:
                board_row.append(char)
        board.append(board_row)
    return board

def board_to_fen(board, turn='w'):
    """10x9 2D array -> FEN pieces part"""
    fen_rows = []
    for row in board:
        empty = 0
        fen_row = ""
        for cell in row:
            if cell is None:
                empty += 1
            else:
                if empty:
                    fen_row += str(empty)
                    empty = 0
                fen_row += cell
        if empty: fen_row += str(empty)
        fen_rows.append(fen_row)
    return "/".join(fen_rows) + f" {turn} - - 0 1"
