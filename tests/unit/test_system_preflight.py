import unittest

from backend.application.services import system_preflight
from backend.utils import config


class TestSystemPreflightNetworkConfig(unittest.TestCase):
    def setUp(self):
        self.old_robot_ip = getattr(config, "ROBOT_IP", None)
        self.old_robot_pc_ip = getattr(config, "ROBOT_PC_IP", None)
        self.old_subnet_mask = getattr(config, "ROBOT_SUBNET_MASK", None)
        self.old_vision_source = getattr(config, "VISION_SOURCE", None)
        self.old_ingest_key = getattr(config, "VISION_TMFLOW_INGEST_KEY", None)
        self.old_fake_robot = getattr(config, "FAKE_ROBOT", None)
        self.old_bind_host = getattr(config, "BIND_HOST", None)
        self.old_is_production = getattr(config, "IS_PRODUCTION", None)

    def tearDown(self):
        config.ROBOT_IP = self.old_robot_ip
        config.ROBOT_PC_IP = self.old_robot_pc_ip
        config.ROBOT_SUBNET_MASK = self.old_subnet_mask
        config.VISION_SOURCE = self.old_vision_source
        config.VISION_TMFLOW_INGEST_KEY = self.old_ingest_key
        config.FAKE_ROBOT = self.old_fake_robot
        config.BIND_HOST = self.old_bind_host
        config.IS_PRODUCTION = self.old_is_production

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


if __name__ == "__main__":
    unittest.main()
