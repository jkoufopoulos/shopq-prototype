#!/usr/bin/env python3
"""
Phase 4 Temporal Decay - Smoke Test

Run Phase 4 temporal enrichment on GDS emails and show what changes.
This verifies the temporal decay pipeline is working end-to-end.

Usage:
    python scripts/smoke_test_phase4.py [--gds-file tests/golden_set/gds-1.0_dev.csv]
"""

from __future__ import annotations

import csv
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.classification.enrichment import (
    enrich_entities_with_temporal_decay,
    get_temporal_stats,
    reset_temporal_stats,
)
from mailq.classification.models import Entity, EventEntity, NotificationEntity


def load_gds_emails(gds_path: Path) -> list[dict]:
    """Load emails from GDS CSV."""
    with open(gds_path) as f:
        reader = csv.DictReader(f)
        return list(reader)


def create_test_entity_from_gds(email: dict, now: datetime) -> Entity | None:
    """
    Create a test entity from GDS row to simulate temporal decay.

    For smoke test, we'll inject temporal fields to demonstrate Phase 4 behavior.
    """
    email_type = email.get("email_type", "other")
    importance = email.get("importance", "routine")
    subject = email.get("subject", "")

    # Base entity
    entity = Entity(
        type=email_type,
        confidence=float(email.get("type_confidence", 0.8)),
        source_email_id=email.get("message_id", ""),
        source_subject=subject,
        source_snippet=email.get("snippet", "")[:200],
        timestamp=now,
        importance=importance,
    )

    # For events, inject temporal fields to test Phase 4
    if email_type == "event":
        # Simulate different temporal scenarios
        if "tonight" in subject.lower() or "today" in subject.lower():
            # Event happening today (imminent)
            start = now + timedelta(hours=2)
            end = now + timedelta(hours=3)
        elif "tomorrow" in subject.lower():
            # Event tomorrow (upcoming)
            start = now + timedelta(days=1, hours=18)
            end = now + timedelta(days=1, hours=20)
        elif any(word in subject.lower() for word in ["next week", "upcoming"]):
            # Event next week (distant)
            start = now + timedelta(days=10)
            end = now + timedelta(days=10, hours=2)
        else:
            # Default: event in 3 days
            start = now + timedelta(days=3)
            end = now + timedelta(days=3, hours=2)

        entity = EventEntity(
            confidence=entity.confidence,
            source_email_id=entity.source_email_id,
            source_subject=entity.source_subject,
            source_snippet=entity.source_snippet,
            timestamp=entity.timestamp,
            importance=entity.importance,
            title=subject,
            event_time=start,
            event_end_time=end,
        )

    # For notifications, check if it's OTP or shipping
    elif email_type == "notification":
        snippet_lower = email.get("snippet", "").lower()

        # OTP detection
        otp_expires_at = None
        if any(
            word in snippet_lower
            for word in ["verification code", "otp", "security code", "one-time"]
        ):
            # Simulate active OTP (expires in 10 min)
            otp_expires_at = now + timedelta(minutes=10)

        # Shipping detection
        ship_status = None
        delivered_at = None
        if "delivered" in snippet_lower:
            ship_status = "delivered"
            delivered_at = now - timedelta(hours=2)  # Delivered 2h ago
        elif "out for delivery" in snippet_lower:
            ship_status = "out_for_delivery"

        if otp_expires_at or ship_status:
            entity = NotificationEntity(
                confidence=entity.confidence,
                source_email_id=entity.source_email_id,
                source_subject=entity.source_subject,
                source_snippet=entity.source_snippet,
                timestamp=entity.timestamp,
                importance=entity.importance,
                category="security" if otp_expires_at else "delivery",
                message=entity.source_snippet,
                otp_expires_at=otp_expires_at,
                ship_status=ship_status,
                delivered_at=delivered_at,
            )

    return entity


def format_importance(imp: str) -> str:
    """Format importance with color."""
    colors = {
        "critical": "\033[91m",  # Red
        "time_sensitive": "\033[93m",  # Yellow
        "routine": "\033[92m",  # Green
    }
    reset = "\033[0m"
    return f"{colors.get(imp, '')}{imp}{reset}"


