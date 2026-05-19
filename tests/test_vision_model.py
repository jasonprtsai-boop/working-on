import unittest
from unittest.mock import Mock, patch

import numpy as np


class TestVisionClassifier(unittest.TestCase):
    def test_classify_color_detects_red_and_black(self):
        with patch("backend.infrastructure.vision.classifier.PiecePredictor") as predictor_cls:
            predictor_cls.return_value = Mock(is_ready=False)
            from backend.infrastructure.vision.classifier import Classifier

            classifier = Classifier()

            red_cell = np.zeros((224, 224, 3), dtype=np.uint8)
            red_cell[:, :] = (0, 0, 255)
            self.assertEqual(classifier.classify_color(red_cell), "red")

            black_cell = np.zeros((224, 224, 3), dtype=np.uint8)
            self.assertEqual(classifier.classify_color(black_cell), "black")

    def test_phash_returns_stable_64bit_signature(self):
        with patch("backend.infrastructure.vision.classifier.PiecePredictor") as predictor_cls:
            predictor_cls.return_value = Mock(is_ready=False)
            from backend.infrastructure.vision.classifier import Classifier

            classifier = Classifier()
            sample = np.zeros((32, 32, 3), dtype=np.uint8)
            sample[8:24, 8:24] = (255, 255, 255)

            digest = classifier.phash(sample)

            self.assertEqual(len(digest), 64)
            self.assertTrue(set(digest).issubset({"0", "1"}))


if __name__ == "__main__":
    unittest.main()
