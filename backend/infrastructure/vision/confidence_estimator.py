class ConfidenceEstimator:
    """[Vision Service] Evaluates the reliability of the current board detection."""

    @staticmethod
    def estimate(detected_pieces, expected_count=32, *, allow_capture: bool = True):
        """Calculates a confidence score based on piece counts and detection probability."""
        if not detected_pieces:
            return 0.0

        if isinstance(detected_pieces, (int, float)):
            actual_count = int(detected_pieces)
            avg_prob = 0.9
        else:
            actual_count = len(detected_pieces)
            probs = []
            for p in detected_pieces:
                if hasattr(p, "confidence"):
                    probs.append(float(getattr(p, "confidence", 0.9) or 0.9))
                elif isinstance(p, dict):
                    probs.append(float(p.get("confidence", p.get("prob", 0.9)) or 0.9))
                else:
                    probs.append(0.9)
            avg_prob = (sum(probs) / actual_count) if actual_count > 0 else 0.9

        # Heuristic: piece count vs expected (32 pieces at start, decreases on capture)
        exp = max(1, int(expected_count))
        if actual_count == exp or (allow_capture and actual_count == exp - 1):
            count_confidence = 1.0
        else:
            diff = min(abs(exp - actual_count), 32)
            count_confidence = max(0.0, 1.0 - (diff / 32.0))

        score = (count_confidence * 0.35) + (avg_prob * 0.65)
        return round(max(0.0, min(1.0, score)), 3)

    @staticmethod
    def evaluate_count(actual_count: int, expected_count: int = 32, *, allow_capture: bool = True) -> dict:
        """Detailed piece count analysis."""
        actual = int(actual_count)
        expected = max(1, int(expected_count))
        diff = actual - expected
        if actual == expected:
            return {
                "valid": True,
                "status": "ok",
                "detected": actual,
                "expected": expected,
                "difference": 0,
                "confidence": 1.0,
            }
        if allow_capture and actual == expected - 1:
            return {
                "valid": True,
                "status": "capture",
                "detected": actual,
                "expected": expected,
                "difference": -1,
                "confidence": 1.0,
            }
        status = "missing" if diff < 0 else "extra"
        count_conf = max(0.0, 1.0 - (min(abs(diff), 32) / 32.0))
        return {
            "valid": False,
            "status": status,
            "detected": actual,
            "expected": expected,
            "difference": diff,
            "confidence": round(count_conf, 3),
        }

    @staticmethod
    def evaluate_piece_types(
        actual_types: dict,
        expected_types: dict | None = None,
        *,
        moving_side: str = "w",
        allow_capture: bool = True,
    ) -> dict:
        """Detailed piece type analysis comparing actual vs expected counts per piece type."""
        from backend.utils.fen.parser import validate_piece_types

        return validate_piece_types(
            actual_types,
            expected_types,
            moving_side=moving_side,
            allow_capture=allow_capture,
        )
