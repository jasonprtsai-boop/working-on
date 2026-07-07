import unittest

from backend.runtime.contract_schema import normalize_diagnostics_payload, validate_contract_payload
from backend.interfaces.api.shared import has_module


class TestDiagnosticsContract(unittest.TestCase):
    def test_normalization_adds_queue_aliases_and_runtime_group(self):
        payload = normalize_diagnostics_payload({
            "queues": {"robot": {"size": 1}},
            "event_bus": {"sequence": 7},
            "persistence": {"dropped_events": 0},
            "async_runtime": {"loop_running": True},
            "control": {"safe_mode": True},
            "custom": "kept-for-debug",
        })

        self.assertEqual(payload["queue"], payload["queues"])
        self.assertEqual(payload["queue"]["robot"]["size"], 1)
        self.assertEqual(payload["runtime"]["event_bus"]["sequence"], 7)
        self.assertTrue(payload["runtime"]["async_runtime"]["loop_running"])
        self.assertEqual(payload["ui"]["extras"]["custom"], "kept-for-debug")
        validate_contract_payload("DIAGNOSTICS.UPDATED", payload)

    def test_normalization_preserves_queue_as_queues_alias(self):
        payload = normalize_diagnostics_payload({"queue": {"frame": {"blocked": True}}})

        self.assertEqual(payload["queues"], payload["queue"])
        self.assertTrue(payload["queues"]["frame"]["blocked"])
        validate_contract_payload("DIAGNOSTICS.UPDATED", payload)

    def test_module_probe_uses_lightweight_spec_lookup(self):
        self.assertTrue(has_module("json"))
        self.assertFalse(has_module("smart_chess_missing_dependency_for_test"))


if __name__ == "__main__":
    unittest.main()
