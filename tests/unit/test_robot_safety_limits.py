from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.infrastructure.robot.safety import RobotSafety


class RobotSafetyLimitsTest(unittest.TestCase):
    def setUp(self):
        cfg = SimpleNamespace(
            ROBOT_MIN_X=-100.0,
            ROBOT_MAX_X=100.0,
            ROBOT_MIN_Y=10.0,
            ROBOT_MAX_Y=200.0,
            ROBOT_MIN_Z=20.0,
            ROBOT_MAX_Z=250.0,
            SOFT_LIMIT_X=(-100.0, 100.0),
            SOFT_LIMIT_Y=(10.0, 200.0),
            SOFT_LIMIT_Z=(20.0, 250.0),
            Z_SAFE=150.0,
            Z_GRAB=30.0,
        )
        self.safety = RobotSafety(cfg)

    def test_accepts_finite_position_inside_workspace(self):
        self.assertEqual(self.safety.validate_position(0, 100, 150), (True, "Safe"))

    def test_rejects_target_outside_xy_workspace(self):
        ok, message = self.safety.validate_position(101, 100, 150)
        self.assertFalse(ok)
        self.assertIn("X coordinate", message)

    def test_rejects_height_outside_z_workspace(self):
        ok, message = self.safety.validate_position(0, 100, 19)
        self.assertFalse(ok)
        self.assertIn("Z coordinate", message)

    def test_rejects_non_finite_coordinates(self):
        ok, message = self.safety.validate_position(float("nan"), 100, 150)
        self.assertFalse(ok)
        self.assertIn("finite", message)


if __name__ == "__main__":
    unittest.main()
