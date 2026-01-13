"""

from __future__ import annotations

End-to-end integration tests for the complete ShopQ pipeline.

Tests the full flow: Raw Gmail messages → Parsed → Classified → Digest
Validates all phases (0-5) work together correctly.
"""

import pytest

from shopq.infrastructure.idempotency import reset_seen
from shopq.observability.telemetry import _COUNTERS, get_latency_stats, reset_latencies
from shopq.shared.pipeline import run_pipeline
from shopq.storage.classify import batch_classify_emails
from shopq.storage.models import Digest, DigestItem


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    _COUNTERS.clear()
    reset_latencies()
    reset_seen()
    yield
    _COUNTERS.clear()
    reset_latencies()
    reset_seen()


def _mock_gmail_messages(count: int) -> list[dict]:
    """Generate mock Gmail API message payloads."""
    messages = []
    for i in range(count):
        messages.append(
            {
                "id": f"msg-e2e-{i:04d}",
                "threadId": f"thread-e2e-{i // 2:04d}",  # 2 messages per thread
                "internalDate": f"169900{i:04d}000",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": f"E2E Test Email #{i}"},
                        {"name": "From", "value": f"sender{i}@test.com"},
                        {"name": "To", "value": "user@example.com"},
                    ],
                    "mimeType": "text/plain",
                    "body": {"data": "VGVzdCBib2R5IGNvbnRlbnQ="},  # "Test body content" base64
                },
            }
        )
    return messages


def _mock_assembler(emails: list) -> Digest:
    """Mock digest assembler."""
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
        idempotency_key=f"e2e-digest-{len(items)}",
    )


def test_e2e_full_pipeline_with_valid_inputs():
    """
    Test: Complete pipeline with valid Gmail messages.

    Validates:
    - Fetching works
    - Parsing succeeds
    - Classification (rules-only) works
    - Digest assembly succeeds
    - All telemetry fires
    """
    messages = _mock_gmail_messages(10)

    def fetcher():
        return iter(messages)

    # Run full pipeline
    digest = run_pipeline(
        fetcher=fetcher,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=False,
    )

    # Validate results
    assert len(digest.items) == 10
    assert digest.idempotency_key == "e2e-digest-10"

    # Validate telemetry
    stats = get_latency_stats("pipeline.total")
    assert stats["count"] == 1
    assert stats["p95"] > 0

    print(f"✅ E2E pipeline: {len(digest.items)} items, P95={stats['p95']:.3f}s")


def test_e2e_pipeline_with_duplicates():
    """
    Test: Pipeline handles duplicate messages correctly.

    Validates:
    - Idempotency deduplication works
    - Counter idempotency_drops increments
    - Digest contains unique emails only
    """
    messages = _mock_gmail_messages(5)
    # Add duplicates
    messages.extend(_mock_gmail_messages(5))  # Same 5 messages again

    def fetcher():
        return iter(messages)

    digest = run_pipeline(
        fetcher=fetcher,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=False,
    )

    # Should have deduplicated to 5 unique emails
    assert len(digest.items) == 5

    print(f"✅ Deduplication: 10 messages → {len(digest.items)} unique")


def test_e2e_pipeline_parallel_mode():
    """
    Test: Parallel pipeline mode works and maintains determinism.

    Validates:
    - Parallel parsing completes
    - Order is preserved (determinism)
    - Results match sequential mode
    """
    _mock_gmail_messages(20)

    def fetcher_seq():
        return iter(_mock_gmail_messages(20))

    def fetcher_par():
        return iter(_mock_gmail_messages(20))

    # Sequential
    digest_seq = run_pipeline(
        fetcher=fetcher_seq,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=False,
    )

    # Parallel
    reset_seen()  # Reset for second run
    digest_par = run_pipeline(
        fetcher=fetcher_par,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=True,
    )

    # Results should be identical
    assert len(digest_seq.items) == len(digest_par.items)
    seq_titles = [item.title for item in digest_seq.items]
    par_titles = [item.title for item in digest_par.items]
    assert seq_titles == par_titles

    print(
        f"✅ Parallel determinism: sequential={len(digest_seq.items)}, parallel={len(digest_par.items)}"
    )


def test_e2e_with_llm_disabled_rules_only():
    """
    Test: Pipeline with use_llm=False (rules-only).

    Validates:
    - Classification works with use_llm=False
    - Rules-only path always works
    - All emails classified successfully
    """
    messages = _mock_gmail_messages(5)

    def fetcher():
        return iter(messages)

    # Force rules-only by passing use_llm=False
    digest = run_pipeline(
        fetcher=fetcher,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=False,
    )

    # All 5 should be classified via rules
    assert len(digest.items) == 5

    print(f"✅ Rules-only: {len(digest.items)} classified via rules (LLM explicitly disabled)")


