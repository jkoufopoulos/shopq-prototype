#!/usr/bin/env python3
"""
Generate edge-case emails to test temporal boundary conditions.

These synthetic emails probe:
- TODAY cutoff (59/60/61 minutes away)
- COMING_UP limits (today 11:55pm vs tomorrow 12:05am)
- Receipt stability (delivered packages across timepoints)
- Critical downgrade timing (bills due exactly 24h, 72h)

Add these to the temporal golden dataset to ensure boundary coverage.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


def create_edge_cases():
    """Create 10 synthetic edge-case emails for temporal boundary testing."""

    edge_cases = [
        # Case 1: Event in 59 minutes (should be TODAY at T0)
        {
            "email_id": "edge_001",
            "subject": "Team standup in 59 minutes",
            "from": "calendar@google.com",
            "snippet": "Reminder: Team standup starts at 2:59pm today. Join via Zoom link.",
            "predicted_importance": "time_sensitive",
            "predicted_type": "event",
            "predicted_category": "event",
            "temporal_hints": "Event in 59 minutes - should be TODAY at T0",
            "expected_t0": "today",
            "expected_t1": "skip",  # Expired
            "expected_t2": "skip",
        },
        # Case 2: Event in 61 minutes (should be COMING_UP at T0)
        {
            "email_id": "edge_002",
            "subject": "Dentist appointment in 61 minutes",
            "from": "appointments@dental.com",
            "snippet": "Your appointment is scheduled for 3:01pm today.",
            "predicted_importance": "time_sensitive",
            "predicted_type": "event",
            "predicted_category": "event",
            "temporal_hints": "Event in 61 minutes - boundary between TODAY and COMING_UP",
            "expected_t0": "coming_up",  # Just outside TODAY window
            "expected_t1": "skip",
            "expected_t2": "skip",
        },
        # Case 3: Event today at 11:55pm (edge of day boundary)
        {
            "email_id": "edge_003",
            "subject": "Late night event tonight at 11:55pm",
            "from": "events@meetup.com",
            "snippet": "Join us for a special late-night event tonight at 11:55pm!",
            "predicted_importance": "time_sensitive",
            "predicted_type": "event",
            "predicted_category": "event",
            "temporal_hints": "Event at 11:55pm today - tests day boundary",
            "expected_t0": "today",  # Still "today"
            "expected_t1": "skip",  # Past
            "expected_t2": "skip",
        },
        # Case 4: Event tomorrow at 12:05am (just after midnight)
        {
            "email_id": "edge_004",
            "subject": "Midnight event tomorrow at 12:05am",
            "from": "events@nightowl.com",
            "snippet": "Special midnight event starting at 12:05am tomorrow!",
            "predicted_importance": "time_sensitive",
            "predicted_type": "event",
            "predicted_category": "event",
            "temporal_hints": "Event at 12:05am tomorrow - tests midnight boundary",
            "expected_t0": "coming_up",  # Tomorrow
            "expected_t1": "today",  # Now "today" (after midnight)
            "expected_t2": "skip",
        },
        # Case 5: Bill due in exactly 24 hours (T1 critical test)
        {
            "email_id": "edge_005",
            "subject": "Bill due tomorrow at this time",
            "from": "billing@utility.com",
            "snippet": "Your electric bill of $150 is due in exactly 24 hours.",
            "predicted_importance": "critical",
            "predicted_type": "notification",
            "predicted_category": "bill",
            "temporal_hints": "Bill due in 24h - should downgrade from CRITICAL to TODAY at T1",
            "expected_t0": "critical",
            "expected_t1": "today",  # Due "today" at T1
            "expected_t2": "skip",  # Overdue, expired
        },
        # Case 6: Package out for delivery (stable TODAY across timepoints)
        {
            "email_id": "edge_006",
            "subject": "Your package is out for delivery today!",
            "from": "shipping@amazon.com",
            "snippet": "Your order #12345 is out for delivery and will arrive today by 8pm.",
            "predicted_importance": "time_sensitive",
            "predicted_type": "notification",
            "predicted_category": "delivery",
            "temporal_hints": "Out for delivery - should be TODAY at T0, then skip (delivered)",
            "expected_t0": "today",
            "expected_t1": "skip",  # Delivered by now
            "expected_t2": "skip",
        },
        # Case 7: Receipt (stable WORTH_KNOWING)
        {
            "email_id": "edge_007",
            "subject": "Your receipt from Starbucks",
            "from": "receipts@starbucks.com",
            "snippet": "Thank you for your purchase! Your receipt for $5.75 is attached.",
            "predicted_importance": "routine",
            "predicted_type": "receipt",
            "predicted_category": "receipt",
            "temporal_hints": "Receipt - should be stable in WORTH_KNOWING across all timepoints",
            "expected_t0": "worth_knowing",
            "expected_t1": "worth_knowing",  # Stable
            "expected_t2": "worth_knowing",  # Still stable
        },
        # Case 8: Event in 7 days (COMING_UP boundary)
        {
            "email_id": "edge_008",
            "subject": "Conference next week - 7 days away",
            "from": "events@conference.com",
            "snippet": "Your conference starts in exactly 7 days. Don't forget to register!",
            "predicted_importance": "time_sensitive",
            "predicted_type": "event",
            "predicted_category": "event",
            "temporal_hints": "Event in 7 days - tests COMING_UP window edge",
            "expected_t0": "coming_up",
            "expected_t1": "coming_up",  # 6 days away
            "expected_t2": "coming_up",  # 4 days away, still in window
        },
        # Case 9: OTP code (critical, but expires quickly)
        {
            "email_id": "edge_009",
            "subject": "Your verification code: 123456",
            "from": "security@service.com",
            "snippet": "Your one-time verification code is 123456. Valid for 10 minutes.",
            "predicted_importance": "critical",
            "predicted_type": "notification",
            "predicted_category": "security",
            "temporal_hints": "OTP - CRITICAL at T0, should be skip by T1 (expired)",
            "expected_t0": "critical",
            "expected_t1": "skip",  # Expired after 24h
            "expected_t2": "skip",
        },
        # Case 10: Promotional email (stable EVERYTHING_ELSE)
        {
            "email_id": "edge_010",
            "subject": "50% off sale - limited time!",
            "from": "marketing@store.com",
            "snippet": "Don't miss our biggest sale of the year! 50% off everything.",
            "predicted_importance": "routine",
            "predicted_type": "promotion",
            "predicted_category": "promotional",
            "temporal_hints": "Promo - should be EVERYTHING_ELSE across all timepoints",
            "expected_t0": "everything_else",
            "expected_t1": "everything_else",
            "expected_t2": "everything_else",
        },
    ]

    # Add empty columns for user labeling (matching the main CSV format)
    for case in edge_cases:
        # T0 labels
        case["t0_critical"] = ""
        case["t0_today"] = ""
        case["t0_coming_up"] = ""
        case["t0_worth_knowing"] = ""
        case["t0_everything_else"] = ""
        case["t0_skip"] = ""

        # T1 labels
        case["t1_critical"] = ""
        case["t1_today"] = ""
        case["t1_coming_up"] = ""
        case["t1_worth_knowing"] = ""
        case["t1_everything_else"] = ""
        case["t1_skip"] = ""

        # T2 labels
        case["t2_critical"] = ""
        case["t2_today"] = ""
        case["t2_coming_up"] = ""
        case["t2_worth_knowing"] = ""
        case["t2_everything_else"] = ""
        case["t2_skip"] = ""

        case["notes"] = ""

    return edge_cases


def main():
    print("=" * 80)
    print("EDGE CASE EMAIL GENERATOR")
    print("=" * 80)
    print()

    # Create edge cases
    edge_cases = create_edge_cases()

    # Convert to DataFrame
    df = pd.DataFrame(edge_cases)

    # Save to CSV
    output_path = Path(__file__).parent.parent / "reports" / "temporal_edge_cases_10_emails.csv"
    df.to_csv(output_path, index=False)

    print(f"✅ Created {len(edge_cases)} edge-case emails")
    print(f"📂 Location: {output_path}")
    print()

    print("EDGE CASES CREATED:")
    print("-" * 80)
    for i, case in enumerate(edge_cases, 1):
        print(f"{i:2d}. {case['subject']}")
        print(f"    Hint: {case['temporal_hints']}")
        print(
            f"    Expected: T0={case['expected_t0']}, T1={case['expected_t1']}, T2={case['expected_t2']}"
        )
        print()

    print("=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print()
    print("1. Merge with main dataset:")
    print("   python3 scripts/merge_edge_cases_to_dataset.py")
    print()
    print("2. OR manually append to temporal_digest_review_50_emails.csv")
    print()
    print("3. Label using interactive tool:")
    print("   python3 scripts/interactive_temporal_review.py")
    print()
    print("4. The 'expected_*' columns show what we think should happen")
    print("   Compare your labels to these expectations to validate logic")
    print()


if __name__ == "__main__":
    main()
