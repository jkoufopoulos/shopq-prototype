# ruff: noqa
"""
Temporal Evaluation: Dataset 2 Full Pipeline Test

This script evaluates the complete ShopQ digest pipeline against Dataset 2:
1. Loads 70 annotated emails from Dataset 2 (Nov 2-9, 2025)
2. Sets digest creation time to T0 (Nov 10, 2025 18:20:07 - 24h after latest email)
3. Runs full classification + temporal decay + digest categorization pipeline
4. Compares pipeline output against T0 ground truth labels
5. Generates detailed evaluation report with metrics and error analysis

Usage:
    python3 scripts/evaluate_temporal_dataset2.py
    python3 scripts/evaluate_temporal_dataset2.py --output reports/temporal_eval_dataset2.md
"""

import argparse
import email.utils
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from shopq.classification.decay import resolve_temporal_importance

from shopq.classification.importance_mapping.guardrails import GuardrailMatcher
from shopq.classification.importance_mapping.mapper import BridgeImportanceMapper
from shopq.classification.pipeline_wrapper import RefactoredPipelineClassifier


def parse_rfc2822_date(date_str: str) -> datetime | None:
    """Parse RFC 2822 date string to datetime."""
    try:
        date_tuple = email.utils.parsedate_tz(date_str)
        if date_tuple:
            timestamp = email.utils.mktime_tz(date_tuple)
            return datetime.fromtimestamp(timestamp, tz=UTC)
    except Exception as e:
        print(f"⚠️  Failed to parse date '{date_str}': {e}")
    return None


def predict_section(
    stored_importance: str,
    email_type: str,
    category: str,
) -> str:
    """
    Predict digest section based on importance, type, and category.

    This is the SIMPLIFIED section predictor (without temporal decay).
    Used as baseline to compare against temporal-aware prediction.
    """
    importance = (stored_importance or "").lower()
    email_type = (email_type or "").lower()

    # Critical importance → CRITICAL section
    if importance == "critical":
        return "critical"

    # Time-sensitive importance → COMING UP section
    if importance == "time_sensitive":
        return "coming_up"

    # Routine importance → depends on type
    if importance == "routine":
        # Receipts, confirmations → WORTH KNOWING
        if email_type in ["receipt", "confirmation"]:
            return "worth_knowing"

        # Promotions, newsletters → EVERYTHING ELSE
        if email_type in ["promotion", "newsletter", "marketing"]:
            return "everything_else"

        # Social media, surveys → SKIP
        if email_type in ["social", "survey"]:
            return "skip"

        # Default routine → WORTH KNOWING
        return "worth_knowing"

    # Fallback
    return "worth_knowing"


def predict_section_with_temporal(
    stored_importance: str,
    email_type: str,
    category: str,
    temporal_start: datetime | None,
    temporal_end: datetime | None,
    now: datetime,
    email_id: str = "unknown",
) -> tuple[str, str]:
    """
    Predict digest section using temporal decay logic.

    Returns:
        (section, reason) - section name and reason for prediction
    """
    # For emails with temporal fields, use temporal decay
    if temporal_start and email_type in ["event", "deadline", "notification"]:
        try:
            result = resolve_temporal_importance(
                email_type=email_type,
                stored_importance=stored_importance,
                temporal_start=temporal_start,
                temporal_end=temporal_end,
                now=now,
            )

            resolved_importance = result.resolved_importance
            decay_reason = result.decay_reason or "no_decay"

            # Check if should be hidden (expired)
            if result.decay_reason == "temporal_expired":
                return "skip", "temporal_expired"

        except Exception as e:
            print(f"  ⚠️  Temporal decay failed for {email_id}: {type(e).__name__}: {e}")
            # Fallback to stored importance without temporal decay
            resolved_importance = stored_importance
            decay_reason = f"error: {str(e)[:50]}"
    else:
        # No temporal fields, use stored importance
        resolved_importance = stored_importance
        decay_reason = "no_temporal_data"

    # Map resolved importance to section
    section = predict_section(resolved_importance, email_type, category)
    return section, decay_reason