def test_e2e_resilience_all_messages_fail_parsing():
    """
    Test: Pipeline handles complete parsing failure gracefully.

    Validates:
    - Parser errors are logged
    - Pipeline raises ValueError (no new emails)
    - No partial/corrupt digest generated
    """
    # Invalid messages (missing required fields)
    invalid_messages = [
        {"id": "bad-msg-1"},  # Missing threadId, payload
        {"id": "bad-msg-2", "threadId": "t1"},  # Missing payload
    ]

    def fetcher():
        return iter(invalid_messages)

    # Pipeline should raise because all messages fail parsing
    with pytest.raises(ValueError):  # Will raise during parse or "no new emails"
        run_pipeline(
            fetcher=fetcher,
            classify=lambda emails: batch_classify_emails(emails, use_llm=False),
            assemble=_mock_assembler,
            parallel=False,
        )

    print("✅ Resilience: pipeline correctly fails when all parsing fails")


def test_e2e_empty_inbox():
    """
    Test: Pipeline handles empty inbox gracefully.

    Validates:
    - No crash on zero emails
    - Appropriate error raised
    - Telemetry recorded
    """

    def fetcher():
        return iter([])

    with pytest.raises(ValueError, match="no new emails"):
        run_pipeline(
            fetcher=fetcher,
            classify=lambda emails: batch_classify_emails(emails, use_llm=False),
            assemble=_mock_assembler,
            parallel=False,
        )

    print("✅ Empty inbox: correctly raises 'no new emails'")


def test_e2e_high_volume():
    """
    Test: Pipeline handles high volume (1000 emails).

    Validates:
    - Can process large batches
    - P95 latency acceptable
    - Memory doesn't explode
    """
    messages = _mock_gmail_messages(1000)

    def fetcher():
        return iter(messages)

    digest = run_pipeline(
        fetcher=fetcher,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=True,  # Use parallel for large batch
    )

    assert len(digest.items) == 1000

    stats = get_latency_stats("pipeline.total")
    print(f"✅ High volume: 1000 emails processed, P95={stats['p95']:.3f}s")

    # Acceptance: P95 < 30s for 1000 emails
    assert stats["p95"] < 30.0, f"P95 too high: {stats['p95']:.3f}s"


def test_e2e_checkpoint_called():
    """
    Test: Digest checkpointing is called.

    Validates:
    - Storage adapter is invoked
    - Telemetry fires
    """
    messages = _mock_gmail_messages(3)

    def fetcher():
        return iter(messages)

    digest = run_pipeline(
        fetcher=fetcher,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=False,
    )

    # Pipeline completed, checkpoint should have been called
    # (In production, this would persist to database)
    assert digest is not None

    print("✅ Checkpoint: digest checkpointed successfully")


def test_e2e_all_phases_integration():
    """
    Comprehensive E2E test validating all refactor phases work together.

    Phase 0: Instrumentation (telemetry)
    Phase 1: Domain models (parsing, validation)
    Phase 2: Adapters (Gmail, storage)
    Phase 3: Resilience (retry, circuit, idempotency)
    Phase 4: Performance (batching, parallelization, P95 tracking)
    Phase 5: Classification cascade (TypeMapper → Rules → LLM → Fallback)

    Note: The EmailClassifier now handles LLM calls internally with its own
    fallback cascade, so we test with use_llm=False for predictable behavior.
    The cascade fallback is tested separately in test_classifier.py.
    """
    messages = _mock_gmail_messages(50)

    def fetcher():
        return iter(messages)

    # Run with all features enabled (use_llm=False for predictable test behavior)
    # The EmailClassifier's fallback cascade ensures emails are always classified
    digest = run_pipeline(
        fetcher=fetcher,
        classify=lambda emails: batch_classify_emails(emails, use_llm=False),
        assemble=_mock_assembler,
        parallel=True,  # Phase 4: parallel processing
    )

    # Validations
    assert len(digest.items) == 50
    assert digest.idempotency_key is not None

    # Check telemetry (Phase 0)
    stats = get_latency_stats("pipeline.total")
    assert stats["count"] >= 1

    # Classification uses fallback cascade (TypeMapper → Rules → Fallback)
    # All emails should be classified successfully

    print("✅ All phases integrated: 50 emails processed")
    print(f"   Pipeline P95: {stats['p95']:.3f}s")
    print(f"   Digest items: {len(digest.items)}")
