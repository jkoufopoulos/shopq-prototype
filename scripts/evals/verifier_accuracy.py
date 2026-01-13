"""
Evaluate Classification with Verifier (Two-LLM Pipeline)

Tests the full classification pipeline:
1. First pass: Gemini classifier
2. Verifier check: If confidence in trigger range (0.50-0.90)
3. Compare before/after accuracy

Usage:
    python scripts/evaluate_with_verifier.py [--limit N] [--random]
"""

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shopq.api.routes.verify import verify_classification
from shopq.classification.memory_classifier import MemoryClassifier
from shopq.observability.confidence import VERIFIER_HIGH_CONFIDENCE, VERIFIER_LOW_CONFIDENCE


def load_gds(csv_path: str) -> list[dict]:
    """Load GDS from CSV with ground truth annotations"""
    emails = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emails.append(row)
    return emails


def map_classifier_type_to_gds(classifier_type: str) -> str:
    """Map classifier type to GDS type format"""
    mapping = {
        "otp": "otp",
        "notification": "notification",
        "receipt": "receipt",
        "event": "event",
        "promotion": "promotion",
        "newsletter": "newsletter",
        "message": "message",
        "uncategorized": "other",
        "other": "other",
    }
    return mapping.get(classifier_type, "other")


def should_verify(result: dict) -> tuple[bool, list[str]]:
    """
    Determine if email should trigger verifier based on confidence.

    Returns:
        (should_verify, reasons)
    """
    reasons = []

    # Check type confidence
    type_conf = result.get("type_conf", 1.0)
    if VERIFIER_LOW_CONFIDENCE <= type_conf <= VERIFIER_HIGH_CONFIDENCE:
        reasons.append(f"type_conf={type_conf:.2f} in trigger range")

    # Check attention confidence
    attention_conf = result.get("attention_conf", 1.0)
    if result.get("attention") == "action_required" and attention_conf < 0.85:
        reasons.append(f"action_required with low conf={attention_conf:.2f}")

    return len(reasons) > 0, reasons


def extract_features(email: dict, result: dict) -> dict:
    """Extract features for verifier context"""
    subject = email.get("subject", "").lower()
    snippet = email.get("snippet", "").lower()

    return {
        "has_order_id": "order" in subject or "#" in subject,
        "has_otp": any(word in subject for word in ["code", "verify", "otp", "2fa"]),
        "has_price": "$" in snippet,
        "has_unsubscribe": "unsubscribe" in snippet,
        "has_review_request": any(
            word in snippet for word in ["review", "rate", "feedback", "how was"]
        ),
    }


def detect_contradictions(result: dict, features: dict) -> list[str]:
    """Detect contradictions between classification and features"""
    contradictions = []

    # Receipt without order/price
    if (
        result.get("type") == "receipt"
        and not features.get("has_order_id")
        and not features.get("has_price")
    ):
        contradictions.append("receipt without order # or price")

    # Action required for review request
    if result.get("attention") == "action_required" and features.get("has_review_request"):
        contradictions.append("action_required for review request")

    # Promotion with order ID
    if result.get("type") == "promotion" and features.get("has_order_id"):
        contradictions.append("promotion with order #")

    return contradictions


