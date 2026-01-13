"""
Tests for Shipping Temporal Decay

NOTE: OTP temporal logic has been removed from resolve_otp_shipping_importance().
OTPs are now handled by:
- Guardrails (force_critical for T0 importance)
- Digest temporal decay (skip - OTPs never appear in digest)
See: docs/features/T0_T1_IMPORTANCE_CLASSIFICATION.md

Verifies that:
- Packages "out for delivery" are escalated to critical
- Delivered packages >24h are downgraded to routine
- Missing shipping fields fail gracefully
"""

from datetime import UTC, datetime, timedelta

import pytest

from mailq.classification.models import NotificationEntity
from mailq.classification.temporal import resolve_otp_shipping_importance


@pytest.fixture
def base_notification():
    """Base notification entity for testing."""
    return NotificationEntity(
        confidence=0.9,
        source_email_id="test_notif_123",
        source_subject="Test Notification",
        source_snippet="Test notification snippet",
        timestamp=datetime.now(UTC),
        importance="time_sensitive",
        category="security",
        message="Test message",
    )


# =============================================================================
# Shipping Temporal Decay Tests
# =============================================================================


def test_shipping_out_for_delivery(base_notification):
    """Packages out for delivery should be escalated to critical."""
    now = datetime.now(UTC)

    entity = base_notification
    entity.ship_status = "out_for_delivery"
    entity.category = "delivery"

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    assert result is not None, "Shipping logic should apply"
    assert result.resolved_importance == "critical"
    assert result.decay_reason == "shipping_out_for_delivery"
    assert result.was_modified is True  # time_sensitive → critical


def test_shipping_delivered_recent(base_notification):
    """Recently delivered packages (<24h) should preserve stored importance."""
    now = datetime.now(UTC)
    delivered_at = now - timedelta(hours=12)  # Delivered 12 hours ago

    entity = base_notification
    entity.ship_status = "delivered"
    entity.delivered_at = delivered_at
    entity.category = "delivery"

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    # Should return None (no decay applies), preserving stored importance
    assert result is None, "No shipping decay should apply for recent delivery"


def test_shipping_delivered_old(base_notification):
    """Old delivered packages (>24h) should be downgraded to routine."""
    now = datetime.now(UTC)
    delivered_at = now - timedelta(hours=30)  # Delivered 30 hours ago

    entity = base_notification
    entity.ship_status = "delivered"
    entity.delivered_at = delivered_at
    entity.category = "delivery"

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    assert result is not None, "Shipping decay should apply"
    assert result.resolved_importance == "routine"
    assert result.decay_reason == "shipping_delivered_old"
    assert result.was_modified is True  # time_sensitive → routine


def test_shipping_delivered_string_datetime(base_notification):
    """Test shipping logic with string datetime (ISO 8601)."""
    now = datetime.now(UTC)
    delivered_at = (now - timedelta(hours=48)).isoformat()  # String format

    entity = base_notification
    entity.ship_status = "delivered"
    entity.delivered_at = delivered_at
    entity.category = "delivery"

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    assert result is not None
    assert result.resolved_importance == "routine"
    assert result.decay_reason == "shipping_delivered_old"


def test_shipping_in_transit(base_notification):
    """Packages in transit should preserve stored importance (no decay)."""
    now = datetime.now(UTC)

    entity = base_notification
    entity.ship_status = "in_transit"
    entity.category = "delivery"

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    # Should return None (no decay applies)
    assert result is None, "No shipping decay should apply for in_transit"


def test_shipping_processing(base_notification):
    """Packages in processing should preserve stored importance (no decay)."""
    now = datetime.now(UTC)

    entity = base_notification
    entity.ship_status = "processing"
    entity.category = "delivery"

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    # Should return None (no decay applies)
    assert result is None, "No shipping decay should apply for processing"


def test_no_shipping_fields(base_notification):
    """Entities without shipping fields should return None (graceful fallback)."""
    now = datetime.now(UTC)

    entity = base_notification
    # No ship_status set

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    assert result is None, "Should return None when no shipping fields present"


def test_shipping_malformed_delivered_at(base_notification):
    """Malformed delivered_at datetime should fail gracefully."""
    now = datetime.now(UTC)

    entity = base_notification
    entity.ship_status = "delivered"
    entity.delivered_at = "invalid-datetime"

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    # Should catch ValueError and return None (fallback to preserving stored importance)
    assert result is None, "Should fail gracefully for malformed datetime"


def test_stored_importance_critical_not_modified(base_notification):
    """If stored importance is already critical, was_modified should be False."""
    now = datetime.now(UTC)

    entity = base_notification
    entity.ship_status = "out_for_delivery"

    result = resolve_otp_shipping_importance(entity, "critical", now)

    assert result is not None
    assert result.resolved_importance == "critical"
    assert result.was_modified is False  # critical → critical (no change)


# =============================================================================
# OTP Fields Now Ignored (Legacy Behavior Removed)
# =============================================================================


def test_otp_fields_ignored(base_notification):
    """OTP fields are now ignored - OTPs handled by guardrails and digest decay.

    OTP temporal logic was removed because:
    1. Guardrails already set OTPs to importance=critical (T0)
    2. Digest temporal decay skips OTPs entirely (T1)
    3. The otp_expired → routine path was useless
    """
    now = datetime.now(UTC)
    otp_expires_at = now - timedelta(minutes=3)  # Would have been "active" before

    entity = base_notification
    entity.otp_expires_at = otp_expires_at

    result = resolve_otp_shipping_importance(entity, "time_sensitive", now)

    # OTP logic removed - should return None (no decay applies)
    assert result is None, "OTP fields should be ignored - handled by guardrails/digest"
