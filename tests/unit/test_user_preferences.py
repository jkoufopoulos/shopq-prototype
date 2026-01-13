"""
Tests for User Preference Module

Validates:
1. Preference CRUD operations
2. Preference application to classified emails
3. Cap enforcement (≤200 preferences/user)
4. Expiry logic (30 days default)
5. Performance (≤100ms for batch operations)
6. Multi-user isolation
7. Explainer functionality
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime

import pytest

from mailq.concepts.preferences import (
    MAX_PREFERENCES_PER_USER,
    UserPreferenceManager,
    get_explainer,
)


@pytest.fixture
def test_db():
    """Create in-memory test database."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def manager(test_db, monkeypatch):
    """Create UserPreferenceManager with test database."""

    # Mock database connection to use test DB
    def mock_transaction():
        class MockContext:
            def __enter__(self):
                return test_db

            def __exit__(self, *args):
                test_db.commit()

        return MockContext()

    def mock_connection():
        return test_db

    monkeypatch.setattr("mailq.concepts.preferences.db_transaction", mock_transaction)
    monkeypatch.setattr("mailq.concepts.preferences.get_db_connection", mock_connection)

    return UserPreferenceManager(user_id="alice")


def test_add_preference_importance_only(manager):
    """Test adding preference for importance only."""
    result = manager.add_preference(
        thread_id="thread_123", importance="critical", reason="User marked as critical"
    )

    assert result["thread_id"] == "thread_123"
    assert result["importance"] == "critical"
    assert result["type"] is None
    assert result["reason"] == "User marked as critical"
    assert "expires_at" in result


def test_add_preference_type_only(manager):
    """Test adding preference for type only."""
    result = manager.add_preference(thread_id="thread_123", email_type="finance")

    assert result["thread_id"] == "thread_123"
    assert result["importance"] is None
    assert result["type"] == "finance"


def test_add_preference_both(manager):
    """Test adding preference for both importance and type."""
    result = manager.add_preference(
        thread_id="thread_123", importance="time_sensitive", email_type="travel"
    )

    assert result["importance"] == "time_sensitive"
    assert result["type"] == "travel"


def test_add_preference_requires_at_least_one_field(manager):
    """Test that at least one field (importance or type) must be provided."""
    with pytest.raises(ValueError, match="Must provide at least one"):
        manager.add_preference(thread_id="thread_123")


def test_add_preference_upserts_existing(manager):
    """Test that adding preference to same thread updates instead of creating duplicate."""
    # Add initial override
    manager.add_preference(thread_id="thread_123", importance="critical")

    # Update override
    manager.add_preference(thread_id="thread_123", importance="routine")

    # Verify only one preference exists
    override = manager.get_preference("thread_123")
    assert override["importance"] == "routine"  # Updated

    # Verify count
    stats = manager.get_stats()
    assert stats["active_preferences"] == 1


def test_get_preference_active(manager):
    """Test getting active preference."""
    manager.add_preference(thread_id="thread_123", importance="critical")

    override = manager.get_preference("thread_123")
    assert override is not None
    assert override["importance"] == "critical"


def test_get_preference_nonexistent(manager):
    """Test getting nonexistent preference returns None."""
    override = manager.get_preference("thread_999")
    assert override is None


def test_get_preference_expired(manager):
    """Test that expired preferences are not returned."""
    # Add override that expires in the past
    manager.add_preference(thread_id="thread_123", importance="critical", expiry_days=-1)

    override = manager.get_preference("thread_123")
    assert override is None  # Expired


def test_apply_preferences_to_emails(manager):
    """Test applying preferences to classified emails."""
    # Add overrides
    manager.add_preference(thread_id="thread_1", importance="critical")
    manager.add_preference(thread_id="thread_2", email_type="finance")

    # Classified emails
    emails = [
        {"thread_id": "thread_1", "importance": "routine", "type": "newsletter"},
        {"thread_id": "thread_2", "importance": "time_sensitive", "type": "purchase"},
        {"thread_id": "thread_3", "importance": "routine", "type": "social"},
    ]

    # Apply overrides
    result = manager.apply_preferences(emails)

    # Thread 1: importance overridden
    assert result[0]["importance"] == "critical"  # Overridden
    assert result[0]["type"] == "newsletter"  # Unchanged
    assert result[0]["source"] == "user_preference"
    assert result[0]["original_importance"] == "routine"

    # Thread 2: type overridden
    assert result[1]["importance"] == "time_sensitive"  # Unchanged
    assert result[1]["type"] == "finance"  # Overridden
    assert result[1]["source"] == "user_preference"
    assert result[1]["original_type"] == "purchase"

    # Thread 3: no override
    assert result[2]["importance"] == "routine"
    assert result[2]["type"] == "social"
    assert result[2].get("source") != "user_preference"


