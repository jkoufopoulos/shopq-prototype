#!/usr/bin/env python3
"""
Validate Phase 1 filters against ground truth (99-email user review)

This script tests the time-decay and self-email filters on the actual
user-labeled dataset to measure effectiveness.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.classification.self_emails import is_self_email
from mailq.classification.time_decay import is_expired_event


def load_ground_truth():
    """Load user-labeled emails from CSV"""
    csv_path = Path(__file__).parent.parent / "inbox_review_with notes - inbox_review.csv"

    if not csv_path.exists():
        print(f"❌ Ground truth file not found: {csv_path}")
        return [], [], []

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    # User marked emails as YES (should feature) or NO (noise)
    featured = [e for e in emails if e["should_feature"].strip().lower() in ["yes", "y"]]
    not_featured = [e for e in emails if e["should_feature"].strip().lower() in ["no", "n"]]

    return emails, featured, not_featured


def validate_time_decay_filter():
    """
    Test time-decay filter on ground truth data.

    User noted these should be filtered:
    - "Accepted: Victor @ Tue Nov 18" (sent Oct 31, but event is Nov 18 → future, don't filter)
    - "Drawing Hive starts in 1 hour" (past event → filter)
    - "Notification: Event @ Wed Oct 29" (past → filter)
    - Multiple "past event" notes in data

    Expected: ~13 past event emails should be filtered
    """
    print("=" * 70)
    print("PHASE 1 VALIDATION: Time-Decay Filter (Expired Events)")
    print("=" * 70)
    print()

    emails, featured, not_featured = load_ground_truth()

    # Test date: Nov 1, 2025 12:00 PM (just after emails were sent)
    test_now = datetime(2025, 11, 1, 12, 0, 0)

    # Find emails with "past event" or "expired" in notes/reasoning
    past_event_notes = [
        e
        for e in emails
        if "past event" in (e.get("notes", "") + e.get("reasoning", "")).lower()
        or "expired" in (e.get("notes", "") + e.get("reasoning", "")).lower()
        or "old email" in (e.get("notes", "") + e.get("reasoning", "")).lower()
    ]

    # Count how many would be filtered
    filtered_count = 0
    filtered_correctly = []
    filtered_incorrectly = []

    for email in emails:
        should_filter = is_expired_event(email, test_now)

        if should_filter:
            filtered_count += 1

            # Check if user also marked this as NO (noise)
            is_noise = email["should_feature"].strip().lower() in ["no", "n"]

            # Check if notes mention "past event"
            is_past_event_note = (
                "past event" in (email.get("notes", "") + email.get("reasoning", "")).lower()
            )

            if is_noise and is_past_event_note:
                filtered_correctly.append(email)
            elif email["should_feature"].strip().lower() in ["yes", "y"]:
                # Oops, filtered something user wanted
                filtered_incorrectly.append(email)

    print("📊 Results:")
    print(f"  Total emails: {len(emails)}")
    print(f"  User marked {len(past_event_notes)} with 'past event' notes")
    print(f"  Filter would remove: {filtered_count} emails")
    print()

    if filtered_correctly:
        print(f"✅ Correctly filtered ({len(filtered_correctly)} emails):")
        for email in filtered_correctly[:5]:  # Show first 5
            subject = email.get("subject", "")[:60]
            notes = email.get("notes", "") or email.get("reasoning", "")
            print(f"  • {subject}...")
            print(f"    → {notes[:80]}")
        if len(filtered_correctly) > 5:
            print(f"  ... and {len(filtered_correctly) - 5} more")
        print()

    if filtered_incorrectly:
        print(f"❌ Incorrectly filtered ({len(filtered_incorrectly)} emails - user wanted these!):")
        for email in filtered_incorrectly:
            subject = email.get("subject", "")[:60]
            print(f"  • {subject}...")
        print()
    else:
        print("✅ No false positives! (didn't filter anything user wanted)")
        print()

    # Summary
    if filtered_count > 0:
        precision = len(filtered_correctly) / filtered_count if filtered_count > 0 else 0
        print(f"📈 Precision: {precision:.1%} ({len(filtered_correctly)}/{filtered_count})")
        print("   (Of emails filtered, how many were correctly identified as past events)")
    else:
        print("⚠️  No emails filtered (filter might be too conservative)")

    print()
    return {
        "total_filtered": filtered_count,
        "correctly_filtered": len(filtered_correctly),
        "incorrectly_filtered": len(filtered_incorrectly),
    }


def validate_self_email_filter():
    """
    Test self-email filter on ground truth data.

    User marked "Your Inbox --Saturday, November 01..." as NO
    with note "Mailq email"

    Expected: 1 MailQ digest email should be filtered
    """
    print("=" * 70)
    print("PHASE 1 VALIDATION: Self-Email Filter (MailQ Digest)")
    print("=" * 70)
    print()

    emails, featured, not_featured = load_ground_truth()

    # Find MailQ digest emails
    mailq_emails = [
        e
        for e in emails
        if "mailq" in (e.get("notes", "") + e.get("reasoning", "")).lower()
        or "your inbox --" in e.get("subject", "").lower()
    ]

    # Count how many would be filtered
    filtered_count = 0
    filtered_correctly = []

    for email in emails:
        should_filter = is_self_email(email, user_email="jkoufopoulos@gmail.com")

        if should_filter:
            filtered_count += 1

            # Check if user also marked this as noise
            is_noise = email["should_feature"].strip().lower() in ["no", "n"]

            # Check if notes mention "mailq"
            is_mailq_note = "mailq" in (email.get("notes", "") + email.get("reasoning", "")).lower()

            if is_noise and (is_mailq_note or "your inbox --" in email.get("subject", "").lower()):
                filtered_correctly.append(email)

    print("📊 Results:")
    print(f"  Total emails: {len(emails)}")
    print(f"  User marked {len(mailq_emails)} with 'mailq' notes")
    print(f"  Filter would remove: {filtered_count} emails")
    print()

    if filtered_correctly:
        print("✅ Correctly filtered MailQ digest emails:")
        for email in filtered_correctly:
            subject = email.get("subject", "")[:60]
            notes = email.get("notes", "") or email.get("reasoning", "")
            print(f"  • {subject}...")
            print(f"    → {notes}")
        print()
    else:
        print("⚠️  No MailQ emails found (might not be in this batch)")
        print()

    return {"total_filtered": filtered_count, "correctly_filtered": len(filtered_correctly)}


def main():
    print("\n🧪 PHASE 1 FILTER VALIDATION")
    print("Testing filters against 99-email ground truth dataset")
    print()

    # Test time-decay filter
    time_decay_results = validate_time_decay_filter()

    # Test self-email filter
    self_email_results = validate_self_email_filter()

    # Overall summary
    print("=" * 70)
    print("OVERALL PHASE 1 IMPACT")
    print("=" * 70)
    total_removed = time_decay_results["total_filtered"] + self_email_results["total_filtered"]
    total_correct = (
        time_decay_results["correctly_filtered"] + self_email_results["correctly_filtered"]
    )

    print("\n📉 Noise Reduction:")
    print(f"  Would filter: {total_removed} emails ({total_removed / 99 * 100:.1f}% of inbox)")
    print(f"  Correctly filtered: {total_correct} emails")

    if time_decay_results.get("incorrectly_filtered", 0) > 0:
        print(f"\n⚠️  WARNING: {time_decay_results['incorrectly_filtered']} false positives!")
        print("  (Filtered emails user wanted to see)")
    else:
        print("\n✅ No false positives - safe to deploy!")

    print()


if __name__ == "__main__":
    main()
