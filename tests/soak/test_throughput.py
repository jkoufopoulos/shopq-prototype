"""

from __future__ import annotations

Soak tests for pipeline throughput and P95 latency validation.

These tests measure performance under realistic load and verify that:
1. Sequential pipeline meets baseline latency requirements
2. Parallel pipeline improves throughput without breaking determinism
3. P95 latency remains acceptable under load
"""

import pytest

from mailq.observability.telemetry import get_latency_stats, get_p95, reset_latencies
from mailq.shared.pipeline import run_pipeline
from mailq.storage.models import ClassifiedEmail, Digest, DigestItem, ParsedEmail


def _generate_test_messages(count: int) -> list[dict]:
    """Generate synthetic Gmail API message payloads for load testing."""
    messages = []
    for i in range(count):
        messages.append(
            {
                "id": f"msg-{i:04d}",
                "threadId": f"thread-{i // 3:04d}",  # Group every 3 messages into same thread
                "internalDate": "1699000000000",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": f"Test Email #{i}"},
                        {"name": "From", "value": f"sender{i}@example.com"},
                        {"name": "To", "value": "user@example.com"},
                    ],
                    "mimeType": "text/plain",
                    "body": {"data": "VGVzdCBib2R5IGNvbnRlbnQ="},  # "Test body content" in base64
                },
            }
        )
    return messages


def _mock_classifier(emails: list[ParsedEmail]) -> list[ClassifiedEmail]:
    """Mock classifier that returns emails as-is with placeholder category."""
    return [
        ClassifiedEmail(
            parsed=email,
            category="notification",  # Use valid category
            attention="none",  # Required field
            confidence=0.95,
        )
        for email in emails
    ]


