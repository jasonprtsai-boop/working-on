import sys
from engine.board import Board
from engine.evaluate import Evaluate
from engine.movegen import MoveGen
from engine.search import Search
from engine.rules import Rules

class UCI:
    def __init__(self):
        self.board = Board()
        self.board.setup_startpos()
        self.searcher = Search()
        self.rules = Rules()

    def move_to_uci(self, move):
        x1, y1, x2, y2 = move
        return f"{chr(ord('a')+x1)}{y1}{chr(ord('a')+x2)}{y2}"

    def uci_to_move(self, uci):
        x1 = ord(uci[0]) - ord('a')
        y1 = int(uci[1])
        x2 = ord(uci[2]) - ord('a')
        y2 = int(uci[3])
        return (x1, y1, x2, y2)

    def loop(self):
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                cmd = line.strip()
                if not cmd:
                    continue

                if cmd == "uci":
                    print("id name XiangqiEngine")
                    print("id author Antigravity")
                    print("uciok")
                    sys.stdout.flush()

                elif cmd == "isready":
                    print("readyok")
                    sys.stdout.flush()

                elif cmd.startswith("position"):
                    self.handle_position(cmd)

                elif cmd.startswith("go"):
                    self.handle_go(cmd)

                elif cmd == "quit":
                    break

                elif cmd == "ucinewgame":
                    self.board = Board()
                    self.board.setup_startpos()
                    self.rules = Rules()

            except EOFError:
                break
            except Exception as e:
                print(f"[UCI] Error: {e}", file=sys.stderr)
                sys.stderr.flush()

    def handle_position(self, cmd):
        parts = cmd.split()
        if len(parts) < 2: return

        if parts[1] == "startpos":
            self.board = Board()
            self.board.setup_startpos()
            self.rules = Rules()
            if "moves" in parts:
                move_idx = parts.index("moves") + 1
                for m_str in parts[move_idx:]:
                    m = self.uci_to_move(m_str)
                    target = self.board.move(*m)
                    self.rules.record_history(self.board)
                    self.rules.update_no_capture(target is not None)
        elif parts[1] == "fen":
            fen = " ".join(parts[2:])
            try:
                self.board.from_fen(fen)
                self.rules = Rules()
            except Exception as e:
                print(f"[UCI] Invalid FEN: {e}", file=sys.stderr)
                sys.stderr.flush()

    def handle_go(self, cmd):
        # Basic go implementation
        best = self.searcher.get_best_move(self.board)
        if best:
            print(f"bestmove {self.move_to_uci(best)}")
        else:
            print("bestmove resign")
        sys.stdout.flush()
