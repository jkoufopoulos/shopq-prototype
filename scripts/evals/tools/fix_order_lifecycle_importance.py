#!/usr/bin/env python3
"""
Fix Order Lifecycle Importance in GDS

Applies the taxonomy rule: shipped and delivered emails are routine,
only out-for-delivery/arriving-today are time_sensitive.

Usage:
    python3 scripts/evals/tools/fix_order_lifecycle_importance.py [--dry-run]

Side Effects:
- Creates backup of gds-2.0.csv
- Updates importance for shipped/delivered emails to routine
"""

import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Patterns for each lifecycle stage
SHIPPED_PATTERNS = [
    "shipped:",
    "has shipped",
    "is on the way",
    "on its way",
    "in transit",
]

DELIVERED_PATTERNS = [
    "delivered:",
    "has been delivered",
    "was delivered",
]

# These should remain time_sensitive - don't touch
OUT_FOR_DELIVERY_PATTERNS = [
    "out for delivery",
    "arriving today",
    "arriving soon",
]


def should_be_routine(subject: str) -> tuple[bool, str]:
    """
    Check if email should be routine based on order lifecycle stage.

    Returns (should_fix, reason)
    """
    subject_lower = subject.lower()

    # Don't touch out-for-delivery emails
    if any(p in subject_lower for p in OUT_FOR_DELIVERY_PATTERNS):
        return False, "out_for_delivery (keep time_sensitive)"

    # Shipped emails should be routine
    if any(p in subject_lower for p in SHIPPED_PATTERNS):
        return True, "shipped (should be routine)"

    # Delivered emails should be routine
    if any(p in subject_lower for p in DELIVERED_PATTERNS):
        return True, "delivered (should be routine)"

    return False, ""


def fix_order_lifecycle(gds_path: Path, dry_run: bool = False) -> list[dict]:
    """
    Fix order lifecycle importance values.

    Side Effects:
    - Creates backup of GDS
    - Updates GDS file (unless dry_run)
    """
    with open(gds_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    changes = []

    for row in rows:
        subject = row.get("subject", "")
        importance = row.get("importance", "")
        email_id = row.get("email_id", "")

        # Only fix time_sensitive emails that should be routine
        if importance != "time_sensitive":
            continue

        should_fix, reason = should_be_routine(subject)
        if should_fix:
            changes.append(
                {
                    "email_id": email_id,
                    "subject": subject[:60],
                    "old": importance,
                    "new": "routine",
                    "reason": reason,
                }
            )
            row["importance"] = "routine"
            row["importance_reason"] = f"taxonomy_fix_{reason.split()[0]}"

    if dry_run:
        return changes

    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = gds_path.with_suffix(f".csv.backup_{timestamp}")
    shutil.copy(gds_path, backup_path)
    print(f"Backup created: {backup_path.name}")

    # Write updated GDS
    with open(gds_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return changes


def main():
    dry_run = "--dry-run" in sys.argv

    gds_path = Path("data/evals/classification/gds-2.0.csv")

    print("=" * 60)
    print("Fix Order Lifecycle Importance")
    print("=" * 60)
    print("Taxonomy rules:")
    print("  - shipped/in_transit → routine (no action possible)")
    print("  - delivered → routine (already happened)")
    print("  - out_for_delivery → time_sensitive (action window)")
    print()

    if dry_run:
        print("MODE: Dry run (no changes will be made)")

    changes = fix_order_lifecycle(gds_path, dry_run=dry_run)

    if not changes:
        print("\nNo changes needed - GDS already follows taxonomy")
        return

    print(f"\n{'Changes to apply:' if dry_run else 'Changes applied:'}")
    print("-" * 60)

    for change in changes:
        print(f"  ID {change['email_id']:3s}: time_sensitive → routine")
        print(f"         {change['subject']}")
        print(f"         Reason: {change['reason']}")

    print("-" * 60)
    print(f"Total: {len(changes)} emails {'would be ' if dry_run else ''}corrected")

    if dry_run:
        print("\nRun without --dry-run to apply changes")


if __name__ == "__main__":
    main()