def main():
    parser = argparse.ArgumentParser(description="Evaluate classification with verifier")
    parser.add_argument("--limit", type=int, default=100, help="Number of emails to evaluate")
    parser.add_argument("--random", action="store_true", help="Randomly sample emails")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show individual results")
    args = parser.parse_args()

    # Load GDS
    gds_path = "data/evals/classification/gds-2.0.csv"
    print(f"Loading GDS from {gds_path}...")
    emails = load_gds(gds_path)

    # Sample emails
    if args.random:
        emails = random.sample(emails, min(args.limit, len(emails)))
    else:
        emails = emails[: args.limit]

    print(f"Evaluating {len(emails)} emails with verifier pipeline...")
    print(f"Verifier trigger range: {VERIFIER_LOW_CONFIDENCE:.2f} - {VERIFIER_HIGH_CONFIDENCE:.2f}")

    # Initialize classifier
    classifier = MemoryClassifier()

    # Track results
    results_before = []  # (pred_type, actual_type)
    results_after = []  # (pred_type, actual_type) after verifier

    verifier_stats = {
        "triggered": 0,
        "confirmed": 0,
        "rejected": 0,
        "improved": 0,
        "worsened": 0,
        "unchanged": 0,
    }

    # Classify each email
    for i, email in enumerate(emails):
        if (i + 1) % 20 == 0:
            print(f"  Processing {i + 1}/{len(emails)}...")

        subject = email.get("subject", "")
        snippet = email.get("snippet", "")
        from_email = email.get("from_email", "")

        # Ground truth
        actual_type = email.get("email_type", "").strip()

        # First pass classification
        try:
            result = classifier.classify(
                subject=subject,
                snippet=snippet,
                from_field=from_email,
            )
        except Exception as e:
            print(f"  Error classifying email {email.get('email_id')}: {e}")
            continue

        pred_type_before = map_classifier_type_to_gds(result.get("type", "other"))
        results_before.append((pred_type_before, actual_type))

        # Check if verifier should be triggered
        trigger, reasons = should_verify(result)

        if trigger:
            verifier_stats["triggered"] += 1

            # Extract features and detect contradictions
            features = extract_features(email, result)
            contradictions = detect_contradictions(result, features)

            # Run verifier
            email_dict = {
                "subject": subject,
                "snippet": snippet,
                "from": from_email,
            }

            verifier_result = verify_classification(
                classifier=classifier,
                email=email_dict,
                first_result=result,
                features=features,
                contradictions=contradictions,
            )

            if verifier_result["verdict"] == "confirm":
                verifier_stats["confirmed"] += 1
                pred_type_after = pred_type_before
            else:
                verifier_stats["rejected"] += 1
                correction = verifier_result.get("correction", {})
                pred_type_after = map_classifier_type_to_gds(
                    correction.get("type", result.get("type", "other"))
                )

                if args.verbose:
                    print(f"\n  Verifier correction: {pred_type_before} → {pred_type_after}")
                    print(f"    Reasons: {reasons}")
                    print(f"    Violations: {verifier_result.get('rubric_violations', [])}")
                    print(f"    Why bad: {verifier_result.get('why_bad', '')}")

            # Track improvement
            was_correct = pred_type_before == actual_type
            is_correct = pred_type_after == actual_type

            if not was_correct and is_correct:
                verifier_stats["improved"] += 1
            elif was_correct and not is_correct:
                verifier_stats["worsened"] += 1
            else:
                verifier_stats["unchanged"] += 1

            results_after.append((pred_type_after, actual_type))
        else:
            results_after.append((pred_type_before, actual_type))

    # Calculate accuracy
    print("\n" + "=" * 60)
    print("CLASSIFICATION ACCURACY WITH VERIFIER")
    print("=" * 60)

    before_correct = sum(1 for pred, actual in results_before if pred == actual)
    after_correct = sum(1 for pred, actual in results_after if pred == actual)

    before_accuracy = before_correct / len(results_before) * 100
    after_accuracy = after_correct / len(results_after) * 100

    print("\nType Accuracy:")
    print(f"  Before verifier: {before_accuracy:5.1f}% ({before_correct}/{len(results_before)})")
    print(f"  After verifier:  {after_accuracy:5.1f}% ({after_correct}/{len(results_after)})")
    print(f"  Delta:           {after_accuracy - before_accuracy:+5.1f}%")

    print("\nVerifier Statistics:")
    print(
        f"  Triggered:  {verifier_stats['triggered']} ({verifier_stats['triggered'] / len(emails) * 100:.1f}%)"
    )
    print(f"  Confirmed:  {verifier_stats['confirmed']}")
    print(f"  Rejected:   {verifier_stats['rejected']}")
    print(f"  Improved:   {verifier_stats['improved']}")
    print(f"  Worsened:   {verifier_stats['worsened']}")
    print(f"  Unchanged:  {verifier_stats['unchanged']}")

    # Error analysis
    print("\n" + "=" * 60)
    print("ERROR ANALYSIS")
    print("=" * 60)

    errors_before = defaultdict(int)
    errors_after = defaultdict(int)

    for pred, actual in results_before:
        if pred != actual:
            errors_before[f"{actual} → {pred}"] += 1

    for pred, actual in results_after:
        if pred != actual:
            errors_after[f"{actual} → {pred}"] += 1

    print("\nTop errors BEFORE verifier:")
    for pattern, count in sorted(errors_before.items(), key=lambda x: -x[1])[:5]:
        print(f"  {pattern}: {count}")

    print("\nTop errors AFTER verifier:")
    for pattern, count in sorted(errors_after.items(), key=lambda x: -x[1])[:5]:
        print(f"  {pattern}: {count}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if after_accuracy > before_accuracy:
        print(f"\n✅ Verifier IMPROVED accuracy by {after_accuracy - before_accuracy:.1f}pp")
    elif after_accuracy < before_accuracy:
        print(f"\n❌ Verifier DECREASED accuracy by {before_accuracy - after_accuracy:.1f}pp")
    else:
        print("\n➖ Verifier had NO EFFECT on accuracy")

    print(
        f"\nNet effect: {verifier_stats['improved']} improved, {verifier_stats['worsened']} worsened"
    )


if __name__ == "__main__":
    main()