def main():
    """Run smoke test."""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 4 Temporal Decay Smoke Test")
    parser.add_argument(
        "--gds-file",
        default="tests/golden_set/gds-1.0_dev.csv",
        help="Path to GDS CSV file",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of emails to process")
    args = parser.parse_args()

    gds_path = Path(args.gds_file)
    if not gds_path.exists():
        print(f"❌ GDS file not found: {gds_path}")
        sys.exit(1)

    print("🔬 Phase 4 Temporal Decay - Smoke Test\n")
    print(f"📂 Loading GDS: {gds_path}")
    print(f"📊 Limit: {args.limit} emails\n")

    # Load GDS emails
    emails = load_gds_emails(gds_path)
    print(f"✅ Loaded {len(emails)} emails from GDS\n")

    # Create test entities
    now = datetime.now(UTC)
    entities = []
    for email in emails[: args.limit]:
        entity = create_test_entity_from_gds(email, now)
        if entity:
            entities.append(entity)

    print(f"✅ Created {len(entities)} test entities\n")
    print("=" * 80)
    print("TEMPORAL ENRICHMENT RESULTS")
    print("=" * 80)

    # Apply temporal enrichment
    reset_temporal_stats()
    enriched = enrich_entities_with_temporal_decay(entities, now=now)

    # Show results
    modified_count = 0
    for entity in enriched:
        stored = getattr(entity, "stored_importance", entity.importance)
        resolved = getattr(entity, "resolved_importance", entity.importance)
        was_modified = getattr(entity, "was_modified", False)
        decay_reason = getattr(entity, "decay_reason", "N/A")
        section = getattr(entity, "digest_section", "N/A")
        hidden = getattr(entity, "hide_in_digest", False)

        if was_modified or entity.type in ["event", "notification"]:
            modified_count += 1
            status = "⚠️  MODIFIED" if was_modified else "✓  Unchanged"
            hide_marker = " [HIDDEN]" if hidden else ""

            print(f"\n{status}{hide_marker}")
            print(f"  Type: {entity.type}")
            print(f"  Subject: {entity.source_subject[:70]}")
            print(f"  Importance: {format_importance(stored)} → {format_importance(resolved)}")
            print(f"  Reason: {decay_reason}")
            print(f"  Section: {section}")

            # Show temporal fields if present
            if hasattr(entity, "event_time") and entity.event_time:
                time_until = entity.event_time - now
                hours = time_until.total_seconds() / 3600
                print(f"  Time until event: {hours:.1f} hours")

            if hasattr(entity, "otp_expires_at") and entity.otp_expires_at:
                time_until = entity.otp_expires_at - now
                mins = time_until.total_seconds() / 60
                print(f"  OTP expires in: {mins:.1f} minutes")

            if hasattr(entity, "ship_status") and entity.ship_status:
                print(f"  Shipping status: {entity.ship_status}")

    # Show statistics
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    stats = get_temporal_stats()
    print(f"Total processed: {stats['total_processed']}")
    print(f"Modified: {modified_count} ({modified_count / len(entities) * 100:.1f}%)")
    print(f"  - Escalated: {stats['escalated']}")
    print(f"  - Downgraded: {stats['downgraded']}")
    print(f"  - Unchanged: {stats['unchanged']}")
    print(f"Hidden from digest: {stats['hidden']}")
    print(f"Parse errors: {stats['parse_errors']}")

    if stats["decay_reasons"]:
        print("\nDecay reasons breakdown:")
        for reason, count in sorted(
            stats["decay_reasons"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  - {reason}: {count}")

    print("\n" + "=" * 80)
    print("✅ SMOKE TEST COMPLETE")
    print("=" * 80)
    print("\nWhat to look for:")
    print("  ✓ Events starting soon → escalated to critical (TODAY section)")
    print("  ✓ Events 3-7 days away → time_sensitive (COMING_UP section)")
    print("  ✓ Events >7 days away → routine (WORTH_KNOWING section)")
    print("  ✓ Expired events → hidden from digest")
    print("  ✓ Active OTP codes → escalated to critical")
    print("  ✓ Packages out for delivery → escalated to critical")
    print("  ✓ Old deliveries → downgraded to routine")
    print("\n")


if __name__ == "__main__":
    main()