def test_apply_preferences_empty_list(manager):
    """Test applying preferences to empty list."""
    result = manager.apply_preferences([])
    assert result == []


def test_apply_preferences_performance(manager):
    """Test that apply_overrides completes in ≤100ms for 100 emails."""
    # Add 50 overrides
    for i in range(50):
        manager.add_preference(thread_id=f"thread_{i}", importance="critical")

    # Create 100 emails (50 with overrides, 50 without)
    emails = [
        {"thread_id": f"thread_{i}", "importance": "routine", "type": "newsletter"}
        for i in range(100)
    ]

    # Measure performance
    start = time.time()
    manager.apply_preferences(emails)
    elapsed_ms = (time.time() - start) * 1000

    # Verify performance target
    assert elapsed_ms < 100, f"apply_preferences took {elapsed_ms:.1f}ms (target: <100ms)"


def test_cap_enforcement(manager):
    """Test that preference cap is enforced (≤200 per user)."""
    # Add MAX_PREFERENCES_PER_USER overrides
    for i in range(MAX_PREFERENCES_PER_USER):
        manager.add_preference(thread_id=f"thread_{i}", importance="critical")

    # Try to add one more
    with pytest.raises(ValueError, match="Preference cap exceeded"):
        manager.add_preference(thread_id="thread_new", importance="critical")


def test_cap_allows_updating_existing(manager):
    """Test that updating existing preference doesn't count against cap."""
    # Fill cap
    for i in range(MAX_PREFERENCES_PER_USER):
        manager.add_preference(thread_id=f"thread_{i}", importance="critical")

    # Updating existing should work
    manager.add_preference(thread_id="thread_0", importance="routine")  # Should succeed


def test_cap_excludes_expired(manager):
    """Test that expired preferences don't count against cap."""
    # Add expired preferences
    for i in range(100):
        manager.add_preference(thread_id=f"thread_old_{i}", importance="critical", expiry_days=-1)

    # Add active preferences (should work because expired don't count)
    for i in range(MAX_PREFERENCES_PER_USER):
        manager.add_preference(thread_id=f"thread_new_{i}", importance="critical")

    # Verify stats
    stats = manager.get_stats()
    assert stats["active_preferences"] == MAX_PREFERENCES_PER_USER
    assert stats["expired_count"] == 100


def test_list_preferences_active_only(manager):
    """Test listing active preferences only."""
    # Add active and expired
    manager.add_preference(thread_id="thread_active", importance="critical", expiry_days=30)
    manager.add_preference(thread_id="thread_expired", importance="routine", expiry_days=-1)

    overrides = manager.list_preferences(include_expired=False)

    assert len(overrides) == 1
    assert overrides[0]["thread_id"] == "thread_active"


def test_list_preferences_include_expired(manager):
    """Test listing all preferences including expired."""
    manager.add_preference(thread_id="thread_active", importance="critical", expiry_days=30)
    manager.add_preference(thread_id="thread_expired", importance="routine", expiry_days=-1)

    overrides = manager.list_preferences(include_expired=True)

    assert len(overrides) == 2


def test_remove_preference(manager):
    """Test removing override."""
    manager.add_preference(thread_id="thread_123", importance="critical")

    # Remove
    removed = manager.remove_preference("thread_123")
    assert removed is True

    # Verify removed
    override = manager.get_preference("thread_123")
    assert override is None

    # Remove nonexistent
    removed = manager.remove_preference("thread_999")
    assert removed is False


