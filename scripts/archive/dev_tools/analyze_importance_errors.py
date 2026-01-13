"""
Analyze Importance Classification Errors

Extract and categorize time_sensitive→routine errors to identify
patterns for prompt improvements and heuristics v2.

Usage:
    python scripts/analyze_importance_errors.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.classification.importance.heuristics import apply_importance_heuristics
from mailq.classification.memory_classifier import MemoryClassifier


def load_gds(csv_path: str) -> list[dict]:
    """Load GDS from CSV with ground truth annotations"""
    emails = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emails.append(row)
    return emails


def main():
    # Load GDS
    gds_path = "data/gds/gds-2.0-manually-reviewed.csv"
    print(f"Loading GDS from {gds_path}...")
    emails = load_gds(gds_path)
    print(f"Loaded {len(emails)} emails\n")

    # Initialize classifier
    classifier = MemoryClassifier()

    # Track errors
    ts_to_routine_errors = []  # Ground truth: time_sensitive, Pred: routine
    routine_to_ts_errors = []  # Ground truth: routine, Pred: time_sensitive

    # Classify each email
    for i, email in enumerate(emails):
        if (i + 1) % 100 == 0:
            print(f"  Processing {i + 1}/{len(emails)}...")

        subject = email.get("subject", "")
        snippet = email.get("snippet", "")
        from_email = email.get("from_email", "")
        actual_importance = email.get("importance", "").strip()

        # Skip if no ground truth
        if not actual_importance:
            continue

        # Run classifier
        try:
            result = classifier.classify(
                subject=subject,
                snippet=snippet,
                from_field=from_email,
            )
        except Exception as e:
            print(f"  Error classifying email {email.get('email_id')}: {e}")
            continue

        # Get LLM importance
        llm_importance = result.get("importance", "routine")

        # Apply heuristics
        heuristic_result = apply_importance_heuristics(
            subject=subject,
            snippet=snippet,
            email_type=result.get("type", ""),
            llm_importance=llm_importance,
            from_email=from_email,
        )
        pred_importance = heuristic_result.final_importance

        # Track errors
        if actual_importance == "time_sensitive" and pred_importance == "routine":
            ts_to_routine_errors.append(
                {
                    "email_id": email.get("email_id"),
                    "subject": subject,
                    "snippet": snippet[:200],
                    "from": from_email,
                    "email_type": email.get("email_type", ""),
                    "pred_type": result.get("type", ""),
                    "llm_importance": llm_importance,
                    "heuristic_applied": heuristic_result.was_modified,
                    "heuristic_rule": heuristic_result.rule_name,
                }
            )
        elif actual_importance == "routine" and pred_importance == "time_sensitive":
            routine_to_ts_errors.append(
                {
                    "email_id": email.get("email_id"),
                    "subject": subject,
                    "snippet": snippet[:200],
                    "from": from_email,
                    "email_type": email.get("email_type", ""),
                    "pred_type": result.get("type", ""),
                    "llm_importance": llm_importance,
                    "heuristic_applied": heuristic_result.was_modified,
                    "heuristic_rule": heuristic_result.rule_name,
                }
            )

    # Analysis: TS → routine errors (under-classification)
    print("\n" + "=" * 80)
    print(f"TIME_SENSITIVE → ROUTINE ERRORS ({len(ts_to_routine_errors)} total)")
    print("=" * 80)
    print("\nThese are emails that SHOULD be time_sensitive but were marked routine.")
    print("Focus: What urgency signals is the LLM missing?\n")

    # Group by email type
    by_type = defaultdict(list)
    for err in ts_to_routine_errors:
        by_type[err["email_type"]].append(err)

    print("By Ground Truth Email Type:")
    for etype, errors in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(f"\n  {etype}: {len(errors)} errors")
        for err in errors[:5]:  # Show up to 5 examples
            print(f"    - {err['subject'][:60]}")
            if err["heuristic_applied"]:
                print(f"      [Heuristic: {err['heuristic_rule']}]")

    # Group by sender domain
    print("\n\nBy Sender Domain:")
    by_domain = defaultdict(list)
    for err in ts_to_routine_errors:
        domain = err["from"].split("@")[-1] if "@" in err["from"] else "unknown"
        by_domain[domain].append(err)

    for domain, errors in sorted(by_domain.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {domain}: {len(errors)}")

    # Analysis: routine → TS errors (over-classification)
    print("\n\n" + "=" * 80)
    print(f"ROUTINE → TIME_SENSITIVE ERRORS ({len(routine_to_ts_errors)} total)")
    print("=" * 80)
    print("\nThese are emails that SHOULD be routine but were marked time_sensitive.")
    print("Focus: What temporal language is being over-interpreted?\n")

    # Group by email type
    by_type = defaultdict(list)
    for err in routine_to_ts_errors:
        by_type[err["email_type"]].append(err)

    print("By Ground Truth Email Type:")
    for etype, errors in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(f"\n  {etype}: {len(errors)} errors")
        for err in errors[:5]:
            print(f"    - {err['subject'][:60]}")
            if err["heuristic_applied"]:
                print(f"      [Heuristic: {err['heuristic_rule']}]")

    # Common patterns in over-classification
    print("\n\nCommon Over-classification Patterns:")
    temporal_keywords = [
        "today",
        "tomorrow",
        "now",
        "soon",
        "week",
        "day",
        "hour",
        "minute",
        "time",
    ]
    for keyword in temporal_keywords:
        count = sum(
            1
            for err in routine_to_ts_errors
            if keyword in err["subject"].lower() or keyword in err["snippet"].lower()
        )
        if count > 0:
            print(f"  '{keyword}': {count} errors")

    # Summary
    print("\n\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)

    print(f"\nTotal TS→routine (under-classification): {len(ts_to_routine_errors)}")
    print(f"Total routine→TS (over-classification): {len(routine_to_ts_errors)}")

    print("\nKey insights for next prompt iteration:")
    print("1. Check the most common email types causing TS→routine errors")
    print("2. Look for urgency patterns the LLM is missing")
    print("3. Identify temporal language causing over-classification")


if __name__ == "__main__":
    main()
