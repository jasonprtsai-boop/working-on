# backend/core/rule_engine.py
import copy
import random
import re
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
        Performs piece movement, turn, capture, flying-general, and self-check
        validation for Xiangqi/UCCI moves.
        """
        if not move_uci or not re.match(r"^[a-i][0-9][a-i][0-9]$", str(move_uci)):
            return False

        fen = self._extract_fen(state_dict)
        try:
            board = self._parse_fen(fen)
        except Exception:
            return False

        turn = self._turn_from_fen(fen)
        from_r, from_c = self._uci_to_rc(move_uci[:2])
        to_r, to_c = self._uci_to_rc(move_uci[2:])

        if not (0 <= from_r < 10 and 0 <= from_c < 9 and 0 <= to_r < 10 and 0 <= to_c < 9):
            return False

        piece = board[from_r][from_c]
        if not piece:
            return False

        if not self._is_own(piece, turn):
            return False

        target = board[to_r][to_c]
        if target and self._is_own(target, turn):
            return False

        moves = self._get_pseudo_legal_moves(board, from_r, from_c, piece, turn)
        for f_rc, t_rc, _ in moves:
            if f_rc == (from_r, from_c) and t_rc == (to_r, to_c):
                return not self._would_leave_general_in_check(board, f_rc, t_rc, turn)
        return False

    def get_fallback_move(self, state: dict) -> dict:
        """
        AI Fallback: Pick a random pseudo-legal move if the engine fails.
        """
        fen = self._extract_fen(state)
        turn = self._turn_from_fen(fen)

        board = self._parse_fen(fen)
        my_pieces = []
        for r in range(10):
            for c in range(9):
                piece = board[r][c]
                if piece:
                    if self._is_own(piece, turn):
                        my_pieces.append((r, c, piece))

        valid_moves = []
        for r, c, piece in my_pieces:
            for move in self._get_pseudo_legal_moves(board, r, c, piece, turn):
                if not self._would_leave_general_in_check(board, move[0], move[1], turn):
                    valid_moves.append(move)

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

    def _extract_fen(self, state_dict: dict) -> str:
        if not isinstance(state_dict, dict):
            return ""
        if isinstance(state_dict.get("fen"), str):
            return state_dict.get("fen", "")
        game = state_dict.get("game")
        if isinstance(game, dict):
            return game.get("fen", "")
        return ""

    def _parse_fen(self, fen: str):
        from backend.utils.fen.parser import fen_to_board

        return fen_to_board(fen, empty="")

    def _turn_from_fen(self, fen: str):
        parts = str(fen or "").split()
        return "white" if len(parts) < 2 or parts[1].lower() == "w" else "black"

    def _uci_to_rc(self, uci: str):
        return 9 - int(uci[1]), ord(uci[0]) - ord('a')

    def _rc_to_uci(self, r, c):
        col = chr(ord('a') + c)
        row = str(9 - r)
        return f"{col}{row}"

    def _is_own(self, piece: str, turn: str) -> bool:
        return piece.isupper() if turn == "white" else piece.islower()

    def _is_enemy_piece(self, piece: str, turn: str) -> bool:
        if not piece:
            return False
        return not self._is_own(piece, turn)

    def _would_leave_general_in_check(self, board, from_rc, to_rc, turn: str) -> bool:
        next_board = copy.deepcopy(board)
        fr, fc = from_rc
        tr, tc = to_rc
        next_board[tr][tc] = next_board[fr][fc]
        next_board[fr][fc] = ""
        if self._generals_face(next_board):
            return True
        return self._is_general_in_check(next_board, turn)

    def _is_general_in_check(self, board, turn: str) -> bool:
        king = "K" if turn == "white" else "k"
        king_pos = None
        for r in range(10):
            for c in range(9):
                if board[r][c] == king:
                    king_pos = (r, c)
                    break
            if king_pos:
                break
        if king_pos is None:
            return True

        enemy_turn = "black" if turn == "white" else "white"
        for r in range(10):
            for c in range(9):
                piece = board[r][c]
                if not piece or not self._is_own(piece, enemy_turn):
                    continue
                for _from, to, _capture in self._get_pseudo_legal_moves(board, r, c, piece, enemy_turn):
                    if to == king_pos:
                        return True
        return False

    def _generals_face(self, board) -> bool:
        red = black = None
        for r in range(10):
            for c in range(9):
                if board[r][c] == "K":
                    red = (r, c)
                elif board[r][c] == "k":
                    black = (r, c)
        if not red or not black or red[1] != black[1]:
            return False
        col = red[1]
        top = min(red[0], black[0]) + 1
        bottom = max(red[0], black[0])
        return all(not board[r][col] for r in range(top, bottom))

    def _get_pseudo_legal_moves(self, board, r, c, piece, turn):
        moves = []
        p_type = piece.lower()

        def is_enemy(tr, tc):
            return self._is_enemy_piece(board[tr][tc], turn)

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
            for nr in range(10):
                if nr == r:
                    continue
                target = board[nr][c]
                if target and target.lower() == "k" and is_enemy(nr, c):
                    lo, hi = sorted((r, nr))
                    if all(not board[row][c] for row in range(lo + 1, hi)):
                        moves.append(((r, c), (nr, c), True))

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
                    if abs(dr) == 2:
                        leg_r, leg_c = r + (dr // 2), c
                    else:
                        leg_r, leg_c = r, c + (dc // 2)
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
