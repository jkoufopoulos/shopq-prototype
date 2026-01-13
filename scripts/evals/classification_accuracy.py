# ruff: noqa
"""
Evaluate Classification Accuracy Against GDS Ground Truth

Runs the MailQ classifier on all 500 GDS emails and compares
predictions to human-annotated ground truth.

Usage:
    python scripts/evaluate_classification_accuracy.py [--limit N]
    python scripts/evaluate_classification_accuracy.py --with-verifier  # Enable second-pass verifier

Metrics:
- Overall accuracy per field (type, importance, client_label)
- Confusion matrices
- Top misclassification patterns
- Per-sender analysis
- Verifier trigger rate and correction impact (with --with-verifier)
"""

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.classification.memory_classifier import MemoryClassifier
from mailq.api.routes.verify import verify_classification as run_verifier

# Import EmailClassifier for refactored pipeline option
from mailq.classification.classifier import EmailClassifier
from mailq.storage.models import ParsedEmail, RawEmail
from datetime import datetime as dt

# Verifier threshold - trigger second-pass if any confidence below this
VERIFIER_CONFIDENCE_THRESHOLD = 0.80


def should_trigger_verifier(result: dict) -> tuple[bool, list[str]]:
    """
    Check if verifier should be triggered based on confidence scores.

    Returns:
        (should_trigger, list of trigger reasons)
    """
    triggers = []

    type_conf = result.get("type_conf", 0)
    importance_conf = result.get("importance_conf", 0)
    attention_conf = result.get("attention_conf", 0)

    if type_conf < VERIFIER_CONFIDENCE_THRESHOLD:
        triggers.append(f"type_conf={type_conf:.2f}")
    if importance_conf < VERIFIER_CONFIDENCE_THRESHOLD:
        triggers.append(f"importance_conf={importance_conf:.2f}")
    if attention_conf < VERIFIER_CONFIDENCE_THRESHOLD:
        triggers.append(f"attention_conf={attention_conf:.2f}")

    # Also trigger for action_required (always verify these per extension logic)
    if result.get("attention") == "action_required":
        triggers.append("attention=action_required")

    return len(triggers) > 0, triggers


def extract_email_features(email: dict) -> dict:
    """Extract features for verifier (matches extension/modules/classification/verifier.js)"""
    text = f"{email.get('subject', '')} {email.get('snippet', '')}".lower()

    import re

    return {
        "has_order_id": bool(
            re.search(r"\b(order|receipt|invoice|confirmation)\s?#?\w{5,}", text, re.I)
        ),
        "has_amount": bool(re.search(r"\$\d+\.\d{2}", text, re.I)),
        "has_calendar_link": bool(
            re.search(r"(zoom\.us|meet\.google\.com|teams\.microsoft\.com)", text, re.I)
        ),
        "has_unsubscribe": bool(re.search(r"unsubscribe", text, re.I)),
        "has_otp": bool(re.search(r"\b\d{4,8}\b.{0,30}(code|otp|verification|2fa)", text, re.I)),
        "has_action_words": bool(
            re.search(
                r"\b(confirm|verify|reset|activate|click|sign in|log in|action required)\b",
                text,
                re.I,
            )
        ),
        "has_promo_words": bool(
            re.search(
                r"\b(sale|discount|offer|deal|limited time|expires|save|free shipping)\b",
                text,
                re.I,
            )
        ),
        "has_review_request": bool(
            re.search(r"(how was your|rate your|review your|tell us what you think)", text, re.I)
        ),
    }


def detect_contradictions(result: dict, features: dict) -> list[str]:
    """Detect contradictions between classification and features"""
    contradictions = []

    # Promotion with order tokens (likely receipt, not promo)
    if result.get("type") == "promotion" and (
        features.get("has_order_id") or features.get("has_amount")
    ):
        contradictions.append("promotion_with_order_tokens")

    # Action required but no action words (might be review request)
    if result.get("attention") == "action_required" and not features.get("has_action_words"):
        contradictions.append("action_required_without_action_words")

    # Receipt with unsubscribe footer (likely promo, not receipt)
    if (
        result.get("type") == "receipt"
        and features.get("has_unsubscribe")
        and not features.get("has_order_id")
    ):
        contradictions.append("receipt_with_unsubscribe_no_order")

    # Action required + promo words (likely promo pressure, not real action)
    if result.get("attention") == "action_required" and features.get("has_promo_words"):
        contradictions.append("action_required_with_promo_language")

    # Review request pattern but marked action_required
    if features.get("has_review_request") and result.get("attention") == "action_required":
        contradictions.append("review_request_marked_action_required")

    return contradictions


