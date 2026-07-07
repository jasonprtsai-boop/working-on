from abc import ABC, abstractmethod
import numpy as np
from typing import List
from backend.utils.logger import get_logger
from .detection_result import Detection, DetectionResult

logger = get_logger(__name__)

class BaseDetector(ABC):
    """
    Abstract base class for all vision detectors.
    The active runtime detector is YOLO.
    """
    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[Detection]:
        ...

    @abstractmethod
    def load_model(self, model_path: str):
        ...
