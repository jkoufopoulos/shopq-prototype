#!/usr/bin/env python3
"""
Interactive GDS Correction Review

Shows each proposed correction one at a time for user approval.
Only applies approved changes to the GDS.
"""

import csv
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_gds(csv_path: str) -> list[dict]:
    """Load GDS from CSV"""
    emails = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emails.append(row)
    return emails


def save_gds(csv_path: str, emails: list[dict]):
    """Save GDS back to CSV"""
    if not emails:
        return

    fieldnames = list(emails[0].keys())
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emails)


def is_order_lifecycle(subject: str, snippet: str, from_email: str) -> bool:
    """Check if email appears to be order lifecycle"""
    order_signals = [
        "shipped",
        "delivered",
        "delivery",
        "order",
        "tracking",
        "package",
        "out for delivery",
        "arriving",
        "confirmation",
        "receipt",
        "refund",
        "return",
    ]

    combined_text = (subject + " " + snippet).lower()
    return any(signal in combined_text for signal in order_signals)


def main():
    gds_path = Path("data/evals/classification/gds-2.0.csv")

    print("Loading GDS...")
    emails = load_gds(str(gds_path))

    # Find candidates: type=notification but likely order lifecycle
    candidates = []
    for email in emails:
        email_type = email.get("email_type", "").strip()
        subject = email.get("subject", "")
        snippet = email.get("snippet", "")
        from_email = email.get("from_email", "")

        if email_type == "notification" and is_order_lifecycle(subject, snippet, from_email):
            candidates.append(email)

    print(f"\nFound {len(candidates)} emails to review\n")
    print("=" * 80)

    # Review each one
    approved_changes = []

    for i, email in enumerate(candidates, 1):
        print(f"\n📧 Email {i} of {len(candidates)}")
        print("=" * 80)
        print(f"From: {email.get('from_email', '')}")
        print(f"Subject: {email.get('subject', '')}")
        print(f"\nSnippet:\n{email.get('snippet', '')}")
        print("\nCurrent Labels:")
        print(f"  type: {email.get('email_type', '')}")
        print(f"  importance: {email.get('importance', '')}")
        print(f"  client_label: {email.get('client_label', '')}")
        print("\nProposed Change:")
        print("  type: notification → receipt")
        print("=" * 80)

        # Get user decision
        while True:
            response = input("\nApprove this change? (y/n/q to quit): ").lower().strip()
            if response in ["y", "n", "q"]:
                break
            print("Please enter y, n, or q")

        if response == "q":
            print("\nQuitting review...")
            break
        if response == "y":
            approved_changes.append(email.get("email_id"))
            print("✅ Approved")
        else:
            print("⏭️  Skipped")

    # Apply approved changes
    if approved_changes:
        print(f"\n\nApplying {len(approved_changes)} approved changes...")

        # Create backup
        backup_path = gds_path.with_suffix(".csv.backup2")
        with open(gds_path) as src, open(backup_path, "w") as dst:
            dst.write(src.read())
        print(f"Backup created: {backup_path}")

        # Apply changes
        changes_made = 0
        for email in emails:
            if email.get("email_id") in approved_changes:
                email["email_type"] = "receipt"
                changes_made += 1

        # Save
        save_gds(str(gds_path), emails)

        print(f"\n✅ Applied {changes_made} changes to GDS")
        print("📊 Summary:")
        print(f"   - Reviewed: {i} emails")
        print(f"   - Approved: {len(approved_changes)} changes")
        print(f"   - Skipped: {i - len(approved_changes)} emails")

    else:
        print("\n\nNo changes approved. GDS unchanged.")


if __name__ == "__main__":
    main()
