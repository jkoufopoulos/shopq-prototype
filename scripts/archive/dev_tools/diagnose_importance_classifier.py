#!/usr/bin/env python3
"""
Complete diagnosis of ImportanceClassifier against ground truth.

Compares actual classifications vs user's manual categorization
to identify systematic failures.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from mailq.classification.importance_classifier import ImportanceClassifier


def load_ground_truth():
    """Load user's manual categorization"""
    csv_path = Path(__file__).parent.parent / "inbox_review_with notes - inbox_review.csv"

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        return list(reader)


def determine_expected_importance(email):
    """Determine what importance level email SHOULD be"""
    reasoning = (email.get("reasoning", "") + " " + email.get("notes", "")).lower()
    email.get("subject", "").lower()
    should_feature = email.get("should_feature", "").strip().lower() in ["yes", "y"]

    if not should_feature:
        return "routine"  # User said don't feature

    # Critical: Bills, statements, security, large charges
    if any(
        kw in reasoning
        for kw in [
            "bill",
            "statement",
            "balance",
            "security",
            "financial alert",
            "large charge",
            "low balance",
        ]
    ):
        return "critical"

    # Time-sensitive: Deliveries, appointments, jobs
    if any(
        kw in reasoning
        for kw in [
            "delivery",
            "delivered",
            "appointment",
            "job alert",
            "hired someone",
            "scheduled",
        ]
    ):
        return "time_sensitive"

    # Everything else user wants featured
    return "time_sensitive"  # Default for featured items


def diagnose_email(classifier, email):
    """Diagnose a single email classification"""
    subject = email.get("subject", "")
    snippet = email.get("snippet", "")
    email_type = email.get("type", "notification")
    attention = email.get("attention", "none")

    # Build text for classification
    text = f"{subject} {snippet}"

    # Get actual classification
    actual = classifier.classify(text, email_type, attention)

    # Get expected classification
    expected = determine_expected_importance(email)

    # Try to find which pattern matched (simple heuristic)
    text_lower = text.lower()
    reason = f"default for type={email_type}, attention={attention}"

    # Check if any critical pattern matched
    for category, patterns in classifier.critical_patterns.items():
        for pattern in patterns:
            if pattern in text_lower:
                reason = f"critical pattern: {category} ('{pattern}')"
                break

    # Check time-sensitive patterns
    if "critical" not in reason:
        for category, patterns in classifier.time_sensitive_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    reason = f"time-sensitive pattern: {category} ('{pattern}')"
                    break

    # Check routine patterns
    if "pattern" not in reason:
        for category, patterns in classifier.routine_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    reason = f"routine pattern: {category} ('{pattern}')"
                    break

    return {
        "subject": subject,
        "expected": expected,
        "actual": actual,
        "match": expected == actual,
        "reason": reason,
        "type": email_type,
        "attention": attention,
        "should_feature": email.get("should_feature", "").strip().lower() in ["yes", "y"],
        "user_reasoning": email.get("reasoning", "") + " " + email.get("notes", ""),
    }


