import unittest
from unittest.mock import patch

from backend.events.bus.event_bus import EventBus
from backend.events.models.base_event import BaseEvent
from backend.utils import config


def event(event_type, payload=None):
    return BaseEvent.create(event_type=event_type, source="unit", payload=payload or {})


class TestEventBus(unittest.TestCase):
    def test_keyed_global_subscriber_replaces_stale_handler(self):
        bus = EventBus(is_singleton=False)
        calls = []

        def stale(event):
            calls.append(("stale", event.event_type))

        def current(event):
            calls.append(("current", event.event_type))

        bus.subscribe_all(stale, key="socketio.forward_event", replace=True)
        bus.subscribe_all(current, key="socketio.forward_event", replace=True)

        bus.publish(event("TEST.EVENT"))

        self.assertEqual(calls, [("current", "TEST.EVENT")])
        self.assertEqual(bus.stats()["global_subscribers"], 1)
        self.assertEqual(bus.stats()["keyed_global_subscribers"], 1)

    def test_duplicate_specific_subscriber_is_ignored(self):
        bus = EventBus(is_singleton=False)
        calls = []

        def handler(event):
            calls.append(event.event_type)

        bus.subscribe("TEST.EVENT", handler)
        bus.subscribe("TEST.EVENT", handler)

        bus.publish(event("TEST.EVENT"))

        self.assertEqual(calls, ["TEST.EVENT"])
        self.assertEqual(bus.stats()["specific_subscribers"], 1)

    def test_async_subscriber_runs_on_registered_runtime(self):
        from backend.application.container import container

        original_services = dict(container._services)
        calls = []

        class FakeLoop:
            def is_running(self):
                return True

            def call_soon_threadsafe(self, fn, *args):
                fn(*args)

        class FakeRuntime:
            def __init__(self):
                self.submitted = []

            def run_task(self, coro):
                import asyncio

                self.submitted.append(coro)
                return asyncio.run(coro)

        fake_runtime = FakeRuntime()
        container.register("runtime", fake_runtime)
        container.register("loop", FakeLoop())

        async def handler(event):
            calls.append(event.event_type)

        try:
            bus = EventBus(is_singleton=False)
            bus.subscribe("TEST.ASYNC", handler, is_async=True)
            bus.publish(event("TEST.ASYNC"))
        finally:
            container._services = original_services

        self.assertEqual(calls, ["TEST.ASYNC"])
        self.assertEqual(len(fake_runtime.submitted), 1)

    def test_handler_failure_publishes_system_error_once(self):
        bus = EventBus(is_singleton=False)
        system_errors = []

        def failing_handler(event):
            raise RuntimeError("boom")

        def system_error_handler(event):
            system_errors.append(event)

        bus.subscribe("TEST.FAIL", failing_handler)
        bus.subscribe("SYSTEM_ERROR", system_error_handler)

        bus.publish(event("TEST.FAIL"))

        self.assertEqual(len(system_errors), 1)
        self.assertEqual(system_errors[0].event_type, "SYSTEM_ERROR")
        self.assertEqual(system_errors[0].payload["event_type"], "TEST.FAIL")
        self.assertEqual(bus.stats()["dead_letters"], 0)

    def test_system_error_failure_is_dead_lettered_not_recursive(self):
        bus = EventBus(is_singleton=False)
        calls = []

        def failing_system_error_handler(event):
            calls.append(event)
            raise RuntimeError("system error handler failed")

        bus.subscribe("SYSTEM_ERROR", failing_system_error_handler)

        bus.publish(event("SYSTEM_ERROR"))

        self.assertEqual(len(calls), 1)
        self.assertEqual(bus.stats()["dead_letters"], 1)

    def test_legacy_dict_events_are_counted_and_resettable(self):
        bus = EventBus(is_singleton=False, allow_legacy_dict_events=True)
        calls = []
        bus.subscribe("TEST.LEGACY", lambda event: calls.append(event.event_type))

        bus.publish_from_legacy({"type": "TEST.LEGACY", "payload": {}, "source": "unit"})
        bus.publish_from_legacy({"type": "TEST.LEGACY", "payload": {}, "source": "unit"})

        self.assertEqual(calls, ["TEST.LEGACY", "TEST.LEGACY"])
        stats = bus.stats()
        self.assertEqual(stats["legacy_dict_events"], 2)
        self.assertEqual(stats["legacy_dict_event_types"], {"TEST.LEGACY": 2})

        bus.reset_for_tests()

        stats = bus.stats()
        self.assertEqual(stats["legacy_dict_events"], 0)
        self.assertEqual(stats["legacy_dict_event_types"], {})
        self.assertEqual(stats["sequence"], 0)

    def test_legacy_dict_events_are_disabled_by_default(self):
        with patch.object(config, "EVENTBUS_ALLOW_LEGACY_DICT_EVENTS", False):
            bus = EventBus(is_singleton=False)

            bus.publish_from_legacy({"type": "TEST.LEGACY", "payload": {}, "source": "unit"})

            stats = bus.stats()
        self.assertFalse(stats["legacy_dict_enabled"])
        self.assertEqual(stats["legacy_dict_events"], 0)
        self.assertEqual(stats["dead_letters"], 1)

    def test_legacy_dict_events_can_be_disabled(self):
        bus = EventBus(is_singleton=False, allow_legacy_dict_events=False)
        calls = []
        bus.subscribe("TEST.LEGACY", lambda event: calls.append(event.event_type))

        bus.publish_from_legacy({"type": "TEST.LEGACY", "payload": {}, "source": "unit"})

        stats = bus.stats()
        self.assertEqual(calls, [])
        self.assertFalse(stats["legacy_dict_enabled"])
        self.assertEqual(stats["legacy_dict_events"], 0)
        self.assertEqual(stats["dead_letters"], 1)


if __name__ == "__main__":
    unittest.main()