def load_gds(csv_path: str) -> list[dict]:
    """Load GDS from CSV with ground truth annotations"""
    emails = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emails.append(row)
    return emails


def map_classifier_type_to_gds(classifier_type: str) -> str:
    """Map classifier type to GDS type format.

    Logs warning if an unmapped type is encountered.
    """
    # Classifier uses: otp|notification|receipt|event|promotion|newsletter|message|uncategorized
    # GDS uses: otp|notification|event|newsletter|promotion|message|receipt|other
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
    if classifier_type not in mapping:
        print(f"  ⚠️  UNMAPPED TYPE: '{classifier_type}' → defaulting to 'other'")
    return mapping.get(classifier_type, "other")


def get_client_label_from_result(result: dict) -> str:
    """Get client_label from LLM output, with fallback to derivation for backwards compatibility"""
    # Prefer direct LLM output
    if "client_label" in result:
        return result["client_label"]

    # Fallback: derive from type/attention (deprecated)
    email_type = result.get("type", "")
    attention = result.get("attention", "none")

    # Type-based mapping takes precedence
    if email_type == "receipt":
        return "receipts"
    if email_type == "message":
        return "messages"
    if email_type == "newsletter":
        return "newsletters"
    if email_type == "otp":
        # OTPs are ephemeral - don't put in action-required
        return "everything-else"
    if attention == "action_required":
        # Only non-OTP action_required goes here (failed payments, security alerts)
        return "action-required"
    return "everything-else"


def compute_confusion_matrix(predictions: list[tuple[str, str]], labels: list[str]) -> dict:
    """Compute confusion matrix for predictions vs ground truth"""
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for pred, actual in predictions:
        matrix[actual][pred] += 1
    return matrix


def print_confusion_matrix(matrix: dict, title: str, labels: list[str]):
    """Pretty print confusion matrix"""
    print(f"\n{title}")
    print("=" * 60)

    # Header
    header = "Actual \\ Pred"
    for label in labels:
        header += f" | {label[:8]:>8}"
    print(header)
    print("-" * len(header))

    # Rows
    for actual in labels:
        row = f"{actual[:12]:<12}"
        for pred in labels:
            count = matrix[actual][pred]
            row += f" | {count:>8}"
        print(row)


def analyze_errors(errors: list[dict], field: str) -> list[tuple[str, list[dict[str, str]]]]:
    """Analyze error patterns and return top patterns"""
    patterns: dict[str, list[dict[str, str]]] = defaultdict(list)

    for error in errors:
        key = f"{error['actual']} -> {error['predicted']}"
        patterns[key].append(error)

    # Sort by count
    sorted_patterns = sorted(patterns.items(), key=lambda x: -len(x[1]))
    return sorted_patterns[:10]


