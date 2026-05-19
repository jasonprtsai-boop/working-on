import re

class FENValidator:
    """
    [State Layer] FEN String Validator for Chinese Chess.
    Ensures that only valid board representations are committed to the SSOT.
    """
    @staticmethod
    def validate(fen: str) -> bool:
        """
        Validates the format of a Chinese Chess FEN string.
        Standard FEN format for CC: <pieces> <turn> - - <half_move> <full_move>
        Example: rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1
        """
        if not fen or not isinstance(fen, str):
            return False

        parts = fen.split(' ')
        if len(parts) < 1:
            return False

        # 1. Validate pieces (10 ranks separated by /)
        ranks = parts[0].split('/')
        if len(ranks) != 10:
            return False

        # 2. Validate pieces count/format (optional but recommended)
        # Simplified: Check for valid characters and row sums
        for rank in ranks:
            count = 0
            for char in rank:
                if char.isdigit():
                    count += int(char)
                elif char.lower() in 'rnbakcp': # Standard CC pieces
                    count += 1
                else:
                    return False # Invalid character
            if count != 9:
                return False # Each rank must have 9 columns

        # 3. Validate turn. Xiangqi engine-facing FEN uses w/b; r is accepted
        # only as a legacy Red alias for older vision payloads.
        if len(parts) > 1:
            if parts[1] not in ('w', 'b', 'r'):
                return False

        return True
