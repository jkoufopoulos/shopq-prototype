#!/usr/bin/env python3
"""
Terminal viewer for Dataset 2 classification comparison: MailQ vs Ground Truth.

Shows T1 classifications (24h after most recent email) ordered by digest section.

Usage:
    python scripts/view_classification_table.py [OPTIONS]

Examples:
    # View all emails in digest order
    python scripts/view_classification_table.py

    # View only mismatches
    python scripts/view_classification_table.py --mismatches-only

    # View specific section
    python scripts/view_classification_table.py --filter skip

    # Show summary only
    python scripts/view_classification_table.py --summary
"""

import csv
import sys


def load_dataset2_with_ground_truth(csv_path: str) -> list[dict]:
    """Load Dataset 2 with both MailQ predictions and ground truth"""
    emails = []

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Get ground truth T1 directly from the column (keep as-is)
            ground_truth_t1 = row.get("ground_truth_t1", "").strip()

            # Default to empty if not specified
            if not ground_truth_t1:
                ground_truth_t1 = ""

            email = {
                "email_id": row["email_id"],
                "subject": row["subject"],
                "from": row.get("from", ""),
                "received_date": row.get("received_date", ""),
                "gds_type": row.get("gds_type", ""),
                "gds_importance": row.get("gds_importance", "routine"),
                "mailq_t1": row.get("mailq_t1", "noise"),
                "ground_truth_t1": ground_truth_t1,
                # Check if temporal context was extracted (look for event times, delivery dates, etc.)
                "has_temporal": "Yes" if _has_temporal_signal(row) else "No",
            }
            emails.append(email)

    return emails


def _has_temporal_signal(row: dict) -> bool:
    """Check if email likely has temporal context extracted"""
    subject = row.get("subject", "").lower()

    # Google Calendar format
    if "@" in subject and any(
        month in subject
        for month in [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ]
    ):
        return True

    # Delivery/receipt keywords
    if any(
        word in subject
        for word in ["delivered:", "shipped:", "order with", "receipt", "autopay", "payment"]
    ):
        return True

    return False


def sort_by_digest_order(emails: list[dict], sort_by: str = "mailq") -> list[dict]:
    """Sort emails by digest section order"""
    section_order = {
        "critical": 0,
        "today": 1,
        "coming_up": 2,
        "worth_knowing": 3,
        "everything_else": 4,
        "noise": 4,  # Same priority as everything_else
        "skip": 5,
    }

    sort_key = "mailq_t1" if sort_by == "mailq" else "ground_truth_t1"
    return sorted(emails, key=lambda e: section_order.get(e[sort_key], 99))


def print_legend():
    """Print legend explaining column meanings"""
    print("\n" + "=" * 100)
    print("CLASSIFICATION COMPARISON: MailQ vs Ground Truth")
    print("=" * 100)
    print("EVALUATION TIME: T1 = 24 hours after most recent email in dataset")
    print("  - Dataset: 70 emails from Nov 2-9, 2025")
    print("  - Most recent email: Nov 9, 2025")
    print("  - Digest evaluation time: Nov 10, 2025 at 6:20 PM EST (24h later)")
    print("=" * 100)
    print("GDS Type      = Gmail Data Science email type (event, receipt, notification, promotion)")
    print("GDS Imp       = Gmail importance level (critical, time_sensitive, routine)")
    print("Temporal      = Whether we extracted time info from email (Yes/No)")
    print("MailQ Placed  = Where MailQ pipeline placed this email at T1")
    print("Ground Truth  = Where human annotator placed this email at T1")
    print("=" * 100)
    print("\nDIGEST SECTIONS (in digest order):")
    print("  critical       = Urgent, high-stakes (verification codes, delivery tracking)")
    print("  today          = Events/deliveries happening today")
    print("  coming_up      = Events/deadlines in next 1-7 days")
    print("  worth_knowing  = Useful info, receipts, confirmations (no urgency)")
    print("  everything_else= Newsletters, promotions, low-value content")
    print("  skip           = Expired events, hidden from digest (in footer)")
    print("=" * 100 + "\n")


def print_table(emails: list[dict], max_subject_len: int = 40):
    """Print emails as formatted table"""

    # Print header
    print(
        f"\n{'Email ID':<12} {'Received':<16} {'Subject':<{max_subject_len}} {'GDS Type':<12} {'GDS Imp':<10} {'Temporal':<9} {'MailQ Placed':<15} {'Ground Truth':<15} {'Match':<6}"
    )
    print("-" * (12 + 16 + max_subject_len + 12 + 10 + 9 + 15 + 15 + 6 + 18))

    # Print rows
    for email in emails:
        subject = email["subject"]
        if len(subject) > max_subject_len:
            subject = subject[: max_subject_len - 3] + "..."

        # Parse and format received date with time, convert to EST
        received_date = email.get("received_date", "")
        # Format: "Thu, 06 Nov 2025 01:42:37 +0000" -> "Nov 5 8:42pm EST"
        if received_date:
            import re
            from datetime import datetime, timedelta, timezone

            # Parse the full date string
            match = re.search(
                r"(\d{1,2})\s+(\w{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s+([\+\-]\d{4})",
                received_date,
            )
            if match:
                day, month, year, hour, minute, second, tz_offset = match.groups()

                # Parse timezone offset
                tz_sign = 1 if tz_offset[0] == "+" else -1
                tz_hours = int(tz_offset[1:3])
                tz_minutes = int(tz_offset[3:5])
                tz_offset_seconds = tz_sign * (tz_hours * 3600 + tz_minutes * 60)

                # Create datetime in original timezone
                dt = datetime(
                    int(year),
                    {
                        "Jan": 1,
                        "Feb": 2,
                        "Mar": 3,
                        "Apr": 4,
                        "May": 5,
                        "Jun": 6,
                        "Jul": 7,
                        "Aug": 8,
                        "Sep": 9,
                        "Oct": 10,
                        "Nov": 11,
                        "Dec": 12,
                    }[month],
                    int(day),
                    int(hour),
                    int(minute),
                    int(second),
                    tzinfo=timezone(timedelta(seconds=tz_offset_seconds)),
                )

                # Convert to EST (UTC-5)
                est_tz = timezone(timedelta(hours=-5))
                dt_est = dt.astimezone(est_tz)

                # Format for display
                hour_int = dt_est.hour
                ampm = "am" if hour_int < 12 else "pm"
                display_hour = hour_int if hour_int <= 12 else hour_int - 12
                if display_hour == 0:
                    display_hour = 12

                received_date = f"{dt_est.strftime('%b')} {dt_est.day} {display_hour}:{dt_est.strftime('%M')}{ampm}"
            else:
                received_date = received_date[:20]  # Fallback

        mailq_section = email["mailq_t1"]
        ground_truth_section = email["ground_truth_t1"]
        match = "✓" if mailq_section == ground_truth_section else "✗"

        print(
            f"{email['email_id']:<12} "
            f"{received_date:<16} "
            f"{subject:<{max_subject_len}} "
            f"{email['gds_type']:<12} "
            f"{email['gds_importance']:<10} "
            f"{email['has_temporal']:<9} "
            f"{mailq_section:<15} "
            f"{ground_truth_section:<15} "
            f"{match:<6}"
        )

    print(f"\n{len(emails)} emails displayed\n")