def get_git_commit() -> str:
    """Get current git commit hash"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def save_errors_to_csv(
    errors: list[dict],
    error_type: str,
    results_dir: Path,
    timestamp: str,
    safe_name: str,
) -> str:
    """
    Save all errors of a given type to a CSV file for detailed analysis.

    Returns path to saved CSV file.
    """
    if not errors:
        return ""

    csv_path = results_dir / f"{timestamp}_{safe_name}_{error_type}_errors.csv"

    # Get all unique keys from errors to create header
    all_keys: set[str] = set()
    for error in errors:
        all_keys.update(error.keys())

    # Order columns sensibly
    priority_cols = [
        "email_id",
        "error_pattern",
        "predicted",
        "actual",
        "subject",
        "from",
        "snippet",
    ]
    ordered_cols = [col for col in priority_cols if col in all_keys]
    ordered_cols += sorted(all_keys - set(ordered_cols))

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ordered_cols)
        writer.writeheader()
        for error in errors:
            writer.writerow(error)

    return str(csv_path)


def save_experiment_results(
    name: str,
    metrics: dict,
    confusion_matrices: dict,
    top_errors: dict,
    all_errors: dict,
    num_emails: int,
    notes: str = "",
) -> str:
    """
    Save experiment results to JSON, markdown, and CSV error files.

    Returns path to saved JSON file.

    Side Effects:
        Writes JSON results file to reports/experiments/
        Writes markdown summary file to reports/experiments/
        Writes CSV error files (one per error type) to reports/experiments/
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_").lower()

    # Create results directory (repo root / reports / experiments)
    results_dir = Path(__file__).parent.parent.parent / "reports" / "experiments"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Save detailed errors to CSV files
    error_csv_paths = {}
    for error_type, errors in all_errors.items():
        csv_path = save_errors_to_csv(errors, error_type, results_dir, timestamp, safe_name)
        if csv_path:
            error_csv_paths[error_type] = csv_path

    # Build results structure
    results = {
        "timestamp": datetime.now().isoformat(),
        "experiment_name": name,
        "git_commit": get_git_commit(),
        "config": {
            "model": "gemini-2.0-flash",
            "prompt_version": "v1",
            "num_emails": num_emails,
        },
        "metrics": metrics,
        "confusion_matrices": confusion_matrices,
        "top_errors": top_errors,
        "error_csv_files": error_csv_paths,
        "notes": notes,
    }

    # Save JSON
    json_path = results_dir / f"{timestamp}_{safe_name}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    # Save markdown summary
    md_path = results_dir / f"{timestamp}_{safe_name}.md"
    with open(md_path, "w") as f:
        f.write(f"# Experiment: {name}\n\n")
        f.write(f"**Timestamp:** {results['timestamp']}\n")
        f.write(f"**Git Commit:** {results['git_commit']}\n")
        f.write(f"**Emails Evaluated:** {num_emails}\n\n")

        f.write("## Accuracy Metrics\n\n")
        f.write(f"- **Type Accuracy:** {metrics['type_accuracy']:.1f}%\n")
        f.write(f"- **Importance Accuracy:** {metrics['importance_accuracy']:.1f}%\n")
        f.write(f"- **Client Label Accuracy:** {metrics['client_label_accuracy']:.1f}%\n\n")

        f.write("## Top Error Patterns\n\n")
        f.write("### Type Errors\n")
        for pattern, count in top_errors.get("type", [])[:5]:
            f.write(f"- {pattern}: {count}\n")

        f.write("\n### Importance Errors\n")
        for pattern, count in top_errors.get("importance", [])[:5]:
            f.write(f"- {pattern}: {count}\n")

        if notes:
            f.write(f"\n## Notes\n\n{notes}\n")

        # List error CSV files
        if error_csv_paths:
            f.write("\n## Error Detail Files\n\n")
            for error_type, csv_path in error_csv_paths.items():
                csv_filename = Path(csv_path).name
                f.write(f"- **{error_type}:** `{csv_filename}`\n")

    return str(json_path)


