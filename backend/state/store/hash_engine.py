import hashlib
import json
from typing import Dict, Any

class HashEngine:
    """
    Computes deterministic hashes for state verification.
    """
    @staticmethod
    def compute_hash(state: Dict[str, Any]) -> str:
        # Sort keys to ensure deterministic output
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode('utf-8')).hexdigest()

    @staticmethod
    def verify(state: Dict[str, Any], expected_hash: str) -> bool:
        return HashEngine.compute_hash(state) == expected_hash
