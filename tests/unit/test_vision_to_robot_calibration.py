from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from backend.application.services.vision_service import VisionService
from backend.interfaces.api.shared import api_bp
from backend.interfaces.api import auth_guard, robot_routes  # noqa: F401
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.utils.kinematics import Kinematics


class VisionToRobotCalibrationTest(unittest.TestCase):
    def test_four_point_homography_maps_center_to_robot_xy(self):
        mapper = Kinematics()
        mapper.calibrate_vision_to_robot(
            image_points=[
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
                [0.0, 10.0],
            ],
            robot_points=[
                [100.0, 200.0],
                [200.0, 200.0],
                [200.0, 300.0],
                [100.0, 300.0],
            ],
            coordinate_space="camera_frame",
        )

        xy = mapper.vision_point_to_robot(5.0, 5.0, coordinate_space="camera_frame")

        self.assertIsNotNone(xy)
        self.assertAlmostEqual(xy[0], 150.0, places=4)
        self.assertAlmostEqual(xy[1], 250.0, places=4)

    def test_coordinate_space_mismatch_is_rejected(self):
        mapper = Kinematics()
        mapper.calibrate_vision_to_robot(
            image_points=[[0, 0], [10, 0], [10, 10], [0, 10]],
            robot_points=[[100, 200], [200, 200], [200, 300], [100, 300]],
            coordinate_space="camera_frame",
        )

        with self.assertRaises(ValueError):
            mapper.vision_point_to_robot(5.0, 5.0, coordinate_space="rectified_board")

    def test_robot_api_calibrates_and_maps_vision_point(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(api_bp, url_prefix="/api")
        client = app.test_client()
        mapper = Kinematics()

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(robot_routes, "kinematics", mapper):
                response = client.post(
                    "/api/robot/calibration",
                    json={
                        "persist": False,
                        "vision_to_robot": {
                            "coordinate_space": "camera_frame",
                            "image_points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                            "robot_points": [[100, 200], [200, 200], [200, 300], [100, 300]],
                        },
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.get_json()["calibration"]["vision_to_robot"]["calibrated"])

                response = client.post(
                    "/api/robot/vision-point",
                    json={"point": [5, 5], "coordinate_space": "camera_frame", "z": 77.0},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pose"][2], 77.0)
        self.assertAlmostEqual(payload["robot"]["x"], 150.0, places=4)
        self.assertAlmostEqual(payload["robot"]["y"], 250.0, places=4)

    def test_vision_service_preserves_robot_anchor_metadata(self):
        service = VisionService.__new__(VisionService)
        service._vision = SimpleNamespace(mapper=None)
        detection = Detection(
            class_id=1,
            class_name="red_rook",
            confidence=0.9,
            bbox=BoundingBox(1.0, 2.0, 3.0, 4.0),
        )

        payload = service._serialize_detection(
            detection,
            source={
                "robot_anchor_point": [123.4, 567.8],
                "robot_coordinate_space": "robot_base_xy",
                "vision_to_robot_coordinate_space": "camera_frame",
            },
        )

        self.assertEqual(payload["robot_anchor_point"], [123.4, 567.8])
        self.assertEqual(payload["robot_coordinate_space"], "robot_base_xy")
        self.assertEqual(payload["vision_to_robot_coordinate_space"], "camera_frame")


if __name__ == "__main__":
    unittest.main()
