from engine.board import Piece

class MoveGen:
    def gen_all(self, board, color):
        moves = []
        for y in range(10):
            for x in range(9):
                p = board.get(x, y)
                if not p or p.color != color:
                    continue
                moves += self.gen_piece(board, x, y, p)

        # Basic filtering: ensure the move doesn't leave the king exposed to 'flying general'
        # and doesn't land on a piece of the same color
        valid_moves = []
        for m in moves:
            x1, y1, x2, y2 = m
            target = board.get(x2, y2)
            if target and target.color == color:
                continue
            valid_moves.append(m)

        return valid_moves

    def gen_piece(self, board, x, y, p):
        m = []
        if p.name == "R":
            m += self.line(board, x, y, [(1,0),(-1,0),(0,1),(0,-1)])
        elif p.name == "N":
            m += self.horse(board, x, y)
        elif p.name == "C":
            m += self.cannon(board, x, y)
        elif p.name == "P":
            m += self.pawn(board, x, y, p.color)
        elif p.name == "K":
            m += self.king(board, x, y)
        elif p.name == "A":
            m += self.advisor(board, x, y, p.color)
        elif p.name == "B":
            m += self.bishop(board, x, y, p.color)
        return m

    def line(self, board, x, y, dirs):
        res = []
        for dx, dy in dirs:
            nx, ny = x+dx, y+dy
            while 0 <= nx < 9 and 0 <= ny < 10:
                p = board.get(nx, ny)
                res.append((x,y,nx,ny))
                if p: break # Blocked by piece (enemy or own)
                nx += dx
                ny += dy
        return res

    def horse(self, board, x, y):
        jumps = [(1,2),(2,1),(-1,2),(-2,1),(1,-2),(2,-1),(-1,-2),(-2,-1)]
        res = []
        for dx, dy in jumps:
            nx, ny = x+dx, y+dy
            if 0 <= nx < 9 and 0 <= ny < 10:
                block_x = x + (dx//2 if abs(dx)==2 else 0)
                block_y = y + (dy//2 if abs(dy)==2 else 0)
                if not board.get(block_x, block_y):
                    res.append((x,y,nx,ny))
        return res

    def cannon(self, board, x, y):
        res = []
        dirs = [(1,0),(-1,0),(0,1),(0,-1)]
        for dx, dy in dirs:
            nx, ny = x+dx, y+dy
            jumped = False
            while 0 <= nx < 9 and 0 <= ny < 10:
                p = board.get(nx, ny)
                if not jumped:
                    if not p:
                        res.append((x,y,nx,ny))
                    else:
                        jumped = True
                else:
                    if p:
                        res.append((x,y,nx,ny))
                        break
                nx += dx
                ny += dy
        return res

    def pawn(self, board, x, y, color):
        res = []
        diry = 1 if color == "r" else -1 # Assuming red starts at bottom (y=0) or top?
        # Standard: Red is at bottom (y=0..4), Black at top (y=5..9) in some conventions.
        # But in UCI/FEN, Red is often 'w' and Black is 'b'.
        # Let's assume Red is y=0-2 range for palace?
        # Actually, let's stick to: Red moves +y if starting at 0, or -y if starting at 9.
        # Let's follow: Red starts at bottom (y=0), Black at top (y=9).
        # So Red moves +y.
        move_dir = 1 if color == "r" else -1
        if 0 <= y + move_dir < 10:
            res.append((x,y,x,y+move_dir))

        # Crossed river?
        crossed = (color == "r" and y >= 5) or (color == "b" and y <= 4)
        if crossed:
            for dx in [-1, 1]:
                if 0 <= x+dx < 9:
                    res.append((x,y,x+dx,y))
        return res

    def king(self, board, x, y):
        res = []
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            nx, ny = x+dx, y+dy
            if 3 <= nx <= 5:
                if (0 <= ny <= 2) or (7 <= ny <= 9):
                    res.append((x,y,nx,ny))
        return res

    def advisor(self, board, x, y, color):
        res = []
        for dx, dy in [(1,1),(1,-1),(-1,1),(-1,-1)]:
            nx, ny = x+dx, y+dy
            if 3 <= nx <= 5:
                if (0 <= ny <= 2) or (7 <= ny <= 9):
                    res.append((x,y,nx,ny))
        return res

    def bishop(self, board, x, y, color):
        res = []
        for dx, dy in [(2,2),(2,-2),(-2,2),(-2,-2)]:
            nx, ny = x+dx, y+dy
            if 0 <= nx < 9 and 0 <= ny < 10:
                # River check
                if (color == "r" and ny > 4) or (color == "b" and ny < 5):
                    continue
                # Eye check
                bx, by = x + dx//2, y + dy//2
                if not board.get(bx, by):
                    res.append((x,y,nx,ny))
        return res
