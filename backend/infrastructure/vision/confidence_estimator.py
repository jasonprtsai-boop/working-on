class ConfidenceEstimator:
    """[Vision Service] Evaluates the reliability of the current board detection."""
    @staticmethod
    def estimate(detected_pieces, expected_count=32):
        """Calculates a confidence score based on piece counts and detection probability."""
        if not detected_pieces: return 0.0

        # Simple heuristic: piece count vs expected
        # (32 pieces at start, decreases over time)
        actual_count = len(detected_pieces)
        count_confidence = 1.0 - (abs(expected_count - actual_count) / 32.0)

        # Average probability from detector (Mock value if missing)
        avg_prob = sum(p.get('prob', 0.9) for p in detected_pieces) / actual_count

        score = (count_confidence * 0.3) + (avg_prob * 0.7)
        return round(max(0, min(1, score)), 2)