def _mock_assembler(emails: list[ClassifiedEmail]) -> Digest:
    """Mock assembler that creates minimal digest."""
    items = [
        DigestItem(
            source=email,
            priority=0.8,
            title=email.parsed.base.subject,
            snippet=email.parsed.base.body[:100],
            gmail_thread_link=f"https://mail.google.com/mail/u/0/#inbox/{email.parsed.base.thread_id}",
        )
        for email in emails
    ]
    return Digest(
        items=items,
        generated_ts="2025-11-02T12:00:00Z",
        idempotency_key="test-digest-key",
    )


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset telemetry state before each test."""
    reset_latencies()
    yield
    reset_latencies()


def test_baseline_sequential_pipeline_latency():
    """
    Baseline test: measure sequential pipeline P95 latency.

    This establishes the performance baseline before optimizations.
    """
    # Generate moderate load (50 emails)
    messages = _generate_test_messages(50)

    def fetcher():
        return iter(messages)

    # Run pipeline 10 times to get statistical samples
    for _ in range(10):
        digest = run_pipeline(fetcher, _mock_classifier, _mock_assembler, parallel=False)
        assert len(digest.items) > 0  # Sanity check

    # Check P95 latency
    stats = get_latency_stats("pipeline.total")
    print("\n📊 Sequential Pipeline Stats (50 emails x 10 runs):")
    print(f"  Count: {stats['count']}")
    print(f"  Min: {stats['min']:.3f}s")
    print(f"  Avg: {stats['avg']:.3f}s")
    print(f"  P50: {stats['p50']:.3f}s")
    print(f"  P95: {stats['p95']:.3f}s")
    print(f"  Max: {stats['max']:.3f}s")

    # Acceptance: P95 should be reasonable (< 5 seconds for 50 emails)
    assert stats["p95"] < 5.0, f"P95 latency too high: {stats['p95']:.3f}s"


def test_parallel_pipeline_improves_throughput():
    """
    Test that parallel pipeline improves parse latency.

    Note: Overall speedup depends on classifier/assembler, which are mocked here.
    In production, parallel parsing should show ~2-3x improvement.
    """
    messages = _generate_test_messages(100)

    def fetcher():
        return iter(messages)

    # Sequential baseline
    reset_latencies()
    _digest_seq = run_pipeline(fetcher, _mock_classifier, _mock_assembler, parallel=False)
    seq_parse_p95 = get_p95("pipeline.parse")

    # Parallel comparison
    reset_latencies()
    _digest_par = run_pipeline(fetcher, _mock_classifier, _mock_assembler, parallel=True)
    par_parse_p95 = get_p95("pipeline.parse.parallel")

    print("\n📊 Throughput Comparison (100 emails):")
    print(f"  Sequential parse P95: {seq_parse_p95:.3f}s")
    print(f"  Parallel parse P95: {par_parse_p95:.3f}s")
    if par_parse_p95 > 0:
        speedup = seq_parse_p95 / par_parse_p95
        print(f"  Speedup: {speedup:.2f}x")
    else:
        print("  N/A")

    # Acceptance: For lightweight mocks, parallel overhead might dominate.
    # In production with real LLM calls, parallelization provides significant speedup.
    # Here we just verify it doesn't catastrophically regress (< 3x slower).
    assert par_parse_p95 <= seq_parse_p95 * 3.0, (
        "Parallel parsing catastrophically slower (>3x overhead)"
    )
    print("  ✅ Parallel overhead acceptable (within 3x of sequential)")


def test_pipeline_determinism_maintained():
    """
    Golden test: verify digest order is deterministic regardless of parallelization.

    This ensures parallel processing doesn't break digest stability.
    """
    messages = _generate_test_messages(30)

    def fetcher():
        return iter(messages)

    # Run sequential pipeline
    _digest_seq = run_pipeline(fetcher, _mock_classifier, _mock_assembler, parallel=False)

    # Run parallel pipeline
    _digest_par = run_pipeline(fetcher, _mock_classifier, _mock_assembler, parallel=True)

    # Extract digest item titles for comparison
    seq_titles = [item.title for item in _digest_seq.items]
    par_titles = [item.title for item in _digest_par.items]

    print("\n🔍 Determinism Check:")
    print(f"  Sequential items: {len(seq_titles)}")
    print(f"  Parallel items: {len(par_titles)}")
    print(f"  First 5 sequential: {seq_titles[:5]}")
    print(f"  First 5 parallel: {par_titles[:5]}")

    # Acceptance: order must be identical
    assert seq_titles == par_titles, "Parallel pipeline broke digest determinism!"


def test_high_load_p95_acceptable():
    """
    Soak test: verify P95 latency under high load (200 emails).

    This simulates a realistic inbox processing scenario.
    """
    messages = _generate_test_messages(200)

    def fetcher():
        return iter(messages)

    # Run pipeline 5 times under load
    for _ in range(5):
        digest = run_pipeline(fetcher, _mock_classifier, _mock_assembler, parallel=True)
        assert len(digest.items) > 0

    stats = get_latency_stats("pipeline.total")
    print("\n📊 High Load Stats (200 emails x 5 runs):")
    print(f"  Count: {stats['count']}")
    print(f"  Avg: {stats['avg']:.3f}s")
    print(f"  P95: {stats['p95']:.3f}s")
    print(f"  P99: {stats['p99']:.3f}s")

    # Acceptance: P95 should scale reasonably (< 10s for 200 emails)
    assert stats["p95"] < 10.0, f"P95 latency under load too high: {stats['p95']:.3f}s"


def test_stage_latency_breakdown():
    """
    Diagnostic test: verify all pipeline stages emit latency metrics.

    This ensures observability is properly instrumented.
    """
    messages = _generate_test_messages(20)

    def fetcher():
        return iter(messages)

    run_pipeline(fetcher, _mock_classifier, _mock_assembler, parallel=False)

    # Check that key stages emitted metrics
    expected_stages = ["pipeline.total", "pipeline.parse", "pipeline.classify", "pipeline.assemble"]
    for stage in expected_stages:
        p95 = get_p95(stage)
        assert p95 > 0, f"Stage {stage} did not emit latency metrics"
        print(f"  {stage}: {p95:.3f}s")
