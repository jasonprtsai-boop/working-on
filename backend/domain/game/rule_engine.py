# backend/core/rule_engine.py
import random
from backend.utils.logger import logger

class RuleEngine:
    """
    [Phase 5] Authoritative Xiangqi Rule Engine.
    Handles move validation and fallback random moves for AI outages.
    """
    def __init__(self):
        self.version = 1

    def is_valid_move(self, state_dict: dict, move_uci: str) -> bool:
        """
        [Rule Guard] Validates if a move is legal in the current FEN state.
        Currently performs pseudo-legal check.
        """
        if not move_uci or len(move_uci) != 4:
            return False

        fen = state_dict.get("fen", "")
        turn = "white" if " w " in fen else "black"

        board = self._parse_fen(fen)
        from_c = ord(move_uci[0]) - ord('a')
        from_r = 9 - int(move_uci[1])
        to_c = ord(move_uci[2]) - ord('a')
        to_r = 9 - int(move_uci[3])

        if not (0 <= from_r < 10 and 0 <= from_c < 9 and 0 <= to_r < 10 and 0 <= to_c < 9):
            return False

        piece = board[from_r][from_c]
        if not piece:
            return False

        # Check turn
        if turn == "white" and not piece.isupper(): return False
        if turn == "black" and not piece.islower(): return False

        # Get all pseudo-legal moves for this piece
        moves = self._get_pseudo_legal_moves(board, from_r, from_c, piece, turn)
        for f_rc, t_rc, _ in moves:
            if f_rc == (from_r, from_c) and t_rc == (to_r, to_c):
                return True
        return False

    def get_fallback_move(self, state: dict) -> dict:
        """
        AI Fallback: Pick a random pseudo-legal move if the engine fails.
        """
        fen = state.get("fen", "")
        turn = "white" if " w " in fen else "black"

        board = self._parse_fen(fen)
        my_pieces = []
        for r in range(10):
            for c in range(9):
                piece = board[r][c]
                if piece:
                    is_mine = piece.isupper() if turn == "white" else piece.islower()
                    if is_mine:
                        my_pieces.append((r, c, piece))

        valid_moves = []
        for r, c, piece in my_pieces:
            moves = self._get_pseudo_legal_moves(board, r, c, piece, turn)
            valid_moves.extend(moves)

        if not valid_moves:
            logger.error("RuleEngine: No legal moves found for fallback.")
            return None

        selected_move = random.choice(valid_moves)
        from_rc, to_rc, is_capture = selected_move

        uci_move = f"{self._rc_to_uci(from_rc[0], from_rc[1])}{self._rc_to_uci(to_rc[0], to_rc[1])}"

        # Build fake analysis result
        return {
            "move": uci_move,
            "best_move": uci_move,
            "score": 0,
            "depth": 1,
            "is_fallback": True
        }

    def _parse_fen(self, fen: str):
        board = [["" for _ in range(9)] for _ in range(10)]
        parts = fen.split(" ")
        rows = parts[0].split("/")
        for r, row in enumerate(rows):
            c = 0
            for char in row:
                if char.isdigit():
                    c += int(char)
                else:
                    board[r][c] = char
                    c += 1
        return board

    def _rc_to_uci(self, r, c):
        col = chr(ord('a') + c)
        row = str(9 - r)
        return f"{col}{row}"

    def _get_pseudo_legal_moves(self, board, r, c, piece, turn):
        moves = []
        p_type = piece.lower()

        def is_enemy(tr, tc):
            target = board[tr][tc]
            if not target: return False
            return target.islower() if turn == "white" else target.isupper()

        def is_empty(tr, tc):
            return board[tr][tc] == ""

        # Pawn (Soldier)
        if p_type == 'p':
            dr = -1 if turn == "white" else 1
            if 0 <= r + dr < 10 and (is_empty(r + dr, c) or is_enemy(r + dr, c)):
                moves.append(((r, c), (r + dr, c), is_enemy(r + dr, c)))
            crossed = (turn == "white" and r <= 4) or (turn == "black" and r >= 5)
            if crossed:
                for dc in [-1, 1]:
                    if 0 <= c + dc < 9 and (is_empty(r, c + dc) or is_enemy(r, c + dc)):
                        moves.append(((r, c), (r, c + dc), is_enemy(r, c + dc)))

        # King (General)
        elif p_type == 'k':
            for dr, dc in [(-1,0), (1,0), (0,-1), (0,1)]:
                nr, nc = r + dr, c + dc
                if turn == "white":
                    if 7 <= nr <= 9 and 3 <= nc <= 5:
                        if is_empty(nr, nc) or is_enemy(nr, nc):
                            moves.append(((r, c), (nr, nc), is_enemy(nr, nc)))
                else:
                    if 0 <= nr <= 2 and 3 <= nc <= 5:
                        if is_empty(nr, nc) or is_enemy(nr, nc):
                            moves.append(((r, c), (nr, nc), is_enemy(nr, nc)))

        # Rook (Chariot)
        elif p_type == 'r':
            for dr, dc in [(-1,0), (1,0), (0,-1), (0,1)]:
                for step in range(1, 10):
                    nr, nc = r + dr * step, c + dc * step
                    if 0 <= nr < 10 and 0 <= nc < 9:
                        if is_empty(nr, nc):
                            moves.append(((r, c), (nr, nc), False))
                        elif is_enemy(nr, nc):
                            moves.append(((r, c), (nr, nc), True))
                            break
                        else: break
                    else: break

        # Cannon
        elif p_type == 'c':
            for dr, dc in [(-1,0), (1,0), (0,-1), (0,1)]:
                jump = False
                for step in range(1, 10):
                    nr, nc = r + dr * step, c + dc * step
                    if 0 <= nr < 10 and 0 <= nc < 9:
                        target = board[nr][nc]
                        if not jump:
                            if target == "": moves.append(((r, c), (nr, nc), False))
                            else: jump = True
                        else:
                            if target != "":
                                if is_enemy(nr, nc): moves.append(((r, c), (nr, nc), True))
                                break
                    else: break

        # Horse (Knight)
        elif p_type == 'n':
            for dr, dc in [(-2,-1), (-2,1), (2,-1), (2,1), (-1,-2), (1,-2), (-1,2), (1,2)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < 10 and 0 <= nc < 9:
                    leg_r, leg_c = r + (dr // 2), c + (dc // 2)
                    if board[leg_r][leg_c] == "":
                        if is_empty(nr, nc) or is_enemy(nr, nc):
                            moves.append(((r, c), (nr, nc), is_enemy(nr, nc)))

        # Elephant (Bishop)
        elif p_type == 'b':
            for dr, dc in [(-2,-2), (-2,2), (2,-2), (2,2)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < 10 and 0 <= nc < 9:
                    eye_r, eye_c = r + (dr // 2), c + (dc // 2)
                    if board[eye_r][eye_c] == "":
                        crossed = (turn == "white" and nr < 5) or (turn == "black" and nr > 4)
                        if not crossed:
                            if is_empty(nr, nc) or is_enemy(nr, nc):
                                moves.append(((r, c), (nr, nc), is_enemy(nr, nc)))

        # Advisor (Guard)
        elif p_type == 'a':
            for dr, dc in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < 10 and 0 <= nc < 9:
                    in_palace = (7 <= nr <= 9 and 3 <= nc <= 5) if turn == "white" else (0 <= nr <= 2 and 3 <= nc <= 5)
                    if in_palace:
                        if is_empty(nr, nc) or is_enemy(nr, nc):
                            moves.append(((r, c), (nr, nc), is_enemy(nr, nc)))
        return moves

rule_engine = RuleEngine()
