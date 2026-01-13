from __future__ import annotations

import pytest

from mailq.infrastructure.idempotency import email_key, is_duplicate, reset_seen
from mailq.infrastructure.retry import AdapterError, CircuitBreaker, RetryPolicy
from mailq.observability.telemetry import _COUNTERS, counter


@pytest.fixture(autouse=True)
def reset_counters():
    _COUNTERS.clear()
    yield
    _COUNTERS.clear()


def test_retry_policy_retries_retryable_errors():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise AdapterError("server error", status_code=503)
        return "ok"

    policy = RetryPolicy(
        stage="test.retry", max_attempts=3, base_delay=0.0, jitter=0.0, sleep_fn=lambda _: None
    )
    result = policy.execute(flaky)
    assert result == "ok"
    assert attempts["count"] == 3
    assert counter("retry_count", 0) >= 2


def test_retry_policy_stops_on_non_retryable_error():
    attempts = {"count": 0}

    def bad_request():
        attempts["count"] += 1
        raise AdapterError("bad request", status_code=404)

    policy = RetryPolicy(
        stage="test.retry", max_attempts=3, base_delay=0.0, jitter=0.0, sleep_fn=lambda _: None
    )
    with pytest.raises(AdapterError):
        policy.execute(bad_request)
    assert attempts["count"] == 1


def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(stage="test.circuit", fail_max=1, reset_timeout=60.0)
    assert breaker.allow_request() is True
    breaker.record_failure()
    assert breaker.allow_request() is False
    assert counter("circuit_open_rate", 0) >= 1


def test_duplicate_tracking_increments_counter():
    reset_seen()
    key = email_key("msg-dup", "2025-11-02T12:00:00Z", "body")
    assert is_duplicate(key) is False
    before = counter("idempotency_drops", 0)
    assert is_duplicate(key) is True
    after = counter("idempotency_drops", 0)
    assert after >= before + 1


def test_email_key_stability():
    reset_seen()
    key1 = email_key("msg-stable", "2025-11-02T12:00:00Z", "hello")
    key2 = email_key("msg-stable", "2025-11-02T12:00:00Z", "hello")
    assert key1 == key2
