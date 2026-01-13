#!/usr/bin/env python3
"""
Apply Claim 1 corrections to GDS:
Change 52 order lifecycle emails from type=notification → type=receipt
"""

import csv
import shutil
from datetime import datetime
from pathlib import Path

# Email IDs to correct
CORRECTION_IDS = {
    108,
    125,
    129,
    138,
    142,
    146,
    161,
    166,
    170,
    178,
    179,
    230,
    237,
    238,
    239,
    240,
    241,
    242,
    243,
    244,
    245,
    246,
    247,
    252,
    255,
    257,
    258,
    259,
    260,
    261,
    262,
    263,
    264,
    265,
    266,
    267,
    268,
    269,
    270,
    307,
    308,
    417,
    419,
    420,
    430,
    441,
    442,
    445,
    446,
    451,
    453,
    500,
}


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


def main():
    gds_path = Path("data/evals/classification/gds-2.0.csv")

    # Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = gds_path.with_suffix(f".csv.backup_claim1_{timestamp}")
    shutil.copy(gds_path, backup_path)
    print(f"✅ Backup created: {backup_path}")

    # Load GDS
    emails = load_gds(str(gds_path))
    print(f"Loaded {len(emails)} emails from GDS")

    # Apply corrections
    corrected_count = 0
    for email in emails:
        email_id = int(email.get("email_id", 0))
        if email_id in CORRECTION_IDS:
            old_type = email.get("email_type")
            if old_type == "notification":
                email["email_type"] = "receipt"
                # Ensure client_label is also correct
                email["client_label"] = "receipts"
                corrected_count += 1
                print(f"  Corrected ID {email_id}: notification → receipt")

    # Save
    save_gds(str(gds_path), emails)

    print(f"\n✅ Applied {corrected_count} corrections to GDS")
    print(f"   Expected: {len(CORRECTION_IDS)} corrections")

    if corrected_count != len(CORRECTION_IDS):
        print(f"\n⚠️  Warning: Expected {len(CORRECTION_IDS)} but applied {corrected_count}")


if __name__ == "__main__":
    main()
