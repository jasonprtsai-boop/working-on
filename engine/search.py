import math
import time
from engine.evaluate import Evaluate
from engine.movegen import MoveGen

class Search:
    def __init__(self):
        self.evaluator = Evaluate()
        self.movegen = MoveGen()
        self.tt = {}
        self.history = {} # (color, move) -> score
        self.killers = [[] for _ in range(32)]
        self.start_time = 0
        self.time_limit = 2.0

    def see(self, board, move):
        target = board.get(move[2], move[3])
        if not target: return 0
        gain = self.evaluator.piece_value[target.name]
        attackers = board.get_attackers(move[2], move[3], board.turn)
        # 排序攻擊者：從小到大
        attackers.sort(key=lambda p: self.evaluator.piece_value[p[2].name])

        value = gain
        for _, _, p in attackers:
            value -= self.evaluator.piece_value[p.name]
            if value < 0: break
        return value

    def order_moves(self, board, moves, depth, tt_move=None):
        def score(m):
            if m == tt_move: return 1000000
            target = board.get(m[2], m[3])
            if target: return 100000 + self.evaluator.piece_value[target.name]
            if m in self.killers[depth if depth < 32 else 0]: return 50000
            return self.history.get(m, 0)
        return sorted(moves, key=score, reverse=True)

    def iterative_deepening(self, board, max_depth=8, time_limit=2.0):
        self.start_time = time.time()
        self.time_limit = time_limit
        best_move = None
        for d in range(1, max_depth + 1):
            if time.time() - self.start_time > self.time_limit: break
            results = self.root_search(board, d, multipv=1)
            if results:
                best_move = results[0].get("raw_move")
        return best_move

    def get_best_move(self, board, max_depth=4, time_limit=2.0):
        return self.iterative_deepening(board, max_depth=max_depth, time_limit=time_limit)

    def root_search(self, board, depth, multipv=3):
        alpha, beta = -math.inf, math.inf
        moves = self.order_moves(board, self.movegen.gen_all(board, board.turn), depth)

        results = []
        for m in moves:
            nb = board.clone(); nb.move(*m)
            val = -self.alpha_beta(nb, depth - 1, -beta, -alpha)
            uci = f"{chr(ord('a')+m[0])}{m[1]}{chr(ord('a')+m[2])}{m[3]}"
            results.append({
                "move": uci,
                "raw_move": m,
                "score": val,
                "depth": depth
            })

            if val > alpha: alpha = val

        # Sort by score descending and take top N
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:multipv]

    def alpha_beta(self, board, depth, alpha, beta):
        if depth <= 0: return self.quiescence(board, alpha, beta)
        if time.time() - self.start_time > self.time_limit: return 0

        moves = self.order_moves(board, self.movegen.gen_all(board, board.turn), depth)
        for i, m in enumerate(moves):
            # 強化版 LMR 邏輯
            is_capture = board.get(m[2], m[3]) is not None
            reduction = 0
            if i >= 3 and depth >= 3 and not is_capture:
                reduction = 1 + (depth // 4)

            nb = board.clone(); nb.move(*m)
            val = -self.alpha_beta(nb, depth - 1 - reduction, -beta, -alpha)

            # Re-search if reduced search failed high
            if reduction > 0 and val > alpha:
                val = -self.alpha_beta(nb, depth - 1, -beta, -alpha)

            if val >= beta:
                if not is_capture and depth < 32:
                    self.killers[depth].append(m)
                return beta
            if val > alpha:
                alpha = val
                self.history[m] = self.history.get(m, 0) + depth * depth
        return alpha

    def quiescence(self, board, alpha, beta):
        stand_pat = self.evaluator.eval(board)
        if board.turn == 'b': stand_pat = -stand_pat
        if stand_pat >= beta: return beta
        alpha = max(alpha, stand_pat)
        captures = [m for m in self.movegen.gen_all(board, board.turn) if board.get(m[2], m[3])]
        for m in captures:
            if self.see(board, m) < -50: continue
            nb = board.clone(); nb.move(*m)
            val = -self.quiescence(nb, -beta, -alpha)
            if val >= beta: return beta
            alpha = max(alpha, val)
        return alpha