def test_cleanup_expired(manager):
    """Test cleanup of expired preferences."""
    # Add expired and active
    manager.add_preference(thread_id="thread_1", importance="critical", expiry_days=-1)
    manager.add_preference(thread_id="thread_2", importance="critical", expiry_days=-1)
    manager.add_preference(thread_id="thread_3", importance="critical", expiry_days=30)

    # Cleanup
    deleted = manager.cleanup_expired()

    assert deleted == 2

    # Verify only active remains
    stats = manager.get_stats()
    assert stats["active_preferences"] == 1


def test_get_stats(manager):
    """Test preference statistics."""
    # Add various overrides
    manager.add_preference(thread_id="thread_1", importance="critical")
    manager.add_preference(thread_id="thread_2", importance="critical")
    manager.add_preference(thread_id="thread_3", importance="routine")
    manager.add_preference(thread_id="thread_4", email_type="finance")
    manager.add_preference(thread_id="thread_5", email_type="travel")
    manager.add_preference(thread_id="thread_6", importance="critical", expiry_days=-1)  # Expired

    stats = manager.get_stats()

    assert stats["total_preferences"] == 6
    assert stats["active_preferences"] == 5
    assert stats["expired_count"] == 1
    assert stats["cap"] == MAX_PREFERENCES_PER_USER
    assert stats["remaining"] == MAX_PREFERENCES_PER_USER - 5
    assert stats["by_importance"]["critical"] == 2  # Expired not counted
    assert stats["by_importance"]["routine"] == 1
    assert stats["by_type"]["finance"] == 1
    assert stats["by_type"]["travel"] == 1


def test_multi_user_isolation(test_db, monkeypatch):
    """Test that overrides are isolated between users."""

    # Mock database
    def mock_transaction():
        class MockContext:
            def __enter__(self):
                return test_db

            def __exit__(self, *args):
                test_db.commit()

        return MockContext()

    def mock_connection():
        return test_db

    monkeypatch.setattr("mailq.concepts.preferences.db_transaction", mock_transaction)
    monkeypatch.setattr("mailq.concepts.preferences.get_db_connection", mock_connection)

    # Create managers for two users
    alice = UserPreferenceManager(user_id="alice")
    bob = UserPreferenceManager(user_id="bob")

    # Alice adds override
    alice.add_preference(thread_id="thread_123", importance="critical")

    # Bob shouldn't see Alice's override
    override = bob.get_preference("thread_123")
    assert override is None

    # Bob's stats shouldn't include Alice's override
    stats = bob.get_stats()
    assert stats["active_preferences"] == 0


def test_explainer_user_override():
    """Test explainer for user preference."""
    email = {
        "importance": "critical",
        "source": "user_override",
        "original_importance": "routine",
        "original_source": "classifier",
        "preference_reason": "User marked as urgent",
    }

    explainer = get_explainer(email)

    assert explainer["importance"] == "critical"
    assert explainer["source"] == "You set this preference"
    assert explainer["reason"] == "User marked as urgent"
    assert "Originally: routine" in explainer["original"]


def test_explainer_classifier():
    """Test explainer for AI classification."""
    email = {
        "importance": "critical",
        "source": "classifier",
        "importance_reason": "Contains urgent keywords",
    }

    explainer = get_explainer(email)

    assert explainer["importance"] == "critical"
    assert explainer["source"] == "AI classification"
    assert explainer["reason"] == "Contains urgent keywords"
    assert "original" not in explainer


def test_explainer_guardrails():
    """Test explainer for guardrails."""
    email = {
        "importance": "routine",
        "source": "guardrails",
        "importance_reason": "OTP code detected",
    }

    explainer = get_explainer(email)

    assert explainer["source"] == "Safety rule"


def test_explainer_type_mapper():
    """Test explainer for type mapper."""
    email = {
        "importance": "time_sensitive",
        "source": "type_mapper",
        "importance_reason": "Calendar event detected",
    }

    explainer = get_explainer(email)

    assert explainer["source"] == "Calendar detection"


def test_batch_get_preferences_performance(manager):
    """Test that batch fetching overrides is efficient."""
    # Add 100 overrides
    for i in range(100):
        manager.add_preference(thread_id=f"thread_{i}", importance="critical")

    # Fetch batch
    thread_ids = [f"thread_{i}" for i in range(100)]

    start = time.time()
    overrides = manager._batch_get_preferences(thread_ids)
    elapsed_ms = (time.time() - start) * 1000

    assert len(overrides) == 100
    assert elapsed_ms < 50, f"Batch fetch took {elapsed_ms:.1f}ms (target: <50ms)"


