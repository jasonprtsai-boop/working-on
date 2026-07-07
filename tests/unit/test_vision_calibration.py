import os
import tempfile
import unittest

import numpy as np
import cv2

from backend.infrastructure.vision.board.coordinate_system import BoardCoordinateSystem, GridConfig
from backend.infrastructure.vision.calibration import (
    apply_homography_point,
    apply_homography_points,
    compute_calibration_quality,
    compute_warp_matrix,
    load_calibration_payload,
    load_calibration,
    save_calibration,
)
from backend.infrastructure.vision.calibration.board_calibrator import BoardCalibrator
from backend.infrastructure.vision.preprocess.image_preprocessor import PerspectiveCorrector
from backend.infrastructure.vision.preprocess.image_preprocessor import ImagePreprocessor
from backend.utils import config


class TestVisionCalibration(unittest.TestCase):
    def test_homography_maps_four_corners_to_rectified_board(self):
        corners = [[10, 20], [210, 18], [220, 320], [5, 300]]
        matrix = compute_warp_matrix(corners, output_size=(1000, 1000))

        self.assertEqual(matrix.shape, (3, 3))
        self.assertAlmostEqual(apply_homography_point(matrix, 10, 20)[0], 0.0, places=3)
        self.assertAlmostEqual(apply_homography_point(matrix, 10, 20)[1], 0.0, places=3)
        self.assertAlmostEqual(apply_homography_point(matrix, 220, 320)[0], 999.0, places=2)
        self.assertAlmostEqual(apply_homography_point(matrix, 220, 320)[1], 999.0, places=2)

    def test_homography_batch_mapping_matches_single_point_mapping(self):
        corners = [[10, 20], [210, 18], [220, 320], [5, 300]]
        matrix = compute_warp_matrix(corners, output_size=(1000, 1000))
        points = [(10, 20), (220, 320), (110, 160)]

        batch = apply_homography_points(matrix, points)
        single = [apply_homography_point(matrix, x, y) for x, y in points]

        self.assertEqual(len(batch), 3)
        for mapped_batch, mapped_single in zip(batch, single):
            self.assertAlmostEqual(mapped_batch[0], mapped_single[0], places=6)
            self.assertAlmostEqual(mapped_batch[1], mapped_single[1], places=6)

    def test_calibration_quality_reports_reprojection_and_geometry_metrics(self):
        corners = [[10, 20], [210, 18], [220, 320], [5, 300]]
        matrix = compute_warp_matrix(corners, output_size=(1000, 1000))

        quality = compute_calibration_quality(corners, matrix, output_size=(1000, 1000))

        self.assertLessEqual(quality["max_reprojection_error_px"], 1e-3)
        self.assertGreater(quality["area_px"], 1000)
        self.assertGreaterEqual(quality["min_angle_deg"], 30)

    def test_perspective_corrector_warps_and_maps_points(self):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        corners = np.array([[10, 20], [140, 15], [145, 100], [8, 105]], dtype=np.float32)

        corrector = PerspectiveCorrector(output_size=(600, 600))
        corrector.set_corners(corners, output_size=(600, 600))
        warped = corrector.warp(frame)
        mapped = corrector.map_point(10, 20)
        raw = corrector.inverse_map_point(*mapped)

        self.assertEqual(warped.shape, (600, 600, 3))
        self.assertTrue(corrector.is_calibrated)
        self.assertAlmostEqual(mapped[0], 0.0, places=3)
        self.assertAlmostEqual(mapped[1], 0.0, places=3)
        self.assertAlmostEqual(raw[0], 10.0, places=3)
        self.assertAlmostEqual(raw[1], 20.0, places=3)

        batch_mapped = corrector.map_points([(10, 20), (145, 100)])
        batch_raw = corrector.inverse_map_points(batch_mapped)
        self.assertAlmostEqual(batch_raw[0][0], 10.0, places=3)
        self.assertAlmostEqual(batch_raw[0][1], 20.0, places=3)
        self.assertAlmostEqual(batch_raw[1][0], 145.0, places=3)
        self.assertAlmostEqual(batch_raw[1][1], 100.0, places=3)

    def test_perspective_corrector_maps_bbox_through_homography(self):
        corners = np.array([[10, 20], [110, 20], [110, 120], [10, 120]], dtype=np.float32)
        corrector = PerspectiveCorrector(output_size=(101, 101))
        corrector.set_corners(corners, output_size=(101, 101))

        mapped = corrector.map_bbox([20, 30, 40, 50])
        raw = corrector.inverse_map_bbox(mapped)

        self.assertEqual(len(mapped), 4)
        self.assertAlmostEqual(mapped[0], 10.0, places=3)
        self.assertAlmostEqual(mapped[1], 10.0, places=3)
        self.assertAlmostEqual(mapped[2], 30.0, places=3)
        self.assertAlmostEqual(mapped[3], 30.0, places=3)
        self.assertAlmostEqual(raw[0], 20.0, places=3)
        self.assertAlmostEqual(raw[1], 30.0, places=3)
        self.assertAlmostEqual(raw[2], 40.0, places=3)
        self.assertAlmostEqual(raw[3], 50.0, places=3)

    def test_board_calibrator_orders_corners(self):
        unordered = np.array([[200, 200], [10, 10], [15, 220], [210, 20]], dtype=np.float32)
        ordered = BoardCalibrator.order_corners(unordered)

        self.assertTrue(BoardCalibrator.validate_corners(ordered, min_area=1000))
        self.assertTrue(np.allclose(ordered[0], [10, 10]))
        self.assertTrue(np.allclose(ordered[1], [210, 20]))
        self.assertTrue(np.allclose(ordered[2], [200, 200]))
        self.assertTrue(np.allclose(ordered[3], [15, 220]))

    def test_board_calibrator_detects_synthetic_board_quad(self):
        frame = np.zeros((320, 420, 3), dtype=np.uint8)
        quad = np.array([[60, 40], [360, 55], [340, 280], [50, 260]], dtype=np.int32)
        cv2.fillConvexPoly(frame, quad, (255, 255, 255))

        corners = BoardCalibrator().detect_auto(frame)

        self.assertIsNotNone(corners)
        self.assertTrue(BoardCalibrator.validate_corners(corners, min_area=1000))

    def test_board_calibrator_downscales_detection_then_returns_original_space_corners(self):
        frame = np.zeros((960, 1280, 3), dtype=np.uint8)
        quad = np.array([[180, 120], [1100, 150], [1040, 820], [140, 780]], dtype=np.int32)
        cv2.fillConvexPoly(frame, quad, (255, 255, 255))

        calibrator = BoardCalibrator(max_detection_dim=240)
        corners = calibrator.detect_auto(frame)

        self.assertIsNotNone(corners)
        self.assertEqual(corners.shape, (4, 2))
        self.assertTrue(BoardCalibrator.validate_corners(corners, min_area=1000))
        self.assertIsNotNone(calibrator.last_quality)
        self.assertIn(calibrator.last_method, {"contour", "aruco"})

    def test_calibration_can_be_saved_and_loaded(self):
        corners = [[10, 20], [210, 18], [220, 320], [5, 300]]
        matrix = compute_warp_matrix(corners, output_size=(1000, 1000))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "vision_calibration.json")
            save_calibration(matrix, corners, path=path, output_size=(1000, 1000))
            loaded = load_calibration(path)
            payload = load_calibration_payload(path)

        self.assertIsNotNone(loaded)
        loaded_matrix, loaded_corners = loaded
        self.assertEqual(loaded_matrix.shape, (3, 3))
        self.assertEqual(len(loaded_corners), 4)
        self.assertIn("quality", payload["metadata"])

    def test_coordinate_system_exposes_round_trip_mapping_helpers(self):
        coord = BoardCoordinateSystem(GridConfig(rows=10, cols=9, width=1000, height=1000))
        point = coord.cell_to_pixel_center(2, 3)

        self.assertEqual(coord.pixel_to_cell(*point), (2, 3))
        self.assertEqual(coord.pixel_to_key(*point), "2,3")
        self.assertEqual(coord.key_to_pixel_center("2,3"), point)
        self.assertEqual(coord.pixels_to_cell_details([point])[0].key, "2,3")

    def test_coordinate_system_uses_stable_half_up_snapping(self):
        coord = BoardCoordinateSystem(GridConfig(rows=10, cols=9, width=901, height=1001))

        self.assertEqual(coord.pixel_to_cell(coord.cell_w * 2.5, coord.cell_h * 4), (3, 4))
        detail = coord.pixel_to_cell_detail(coord.cell_w * 3 + 2, coord.cell_h * 4 - 3)

        self.assertIsNotNone(detail)
        self.assertEqual(detail.key, "3,4")
        self.assertGreater(detail.distance_px, 0)

    def test_image_preprocessor_modes_keep_shape_and_allow_raw(self):
        frame = np.zeros((24, 32, 3), dtype=np.uint8)
        old_mode = getattr(config, "VISION_PREPROCESS_MODE", "fast")
        try:
            config.VISION_PREPROCESS_MODE = "off"
            raw = ImagePreprocessor().process(frame)
            self.assertIs(raw, frame)

            config.VISION_PREPROCESS_MODE = "fast"
            fast = ImagePreprocessor().process(frame)
            self.assertEqual(fast.shape, frame.shape)

            config.VISION_PREPROCESS_MODE = "balanced"
            balanced = ImagePreprocessor().process(frame)
            self.assertEqual(balanced.shape, frame.shape)
        finally:
            config.VISION_PREPROCESS_MODE = old_mode


if __name__ == "__main__":
    unittest.main()
