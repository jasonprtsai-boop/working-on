from backend.utils.fen.parser import board_to_fen


class FENBuilder:
    """Legacy wrapper around the canonical FEN serializer."""

    def build(self, board_dict, turn="w"):
        return board_to_fen(board_dict, turn=turn)


fen_builder = FENBuilder()
