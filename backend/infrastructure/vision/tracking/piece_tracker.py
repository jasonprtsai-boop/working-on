from typing import List, Dict, Tuple
import time
from backend.infrastructure.vision.detection.detection_result import Detection

class PieceTracker:
    """
    Tracks pieces across frames to maintain identity and handle occlusion.
    Uses simple distance-based tracking (Centroid Tracking).
    """
    def __init__(self, max_disappeared: int = 5, distance_threshold: float = 50.0):
        self.next_object_id = 0
        self.objects: Dict[int, Tuple[float, float]] = {}  # ID -> (cx, cy)
        self.metadata: Dict[int, Dict] = {}               # ID -> info (class, confidence)
        self.disappeared: Dict[int, int] = {}             # ID -> count
        self.max_disappeared = max_disappeared
        self.distance_threshold = distance_threshold

    def update(self, detections: List[Detection]):
        """
        Updates tracked objects with new detections.
        """
        if not detections:
            # Mark all existing objects as disappeared
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self._deregister(object_id)
            return self.objects

        # Calculate centroids of detections
        input_centroids = [det.bbox.center for det in detections]

        if not self.objects:
            # Register all detections
            for i, centroid in enumerate(input_centroids):
                self._register(centroid, detections[i])
        else:
            object_ids = list(self.objects.keys())
            object_centroids = list(self.objects.values())

            # Simple Euclidean distance matching
            # In a real system, use Hungarian algorithm or KD-Tree
            for i, input_centroid in enumerate(input_centroids):
                distances = [np.linalg.norm(np.array(input_centroid) - np.array(obj_centroid))
                             for obj_centroid in object_centroids]

                min_dist_idx = np.argmin(distances)
                if distances[min_dist_idx] < self.distance_threshold:
                    object_id = object_ids[min_dist_idx]
                    self.objects[object_id] = input_centroid
                    self.metadata[object_id] = {"class": detections[i].class_name, "conf": detections[i].confidence}
                    self.disappeared[object_id] = 0
                else:
                    self._register(input_centroid, detections[i])

        return self.objects

    def _register(self, centroid: Tuple[float, float], det: Detection):
        self.objects[self.next_object_id] = centroid
        self.metadata[self.next_object_id] = {"class": det.class_name, "conf": det.confidence}
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1

    def _deregister(self, object_id: int):
        del self.objects[object_id]
        del self.metadata[object_id]
        del self.disappeared[object_id]

import numpy as np # Needed for distance calculation
