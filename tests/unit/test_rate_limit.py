import unittest

from backend.utils.rate_limit import FixedWindowRateLimiter, RateLimitExceeded


class TestRateLimit(unittest.TestCase):
    def test_fixed_window_blocks_after_limit(self):
        limiter = FixedWindowRateLimiter()
        limiter.check("client", limit=2, window_seconds=60)
        limiter.check("client", limit=2, window_seconds=60)

        with self.assertRaises(RateLimitExceeded) as ctx:
            limiter.check("client", limit=2, window_seconds=60)

        self.assertGreaterEqual(ctx.exception.retry_after_seconds, 1)

    def test_bucket_count_is_bounded_and_clear_resets_state(self):
        limiter = FixedWindowRateLimiter(max_buckets=2)
        limiter.check("a", limit=10, window_seconds=60)
        limiter.check("b", limit=10, window_seconds=60)
        limiter.check("c", limit=10, window_seconds=60)

        self.assertLessEqual(limiter.bucket_count(), 2)
        limiter.clear()
        self.assertEqual(limiter.bucket_count(), 0)


if __name__ == "__main__":
    unittest.main()
