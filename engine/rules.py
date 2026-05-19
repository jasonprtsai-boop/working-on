class Rules:
    def __init__(self):
        self.no_capture = 0
        self.repetition_map = {}

    def flying_general(self, board):
        rk = bk = None
        for y in range(10):
            for x in range(9):
                p = board.get(x, y)
                if p and p.name == "K":
                    if p.color == "r":
                        rk = (x, y)
                    else:
                        bk = (x, y)

        if not rk or not bk:
            return False

        if rk[0] != bk[0]:
            return False

        x = rk[0]
        # Check if there are any pieces between the two kings
        for y in range(min(rk[1], bk[1]) + 1, max(rk[1], bk[1])):
            if board.get(x, y):
                return False

        return True

    def hash_board(self, board):
        # A very simple hash for repetition detection
        res = []
        for y in range(10):
            for x in range(9):
                p = board.get(x, y)
                if p:
                    res.append(f"{x}{y}{p.color}{p.name}")
        return "-".join(res) + f"-{board.turn}"

    def repetition(self, board):
        h = self.hash_board(board)
        return self.repetition_map.get(h, 0) >= 3

    def record_history(self, board):
        h = self.hash_board(board)
        self.repetition_map[h] = self.repetition_map.get(h, 0) + 1

    def update_no_capture(self, captured):
        if captured:
            self.no_capture = 0
        else:
            self.no_capture += 1
        return self.no_capture >= 120
