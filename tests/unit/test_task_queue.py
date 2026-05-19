import unittest

from backend.app.task_queue import TaskQueueRegistry


class TestTaskQueueRegistry(unittest.TestCase):
    def test_clear_deduplicates_hooks_and_skips_observers_by_default(self):
        registry = TaskQueueRegistry()
        calls = []

        registry.register_clear_hook(lambda: calls.append("work"), key="work")
        registry.register_clear_hook(lambda: calls.append("duplicate"), key="work")
        registry.register_clear_hook(lambda: calls.append("observer"), key="observer", kind="observer")

        registry.clear()

        self.assertEqual(calls, ["work"])
        self.assertEqual(registry.hook_count(), 2)
        self.assertEqual(registry.hook_count(include_observers=False), 1)


if __name__ == "__main__":
    unittest.main()