def get_ground_truth_section(row: pd.Series, timepoint: str) -> str:
    """Extract ground truth section from T0/T1/T2 columns."""
    prefix = f"{timepoint}_"

    # Check which section has an 'X' marker
    if row.get(f"{prefix}critical") == "X":
        return "critical"
    if row.get(f"{prefix}today") == "X":
        return "today"
    if row.get(f"{prefix}coming_up") == "X":
        return "coming_up"
    if row.get(f"{prefix}worth_knowing") == "X":
        return "worth_knowing"
    if row.get(f"{prefix}everything_else") == "X":
        return "everything_else"
    if row.get(f"{prefix}skip") == "X":
        return "skip"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Evaluate temporal decay pipeline on Dataset 2")
    parser.add_argument(
        "--dataset",
        type=str,
        default="reports/dataset2_nov2-9_70_emails.csv",
        help="Path to Dataset 2 CSV",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/temporal_eval_dataset2.md",
        help="Output markdown report path",
    )
    parser.add_argument(
        "--digest-time",
        type=str,
        default="2025-11-10T18:20:07",
        help="Digest creation time (ISO format, default: 24h after latest email in dataset)",
    )
    args = parser.parse_args()

    # Load Dataset 2
    dataset_path = Path(__file__).parent.parent / args.dataset
    if not dataset_path.exists():
        print(f"❌ Dataset not found: {dataset_path}")
        return 1

    df = pd.read_csv(dataset_path)
    print(f"✅ Loaded {len(df)} emails from Dataset 2")
    print(f"📂 Dataset: {dataset_path}")
    print()

    # Parse digest creation time (T0)
    digest_time = datetime.fromisoformat(args.digest_time)
    if digest_time.tzinfo is None:
        digest_time = digest_time.replace(tzinfo=UTC)

    print(f"⏰ Digest creation time (T0): {digest_time.isoformat()}")
    print("   (24 hours after latest email in dataset)")
    print()

    # Initialize pipeline components
    base_classifier = RefactoredPipelineClassifier()
    guardrails = GuardrailMatcher()
    importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)

    # Evaluation results
    results = []
    confusion_matrix = defaultdict(lambda: defaultdict(int))
    errors = []

    print("🔄 Running full pipeline on Dataset 2 emails...")
    print()

    for idx, row in df.iterrows():
        email_id = row["email_id"]

        # Step 1: Base classification
        classification = base_classifier.classify(
            subject=row["subject"],
            snippet=row["snippet"],
            from_field=row["from"],
        )

        # Step 2: Apply importance mapping
        email_with_classification = {
            "subject": row["subject"],
            "snippet": row["snippet"],
            "from": row["from"],
            **classification,
        }

        decision = importance_mapper.map_email(email_with_classification)
        final_importance = decision.importance or "routine"

        # Step 3: Extract temporal fields (if any)
        # NOTE: Dataset 2 doesn't have temporal_start/temporal_end columns
        # We'll need to infer them from the email content/subject for events
        # For now, set to None (this is a limitation we should document)
        temporal_start = None
        temporal_end = None

        # Step 4: Apply temporal decay and predict section
        email_type = classification.get("type", "")
        category = classification.get("category", "")

        predicted_section, decay_reason = predict_section_with_temporal(
            stored_importance=final_importance,
            email_type=email_type,
            category=category,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            now=digest_time,
            email_id=email_id,
        )

        # Step 5: Get ground truth from T0 annotations
        ground_truth = get_ground_truth_section(row, "t0")

        # Check if prediction matches ground truth
        is_correct = predicted_section == ground_truth

        # Update confusion matrix
        confusion_matrix[ground_truth][predicted_section] += 1

        # Track errors
        if not is_correct:
            errors.append(
                {
                    "email_id": email_id,
                    "subject": row["subject"][:60],
                    "ground_truth": ground_truth,
                    "predicted": predicted_section,
                    "importance": final_importance,
                    "type": email_type,
                    "category": category,
                    "decay_reason": decay_reason,
                }
            )

        # Store result
        results.append(
            {
                "email_id": email_id,
                "subject": row["subject"],
                "from": row["from"],
                "predicted_importance": final_importance,
                "predicted_type": email_type,
                "predicted_category": category,
                "predicted_section": predicted_section,
                "ground_truth_section": ground_truth,
                "is_correct": is_correct,
                "decay_reason": decay_reason,
            }
        )

    # Calculate metrics
    total_emails = len(results)
    correct_predictions = sum(1 for r in results if r["is_correct"])
    accuracy = correct_predictions / total_emails if total_emails > 0 else 0

    # Per-section metrics
    section_metrics = {}
    sections = ["critical", "today", "coming_up", "worth_knowing", "everything_else", "skip"]

    for section in sections:
        tp = confusion_matrix[section][section]
        fp = sum(confusion_matrix[other][section] for other in sections if other != section)
        fn = sum(confusion_matrix[section][other] for other in sections if other != section)
        tn = sum(
            confusion_matrix[gt][pred]
            for gt in sections
            for pred in sections
            if gt != section and pred != section
        )

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        section_metrics[section] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    # Generate markdown report
    output_path = Path(__file__).parent.parent / args.output

    with open(output_path, "w") as f:
        f.write("# Temporal Evaluation: Dataset 2 Full Pipeline Test\n\n")
        f.write(f"**Date**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
        f.write(f"**Dataset**: {args.dataset}\n\n")
        f.write(f"**Digest Time (T0)**: {digest_time.isoformat()}\n\n")
        f.write(f"**Total Emails**: {total_emails}\n\n")
        f.write("---\n\n")

        # Overall metrics
        f.write("## Overall Metrics\n\n")
        f.write(f"- **Accuracy**: {accuracy:.2%} ({correct_predictions}/{total_emails})\n")
        f.write(f"- **Errors**: {len(errors)}\n\n")

        # Per-section metrics
        f.write("## Per-Section Metrics\n\n")
        f.write("| Section | Precision | Recall | F1 Score | TP | FP | FN |\n")
        f.write("|---------|-----------|--------|----------|----|----|----|\n")

        for section in sections:
            m = section_metrics[section]
            f.write(
                f"| {section.upper()} | "
                f"{m['precision']:.2%} | "
                f"{m['recall']:.2%} | "
                f"{m['f1']:.2%} | "
                f"{m['tp']} | "
                f"{m['fp']} | "
                f"{m['fn']} |\n"
            )

        f.write("\n")

        # Confusion matrix
        f.write("## Confusion Matrix\n\n")
        f.write("| Ground Truth \\ Predicted | " + " | ".join(s.upper() for s in sections) + " |\n")
        f.write("|" + "|".join(["-" * 25] + ["-" * 10 for _ in sections]) + "|\n")

        for gt in sections:
            row = f"| {gt.upper()} | "
            row += " | ".join(str(confusion_matrix[gt][pred]) for pred in sections)
            row += " |\n"
            f.write(row)

        f.write("\n")

        # Error analysis
        f.write("## Error Analysis\n\n")
        f.write(f"Total errors: {len(errors)}\n\n")

        if errors:
            # Group errors by type
            error_patterns = defaultdict(list)
            for err in errors:
                pattern = f"{err['ground_truth']} → {err['predicted']}"
                error_patterns[pattern].append(err)

            f.write("### Errors by Pattern\n\n")
            for pattern, pattern_errors in sorted(error_patterns.items(), key=lambda x: -len(x[1])):
                f.write(f"#### {pattern} ({len(pattern_errors)} errors)\n\n")
                f.write("| Email ID | Subject | Importance | Type | Category |\n")
                f.write("|----------|---------|------------|------|----------|\n")

                for err in pattern_errors[:10]:  # Show first 10
                    f.write(
                        f"| {err['email_id']} | "
                        f"{err['subject']} | "
                        f"{err['importance']} | "
                        f"{err['type']} | "
                        f"{err['category']} |\n"
                    )

                if len(pattern_errors) > 10:
                    f.write(f"\n*...and {len(pattern_errors) - 10} more*\n")

                f.write("\n")

        # Known limitations
        f.write("## Known Limitations\n\n")
        f.write(
            "1. **Missing temporal fields**: Dataset 2 doesn't have `temporal_start`/`temporal_end` columns\n"
        )
        f.write("   - Events/deadlines cannot use temporal decay logic\n")
        f.write("   - Need to extract event times from email content (future enhancement)\n\n")
        f.write("2. **Simplified section mapping**: Using basic importance → section mapping\n")
        f.write("   - Not using full digest categorization pipeline\n")
        f.write("   - Need to integrate with DigestCategorizer for complete evaluation\n\n")

        # Next steps
        f.write("## Next Steps\n\n")
        f.write("1. Add temporal field extraction to Dataset 2 (parse event times from subjects)\n")
        f.write("2. Integrate full digest categorization pipeline (DigestCategorizer)\n")
        f.write("3. Run evaluation at T1 (+1 day) and T2 (+1 week) to test temporal decay\n")
        f.write("4. Compare temporal-aware vs. non-temporal-aware classification\n\n")

    print("✅ Evaluation complete!")
    print()
    print(f"📊 Overall Accuracy: {accuracy:.2%} ({correct_predictions}/{total_emails})")
    print(f"❌ Errors: {len(errors)}")
    print()
    print(f"📄 Full report saved to: {output_path}")
    print()

    # Print top error patterns
    if errors:
        error_patterns = defaultdict(int)
        for err in errors:
            pattern = f"{err['ground_truth']} → {err['predicted']}"
            error_patterns[pattern] += 1

        print("🔍 Top Error Patterns:")
        for pattern, count in sorted(error_patterns.items(), key=lambda x: -x[1])[:5]:
            print(f"   {pattern}: {count} errors")

    return 0


if __name__ == "__main__":
    sys.exit(main())
