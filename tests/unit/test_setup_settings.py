import tempfile
import unittest
from pathlib import Path

from backend.interfaces.api.auth_guard import _has_required_role
from backend.interfaces.api.setup_routes import current_setup_settings, normalize_setup_settings
from backend.application.services.commissioning_report import (
    load_commissioning_report,
    mark_settings_saved,
    record_hardware_test,
    record_preflight,
)
from backend.utils.setup_settings import deep_merge, get_nested, load_settings, save_settings


class TestSetupSettings(unittest.TestCase):
    def test_setup_settings_round_trip_and_deep_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "setup_settings.json"
            save_settings({"robot": {"motion": {"z_safe": 120}}}, path)

            loaded = load_settings(path)
            merged = deep_merge(loaded, {"robot": {"motion": {"z_grab": 15}}})

            self.assertEqual(get_nested(loaded, "robot.motion.z_safe"), 120)
            self.assertEqual(merged["robot"]["motion"], {"z_safe": 120, "z_grab": 15})

    def test_normalize_setup_settings_accepts_safe_current_shape(self):
        base = current_setup_settings()
        normalized = normalize_setup_settings(base, base=base)

        self.assertEqual(normalized["vision"]["camera_index"], base["vision"]["camera_index"])
        self.assertIn(normalized["vision"]["source"], {"opencv", "tmflow_json"})
        self.assertIn("tmflow_json", normalized["vision"])
        self.assertIn("dead_zone_range", normalized["robot"]["calibration"])

    def test_normalize_setup_settings_accepts_tmflow_json_vision_source(self):
        base = current_setup_settings()
        normalized = normalize_setup_settings(
            {
                "vision": {
                    "source": "tmflow_json",
                    "tmflow_json": {
                        "host": "192.168.10.10",
                        "port": 5891,
                        "timeout_sec": 2.0,
                        "max_message_bytes": 1_048_576,
                        "fps_limit": 2.0,
                    },
                }
            },
            base=base,
        )

        self.assertEqual(normalized["vision"]["source"], "tmflow_json")
        self.assertEqual(normalized["vision"]["tmflow_json"]["host"], "192.168.10.10")
        self.assertEqual(normalized["vision"]["tmflow_json"]["port"], 5891)

    def test_normalize_setup_settings_rejects_invalid_vision_source(self):
        base = current_setup_settings()

        with self.assertRaises(ValueError):
            normalize_setup_settings({"vision": {"source": "unknown"}}, base=base)

    def test_normalize_setup_settings_accepts_techmanpy_tmflow_baseline(self):
        base = current_setup_settings()
        normalized = normalize_setup_settings(
            {
                "robot": {
                    "connection": {
                        "adapter": "techmanpy",
                        "ip": "192.168.10.10",
                        "port": 5890,
                        "pc_ip": "192.168.10.50",
                        "subnet_mask": "255.255.0.0",
                        "tmflow_version": "1.82",
                        "controller_version": "1.82.51",
                    },
                    "techmanpy": {
                        "require_listen_node": True,
                        "motion_mode": "ptp",
                    },
                }
            },
            base=base,
        )

        self.assertEqual(normalized["robot"]["connection"]["adapter"], "techmanpy")
        self.assertEqual(normalized["robot"]["connection"]["port"], 5890)
        self.assertEqual(normalized["robot"]["connection"]["ip"], "192.168.10.10")
        self.assertEqual(normalized["robot"]["techmanpy"]["motion_mode"], "ptp")

    def test_normalize_setup_settings_accepts_tmflow_json_baseline(self):
        base = current_setup_settings()
        normalized = normalize_setup_settings(
            {
                "robot": {
                    "connection": {
                        "adapter": "tmflow_json",
                        "ip": "192.168.10.10",
                        "port": 5890,
                        "pc_ip": "192.168.10.50",
                        "subnet_mask": "255.255.0.0",
                    },
                    "tmflow_json": {
                        "wire_format": "envelope",
                        "ack_timeout_sec": 2.0,
                        "done_timeout_sec": 30.0,
                        "long_task_timeout_sec": 90.0,
                    },
                }
            },
            base=base,
        )

        self.assertEqual(normalized["robot"]["connection"]["adapter"], "tmflow_json")
        self.assertEqual(normalized["robot"]["connection"]["port"], 5890)
        self.assertEqual(normalized["robot"]["tmflow_json"]["wire_format"], "envelope")

    def test_normalize_setup_settings_rejects_json_non_5890_port(self):
        base = current_setup_settings()
        payload = {
            "robot": {
                "connection": {
                    "adapter": "tmflow_json",
                    "port": 502,
                }
            }
        }

        with self.assertRaises(ValueError):
            normalize_setup_settings(payload, base=base)

    def test_normalize_setup_settings_rejects_unsafe_z_profile(self):
        base = current_setup_settings()
        payload = {
            "robot": {
                "motion": {
                    "z_safe": 10,
                    "z_grab": 20,
                }
            }
        }

        with self.assertRaises(ValueError):
            normalize_setup_settings(payload, base=base)

    def test_setup_role_is_scoped_below_admin(self):
        self.assertTrue(_has_required_role("setup", "setup"))
        self.assertTrue(_has_required_role("admin", "setup"))
        self.assertTrue(_has_required_role("setup", "operator"))
        self.assertFalse(_has_required_role("operator", "setup"))
        self.assertFalse(_has_required_role("setup", "admin"))

    def test_commissioning_report_tracks_setup_preflight_and_hardware(self):
        from backend.utils import config

        old_path = getattr(config, "COMMISSIONING_REPORT_FILE", None)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                config.COMMISSIONING_REPORT_FILE = str(Path(tmp) / "commissioning.json")

                mark_settings_saved({"robot": {"runtime": {"fake_robot": True}}, "vision": {"camera_index": 0}})
                record_preflight({"ready": True, "failures": [], "warnings": [], "checks": []})
                record_hardware_test("status", {"ok": True, "dry_run": True, "message": "validated"})
                report = load_commissioning_report()

                self.assertTrue(report["steps"]["settings_saved"]["ok"])
                self.assertTrue(report["steps"]["preflight"]["ok"])
                self.assertTrue(report["steps"]["hardware"]["ok"])
                self.assertIn("status", report["steps"]["hardware"]["actions"])
            finally:
                config.COMMISSIONING_REPORT_FILE = old_path


if __name__ == "__main__":
    unittest.main()
