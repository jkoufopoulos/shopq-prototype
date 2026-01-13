"""
Minimal telemetry helpers used during refactor bootstrapping.

These wrappers do not send metrics externally yet; they provide structured
logging and in-memory counters so tests can assert instrumentation.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger("shopq.telemetry")

_COUNTERS: dict[str, int] = {}
_LATENCIES: dict[str, list[float]] = {}


def _normalize_latency_name(metric_name: str) -> str:
    if metric_name.endswith("_ms"):
        return metric_name
    if metric_name.endswith(".latency"):
        return f"{metric_name}_ms"
    return metric_name


def log_event(event_name: str, **fields: Any) -> None:
    """
    Structured log event. Caller must ensure PII is anonymized/redacted.

    Side Effects:
        - Writes to logger (info level)
    """
    logger.info("event=%s %s", event_name, fields)


def counter(name: str, increment: int = 1) -> int:
    """
    Increment an in-memory counter and emit a debug log.

    Side Effects:
        - Modifies _COUNTERS dict (in-memory state)
        - Writes to logger (debug level)
    """
    value = _COUNTERS.get(name, 0) + increment
    _COUNTERS[name] = value
    logger.debug("counter=%s value=%s", name, value)
    return value


@contextlib.contextmanager
def time_block(metric_name: str) -> Iterator[None]:
    """
    Context manager for timing code blocks.
    Records latency for P95 calculation.

    Side Effects:
        - Appends to _LATENCIES dict (in-memory state)
        - Writes to logger (debug level) with timing
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        normalized = _normalize_latency_name(metric_name)
        logger.debug("timing=%s seconds=%.6f", normalized, elapsed)

        # Record latency for percentile tracking
        if normalized not in _LATENCIES:
            _LATENCIES[normalized] = []
        _LATENCIES[normalized].append(elapsed)


def get_p95(metric_name: str) -> float:
    """
    Calculate P95 latency for a given metric.
    Returns 0.0 if no samples recorded.
    """
    normalized = _normalize_latency_name(metric_name)
    samples = _LATENCIES.get(normalized, [])
    if not samples:
        return 0.0

    sorted_samples = sorted(samples)
    idx = int(len(sorted_samples) * 0.95)
    return sorted_samples[idx] if idx < len(sorted_samples) else sorted_samples[-1]


def get_latency_stats(metric_name: str) -> dict[str, float]:
    """
    Get latency statistics (min, max, avg, p50, p95, p99) for a metric.
    """
    normalized = _normalize_latency_name(metric_name)
    samples = _LATENCIES.get(normalized, [])
    if not samples:
        return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}

    sorted_samples = sorted(samples)
    count = len(sorted_samples)

    return {
        "count": count,
        "min": sorted_samples[0],
        "max": sorted_samples[-1],
        "avg": sum(sorted_samples) / count,
        "p50": sorted_samples[int(count * 0.50)],
        "p95": sorted_samples[int(count * 0.95)],
        "p99": sorted_samples[int(count * 0.99)] if count > 1 else sorted_samples[-1],
    }


def reset_latencies() -> None:
    """
    Clear all recorded latencies (useful for tests).

    Side Effects:
        - Clears _LATENCIES dict (in-memory state)
    """
    _LATENCIES.clear()