def print_summary(emails: list[dict]):
    """Print accuracy summary"""
    from collections import Counter

    total = len(emails)
    matches = sum(1 for e in emails if e["mailq_t1"] == e["ground_truth_t1"])
    accuracy = matches / total * 100 if total > 0 else 0

    print("\n" + "=" * 80)
    print("ACCURACY SUMMARY (T1 = 24h after most recent email)")
    print("=" * 80)
    print("Evaluation Time: Nov 10, 2025 at 6:20 PM EST")
    print(f"Overall Accuracy: {accuracy:.1f}% ({matches}/{total} correct)")
    print()

    # MailQ section distribution
    mailq_counts = Counter([e["mailq_t1"] for e in emails])
    print("MailQ Section Distribution:")
    print("-" * 40)
    for section in ["critical", "today", "coming_up", "worth_knowing", "noise", "skip"]:
        count = mailq_counts.get(section, 0)
        pct = count / total * 100 if total else 0
        print(f"  {section:<20} {count:>3} ({pct:>5.1f}%)")

    print()

    # Ground Truth section distribution
    gt_counts = Counter([e["ground_truth_t1"] for e in emails])
    print("Ground Truth Section Distribution:")
    print("-" * 40)
    for section in ["critical", "today", "coming_up", "worth_knowing", "everything_else", "skip"]:
        count = gt_counts.get(section, 0)
        pct = count / total * 100 if total else 0
        print(f"  {section:<20} {count:>3} ({pct:>5.1f}%)")

    print()

    # Confusion matrix (simplified)
    print("Top Misclassification Patterns:")
    print("-" * 60)
    mismatches = [e for e in emails if e["mailq_t1"] != e["ground_truth_t1"]]
    mismatch_patterns = Counter([(e["ground_truth_t1"], e["mailq_t1"]) for e in mismatches])

    for (gt, mailq), count in mismatch_patterns.most_common(10):
        print(f"  Ground Truth: {gt:<15} → MailQ: {mailq:<15} ({count} emails)")

    print("=" * 80 + "\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="View Dataset 2 classification comparison")
    parser.add_argument("--filter", help="Filter by ground truth T1 section")
    parser.add_argument("--head", type=int, help="Show only first N emails")
    parser.add_argument("--summary", action="store_true", help="Show summary statistics only")
    parser.add_argument(
        "--mismatches-only",
        action="store_true",
        help="Show only emails where MailQ != Ground Truth",
    )
    parser.add_argument("--no-legend", action="store_true", help="Skip printing the legend")
    parser.add_argument(
        "--sort-by",
        choices=["mailq", "ground-truth"],
        default="ground-truth",
        help="Sort by MailQ section or Ground Truth section (default: ground-truth)",
    )
    args = parser.parse_args()

    # Load data from the clean comparison CSV
    csv_path = "reports/dataset2_t1_comparison_clean.csv"
    emails = load_dataset2_with_ground_truth(csv_path)

    if not emails:
        print(f"Error: Could not load data from {csv_path}")
        return 1

    # Print legend (unless summary-only or user disabled it)
    if not args.summary and not args.no_legend:
        print_legend()

    # Apply filters
    if args.filter:
        emails = [e for e in emails if e["ground_truth_t1"].lower() == args.filter.lower()]
        print(f"Filtered to Ground Truth section: {args.filter}\n")

    if args.mismatches_only:
        emails = [e for e in emails if e["mailq_t1"] != e["ground_truth_t1"]]
        print("Filtered to mismatches only (MailQ != Ground Truth)\n")

    # Sort by digest order
    sort_by = "mailq" if args.sort_by == "mailq" else "ground-truth"
    emails = sort_by_digest_order(emails, sort_by=sort_by.replace("-", "_"))

    if args.head:
        emails = emails[: args.head]

    # Display
    if args.summary:
        # For summary, load all emails (not filtered)
        all_emails = load_dataset2_with_ground_truth(csv_path)
        print_summary(all_emails)
    else:
        print_table(emails)
        if not args.filter and not args.head and not args.mismatches_only:
            print_summary(load_dataset2_with_ground_truth(csv_path))

    return 0


if __name__ == "__main__":
    sys.exit(main())
