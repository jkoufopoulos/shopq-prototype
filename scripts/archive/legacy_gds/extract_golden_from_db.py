#!/usr/bin/env python3
"""
Extract golden dataset from shopq_tracking.db

Pulls real emails with ShopQ importance labels, balances classes,
and creates a golden dataset for Phase 0 validation.
"""

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path


def extract_emails_from_db(db_path: Path, limit_per_class: dict = None):
    """
    Extract emails from database, optionally limiting per class for balance.

    Args:
        db_path: Path to shopq_tracking.db
        limit_per_class: Dict of {importance: max_count} to balance dataset
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    emails = []

    if limit_per_class:
        # Sample from each class separately, deduping by thread_id
        for importance, limit in limit_per_class.items():
            query = """
                SELECT *
                FROM email_threads
                WHERE importance = ?
                  AND id IN (
                    SELECT MIN(id)
                    FROM email_threads
                    WHERE importance = ?
                    GROUP BY thread_id
                  )
                ORDER BY RANDOM()
                LIMIT ?
            """
            cursor = conn.execute(query, (importance, importance, limit))
            emails.extend([dict(row) for row in cursor.fetchall()])
    else:
        # Get all emails, dedupe by thread_id (keep first occurrence)
        query = """
            SELECT *
            FROM email_threads
            WHERE id IN (
                SELECT MIN(id)
                FROM email_threads
                GROUP BY thread_id
            )
            ORDER BY RANDOM()
        """
        cursor = conn.execute(query)
        emails = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return emails


def analyze_dataset(emails):
    """Analyze dataset balance and coverage."""
    total = len(emails)

    importance_counts = Counter(e["importance"] for e in emails)
    email_type_counts = Counter(e["email_type"] for e in emails)
    decider_counts = Counter(e["decider"] for e in emails)

    # Count emails with complete fields
    complete_fields = {
        "from_email": sum(1 for e in emails if e.get("from_email")),
        "subject": sum(1 for e in emails if e.get("subject")),
        "email_type": sum(1 for e in emails if e.get("email_type")),
        "importance": sum(1 for e in emails if e.get("importance")),
        "attention": sum(1 for e in emails if e.get("attention")),
        "domains": sum(1 for e in emails if e.get("domains")),
    }

    analysis = {
        "total_emails": total,
        "importance_distribution": dict(importance_counts),
        "email_type_distribution": dict(email_type_counts),
        "decider_distribution": dict(decider_counts),
        "field_completeness": {
            k: {"count": v, "percentage": round(v / total * 100, 1) if total > 0 else 0}
            for k, v in complete_fields.items()
        },
        "balance_check": {},
    }

    # Check balance
    for importance, count in importance_counts.items():
        pct = (count / total * 100) if total > 0 else 0
        analysis["balance_check"][importance] = {
            "count": count,
            "percentage": round(pct, 1),
            "balanced": pct <= 60,
        }

    return analysis


def write_golden_dataset(emails, output_path: Path):
    """Write golden dataset CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Define column order for Phase 0
    columns = [
        "message_id",
        "thread_id",
        "from_email",
        "subject",
        "received_date",
        "email_type",
        "type_confidence",
        "attention",
        "relationship",
        "domains",
        "domain_confidence",
        "importance",
        "importance_reason",
        "decider",
        "verifier_used",
        "verifier_verdict",
        "verifier_reason",
        "entity_extracted",
        "entity_type",
        "entity_confidence",
        "entity_details",
        "in_digest",
        "in_featured",
        "in_orphaned",
        "in_noise",
        "noise_category",
        "summary_line",
        "summary_linked",
        "session_id",
        "timestamp",
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(emails)

    print(f"✅ Wrote {len(emails)} emails to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Extract golden dataset from shopq_tracking.db")
    parser.add_argument(
        "--db", type=Path, default=Path("data/shopq_tracking.db"), help="Path to shopq_tracking.db"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/golden_set/golden_dataset_from_db.csv"),
        help="Output CSV path",
    )
    parser.add_argument("--total", type=int, default=600, help="Total number of emails to extract")
    parser.add_argument(
        "--balance",
        action="store_true",
        help="Balance classes to meet <60pct per class requirement",
    )

    args = parser.parse_args()

    print("🚀 Extracting golden dataset from ShopQ tracking database...")
    print(f"   Database: {args.db}")
    print(f"   Output: {args.output}")
    print(f"   Target total: {args.total}")
    print(f"   Balance classes: {args.balance}")
    print()

    # First, get current distribution
    conn = sqlite3.connect(args.db)
    cursor = conn.execute("""
        SELECT importance, COUNT(*) as count
        FROM email_threads
        GROUP BY importance
    """)
    current_dist = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    print("📊 Current database distribution:")
    total_in_db = sum(current_dist.values())
    for importance, count in current_dist.items():
        pct = (count / total_in_db * 100) if total_in_db > 0 else 0
        print(f"  {importance}: {count} ({pct:.1f}%)")
    print(f"  Total: {total_in_db}")
    print()

    # Calculate limits per class if balancing
    limit_per_class = None
    if args.balance:
        # Target: no class > 60%, aim for roughly 50/30/20 split
        # (routine/time_sensitive/critical)
        limit_per_class = {
            "routine": min(int(args.total * 0.50), current_dist.get("routine", 0)),
            "time_sensitive": min(int(args.total * 0.30), current_dist.get("time_sensitive", 0)),
            "critical": min(int(args.total * 0.20), current_dist.get("critical", 0)),
        }
        print("🎯 Target balanced distribution:")
        for importance, limit in limit_per_class.items():
            pct = limit / sum(limit_per_class.values()) * 100
            print(f"  {importance}: {limit} ({pct:.1f}%)")
        print()

    # Extract emails
    print("📂 Extracting emails from database...")
    emails = extract_emails_from_db(args.db, limit_per_class)

    if not emails:
        print("❌ No emails extracted!")
        return

    print(f"✅ Extracted {len(emails)} emails")
    print()

    # Analyze
    print("📊 Dataset Analysis:")
    analysis = analyze_dataset(emails)

    print(f"  Total: {analysis['total_emails']}")
    print("\n  Importance distribution:")
    for importance, stats in analysis["balance_check"].items():
        balanced_icon = "✅" if stats["balanced"] else "⚠️ "
        print(f"    {balanced_icon} {importance}: {stats['count']} ({stats['percentage']}%)")

    print("\n  Email type distribution:")
    sorted_types = sorted(
        analysis["email_type_distribution"].items(), key=lambda x: x[1], reverse=True
    )[:10]
    for email_type, count in sorted_types:
        pct = count / analysis["total_emails"] * 100
        print(f"    {email_type}: {count} ({pct:.1f}%)")

    print("\n  Decider distribution:")
    for decider, count in analysis["decider_distribution"].items():
        pct = count / analysis["total_emails"] * 100
        print(f"    {decider}: {count} ({pct:.1f}%)")

    print("\n  Field completeness:")
    for field, stats in analysis["field_completeness"].items():
        if stats["percentage"] >= 90:
            icon = "✅"
        elif stats["percentage"] >= 50:
            icon = "⚠️ "
        else:
            icon = "❌"
        total = analysis["total_emails"]
        print(f"    {icon} {field}: {stats['count']}/{total} ({stats['percentage']}%)")

    # Check Phase 0 requirements
    print("\n✅ Phase 0 Requirements Check:")
    status = "✅" if analysis["total_emails"] >= 500 else "❌"
    print(f"  {status} Emails >= 500: {analysis['total_emails']}")

    all_balanced = all(stats["balanced"] for stats in analysis["balance_check"].values())
    print(f"  {'✅' if all_balanced else '⚠️ '} No class > 60%: {all_balanced}")

    importance_pct = analysis["field_completeness"]["importance"]["percentage"]
    importance_complete = importance_pct == 100
    status = "✅" if importance_complete else "❌"
    print(f"  {status} Importance labels 100%: {importance_pct}%")

    # Write output
    print()
    write_golden_dataset(emails, args.output)

    # Write metadata
    metadata_path = args.output.parent / f"{args.output.stem}_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"✅ Wrote metadata to {metadata_path}")

    print("\n✅ Golden dataset from real ShopQ data created!")
    print("\n📝 Next steps:")
    print(f"   1. Review {args.output} for quality")
    print("   2. Manually review a sample to validate importance labels")
    print("   3. Use this dataset for Phase 0 mapper seed extraction")


if __name__ == "__main__":
    main()
