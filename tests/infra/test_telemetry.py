from __future__ import annotations

import unittest

from shopq.observability.telemetry import (
    counter,
    get_latency_stats,
    get_p95,
    reset_latencies,
    time_block,
)


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        reset_latencies()

    def test_time_block_appends_ms_suffix(self):
        metric_name = "gmail.fetch.latency"

        with time_block(metric_name):
            pass

        stats = get_latency_stats(metric_name)
        self.assertEqual(stats["count"], 1)

        p95 = get_p95(metric_name)
        self.assertGreaterEqual(p95, 0.0)

    def test_time_block_respects_existing_suffix(self):
        metric_name = "pipeline.total_ms"

        with time_block(metric_name):
            pass

        stats = get_latency_stats(metric_name)
        self.assertEqual(stats["count"], 1)

    def test_counter_increments(self):
        before = counter("test.counter", 0)
        counter("test.counter")
        after = counter("test.counter", 0)
        self.assertEqual(after, before + 1)


if __name__ == "__main__":
    unittest.main()
