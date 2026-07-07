import asyncio
import unittest

from backend.runtime.messaging.queues import AsyncQueueManager


class TestAsyncQueueManager(unittest.TestCase):
    def test_put_latest_records_drop_oldest_stats(self):
        async def scenario():
            manager = AsyncQueueManager()
            queue = manager.frame_queue
            await manager.put_latest(queue, "old")
            await manager.put_latest(queue, "new")
            return queue, manager.stats()

        queue, stats = asyncio.run(scenario())

        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(queue.get_nowait(), "new")
        self.assertEqual(stats["frame"]["policy"], "latest-only")
        self.assertEqual(stats["frame"]["dropped_oldest"], 1)
        self.assertEqual(stats["frame"]["put_count"], 2)
        self.assertEqual(stats["frame"]["get_count"], 0)
        self.assertEqual(stats["frame"]["blocked_reason"], "full")
        self.assertEqual(stats["frame"]["status"], "blocked")
        self.assertIn("blocked", stats["frame"])
        self.assertIn("age_sec", stats["frame"])
        self.assertIn("consumer_idle_sec", stats["frame"])
        self.assertIn("utilization", stats["frame"])

    def test_queue_stats_mark_full_queue_blocked(self):
        async def scenario():
            manager = AsyncQueueManager()
            queue = manager.frame_queue
            await manager.put_latest(queue, "frame")
            return manager.stats()

        stats = asyncio.run(scenario())

        self.assertTrue(stats["frame"]["full"])
        self.assertTrue(stats["frame"]["blocked"])

    def test_consumer_gets_are_recorded_without_counting_drops(self):
        async def scenario():
            manager = AsyncQueueManager()
            queue = manager.frame_queue
            await manager.put_latest(queue, "old")
            await manager.put_latest(queue, "new")
            item = await queue.get()
            return item, manager.stats()

        item, stats = asyncio.run(scenario())

        self.assertEqual(item, "new")
        self.assertEqual(stats["frame"]["dropped_oldest"], 1)
        self.assertEqual(stats["frame"]["get_count"], 1)
        self.assertEqual(stats["frame"]["size"], 0)
        self.assertEqual(stats["frame"]["status"], "warning")

    def test_stale_non_full_queue_is_marked_blocked(self):
        async def scenario():
            manager = AsyncQueueManager()
            queue = manager.robot_queue
            await manager.put_latest(queue, "move")
            manager._last_put_at["robot"] -= manager._blocked_after_sec + 1.0
            return manager.stats()

        stats = asyncio.run(scenario())

        self.assertFalse(stats["robot"]["full"])
        self.assertTrue(stats["robot"]["blocked"])
        self.assertEqual(stats["robot"]["blocked_reason"], "stale_item")


if __name__ == "__main__":
    unittest.main()