def main():
    print("=" * 80)
    print("IMPORTANCE CLASSIFIER DIAGNOSIS")
    print("=" * 80)
    print()

    # Load data
    emails = load_ground_truth()
    print(f"✅ Loaded {len(emails)} emails from ground truth")
    print()

    # Initialize classifier
    classifier = ImportanceClassifier()

    # Diagnose all emails
    print("🔍 Classifying all emails...")
    print()

    results = []
    for email in emails:
        result = diagnose_email(classifier, email)
        results.append(result)

    # Analysis
    print("=" * 80)
    print("OVERALL ACCURACY")
    print("=" * 80)
    print()

    total = len(results)
    correct = sum(1 for r in results if r["match"])
    incorrect = total - correct

    print(f"  Total emails: {total}")
    print(f"  Correct: {correct} ({correct / total * 100:.1f}%)")
    print(f"  Incorrect: {incorrect} ({incorrect / total * 100:.1f}%)")
    print()

    # Breakdown by expected category
    print("=" * 80)
    print("ACCURACY BY CATEGORY")
    print("=" * 80)
    print()

    by_category = defaultdict(list)
    for r in results:
        by_category[r["expected"]].append(r)

    for category, items in sorted(by_category.items()):
        correct = sum(1 for r in items if r["match"])
        total = len(items)
        print(f"  {category.upper()}: {correct}/{total} correct ({correct / total * 100:.1f}%)")

    print()

    # Critical errors (should be critical, but classified as routine)
    print("=" * 80)
    print("🚨 CRITICAL ERRORS (Should be CRITICAL, but classified ROUTINE)")
    print("=" * 80)
    print()

    critical_errors = [
        r for r in results if r["expected"] == "critical" and r["actual"] == "routine"
    ]

    if critical_errors:
        print(f"Found {len(critical_errors)} critical emails mis-classified as routine:")
        print()

        for i, r in enumerate(critical_errors[:10], 1):
            print(f"{i}. {r['subject'][:70]}")
            print(f"   Why important: {r['user_reasoning'][:60]}")
            print(f"   Classifier said: {r['reason']}")
            print(f"   Type: {r['type']}, Attention: {r['attention']}")
            print()

        if len(critical_errors) > 10:
            print(f"   ... and {len(critical_errors) - 10} more")
            print()
    else:
        print("✅ No critical errors found!")
        print()

    # Time-sensitive errors
    print("=" * 80)
    print("⏰ TIME-SENSITIVE ERRORS (Should be TIME_SENSITIVE, but classified ROUTINE)")
    print("=" * 80)
    print()

    time_errors = [
        r for r in results if r["expected"] == "time_sensitive" and r["actual"] == "routine"
    ]

    if time_errors:
        print(f"Found {len(time_errors)} time-sensitive emails mis-classified as routine:")
        print()

        for i, r in enumerate(time_errors[:10], 1):
            print(f"{i}. {r['subject'][:70]}")
            print(f"   Why important: {r['user_reasoning'][:60]}")
            print(f"   Classifier said: {r['reason']}")
            print(f"   Type: {r['type']}, Attention: {r['attention']}")
            print()

        if len(time_errors) > 10:
            print(f"   ... and {len(time_errors) - 10} more")
            print()
    else:
        print("✅ No time-sensitive errors found!")
        print()

    # False positives (should be routine, but classified as important)
    print("=" * 80)
    print("❌ FALSE POSITIVES (Should be ROUTINE, but classified CRITICAL/TIME_SENSITIVE)")
    print("=" * 80)
    print()

    false_positives = [
        r for r in results if r["expected"] == "routine" and r["actual"] != "routine"
    ]

    if false_positives:
        print(f"Found {len(false_positives)} routine emails mis-classified as important:")
        print()

        for i, r in enumerate(false_positives[:10], 1):
            print(f"{i}. {r['subject'][:70]}")
            print(f"   User said: {r['user_reasoning'][:60]}")
            print(f"   Classifier said: {r['actual']} - {r['reason']}")
            print()

        if len(false_positives) > 10:
            print(f"   ... and {len(false_positives) - 10} more")
            print()
    else:
        print("✅ No false positives found!")
        print()

    # Pattern analysis
    print("=" * 80)
    print("📊 PATTERN ANALYSIS")
    print("=" * 80)
    print()

    print("Reasons given by classifier:")
    print()

    reason_counts = defaultdict(int)
    for r in results:
        reason_counts[r["reason"]] += 1

    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {count:3}x - {reason}")

    print()

    # Missing patterns
    print("=" * 80)
    print("🔍 MISSING PATTERNS (Keywords in user reasoning not caught)")
    print("=" * 80)
    print()

    # Find keywords in user reasoning that should trigger classification
    missed_keywords = defaultdict(int)

    for r in results:
        if not r["match"] and r["expected"] != "routine":
            # Extract keywords from user reasoning
            user_keywords = r["user_reasoning"].lower()

            # Common important keywords
            for keyword in [
                "bill",
                "statement",
                "delivery",
                "delivered",
                "appointment",
                "job alert",
                "security",
                "balance",
                "hired",
                "scheduled",
            ]:
                if keyword in user_keywords:
                    missed_keywords[keyword] += 1

    if missed_keywords:
        print("Keywords appearing in user reasoning but not triggering classification:")
        print()
        for keyword, count in sorted(missed_keywords.items(), key=lambda x: -x[1]):
            print(f"  {count:3}x - '{keyword}'")
        print()
    else:
        print("✅ All keywords properly detected!")
        print()

    # Confusion matrix
    print("=" * 80)
    print("📊 CONFUSION MATRIX")
    print("=" * 80)
    print()

    matrix = defaultdict(lambda: defaultdict(int))
    for r in results:
        matrix[r["expected"]][r["actual"]] += 1

    print("                      Actual Classification")
    print("Expected     |  Critical  | Time-Sens  |  Routine   | Total")
    print("-" * 65)

    for expected in ["critical", "time_sensitive", "routine"]:
        counts = matrix[expected]
        total = sum(counts.values())
        if total > 0:
            print(
                f"{expected:12} | {counts['critical']:10} | "
                f"{counts['time_sensitive']:10} | {counts['routine']:10} | {total}"
            )

    print()

    # Save detailed report
    output_path = Path(__file__).parent.parent / "importance_classifier_diagnosis.csv"
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "subject",
                "expected",
                "actual",
                "match",
                "reason",
                "type",
                "attention",
                "should_feature",
                "user_reasoning",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"💾 Detailed results saved to: {output_path}")
    print()

    # Summary recommendations
    print("=" * 80)
    print("🎯 RECOMMENDATIONS")
    print("=" * 80)
    print()

    if critical_errors:
        print(f"1. FIX CRITICAL CLASSIFICATION ({len(critical_errors)} errors)")
        print("   Add patterns for:")
        critical_keywords = set()
        for r in critical_errors[:5]:
            words = r["user_reasoning"].lower().split()
            critical_keywords.update([w for w in words if len(w) > 4])
        print(f"   - {', '.join(list(critical_keywords)[:10])}")
        print()

    if time_errors:
        print(f"2. FIX TIME-SENSITIVE CLASSIFICATION ({len(time_errors)} errors)")
        print("   Add patterns for:")
        time_keywords = set()
        for r in time_errors[:5]:
            words = r["user_reasoning"].lower().split()
            time_keywords.update([w for w in words if len(w) > 4])
        print(f"   - {', '.join(list(time_keywords)[:10])}")
        print()

    if false_positives:
        print(f"3. REDUCE FALSE POSITIVES ({len(false_positives)} errors)")
        print("   Add exclusion patterns or lower priority for:")
        for r in false_positives[:3]:
            print(f"   - {r['subject'][:50]}")
        print()

    print("=" * 80)
    print("✅ Diagnosis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
