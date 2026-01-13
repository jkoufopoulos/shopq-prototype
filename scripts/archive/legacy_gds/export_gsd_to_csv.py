#!/usr/bin/env python3
"""
Export all Ground Source of Decisions (GSD) data to CSV files.

Creates 4 CSV files:
1. gsd_classifications.csv - Main classification ground truth (type, importance, temporal)
2. gsd_digest_sections.csv - Which section each email should appear in
3. gsd_feedback.csv - User feedback on digest decisions (from database)
4. gsd_organization_patterns.csv - Email organization patterns (from database)
"""

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

# Project root
REPO_ROOT = Path(__file__).parent.parent
GOLDEN_SET_DIR = REPO_ROOT / "tests" / "golden_set"
OUTPUT_DIR = REPO_ROOT / "gsd_exports"
DB_PATH = REPO_ROOT / "mailq" / "data" / "mailq.db"

# Main GSD file
GDS_FILE = GOLDEN_SET_DIR / "gds-1.0.csv"
MESSAGES_FILE = GOLDEN_SET_DIR / "messages.jsonl"


def load_gds_classifications() -> list[dict[str, Any]]:
    """Load main GSD classification data."""
    data = []

    if GDS_FILE.exists():
        with open(GDS_FILE, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
        print(f"✓ Loaded {len(data)} records from {GDS_FILE.name}")
    else:
        print(f"✗ File not found: {GDS_FILE}")

    return data


def load_messages_jsonl() -> list[dict[str, Any]]:
    """Load messages from JSONL file."""
    data = []

    if MESSAGES_FILE.exists():
        with open(MESSAGES_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        print(f"✓ Loaded {len(data)} messages from {MESSAGES_FILE.name}")
    else:
        print(f"✗ File not found: {MESSAGES_FILE}")

    return data


def determine_digest_section(email: dict[str, Any]) -> str:
    """
    Determine which digest section an email should appear in based on GSD schema.

    Maps importance → digest section:
    - critical → TODAY (NOW)
    - time_sensitive → COMING_UP
    - routine → WORTH_KNOWING
    """
    importance = email.get("importance", "").lower()
    email_type = email.get("type", "").lower()

    # Importance-based section assignment
    if importance == "critical":
        return "TODAY"
    if importance == "time_sensitive":
        return "COMING_UP"
    if importance == "routine":
        return "WORTH_KNOWING"
    return "UNKNOWN"


def export_gsd_classifications(data: list[dict[str, Any]], output_path: Path):
    """Export main GSD classification ground truth."""
    if not data:
        print("⚠ No classification data to export")
        return

    # Use all columns from the source data
    fieldnames = list(data[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"✓ Exported {len(data)} classifications to {output_path.name}")


def export_digest_sections(
    gds_data: list[dict[str, Any]], messages_data: list[dict[str, Any]], output_path: Path
):
    """
    Export which digest section each email should appear in.

    Combines GDS classification data with message metadata to determine section assignment.
    """
    section_data = []

    for gds_row in gds_data:
        message_id = gds_row.get("message_id", "")

        # Determine section
        section = determine_digest_section(gds_row)

        section_data.append(
            {
                "message_id": message_id,
                "email_type": gds_row.get("email_type", ""),
                "importance": gds_row.get("importance", ""),
                "digest_section": section,
                "from_email": gds_row.get("from_email", ""),
                "subject": gds_row.get("subject", ""),
                "snippet": (gds_row.get("snippet", "") or "")[:100],  # Truncate for readability
                "timestamp": gds_row.get("timestamp", gds_row.get("received_date", "")),
                "temporal_start": gds_row.get("temporal_start", ""),
                "temporal_end": gds_row.get("temporal_end", ""),
                "p0_category": gds_row.get("p0_category", ""),
                "in_digest": gds_row.get("in_digest", ""),
                "in_featured": gds_row.get("in_featured", ""),
                "in_noise": gds_row.get("in_noise", ""),
            }
        )

    fieldnames = [
        "message_id",
        "email_type",
        "importance",
        "digest_section",
        "from_email",
        "subject",
        "snippet",
        "timestamp",
        "temporal_start",
        "temporal_end",
        "p0_category",
        "in_digest",
        "in_featured",
        "in_noise",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(section_data)

    print(f"✓ Exported {len(section_data)} section assignments to {output_path.name}")


def export_feedback_from_db(output_path: Path):
    """Export user feedback from database."""
    if not DB_PATH.exists():
        print(f"⚠ Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM digest_feedback")
    rows = cursor.fetchall()

    if not rows:
        print("⚠ No feedback data in database")
        conn.close()
        return

    fieldnames = rows[0].keys()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    conn.close()
    print(f"✓ Exported {len(rows)} feedback records to {output_path.name}")


def export_patterns_from_db(output_path: Path):
    """Export learned organization patterns from database."""
    if not DB_PATH.exists():
        print(f"⚠ Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM digest_patterns")
    rows = cursor.fetchall()

    if not rows:
        print("⚠ No pattern data in database")
        conn.close()
        return

    fieldnames = rows[0].keys()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    conn.close()
    print(f"✓ Exported {len(rows)} patterns to {output_path.name}")


def main():
    """Export all GSD data to CSV files."""
    print("\n" + "=" * 60)
    print("GSD Data Export")
    print("=" * 60 + "\n")

    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Load data
    print("Loading data...\n")
    gds_data = load_gds_classifications()
    messages_data = load_messages_jsonl()

    # Export files
    print("\nExporting CSV files...\n")

    # 1. Main classifications
    export_gsd_classifications(gds_data, OUTPUT_DIR / f"gsd_classifications_{timestamp}.csv")

    # 2. Digest sections
    export_digest_sections(
        gds_data, messages_data, OUTPUT_DIR / f"gsd_digest_sections_{timestamp}.csv"
    )

    # 3. User feedback (from database)
    export_feedback_from_db(OUTPUT_DIR / f"gsd_feedback_{timestamp}.csv")

    # 4. Organization patterns (from database)
    export_patterns_from_db(OUTPUT_DIR / f"gsd_organization_patterns_{timestamp}.csv")

    print("\n" + "=" * 60)
    print(f"✓ All exports complete! Files saved to: {OUTPUT_DIR}/")
    print("=" * 60 + "\n")

    # Also create symlinks to latest versions (without timestamp)
    for old_name, new_name in [
        (f"gsd_classifications_{timestamp}.csv", "gsd_classifications_latest.csv"),
        (f"gsd_digest_sections_{timestamp}.csv", "gsd_digest_sections_latest.csv"),
        (f"gsd_feedback_{timestamp}.csv", "gsd_feedback_latest.csv"),
        (f"gsd_organization_patterns_{timestamp}.csv", "gsd_organization_patterns_latest.csv"),
    ]:
        old_path = OUTPUT_DIR / old_name
        new_path = OUTPUT_DIR / new_name
        if old_path.exists():
            if new_path.exists():
                new_path.unlink()
            new_path.symlink_to(old_name)


if __name__ == "__main__":
    main()