def main():
    parser = argparse.ArgumentParser(description="Evaluate classification accuracy")
    parser.add_argument("--limit", type=int, help="Limit number of emails to evaluate")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show individual errors")
    parser.add_argument(
        "--save-results", action="store_true", help="Save results to experiments log"
    )
    parser.add_argument(
        "--name", type=str, default="baseline", help="Experiment name for saved results"
    )
    parser.add_argument("--notes", type=str, default="", help="Notes to include with saved results")
    parser.add_argument(
        "--with-verifier",
        action="store_true",
        help="Enable second-pass verifier for low-confidence classifications",
    )
    parser.add_argument(
        "--use-refactored",
        action="store_true",
        help="Use refactored EmailClassifier instead of MemoryClassifier",
    )
    args = parser.parse_args()

    # Load GDS
    gds_path = "data/evals/classification/gds-2.0.csv"
    print(f"Loading GDS from {gds_path}...")
    emails = load_gds(gds_path)

    if args.limit:
        emails = emails[: args.limit]

    print(f"Evaluating {len(emails)} emails...")

    # Initialize classifier based on flag
    use_refactored = args.use_refactored
    if use_refactored:
        print("Using refactored EmailClassifier pipeline...")
        email_classifier = EmailClassifier()
        classifier = None  # Not used in refactored path
    else:
        print("Using MemoryClassifier pipeline...")
        classifier = MemoryClassifier()
        # Reset circuit breaker to ensure clean state for eval run
        classifier.reset_circuit_breaker()
        email_classifier = None  # Not used in legacy path
    # ImportanceClassifier no longer used - Gemini outputs importance directly

    # Track results
    type_predictions = []
    importance_predictions = []
    client_label_predictions = []

    type_errors = []
    importance_errors = []
    client_label_errors = []
    classification_failures = []  # Track classification errors

    # Verifier tracking (only used with --with-verifier)
    verifier_triggered_count = 0
    verifier_corrected_count = 0
    verifier_trigger_reasons = []
    verifier_decisions = []  # Track each verifier decision for detailed analysis

    # Confidence tracking
    type_confidences = []
    importance_confidences = []
    attention_confidences = []

    # Classify each email
    for i, email in enumerate(emails):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i + 1}/{len(emails)}...")

        subject = email.get("subject", "")
        snippet = email.get("snippet", "")
        from_email = email.get("from_email", "")
        email_id = email.get("email_id", f"eval-{i}")

        # Run classifier
        try:
            if use_refactored:
                # Use EmailClassifier (refactored pipeline)
                # Create ParsedEmail from eval data
                base = RawEmail(
                    message_id=str(email_id),
                    thread_id=f"thread-{email_id}",
                    received_ts=dt.now().isoformat(),
                    subject=subject,
                    from_address=from_email,
                    to_address="eval@mailq.local",
                    body=snippet,
                )
                parsed = ParsedEmail(base=base, body_text=snippet, body_html=None)

                # Classify using EmailClassifier
                classified = email_classifier.classify(parsed, use_rules=True, use_llm=True)

                # Convert ClassifiedEmail to dict for compatibility with rest of eval
                from mailq.storage.classification import compute_client_label

                result = {
                    "type": classified.category,
                    "type_conf": classified.type_confidence,
                    "importance": classified.importance,
                    "importance_conf": classified.confidence,
                    "attention": classified.attention,
                    "attention_conf": classified.attention_confidence,
                    "client_label": compute_client_label(
                        classified.category, classified.importance
                    ),
                    "domains": classified.domains,
                    "domain_conf": classified.domain_confidence,
                    "relationship": classified.relationship,
                    "relationship_conf": classified.relationship_confidence,
                    "decider": classified.decider,
                    "reason": classified.reason,
                }
            else:
                # Use MemoryClassifier (legacy pipeline)
                result = classifier.classify(
                    subject=subject,
                    snippet=snippet,
                    from_field=from_email,
                )
        except Exception as e:
            print(f"  ❌ ERROR classifying email {email.get('email_id')}: {type(e).__name__}: {e}")
            classification_failures.append(
                {
                    "email_id": email.get("email_id"),
                    "subject": subject[:60],
                    "error_type": type(e).__name__,
                    "error_msg": str(e),
                }
            )
            # Use fallback result so metrics have consistent denominator
            result = {
                "type": "uncategorized",
                "importance": "routine",
                "client_label": "everything-else",
                "type_conf": 0.0,
                "importance_conf": 0.0,
                "attention_conf": 0.0,
            }

        # Collect confidence scores (before any verifier modifications)
        type_confidences.append(result.get("type_conf", 0.0))
        importance_confidences.append(result.get("importance_conf", 0.0))
        attention_confidences.append(result.get("attention_conf", 0.0))

        # Run verifier if enabled and confidence is low
        if args.with_verifier:
            should_verify, trigger_reasons = should_trigger_verifier(result)
            if should_verify:
                verifier_triggered_count += 1
                verifier_trigger_reasons.extend(trigger_reasons)

                # Extract features and detect contradictions for verifier
                features = extract_email_features(email)
                contradictions = detect_contradictions(result, features)

                # Build email dict for verifier
                email_for_verifier = {
                    "from": from_email,
                    "subject": subject,
                    "snippet": snippet,
                }

                # Call verifier
                try:
                    # Store original values before verifier
                    original_type = result.get("type")
                    original_importance = result.get("importance")
                    original_attention = result.get("attention")

                    verifier_result = run_verifier(
                        classifier=classifier,
                        email=email_for_verifier,
                        first_result=result,
                        features=features,
                        contradictions=contradictions,
                    )

                    # Track verifier decision details
                    decision = {
                        "email_id": email.get("email_id"),
                        "trigger_reasons": trigger_reasons,
                        "verdict": verifier_result.get("verdict"),
                        "original": {
                            "type": original_type,
                            "importance": original_importance,
                            "attention": original_attention,
                        },
                        "why_bad": verifier_result.get("why_bad", ""),
                    }

                    # Apply corrections if verifier rejects
                    if verifier_result.get("verdict") == "reject":
                        verifier_corrected_count += 1
                        correction = verifier_result.get("correction", {})
                        decision["correction"] = correction
                        if correction:
                            if correction.get("type"):
                                result["type"] = correction["type"]
                            if correction.get("importance"):
                                result["importance"] = correction["importance"]
                            if correction.get("attention"):
                                result["attention"] = correction["attention"]
                            # Recalculate client_label after corrections
                            result["client_label"] = get_client_label_from_result(result)

                    verifier_decisions.append(decision)
                except Exception as e:
                    print(f"  ⚠️  Verifier error for email {email.get('email_id')}: {e}")

        # Map predictions to GDS format
        pred_type = map_classifier_type_to_gds(result.get("type", "other"))
        pred_importance = result.get("importance", "routine")  # Gemini's importance (no heuristics)
        pred_client_label = get_client_label_from_result(result)

        # Get ground truth
        actual_type = email.get("email_type", "").strip()
        actual_importance = email.get("importance", "").strip()
        actual_client_label = email.get("client_label", "").strip()

        # Track predictions
        type_predictions.append((pred_type, actual_type))
        importance_predictions.append((pred_importance, actual_importance))
        client_label_predictions.append((pred_client_label, actual_client_label))

        # Track errors with full details for CSV export
        if pred_type != actual_type:
            type_errors.append(
                {
                    "email_id": email.get("email_id"),
                    "error_pattern": f"{actual_type} -> {pred_type}",
                    "predicted": pred_type,
                    "actual": actual_type,
                    "subject": subject,
                    "from": from_email,
                    "snippet": snippet[:200] if snippet else "",
                }
            )

        if pred_importance != actual_importance:
            importance_errors.append(
                {
                    "email_id": email.get("email_id"),
                    "error_pattern": f"{actual_importance} -> {pred_importance}",
                    "predicted": pred_importance,
                    "actual": actual_importance,
                    "subject": subject,
                    "from": from_email,
                    "snippet": snippet[:200] if snippet else "",
                    "email_type": pred_type,
                }
            )

        if pred_client_label != actual_client_label:
            client_label_errors.append(
                {
                    "email_id": email.get("email_id"),
                    "error_pattern": f"{actual_client_label} -> {pred_client_label}",
                    "predicted": pred_client_label,
                    "actual": actual_client_label,
                    "subject": subject,
                    "from": from_email,
                    "snippet": snippet[:200] if snippet else "",
                    "email_type": pred_type,
                }
            )

    # Calculate accuracy
    print("\n" + "=" * 60)
    print("CLASSIFICATION ACCURACY RESULTS")
    print("=" * 60)

    # Type accuracy
    type_correct = sum(1 for pred, actual in type_predictions if pred == actual)
    type_accuracy = type_correct / len(type_predictions) * 100

    importance_correct = sum(1 for pred, actual in importance_predictions if pred == actual)
    importance_accuracy = importance_correct / len(importance_predictions) * 100

    client_label_correct = sum(1 for pred, actual in client_label_predictions if pred == actual)
    client_label_accuracy = client_label_correct / len(client_label_predictions) * 100

    print("\nOverall Accuracy:")
    print(f"  email_type:   {type_accuracy:5.1f}% ({type_correct}/{len(type_predictions)})")
    print(
        f"  importance:   {importance_accuracy:5.1f}% ({importance_correct}/{len(importance_predictions)})"
    )
    print(
        f"  client_label: {client_label_accuracy:5.1f}% ({client_label_correct}/{len(client_label_predictions)})"
    )

    # Confusion matrices
    type_labels = [
        "otp",
        "notification",
        "event",
        "newsletter",
        "promotion",
        "message",
        "receipt",
        "other",
    ]
    importance_labels = ["critical", "time_sensitive", "routine"]
    client_labels = ["action-required", "receipts", "messages", "everything-else"]

    type_matrix = compute_confusion_matrix(type_predictions, type_labels)
    importance_matrix = compute_confusion_matrix(importance_predictions, importance_labels)
    client_matrix = compute_confusion_matrix(client_label_predictions, client_labels)

    print_confusion_matrix(type_matrix, "Email Type Confusion Matrix", type_labels)
    print_confusion_matrix(importance_matrix, "Importance Confusion Matrix", importance_labels)
    print_confusion_matrix(client_matrix, "Client Label Confusion Matrix", client_labels)

    # Top error patterns
    print("\n" + "=" * 60)
    print("TOP MISCLASSIFICATION PATTERNS")
    print("=" * 60)

    print("\nEmail Type Errors:")
    for pattern, examples in analyze_errors(type_errors, "type"):
        print(f"  {pattern}: {len(examples)} errors")
        if args.verbose and examples:
            for ex in examples[:2]:
                print(f"    - {ex['subject']}")

    print("\nImportance Errors:")
    for pattern, examples in analyze_errors(importance_errors, "importance"):
        print(f"  {pattern}: {len(examples)} errors")
        if args.verbose and examples:
            for ex in examples[:2]:
                print(f"    - {ex['subject']}")

    print("\nClient Label Errors:")
    for pattern, examples in analyze_errors(client_label_errors, "client_label"):
        print(f"  {pattern}: {len(examples)} errors")
        if args.verbose and examples:
            for ex in examples[:2]:
                print(f"    - {ex['subject']}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total emails evaluated: {len(emails)}")
    print(f"Type errors: {len(type_errors)}")
    print(f"Importance errors: {len(importance_errors)}")
    print(f"Client label errors: {len(client_label_errors)}")
    if classification_failures:
        print(f"\n⚠️  Classification failures: {len(classification_failures)}")
        for failure in classification_failures[:5]:  # Show first 5
            print(f"    - Email {failure['email_id']}: {failure['error_type']}")

    # Verifier stats (if enabled)
    if args.with_verifier:
        print("\n" + "-" * 40)
        print("VERIFIER STATS")
        print("-" * 40)
        trigger_rate = verifier_triggered_count / len(emails) * 100 if emails else 0
        correction_rate = (
            verifier_corrected_count / verifier_triggered_count * 100
            if verifier_triggered_count
            else 0
        )
        print(f"Verifier triggered: {verifier_triggered_count}/{len(emails)} ({trigger_rate:.1f}%)")
        print(
            f"Verifier corrected: {verifier_corrected_count}/{verifier_triggered_count} ({correction_rate:.1f}%)"
        )

        # Show top trigger reasons
        from collections import Counter

        reason_counts = Counter(verifier_trigger_reasons)
        if reason_counts:
            print("\nTop trigger reasons:")
            for reason, count in reason_counts.most_common(5):
                print(f"  {reason}: {count}")

        # Show verifier correction examples
        if verifier_decisions:
            corrections = [d for d in verifier_decisions if d.get("verdict") == "reject"]
            if corrections:
                print(f"\nVerifier corrections ({len(corrections)} total):")
                for corr in corrections[:5]:  # Show first 5
                    print(f"  Email {corr['email_id']}:")
                    print(f"    Original: {corr['original']}")
                    print(f"    Correction: {corr.get('correction', {})}")
                    if corr.get("why_bad"):
                        print(f"    Why: {corr['why_bad']}")

    # Confidence Statistics (always show)
    print("\n" + "-" * 40)
    print("CONFIDENCE STATISTICS")
    print("-" * 40)
    if type_confidences:
        from statistics import mean, median

        print(
            f"Type confidence:       mean={mean(type_confidences):.2f}, "
            f"median={median(type_confidences):.2f}, "
            f"min={min(type_confidences):.2f}, max={max(type_confidences):.2f}"
        )
        print(
            f"Importance confidence: mean={mean(importance_confidences):.2f}, "
            f"median={median(importance_confidences):.2f}, "
            f"min={min(importance_confidences):.2f}, max={max(importance_confidences):.2f}"
        )
        print(
            f"Attention confidence:  mean={mean(attention_confidences):.2f}, "
            f"median={median(attention_confidences):.2f}, "
            f"min={min(attention_confidences):.2f}, max={max(attention_confidences):.2f}"
        )

        # Count low confidence predictions
        low_type = sum(1 for c in type_confidences if c < VERIFIER_CONFIDENCE_THRESHOLD)
        low_imp = sum(1 for c in importance_confidences if c < VERIFIER_CONFIDENCE_THRESHOLD)
        low_att = sum(1 for c in attention_confidences if c < VERIFIER_CONFIDENCE_THRESHOLD)
        print(f"\nBelow {VERIFIER_CONFIDENCE_THRESHOLD} threshold:")
        print(
            f"  Type: {low_type}/{len(type_confidences)} ({low_type / len(type_confidences) * 100:.1f}%)"
        )
        print(
            f"  Importance: {low_imp}/{len(importance_confidences)} ({low_imp / len(importance_confidences) * 100:.1f}%)"
        )
        print(
            f"  Attention: {low_att}/{len(attention_confidences)} ({low_att / len(attention_confidences) * 100:.1f}%)"
        )
    else:
        print("No confidence data collected")

    if type_accuracy >= 85:
        print("\n[OK] Type accuracy is good (>=85%)")
    else:
        print("\n[!!] Type accuracy needs improvement (<85%)")

    if importance_accuracy >= 80:
        print("[OK] Importance accuracy is acceptable (>=80%)")
    else:
        print("[!!] Importance accuracy needs improvement (<80%)")

    # Save results if requested
    if args.save_results:
        metrics = {
            "type_accuracy": type_accuracy,
            "type_correct": type_correct,
            "type_total": len(type_predictions),
            "importance_accuracy": importance_accuracy,
            "importance_correct": importance_correct,
            "importance_total": len(importance_predictions),
            "client_label_accuracy": client_label_accuracy,
            "client_label_correct": client_label_correct,
            "client_label_total": len(client_label_predictions),
        }

        # Add verifier metrics if enabled
        if args.with_verifier:
            trigger_rate = verifier_triggered_count / len(emails) * 100 if emails else 0
            correction_rate = (
                verifier_corrected_count / verifier_triggered_count * 100
                if verifier_triggered_count
                else 0
            )
            metrics["verifier_enabled"] = True
            metrics["verifier_triggered_count"] = verifier_triggered_count
            metrics["verifier_corrected_count"] = verifier_corrected_count
            metrics["verifier_trigger_rate"] = trigger_rate
            metrics["verifier_correction_rate"] = correction_rate

        # Add confidence statistics
        if type_confidences:
            from statistics import mean, median

            metrics["confidence_stats"] = {
                "type": {
                    "mean": round(mean(type_confidences), 3),
                    "median": round(median(type_confidences), 3),
                    "min": round(min(type_confidences), 3),
                    "max": round(max(type_confidences), 3),
                    "below_threshold": sum(
                        1 for c in type_confidences if c < VERIFIER_CONFIDENCE_THRESHOLD
                    ),
                },
                "importance": {
                    "mean": round(mean(importance_confidences), 3),
                    "median": round(median(importance_confidences), 3),
                    "min": round(min(importance_confidences), 3),
                    "max": round(max(importance_confidences), 3),
                    "below_threshold": sum(
                        1 for c in importance_confidences if c < VERIFIER_CONFIDENCE_THRESHOLD
                    ),
                },
                "attention": {
                    "mean": round(mean(attention_confidences), 3),
                    "median": round(median(attention_confidences), 3),
                    "min": round(min(attention_confidences), 3),
                    "max": round(max(attention_confidences), 3),
                    "below_threshold": sum(
                        1 for c in attention_confidences if c < VERIFIER_CONFIDENCE_THRESHOLD
                    ),
                },
                "threshold": VERIFIER_CONFIDENCE_THRESHOLD,
            }

        # Convert confusion matrices to serializable format
        confusion_matrices = {
            "type": {k: dict(v) for k, v in type_matrix.items()},
            "importance": {k: dict(v) for k, v in importance_matrix.items()},
            "client_label": {k: dict(v) for k, v in client_matrix.items()},
        }

        # Extract top errors as simple tuples
        top_errors = {
            "type": [
                (pattern, len(examples))
                for pattern, examples in analyze_errors(type_errors, "type")
            ],
            "importance": [
                (pattern, len(examples))
                for pattern, examples in analyze_errors(importance_errors, "importance")
            ],
            "client_label": [
                (pattern, len(examples))
                for pattern, examples in analyze_errors(client_label_errors, "client_label")
            ],
        }

        # Collect all errors for CSV export
        all_errors = {
            "type": type_errors,
            "importance": importance_errors,
            "client_label": client_label_errors,
        }

        saved_path = save_experiment_results(
            name=args.name,
            metrics=metrics,
            confusion_matrices=confusion_matrices,
            top_errors=top_errors,
            all_errors=all_errors,
            num_emails=len(emails),
            notes=args.notes,
        )
        print(f"\nResults saved to: {saved_path}")

        # Print CSV file locations
        print("\nError detail CSVs:")
        for error_type in ["type", "importance", "client_label"]:
            error_count = len(all_errors[error_type])
            if error_count > 0:
                print(f"  {error_type}: {error_count} errors logged")


if __name__ == "__main__":
    main()
