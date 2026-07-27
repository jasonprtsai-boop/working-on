from collections import deque
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

class TemporalValidator:
    """
    Ensures stability by requiring multiple consecutive identical detections
    before committing to a state change.
    """
    def __init__(self, window_size: int = 3):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        self.last_stable_state: Optional[Dict[str, str]] = None

    def validate(self, current_state: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        Returns the stable state if consensus is reached, else None.
        """
        self.history.append(current_state)

        if len(self.history) < self.window_size:
            return None

        # Simplified equality check for dict states
        # In production, you might want a more robust deep comparison
        first = self.history[0]
        for h in list(self.history)[1:]:
            if h != first:
                return None

        # Consensus reached
        if first != self.last_stable_state:
            if self.last_stable_state is not None:
                diff_count = 0
                all_keys = set(first.keys()).union(set(self.last_stable_state.keys()))
                for k in all_keys:
                    if first.get(k) != self.last_stable_state.get(k):
                        diff_count += 1
                
                if diff_count > 6:
                    logger.warning(f"Board state differs too much from previous stable frame: {diff_count} pieces changed.")
                    # Optional: Could add logic to reject or require longer stability here

            self.last_stable_state = first
            return first

        return None

    def reset(self):
        self.history.clear()
        self.last_stable_state = None
