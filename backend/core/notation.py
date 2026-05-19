def move_to_chinese(move_str: str, fen: str, is_red: bool) -> str:
    """Return a stable human-readable fallback for move notation."""
    if not isinstance(move_str, str) or len(move_str) != 4:
        return str(move_str)
    return move_str
