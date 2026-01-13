#!/usr/bin/env python3
"""
Auto-extract temporal_start and temporal_end for events and deadlines.

Only processes emails with type ∈ {event, deadline}.
Proposes temporal fields using dateparser + regex.
Outputs for human verification.
"""

import csv
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# Note: This is a placeholder - in production you'd use dateparser library
# For now, we'll use simple regex patterns


def extract_temporal_from_event(
    subject: str,
    snippet: str,
    received_date: str,  # noqa: ARG001
) -> tuple:
    """
    Extract temporal_start and temporal_end for event emails.

    Returns: (temporal_start, temporal_end, confidence, method)
    """
    combined = f"{subject} {snippet}".lower()

    # Try to find explicit date/time patterns
    # Pattern: "on Monday, Nov 11 at 3pm"
    # Pattern: "tomorrow at 10am"
    # Pattern: "this week"

    # Simplified for demo - would use dateparser in production

    # Check for "tomorrow"
    if "tomorrow" in combined:
        # Assume 9am-10am tomorrow
        tomorrow = datetime.now() + timedelta(days=1)
        start = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        end = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        return (start.isoformat() + "Z", end.isoformat() + "Z", 0.7, "tomorrow_pattern")

    # Check for "this week"
    if "this week" in combined or "coming up" in combined:
        # Assume within 7 days
        future = datetime.now() + timedelta(days=3)
        start = future.replace(hour=9, minute=0, second=0, microsecond=0)
        end = future.replace(hour=10, minute=0, second=0, microsecond=0)
        return (start.isoformat() + "Z", end.isoformat() + "Z", 0.5, "this_week_pattern")

    # Check for calendar invite keywords
    if "join with google meet" in combined or "calendar" in combined:
        # Likely has structured time - suggest manual review
        return (None, None, 0.3, "calendar_invite_needs_manual")

    return (None, None, 0.0, "no_pattern_found")


def extract_temporal_from_deadline(
    subject: str,
    snippet: str,
    received_date: str,  # noqa: ARG001
) -> tuple:
    """
    Extract temporal_start (due date) for deadline emails.

    Returns: (temporal_start, None, confidence, method)
    """
    combined = f"{subject} {snippet}".lower()

    # Pattern: "due today"
    if "due today" in combined or "expires today" in combined or "ends today" in combined:
        today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
        return (today.isoformat() + "Z", None, 0.9, "due_today_pattern")

    # Pattern: "due tomorrow"
    if "due tomorrow" in combined or "expires tomorrow" in combined:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)
        return (tomorrow.isoformat() + "Z", None, 0.9, "due_tomorrow_pattern")

    # Pattern: "pay by", "submit by", "due by"
    if any(word in combined for word in ["pay by", "submit by", "due by", "deadline"]):
        # Would use dateparser here - for now suggest manual review
        return (None, None, 0.5, "deadline_keyword_needs_manual")

    return (None, None, 0.0, "no_pattern_found")


def main():
    input_path = Path("tests/golden_set/golden_dataset_500_labeled.csv")
    output_path = Path("tests/golden_set/golden_dataset_500_with_temporal.csv")
    review_path = Path("tests/golden_set/temporal_for_review.csv")

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        print("   Run manual_label_golden_set.py first to create labeled dataset")
        return

    print("🔍 Extracting temporal fields for events and deadlines...")
    print(f"   Input: {input_path}")
    print()

    # Load labeled dataset
    with open(input_path) as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    # Filter to events and deadlines
    events_deadlines = [e for e in emails if e.get("type") in ["event", "deadline"]]

    print(f"📊 Found {len(events_deadlines)} emails needing temporal extraction:")
    type_counts = Counter(e["type"] for e in events_deadlines)
    for email_type, count in type_counts.items():
        print(f"   {email_type}: {count}")
    print()

    # Extract temporal fields
    extracted = []
    needs_review = []
    stats = Counter()

    for email in events_deadlines:
        email_type = email["type"]
        subject = email.get("subject", "")
        snippet = email.get("snippet", "")
        received_date = email.get("received_date", "")

        if email_type == "event":
            start, end, conf, method = extract_temporal_from_event(subject, snippet, received_date)
        elif email_type == "deadline":
            start, end, conf, method = extract_temporal_from_deadline(
                subject, snippet, received_date
            )
        else:
            continue

        email["temporal_start"] = start or ""
        email["temporal_end"] = end or ""
        email["temporal_confidence"] = conf
        email["temporal_method"] = method

        stats[method] += 1

        if conf < 0.7 or start is None:
            needs_review.append(email)
            extracted.append(
                {
                    "message_id": email["message_id"],
                    "type": email_type,
                    "subject": subject[:80],
                    "snippet": snippet[:100],
                    "temporal_start": start or "NEEDS_REVIEW",
                    "temporal_end": end or "",
                    "confidence": conf,
                    "method": method,
                }
            )

    # Add temporal fields to all emails (null for non-events/deadlines)
    for email in emails:
        if email["type"] not in ["event", "deadline"]:
            email["temporal_start"] = ""
            email["temporal_end"] = ""
            email["temporal_confidence"] = ""
            email["temporal_method"] = ""
        email["version"] = "gds-1.0"

    # Write updated dataset
    print("📊 Extraction Results:")
    for method, count in stats.items():
        print(f"   {method}: {count}")
    print()

    # Write main dataset
    with open(output_path, "w", newline="") as f:
        if emails:
            writer = csv.DictWriter(f, fieldnames=emails[0].keys())
            writer.writeheader()
            writer.writerows(emails)

    print(f"✅ Wrote dataset with temporal fields to {output_path}")

    # Write review file
    if extracted:
        with open(review_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=extracted[0].keys())
            writer.writeheader()
            writer.writerows(extracted)

        print(f"⚠️  {len(needs_review)} emails need manual temporal review")
        print(f"   Review file: {review_path}")
        print()
        print("📝 Next steps:")
        print("   1. Review temporal_for_review.csv")
        print("   2. Manually set temporal_start/temporal_end for low-confidence items")
        print("   3. Re-run this script or update golden_dataset_500_with_temporal.csv directly")
    else:
        print("✅ All temporal fields extracted with high confidence")

    print()
    print("📊 Final Dataset Summary:")
    print(f"   Total emails: {len(emails)}")
    print(f"   With temporal fields: {len(events_deadlines)}")
    print(f"   Without temporal fields: {len(emails) - len(events_deadlines)}")


if __name__ == "__main__":
    main()
