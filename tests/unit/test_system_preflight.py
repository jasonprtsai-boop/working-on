import unittest
from unittest.mock import patch

from backend.application.services import system_preflight
from backend.interfaces.api import shared
from backend.utils import config


class TestSystemPreflightNetworkConfig(unittest.TestCase):
    def setUp(self):
        self.old_robot_ip = getattr(config, "ROBOT_IP", None)
        self.old_robot_port = getattr(config, "ROBOT_PORT", None)
        self.old_robot_timeout = getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", None)
        self.old_robot_pc_ip = getattr(config, "ROBOT_PC_IP", None)
        self.old_subnet_mask = getattr(config, "ROBOT_SUBNET_MASK", None)
        self.old_vision_source = getattr(config, "VISION_SOURCE", None)
        self.old_ingest_key = getattr(config, "VISION_TMFLOW_INGEST_KEY", None)
        self.old_fake_robot = getattr(config, "FAKE_ROBOT", None)
        self.old_fake_vision = getattr(config, "FAKE_VISION", None)
        self.old_auto_execute = getattr(config, "AUTO_EXECUTE_ROBOT", None)
        self.old_bind_host = getattr(config, "BIND_HOST", None)
        self.old_is_production = getattr(config, "IS_PRODUCTION", None)

    def tearDown(self):
        config.ROBOT_IP = self.old_robot_ip
        config.ROBOT_PORT = self.old_robot_port
        config.ROBOT_CONNECT_TIMEOUT_SEC = self.old_robot_timeout
        config.ROBOT_PC_IP = self.old_robot_pc_ip
        config.ROBOT_SUBNET_MASK = self.old_subnet_mask
        config.VISION_SOURCE = self.old_vision_source
        config.VISION_TMFLOW_INGEST_KEY = self.old_ingest_key
        config.FAKE_ROBOT = self.old_fake_robot
        config.FAKE_VISION = self.old_fake_vision
        config.AUTO_EXECUTE_ROBOT = self.old_auto_execute
        config.BIND_HOST = self.old_bind_host
        config.IS_PRODUCTION = self.old_is_production

    def _patched_preflight_helpers(self, vision_readiness):
        return (
            patch.object(system_preflight, "_robot_status", return_value={"connected": True}),
            patch.object(system_preflight, "_robot_network_config", return_value={"ok": True, "message": "network ready", "details": {}}),
            patch.object(system_preflight, "_tmflow_vision_ingest_key_status", return_value={"ok": True, "message": "ingest key ready", "details": {}}),
            patch.object(system_preflight, "_motion_profile_safe", return_value=True),
            patch.object(system_preflight, "_board_and_dead_zone_safe", return_value=True),
            patch.object(system_preflight, "_vision_readiness_status", return_value=vision_readiness),
        )

    def _vision_check(self, report):
        return next(item for item in report["checks"] if item["key"] == "vision_ready")

    def test_robot_network_config_accepts_lab_subnet(self):
        config.ROBOT_IP = "192.168.10.10"
        config.ROBOT_PC_IP = "192.168.10.50"
        config.ROBOT_SUBNET_MASK = "255.255.0.0"

        result = system_preflight._robot_network_config()

        self.assertTrue(result["ok"])
        self.assertEqual(result["details"]["robot_network"], "192.168.0.0/16")
        self.assertEqual(result["details"]["pc_network"], "192.168.0.0/16")

    def test_robot_network_config_rejects_different_subnet(self):
        config.ROBOT_IP = "192.168.10.10"
        config.ROBOT_PC_IP = "10.10.10.50"
        config.ROBOT_SUBNET_MASK = "255.255.0.0"

        result = system_preflight._robot_network_config()

        self.assertFalse(result["ok"])
        self.assertIn("same subnet", result["message"])

    def test_tmflow_vision_ingest_key_required_for_real_robot(self):
        config.VISION_SOURCE = "tmflow_json"
        config.VISION_TMFLOW_INGEST_KEY = ""
        config.FAKE_ROBOT = False
        config.BIND_HOST = "127.0.0.1"
        config.IS_PRODUCTION = False

        result = system_preflight._tmflow_vision_ingest_key_status()

        self.assertFalse(result["ok"])
        self.assertTrue(result["details"]["required"])

    def test_tmflow_vision_ingest_key_optional_for_local_simulation(self):
        config.VISION_SOURCE = "tmflow_json"
        config.VISION_TMFLOW_INGEST_KEY = ""
        config.FAKE_ROBOT = True
        config.BIND_HOST = "127.0.0.1"
        config.IS_PRODUCTION = False

        result = system_preflight._tmflow_vision_ingest_key_status()

        self.assertTrue(result["ok"])
        self.assertFalse(result["details"]["required"])

    def test_robot_tcp_probe_attempts_tmflow_connection_for_real_robot(self):
        config.ROBOT_IP = "192.0.2.10"
        config.ROBOT_PORT = 5890
        config.ROBOT_CONNECT_TIMEOUT_SEC = 0.25

        with patch.object(system_preflight.socket, "create_connection") as connect:
            connect.return_value.__enter__.return_value = object()
            result = system_preflight._robot_tcp_connect_probe(
                fake_robot=False,
                adapter="tmflow_json",
                robot_status={"connected": False},
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["required"])
        connect.assert_called_once_with(("192.0.2.10", 5890), timeout=0.25)

    def test_robot_tcp_probe_reuses_existing_connected_status(self):
        with patch.object(system_preflight.socket, "create_connection") as connect:
            result = system_preflight._robot_tcp_connect_probe(
                fake_robot=False,
                adapter="tmflow_json",
                robot_status={"connected": True},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["details"]["source"], "robot_status")
        connect.assert_not_called()

    def test_real_robot_preflight_fails_when_vision_fell_back_to_simulation(self):
        config.FAKE_ROBOT = False
        config.AUTO_EXECUTE_ROBOT = True
        vision_readiness = {
            "ok": False,
            "message": "Real vision failed to start and fallback simulation is active.",
            "details": {"fallback": True, "fallback_reason": "model missing"},
        }
        patches = self._patched_preflight_helpers(vision_readiness)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            report = system_preflight.build_preflight_report()

        vision = self._vision_check(report)
        self.assertFalse(report["ready"])
        self.assertEqual(vision["severity"], "error")
        self.assertIn("fallback", vision["message"])
        self.assertEqual(vision["details"]["fallback_reason"], "model missing")

    def test_fake_robot_preflight_warns_when_vision_fell_back_to_simulation(self):
        config.FAKE_ROBOT = True
        config.AUTO_EXECUTE_ROBOT = False
        vision_readiness = {
            "ok": False,
            "message": "Real vision failed to start and fallback simulation is active.",
            "details": {"fallback": True, "fallback_reason": "model missing"},
        }
        patches = self._patched_preflight_helpers(vision_readiness)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            report = system_preflight.build_preflight_report()

        vision = self._vision_check(report)
        self.assertTrue(report["ready"])
        self.assertEqual(vision["severity"], "warning")
        self.assertTrue(any(item["key"] == "vision_ready" for item in report["warnings"]))

    def test_fake_vision_is_not_ready_for_real_robot_mode(self):
        config.FAKE_VISION = True
        result = system_preflight._vision_readiness_status(fake_robot=False)

        self.assertFalse(result["ok"])
        self.assertTrue(result["details"]["simulation"])
        self.assertIn("real robot", result["message"])

    def test_unavailable_real_vision_does_not_count_as_simulation_fallback(self):
        config.FAKE_VISION = False

        class UnavailableVision:
            def get_calibration_status(self):
                return {
                    "calibrated": False,
                    "loaded_from_file": False,
                    "simulation": False,
                    "fallback": False,
                    "startup_failure": True,
                    "startup_error": "camera offline",
                }

        with patch.object(
            shared,
            "runtime_vision_status",
            return_value={
                "system": "UnavailableVisionSystem",
                "mode": "unavailable",
                "available": False,
                "simulation": False,
                "fallback": False,
                "startup_failure": True,
                "startup_error": "camera offline",
            },
        ), patch.object(shared, "vision_system", UnavailableVision()):
            result = system_preflight._vision_readiness_status(fake_robot=False)

        self.assertFalse(result["ok"])
        self.assertFalse(result["details"]["simulation"])
        self.assertFalse(result["details"]["fallback"])
        self.assertEqual(result["details"]["startup_error"], "camera offline")
        self.assertIn("unavailable", result["message"])


if __name__ == "__main__":
    unittest.main()
