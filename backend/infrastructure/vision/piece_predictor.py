import os
import cv2
import numpy as np
from typing import Optional
from backend.utils.logger import logger

# Mapping from AI Model Index to UCI Piece Codes
AI_PIECE_MAPPING = {
    0: "A", 1: "P", 2: "R", 3: "K", 4: "C", 5: "B", 6: "N",     # Red
    7: "a", 8: "r", 9: "p", 10: "c", 11: "n", 12: "k", 13: "b"   # Black
}

class PiecePredictor:
    """[Industrial Architecture] Piece Classification Engine using TensorFlow/Keras."""
    def __init__(self, model_path: Optional[str] = None):
        self._model_path = model_path or os.path.join(os.path.dirname(__file__), "models", "chess_pieces")
        self._model = None
        self._load_model()

    def _load_model(self):
        try:
            import tensorflow as tf
            from tensorflow import keras

            if os.path.exists(self._model_path):
                logger.info(f"[Vision] Loading AI Model from {self._model_path}...")
                self._model = keras.Sequential([
                    keras.layers.TFSMLayer(self._model_path, call_endpoint='serving_default')
                ])
                logger.info("[Vision] AI Model loaded successfully.")
            else:
                logger.warning(f"[Vision] AI Model not found at {self._model_path}.")
        except Exception as e:
            logger.info(f"[Vision] AI Engine (TensorFlow) load failed: {e}")

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def predict(self, cell: np.ndarray, color: str) -> str:
        """Run inference on a single cell image."""
        if not self._model:
            return "P" if color == "red" else "p"

        try:
            # Preprocessing (224x224, Normalized to [-1, 1])
            img_rgb = cv2.cvtColor(cell, cv2.COLOR_BGR2RGB)
            img_resized = cv2.resize(img_rgb, (224, 224), interpolation=cv2.INTER_LANCZOS4)
            img_array = (img_resized.astype(np.float32) / 127.5) - 1
            data = np.expand_dims(img_array, axis=0)

            # Inference
            prediction_output = self._model(data)
            if isinstance(prediction_output, dict):
                prediction = list(prediction_output.values())[0].numpy()
            else:
                prediction = prediction_output.numpy()

            probs = prediction[0]

            # Filter by color to increase accuracy
            indices = range(0, 7) if color == "red" else range(7, 14)
            best_idx = max(indices, key=lambda i: probs[i])

            return AI_PIECE_MAPPING.get(best_idx, "P" if color == "red" else "p")
        except Exception as e:
            logger.error(f"[Vision] AI Prediction error: {e}")
            return "P" if color == "red" else "p"
