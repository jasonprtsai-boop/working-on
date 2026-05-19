class Evaluate:
    piece_value = {
        "K": 10000,
        "R": 500,
        "N": 300,
        "C": 300,
        "A": 120,
        "B": 120,
        "P": 70
    }

    def eval(self, board):
        score = 0
        for y in range(10):
            for x in range(9):
                p = board.get(x,y)
                if not p:
                    continue

                v = self.piece_value.get(p.name, 0)
                if p.color == "r":
                    score += v
                else:
                    score -= v
        return score
