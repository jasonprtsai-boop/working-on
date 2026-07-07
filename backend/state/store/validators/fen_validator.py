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
        try:
            from backend.utils.fen.parser import validate_fen

            return validate_fen(fen)
        except Exception:
            return False
