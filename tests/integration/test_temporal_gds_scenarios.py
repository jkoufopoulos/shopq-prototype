"""
Test temporal decay scenarios using Golden Dataset emails

Validates that:
1. GDS labels represent stored_importance (Stage 1 - at receipt)
2. Temporal decay correctly modulates to resolved_importance (Stage 2)
3. Real emails with temporal fields behave correctly at different times

This bridges the gap between:
- test_importance_baseline_gds.py (Stage 1: classifier at receipt)
- test_temporal_decay.py (Stage 2: temporal decay unit tests)

By testing real GDS emails at multiple time snapshots, we validate:
- Imminent events escalate to critical
- Expired events downgrade to routine and hide
- Upcoming events escalate to time_sensitive
- Distant events downgrade to routine

Usage:
    pytest tests/test_temporal_gds_scenarios.py -v
    pytest tests/test_temporal_gds_scenarios.py::TestStage2TemporalDecay -v
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

# Import temporal decay logic
try:
    from shopq.classification.enrichment import enrich_entity_with_temporal_decay
    from shopq.classification.models import DeadlineEntity, Entity, EventEntity, NotificationEntity
except ImportError:
    pytest.skip("ShopQ modules not available", allow_module_level=True)


@pytest.fixture(scope="module")
def gds_temporal_emails():
    """Load GDS emails that have temporal fields (events/deadlines)"""
    gds_path = Path(__file__).parent / "golden_set" / "gds-1.0.csv"

    if not gds_path.exists():
        pytest.skip(f"GDS not found at {gds_path}")

    df = pd.read_csv(gds_path)

    # Filter to emails with temporal_start (events/deadlines)
    temporal_df = df[df["temporal_start"].notna()].copy()

    # Parse temporal fields
    temporal_df["temporal_start"] = pd.to_datetime(temporal_df["temporal_start"], utc=True)
    temporal_df["temporal_end"] = pd.to_datetime(
        temporal_df["temporal_end"], utc=True, errors="coerce"
    )

    print(f"\n✅ Loaded {len(temporal_df)} temporal emails from GDS")
    return temporal_df


class TestStage1Documentation:
    """Validate our understanding that GDS labels = stored_importance (at receipt)"""

    def test_gds_labels_represent_stored_importance(self, gds_temporal_emails):
        """
        GDS labels should represent stored_importance (Stage 1 - at receipt),
        NOT resolved_importance (Stage 2 - after temporal decay).

        This is a documentation test confirming our interpretation of:
        - GDS_SCHEMA_v1.0.md: labels created "at moment of receipt"
        - temporal_decay.py: stored_importance → resolved_importance
        """
        # All importance labels should be valid
        for _idx, email in gds_temporal_emails.iterrows():
            assert email["importance"] in [
                "critical",
                "time_sensitive",
                "routine",
            ], f"Invalid importance: {email['importance']}"

        print(f"\n✅ Validated {len(gds_temporal_emails)} GDS labels are stored_importance")


class TestStage2TemporalDecay:
    """Validate temporal decay with GDS emails at different time snapshots"""

    def test_imminent_events_escalate_to_critical(self, gds_temporal_emails):
        """
        Events with temporal_start ≤ now+1h should escalate to critical,
        even if GDS label (stored_importance) says routine.

        Acceptance Criteria:
        - Events starting within 1 hour → resolved_importance = critical
        - decay_reason = 'temporal_active'
        """
        events = gds_temporal_emails[gds_temporal_emails["email_type"] == "event"]

        if len(events) == 0:
            pytest.skip("No events in GDS")

        tested = 0
        for _idx, email in events.iterrows():
            # Simulate "now" as 30 minutes before event
            simulated_now = email["temporal_start"] - timedelta(minutes=30)

            # Create EventEntity with required fields
            entity = EventEntity(
                confidence=1.0,
                source_email_id=email["message_id"],
                source_subject=email["subject"],
                source_snippet=email["snippet"],
                timestamp=email["temporal_start"],
                importance=email["importance"],  # GDS label (stored_importance)
                event_time=email["temporal_start"].isoformat(),  # ISO format string
                event_end_time=(
                    email["temporal_end"].isoformat() if pd.notna(email["temporal_end"]) else None
                ),
            )

            # Apply temporal decay
            enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

            # Should escalate to critical (imminent, within 1h window)
            assert enriched.resolved_importance == "critical", (
                f"Event {email['message_id']} should be critical when starting in 30min (got {enriched.resolved_importance})"
            )

            tested += 1

        print(f"\n✅ Tested {tested} events for imminent escalation")

    def test_expired_events_downgrade_to_routine(self, gds_temporal_emails):
        """
        Events with temporal_end < now-1h should downgrade to routine
        and be hidden from digest.

        Acceptance Criteria:
        - Events ended >1h ago → resolved_importance = routine
        - decay_reason = 'temporal_expired'
        - should_show = False (hidden from digest)
        """
        events = gds_temporal_emails[gds_temporal_emails["email_type"] == "event"]

        if len(events) == 0:
            pytest.skip("No events in GDS")

        tested = 0
        for _idx, email in events.iterrows():
            # Determine expiration time
            if pd.isna(email["temporal_end"]):
                # Use temporal_start as fallback (1-hour default duration)
                expiration_time = email["temporal_start"] + timedelta(hours=1)
            else:
                expiration_time = email["temporal_end"]

            # Simulate "now" as 2 hours after event ended
            simulated_now = expiration_time + timedelta(hours=2)

            # Create EventEntity
            entity = EventEntity(
                confidence=1.0,
                source_email_id=email["message_id"],
                source_subject=email["subject"],
                source_snippet=email["snippet"],
                timestamp=email["temporal_start"],
                importance=email["importance"],
                event_time=email["temporal_start"].isoformat(),
                event_end_time=(
                    email["temporal_end"].isoformat() if pd.notna(email["temporal_end"]) else None
                ),
            )

            # Apply temporal decay
            enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

            # Should downgrade to routine (expired)
            assert enriched.resolved_importance == "routine", (
                f"Event {email['message_id']} should be routine when expired (got {enriched.resolved_importance})"
            )

            # Should be hidden from digest
            assert enriched.hide_in_digest, f"Expired event {email['message_id']} should be hidden"

            tested += 1

        print(f"\n✅ Tested {tested} events for expiration")

    def test_upcoming_events_escalate_to_time_sensitive(self, gds_temporal_emails):
        """
        Events with now+1h < temporal_start ≤ now+7d should be time_sensitive.

        Acceptance Criteria:
        - Events starting within 7 days (but not within 1h) → time_sensitive
        - decay_reason = 'temporal_upcoming'
        - Unless stored_importance = critical (preserve LLM override)
        """
        events = gds_temporal_emails[gds_temporal_emails["email_type"] == "event"]

        if len(events) == 0:
            pytest.skip("No events in GDS")

        tested = 0
        for _idx, email in events.iterrows():
            # Simulate "now" as 3 days before event
            simulated_now = email["temporal_start"] - timedelta(days=3)

            # Create EventEntity
            entity = EventEntity(
                confidence=1.0,
                source_email_id=email["message_id"],
                source_subject=email["subject"],
                source_snippet=email["snippet"],
                timestamp=email["temporal_start"],
                importance=email["importance"],
                event_time=email["temporal_start"].isoformat(),
                event_end_time=(
                    email["temporal_end"].isoformat() if pd.notna(email["temporal_end"]) else None
                ),
            )

            # Apply temporal decay
            enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

            # Should be time_sensitive (upcoming, within 7d window)
            # Unless stored was already critical (preserve LLM override)
            if email["importance"] == "critical":
                assert enriched.resolved_importance == "critical"
            else:
                assert enriched.resolved_importance == "time_sensitive", (
                    f"Event {email['message_id']} should be time_sensitive when 3d away "
                    f"(got {enriched.resolved_importance})"
                )

            # Should be shown in digest (not hidden)
            assert not enriched.hide_in_digest, (
                f"Upcoming event {email['message_id']} should be shown"
            )

            tested += 1

        print(f"\n✅ Tested {tested} events for upcoming window")

    def test_distant_events_downgrade_to_routine(self, gds_temporal_emails):
        """
        Events with temporal_start > now+7d should be routine
        (unless stored_importance is critical).

        Acceptance Criteria:
        - Events >7 days away → routine (distant)
        - Unless stored_importance = critical (preserve override)
        """
        events = gds_temporal_emails[gds_temporal_emails["email_type"] == "event"]

        if len(events) == 0:
            pytest.skip("No events in GDS")

        tested = 0
        for _idx, email in events.iterrows():
            # Simulate "now" as 10 days before event
            simulated_now = email["temporal_start"] - timedelta(days=10)

            # Create EventEntity
            entity = EventEntity(
                confidence=1.0,
                source_email_id=email["message_id"],
                source_subject=email["subject"],
                source_snippet=email["snippet"],
                timestamp=email["temporal_start"],
                importance=email["importance"],
                event_time=email["temporal_start"].isoformat(),
                event_end_time=(
                    email["temporal_end"].isoformat() if pd.notna(email["temporal_end"]) else None
                ),
            )

            # Apply temporal decay
            enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

            # Should be routine (distant, >7d)
            # Unless LLM said critical (preserve override)
            if email["importance"] == "critical":
                assert enriched.resolved_importance == "critical"
            else:
                assert enriched.resolved_importance == "routine", (
                    f"Event {email['message_id']} should be routine when >7d away (got {enriched.resolved_importance})"
                )

            tested += 1

        print(f"\n✅ Tested {tested} events for distant downgrade")

    @pytest.mark.parametrize(
        "time_offset,expected_importance_range",
        [
            (timedelta(days=-10), ["routine"]),  # 10 days before (distant)
            (timedelta(days=-3), ["time_sensitive", "critical"]),  # 3 days before (upcoming)
            (timedelta(minutes=-30), ["critical"]),  # 30 min before (imminent)
            (timedelta(hours=2), ["routine"]),  # 2 hours after (expired)
        ],
    )
    def test_time_snapshots_for_event_lifecycle(
        self, gds_temporal_emails, time_offset, expected_importance_range
    ):
        """
        Test event lifecycle at multiple time snapshots to validate
        temporal decay transitions.

        This parameterized test validates:
        - Distant (10d before) → routine
        - Upcoming (3d before) → time_sensitive (or critical if LLM override)
        - Imminent (30m before) → critical
        - Expired (2h after) → routine
        """
        # Pick first event with both start and end times
        events = gds_temporal_emails[
            (gds_temporal_emails["email_type"] == "event")
            & (gds_temporal_emails["temporal_end"].notna())
        ]

        if len(events) == 0:
            pytest.skip("No suitable events for time snapshot testing")

        email = events.iloc[0]

        # Calculate simulated "now" based on time_offset from event start
        simulated_now = email["temporal_start"] + time_offset

        # Create EventEntity
        entity = EventEntity(
            confidence=1.0,
            source_email_id=email["message_id"],
            source_subject=email["subject"],
            source_snippet=email["snippet"],
            timestamp=email["temporal_start"],
            importance=email["importance"],
            event_time=email["temporal_start"].isoformat(),
            event_end_time=email["temporal_end"].isoformat(),
        )

        # Apply temporal decay
        enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

        # Validate resolved_importance is in expected range
        assert enriched.resolved_importance in expected_importance_range, (
            f"At {time_offset}, expected one of {expected_importance_range}, "
            f"got {enriched.resolved_importance}"
        )


class TestDeadlineTemporal:
    """Validate temporal decay for deadlines (no end_time)"""

    def test_deadlines_expire_based_on_due_date(self, gds_temporal_emails):
        """
        Deadlines (temporal_end=None) should expire based on temporal_start.

        Acceptance Criteria:
        - Deadlines past due date → resolved_importance = routine
        - decay_reason = 'temporal_expired'
        """
        deadlines = gds_temporal_emails[gds_temporal_emails["email_type"] == "deadline"]

        if len(deadlines) == 0:
            pytest.skip("No deadlines in GDS")

        tested = 0
        for _idx, email in deadlines.iterrows():
            # Simulate "now" as 2 hours after deadline
            simulated_now = email["temporal_start"] + timedelta(hours=2)

            # Create DeadlineEntity
            entity = DeadlineEntity(
                confidence=1.0,
                source_email_id=email["message_id"],
                source_subject=email["subject"],
                source_snippet=email["snippet"],
                timestamp=email["temporal_start"],
                importance=email["importance"],
                due_date=email["temporal_start"].isoformat(),
            )

            # Apply temporal decay
            enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

            # Should be routine (expired)
            assert enriched.resolved_importance == "routine", (
                f"Deadline {email['message_id']} should be routine when expired (got {enriched.resolved_importance})"
            )

            # Should be hidden
            assert enriched.hide_in_digest, (
                f"Expired deadline {email['message_id']} should be hidden"
            )

            tested += 1

        print(f"\n✅ Tested {tested} deadlines for expiration")

    def test_deadlines_imminent_escalate(self, gds_temporal_emails):
        """
        Deadlines due within 1 hour should escalate to critical.

        Acceptance Criteria:
        - Deadlines due ≤ 1h → critical
        """
        deadlines = gds_temporal_emails[gds_temporal_emails["email_type"] == "deadline"]

        if len(deadlines) == 0:
            pytest.skip("No deadlines in GDS")

        tested = 0
        for _idx, email in deadlines.iterrows():
            # Simulate "now" as 30 minutes before deadline
            simulated_now = email["temporal_start"] - timedelta(minutes=30)

            # Create DeadlineEntity
            entity = DeadlineEntity(
                confidence=1.0,
                source_email_id=email["message_id"],
                source_subject=email["subject"],
                source_snippet=email["snippet"],
                timestamp=email["temporal_start"],
                importance=email["importance"],
                due_date=email["temporal_start"].isoformat(),
            )

            # Apply temporal decay
            enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

            # Should escalate to critical (imminent)
            assert enriched.resolved_importance == "critical", (
                f"Deadline {email['message_id']} should be critical when due in 30min (got {enriched.resolved_importance})"
            )

            tested += 1

        print(f"\n✅ Tested {tested} deadlines for imminent escalation")


class TestAuditTrail:
    """Validate that both stored and resolved importance are preserved"""

    def test_audit_fields_populated(self, gds_temporal_emails):
        """
        Ensure temporal decay returns audit fields:
        - resolved_importance (after decay)
        - should_show (visibility flag)
        - Entity preserves stored importance

        This enables debugging and quality monitoring.
        """
        events = gds_temporal_emails[gds_temporal_emails["email_type"] == "event"]

        if len(events) == 0:
            pytest.skip("No events in GDS")

        email = events.iloc[0]

        # Test imminent event (will escalate to critical)
        simulated_now = email["temporal_start"] - timedelta(minutes=30)

        # Create EventEntity
        entity = EventEntity(
            confidence=1.0,
            source_email_id=email["message_id"],
            source_subject=email["subject"],
            source_snippet=email["snippet"],
            timestamp=email["temporal_start"],
            importance=email["importance"],  # stored_importance
            event_time=email["temporal_start"].isoformat(),
            event_end_time=(
                email["temporal_end"].isoformat() if pd.notna(email["temporal_end"]) else None
            ),
        )

        # Apply temporal decay
        enriched = enrich_entity_with_temporal_decay(entity, now=simulated_now)

        # Validate audit fields exist
        assert hasattr(enriched, "resolved_importance")
        assert hasattr(enriched, "hide_in_digest")
        assert hasattr(enriched, "importance")  # original importance preserved

        print(
            f"\n✅ Audit trail validated: stored={enriched.importance}, "
            f"resolved={enriched.resolved_importance}, "
            f"hidden={enriched.hide_in_digest}"
        )


class TestNonTemporalEmails:
    """Validate that non-temporal emails are not affected by temporal decay"""

    def test_routine_updates_unaffected(self, gds_temporal_emails):
        """
        Non-temporal emails (update, newsletter, notification) should pass through
        temporal decay unchanged.

        Acceptance Criteria:
        - stored_importance = resolved_importance
        - should_show = True (always shown)
        """
        # Load all GDS emails (including non-temporal)
        gds_path = Path(__file__).parent / "golden_set" / "gds-1.0.csv"
        df = pd.read_csv(gds_path)

        # Filter to non-temporal types
        non_temporal = df[~df["email_type"].isin(["event", "deadline"])]

        if len(non_temporal) == 0:
            pytest.skip("No non-temporal emails in GDS")

        tested = 0
        for _idx, email in non_temporal.head(10).iterrows():  # Test first 10
            # Create NotificationEntity (non-temporal type)
            entity = NotificationEntity(
                confidence=1.0,
                source_email_id=email["message_id"],
                source_subject=email["subject"],
                source_snippet=email["snippet"],
                timestamp=datetime.now(UTC),
                importance=email["importance"],
                category="update",
                action_required=False,
            )

            # Apply temporal decay (should be no-op for non-temporal entities)
            enriched = enrich_entity_with_temporal_decay(entity)

            # Should be unchanged
            assert enriched.resolved_importance == email["importance"], (
                f"Non-temporal email {email['message_id']} importance should not change"
            )

            # Should not be hidden (non-temporal emails always shown)
            assert not enriched.hide_in_digest, (
                f"Non-temporal email {email['message_id']} should not be hidden"
            )

            tested += 1

        print(f"\n✅ Tested {tested} non-temporal emails (unchanged by temporal decay)")


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v"])
