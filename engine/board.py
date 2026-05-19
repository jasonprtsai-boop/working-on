import random
from dataclasses import dataclass

W, H = 9, 10

from backend.core.coordinate_system import CoordinateSystem

def uci_to_rc(uci):
    # Map to Canonical (row, col)
    return CoordinateSystem().uci_to_internal(uci)

def rc_to_uci(r, c):
    return CoordinateSystem().internal_to_uci(r, c)

@dataclass
class Piece:
    name: str   # K A B R N C P
    color: str  # r / b
    def __str__(self): return f"{self.color}{self.name}"

class Zobrist:
    def __init__(self):
        self.table = {}
        for p in ["K", "A", "B", "R", "N", "C", "P"]:
            for c in ["r", "b"]:
                for sq in range(90):
                    self.table[(p, c, sq)] = random.getrandbits(64)
        self.side_to_move = random.getrandbits(64)

    def get_hash(self, board):
        h = 0
        for y in range(H):
            for x in range(W):
                p = board.grid[y][x]
                if p: h ^= self.table[(p.name, p.color, y * W + x)]
        if board.turn == "b": h ^= self.side_to_move
        return h

class Board:
    def __init__(self, zobrist=None):
        self.grid = [[None for _ in range(W)] for _ in range(H)]
        self.turn = "r"
        self.zobrist = zobrist if zobrist else Zobrist()
        self.hash = 0
        self.occupied = 0

    def get(self, x, y):
        return self.grid[y][x] if 0 <= x < 9 and 0 <= y < 10 else None

    def set(self, x, y, p):
        idx = y * W + x
        if p: self.occupied |= (1 << idx)
        else: self.occupied &= ~(1 << idx)
        target = self.grid[y][x]
        self.grid[y][x] = p
        return target

    def update_hash(self, x, y, p):
        if p:
            self.hash ^= self.zobrist.table[(p.name, p.color, y * W + x)]

    def move(self, x1, y1, x2, y2):
        p = self.get(x1, y1)
        target = self.get(x2, y2)

        # 增量更新雜湊
        self.update_hash(x1, y1, p)      # 移除起點棋子
        self.update_hash(x2, y2, target) # 移除終點原有的棋子
        self.update_hash(x2, y2, p)      # 在終點放置移動的棋子

        self.set(x2, y2, p)
        self.set(x1, y1, None)

        self.hash ^= self.zobrist.side_to_move # 切換走棋方
        self.turn = "b" if self.turn == "r" else "r"

        return target

    def clone(self):
        nb = Board(self.zobrist)
        nb.grid = [row[:] for row in self.grid]
        nb.turn = self.turn
        nb.occupied = self.occupied
        nb.hash = self.hash
        return nb

    def get_attackers(self, tx, ty, color):
        from engine.movegen import MoveGen
        mg = MoveGen()
        attackers = []
        for y in range(H):
            for x in range(W):
                p = self.grid[y][x]
                if p and p.color == color:
                    moves = mg.gen_piece(self, x, y, p)
                    if any(m[2] == tx and m[3] == ty for m in moves):
                        attackers.append((x, y, p))
        return attackers

    def from_fen(self, fen):
        """Sets board state from a FEN string."""
        parts = fen.split()
        rows = parts[0].split('/')
        self.grid = [[None for _ in range(W)] for _ in range(H)]
        for r, row in enumerate(rows):
            c = 0
            for char in row:
                if char.isdigit():
                    c += int(char)
                else:
                    color = "r" if char.isupper() else "b"
                    name = char.upper()
                    self.set(c, r, Piece(name, color))
                    c += 1
        self.turn = "r" if parts[1] == "w" else "b"
        self.hash = self.zobrist.get_hash(self)

    def to_fen(self):
        """Converts board state to a FEN string."""
        rows = []
        for r in range(H):
            empty = 0
            row_str = ""
            for c in range(W):
                p = self.get(c, r)
                if p:
                    if empty:
                        row_str += str(empty)
                        empty = 0
                    char = p.name.upper() if p.color == "r" else p.name.lower()
                    row_str += char
                else:
                    empty += 1
            if empty: row_str += str(empty)
            rows.append(row_str)
        fen = "/".join(rows)
        fen += " w" if self.turn == "r" else " b"
        return fen

    def setup_startpos(self):
        self.from_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