def test_expiry_custom_days(manager):
    """Test custom expiry days."""
    # 7-day expiry
    result = manager.add_preference(thread_id="thread_123", importance="critical", expiry_days=7)

    # Verify expiry is ~7 days from now
    expires_at = datetime.fromisoformat(result["expires_at"])
    now = datetime.now(UTC)
    delta = expires_at - now

    assert 6.9 < delta.total_seconds() / 86400 < 7.1  # Within 0.1 day of 7 days


def test_preference_preserves_original_fields(manager):
    """Test that applying override preserves original classification fields."""
    manager.add_preference(thread_id="thread_1", importance="critical")

    emails = [
        {
            "thread_id": "thread_1",
            "importance": "routine",
            "type": "newsletter",
            "source": "classifier",
            "importance_reason": "Low priority content",
            "other_field": "preserved",
        }
    ]

    result = manager.apply_preferences(emails)

    # Override applied
    assert result[0]["importance"] == "critical"
    assert result[0]["source"] == "user_preference"

    # Original preserved
    assert result[0]["original_importance"] == "routine"
    assert result[0]["original_source"] == "classifier"

    # Other fields preserved
    assert result[0]["type"] == "newsletter"
    assert result[0]["importance_reason"] == "Low priority content"
    assert result[0]["other_field"] == "preserved"


# ============================================================================
# CRITICAL INVARIANT TESTS (Architecture Review Requirements)
# ============================================================================


def test_invariant_taxonomy_immutability(manager):
    """
    INVARIANT: Taxonomy (type, event dates) must NEVER change due to preferences.

    This is a foundational constraint: preferences personalize importance/sectioning,
    but the underlying email classification (what it IS) stays immutable.
    """
    manager.add_preference(thread_id="thread_1", importance="critical")

    emails = [
        {
            "thread_id": "thread_1",
            "importance": "routine",
            "type": "finance",  # Taxonomy field
            "event_start": "2025-11-15T14:00:00",  # Taxonomy field
            "domains": ["banking", "receipt"],  # Taxonomy field
        }
    ]

    result = manager.apply_preferences(emails)

    # Importance CAN change (that's the point of preferences)
    assert result[0]["importance"] == "critical"

    # Taxonomy fields MUST NOT change
    assert result[0]["type"] == "finance", "Type changed! Taxonomy immutability violated"
    assert result[0]["event_start"] == "2025-11-15T14:00:00", "Event date changed!"
    assert result[0]["domains"] == ["banking", "receipt"], "Domains changed!"


def test_invariant_precedence_chain(test_db, monkeypatch):
    """
    INVARIANT: Precedence order must be Explicit > Implicit > Base.

    Since implicit learning is deferred (Phase 2), this test validates that
    explicit preferences (Phase 1) take precedence over base classification.

    When implicit learning is added, extend this test to verify:
    - base_importance = "routine"
    - implicit_boost adds +0.3 → "time_sensitive"
    - explicit override sets "critical" → final = "critical"
    """

    def mock_transaction():
        class MockContext:
            def __enter__(self):
                return test_db

            def __exit__(self, *args):
                test_db.commit()

        return MockContext()

    def mock_connection():
        return test_db

    monkeypatch.setattr("mailq.concepts.preferences.db_transaction", mock_transaction)
    monkeypatch.setattr("mailq.concepts.preferences.get_db_connection", mock_connection)

    manager = UserPreferenceManager(user_id="alice")

    # Base classification
    email = {"thread_id": "T1", "importance": "routine"}

    # Apply explicit preference
    manager.add_preference("T1", importance="critical", reason="Explicit user override")
    result = manager.apply_preferences([email])

    # Explicit preference must win over base
    assert result[0]["importance"] == "critical"
    assert result[0]["source"] == "user_preference"
    assert result[0]["original_importance"] == "routine"


