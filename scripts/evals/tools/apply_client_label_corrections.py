#!/usr/bin/env python3
"""
Apply Client Label Corrections to GDS

Reads decisions from client_label_review_decisions.csv and applies them to gds-2.0.csv.
Creates a backup before making changes.

Usage:
    python3 scripts/evals/tools/apply_client_label_corrections.py [--dry-run]

Side Effects:
- Creates backup of gds-2.0.csv
- Modifies gds-2.0.csv client_label values based on review decisions
"""

import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path


def load_decisions(decisions_path: Path) -> dict[int, dict]:
    """Load review decisions keyed by email_id"""
    decisions = {}
    if not decisions_path.exists():
        print(f"Error: Decisions file not found: {decisions_path}")
        sys.exit(1)

    with open(decisions_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email_id = int(row["email_id"])
            decisions[email_id] = row
    return decisions


def apply_corrections(
    gds_path: Path, decisions: dict[int, dict], dry_run: bool = False
) -> list[dict]:
    """
    Apply client_label corrections to GDS.

    Returns list of changes made.

    Side Effects:
    - Creates backup of GDS file
    - Writes updated GDS file (unless dry_run)
    """
    # Read current GDS
    with open(gds_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    changes = []

    for row in rows:
        email_id = int(row["email_id"])
        if email_id in decisions:
            decision = decisions[email_id]

            # Only update GDS when LLM was correct (decision == "llm")
            if decision["decision"] != "llm":
                continue

            old_label = row["client_label"]
            new_label = decision["correct_value"]

            if old_label != new_label:
                changes.append(
                    {
                        "email_id": email_id,
                        "subject": row["subject"][:60],
                        "old": old_label,
                        "new": new_label,
                        "decision_source": decision["decision"],
                        "note": decision.get("note", ""),
                    }
                )
                row["client_label"] = new_label

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
    decisions_path = Path("data/evals/classification/client_label_review_decisions.csv")

    print("=" * 60)
    print("Apply Client Label Corrections to GDS")
    print("=" * 60)

    if dry_run:
        print("MODE: Dry run (no changes will be made)")

    # Load decisions
    decisions = load_decisions(decisions_path)
    print(f"Loaded {len(decisions)} review decisions")

    # Apply corrections
    changes = apply_corrections(gds_path, decisions, dry_run=dry_run)

    if not changes:
        print("\nNo changes needed - GDS already matches review decisions")
        return

    # Display changes
    print(f"\n{'Changes to apply:' if dry_run else 'Changes applied:'}")
    print("-" * 60)

    for change in changes:
        print(f"  ID {change['email_id']:3d}: {change['old']:>16s} -> {change['new']:<16s}")
        print(f"         {change['subject']}")
        if change["note"]:
            print(f"         Note: {change['note']}")

    print("-" * 60)
    print(f"Total: {len(changes)} client_label values {'would be ' if dry_run else ''}updated")

    if dry_run:
        print("\nRun without --dry-run to apply changes")


if __name__ == "__main__":
    main()