def test_invariant_multi_tenancy_isolation(test_db, monkeypatch):
    """
    INVARIANT: Preferences must be isolated by user_id (same thread_id, different users).

    Security requirement: User A cannot see or be affected by User B's preferences.
    """

    def mock_transaction():
        class MockContext:
            def __enter__(self):
                return test_db

            def __exit__(self, *args):
                test_db.commit()

        return MockContext()

    def mock_connection():
        return test_db

    monkeypatch.setattr("mailq.concepts.preferences.db_transaction", mock_transaction)
    monkeypatch.setattr("mailq.concepts.preferences.get_db_connection", mock_connection)

    alice = UserPreferenceManager(user_id="alice")
    bob = UserPreferenceManager(user_id="bob")

    # Alice marks thread as critical
    alice.add_preference("shared_thread_123", importance="critical")

    # Bob applies preferences to the SAME thread_id
    emails = [{"thread_id": "shared_thread_123", "importance": "routine"}]
    bob_result = bob.apply_preferences(emails)

    # Bob should NOT see Alice's preference (multi-tenant isolation)
    assert bob_result[0]["importance"] == "routine", "Multi-tenancy violated!"
    assert bob_result[0].get("source") != "user_preference"


def test_invariant_performance_sla(manager):
    """
    INVARIANT: apply_preferences must complete in ≤100ms for 100 emails.

    Performance target from architecture review. This leaves headroom for:
    - Future implicit learning (Phase 2): +50ms
    - Stage 1.5 integration overhead: ~10ms
    """
    # Add 50 preferences (realistic load)
    for i in range(50):
        manager.add_preference(thread_id=f"thread_{i}", importance="critical")

    # Create 100 emails (50% match rate)
    emails = [
        {"thread_id": f"thread_{i}", "importance": "routine", "type": "newsletter"}
        for i in range(100)
    ]

    # Measure Stage 1.5 performance
    start = time.time()
    manager.apply_preferences(emails)
    elapsed_ms = (time.time() - start) * 1000

    # Must complete within 100ms (architecture requirement)
    assert elapsed_ms < 100, f"Performance SLA violated: {elapsed_ms:.1f}ms (target: <100ms)"


def test_invariant_missing_thread_id_is_noop(manager):
    """
    INVARIANT: Emails without thread_id must not crash (graceful degradation).

    Edge case: Some emails might not have thread_id (API payload variations).
    Preferences should skip them gracefully without affecting other emails.
    """
    manager.add_preference(thread_id="thread_1", importance="critical")

    emails = [
        {"thread_id": "thread_1", "importance": "routine"},  # Has thread_id
        {"importance": "routine"},  # Missing thread_id
        {"thread_id": None, "importance": "routine"},  # None thread_id
    ]

    # Should not crash
    result = manager.apply_preferences(emails)

    # Email with thread_id: preference applied
    assert result[0]["importance"] == "critical"

    # Emails without thread_id: unchanged (no-op)
    assert result[1]["importance"] == "routine"
    assert result[2]["importance"] == "routine"


def test_invariant_temporal_decay_interaction(manager):
    """
    INVARIANT: Explicit preferences respect temporal relevance.

    From architecture review decision:
    - Expired/irrelevant items (past events, lapsed OTPs) CAN be hidden even if preferred
    - For active items, explicit preference wins until TTL ends

    This test validates that:
    1. Preferences apply correctly to active emails
    2. Temporal decay logic (implemented elsewhere) can still demote stale items
    3. Preferences show age metadata for UI display
    """
    # Add preference for a thread
    manager.add_preference(
        thread_id="thread_event", importance="critical", reason="Important conference"
    )

    emails = [
        {
            "thread_id": "thread_event",
            "importance": "routine",
            "type": "event",
            "event_start": "2025-11-15T14:00:00",
        }
    ]

    # Apply preference
    applied = manager.apply_preferences(emails)

    # Preference applied successfully
    assert applied[0]["importance"] == "critical"
    assert applied[0]["source"] == "user_preference"
    assert applied[0]["preference_reason"] == "Important conference"

    # Verify preference metadata includes expiry (for temporal decay logic)
    pref = manager.get_preference("thread_event")
    assert pref is not None
    assert "expires_at" in pref

    # Future temporal decay stage can check:
    # - if event_start is in past AND preference is expired → demote
    # - if preference is active → respect user intent
    # This validates the nuanced rule from architecture review
