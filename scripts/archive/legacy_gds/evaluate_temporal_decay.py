# ruff: noqa
#!/usr/bin/env python3
"""
Evaluate Temporal Decay Logic against T0 Golden Dataset.

Tests digest generation at three timepoints:
- T0: Just received (baseline)
- T1: +24 hours (test temporal decay)
- T2: +72 hours (test aggressive decay)

Compares system predictions to user's manual labels and generates accuracy report.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.digest.categorizer import DigestCategorizer

from mailq.classification.enrichment import enrich_entities_with_temporal_decay
from mailq.classification.extractor import HybridExtractor
from mailq.classification.importance_mapping.guardrails import GuardrailMatcher
from mailq.classification.importance_mapping.mapper import BridgeImportanceMapper
from mailq.classification.pipeline_wrapper import RefactoredPipelineClassifier


def load_golden_dataset():
    """Load the manually labeled golden dataset."""
    csv_path = Path(__file__).parent.parent / "reports" / "temporal_digest_review_50_emails.csv"

    if not csv_path.exists():
        print(f"❌ Golden dataset not found at: {csv_path}")
        print("Run: python3 scripts/create_temporal_digest_review.py")
        print("Then: python3 scripts/interactive_temporal_review.py")
        return None

    df = pd.read_csv(csv_path)

    # Check if T0 labels exist
    if not (df["t0_critical"].notna().any() or df["t0_today"].notna().any()):
        print("❌ T0 labels not found. Please complete T0 labeling first.")
        print("Run: python3 scripts/interactive_temporal_review.py")
        return None

    return df


def get_user_section(email, timepoint):
    """Get the section user labeled for this email at given timepoint."""
    prefix = f"{timepoint}_"

    if email.get(f"{prefix}critical") == "X":
        return "critical"
    if email.get(f"{prefix}today") == "X":
        return "today"
    if email.get(f"{prefix}coming_up") == "X":
        return "coming_up"
    if email.get(f"{prefix}worth_knowing") == "X":
        return "worth_knowing"
    if email.get(f"{prefix}everything_else") == "X":
        return "everything_else"
    if email.get(f"{prefix}skip") == "X":
        return "skip"

    return None  # Not labeled yet


def classify_email(email_row, base_classifier, importance_mapper, guardrails):
    """Classify a single email using the full pipeline."""
    # Backend classification
    base_classification = base_classifier.classify(
        subject=email_row["subject"],
        snippet=email_row["snippet"],
        from_field=email_row["from"],
    )

    # Apply importance mapping
    email_with_classification = {
        "subject": email_row["subject"],
        "snippet": email_row["snippet"],
        "from": email_row["from"],
        "id": email_row["email_id"],
        "thread_id": email_row["email_id"],
        **base_classification,
    }

    decision = importance_mapper.map_email(email_with_classification)
    final_importance = decision.importance or "routine"

    return {
        **email_with_classification,
        "importance": final_importance,
        "type": base_classification.get("type", ""),
        "category": base_classification.get("category", ""),
    }


def extract_and_enrich_entity(email, extractor, current_time):
    """Extract entity from email and apply temporal enrichment."""
    # Try to extract entity
    entities = extractor.extract_from_email(
        subject=email["subject"],
        snippet=email["snippet"],
        from_email=email["from"],
        email_id=email["id"],
    )

    if not entities:
        return None

    entity = entities[0]  # Take first entity

    # Apply temporal enrichment (same as Stage 3.5 in context_digest.py)
    enriched = enrich_entities_with_temporal_decay([entity], now=current_time)

    if not enriched:
        return None

    return enriched[0]


def categorize_email(email, entity, categorizer, timepoint_name):
    """
    Determine final digest section using categorizer.

    This mimics the hybrid renderer's section mapping logic.
    """
    if entity:
        # Has entity → use resolved_importance
        section = categorizer.categorize(entity)
    else:
        # No entity → use stored importance (simplified mapping)
        importance = email.get("importance", "routine")
        if importance == "critical":
            section = "critical"
        elif importance == "time_sensitive":
            section = "coming_up"  # Default for time_sensitive without entity
        else:
            section = "worth_knowing"

    # Map "skip" to "everything_else" for comparison
    if section == "skip":
        return "skip"

    return section


def evaluate_timepoint(df, timepoint, hours_offset):
    """Evaluate system predictions at a specific timepoint."""
    print(f"\n{'=' * 80}")
    print(f"EVALUATING {timepoint.upper()} (+{hours_offset} hours)")
    print(f"{'=' * 80}\n")

    # Initialize classifiers
    base_classifier = RefactoredPipelineClassifier()
    guardrails = GuardrailMatcher()
    importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)
    categorizer = DigestCategorizer(verbose=False)
    extractor = HybridExtractor()

    # Set current time (T0 + offset)
    t0_time = datetime.now()
    current_time = t0_time + timedelta(hours=hours_offset)

    results = []
    correct = 0
    total = 0
    confusion_matrix = {}

    for idx, email_row in df.iterrows():
        # Get user's label for this timepoint
        user_section = get_user_section(email_row, timepoint)

        if user_section is None:
            print(f"⚠️  Email {idx + 1} not labeled for {timepoint.upper()}, skipping")
            continue

        # Classify email
        email = classify_email(email_row, base_classifier, importance_mapper, guardrails)

        # Extract and enrich entity
        entity = extract_and_enrich_entity(email, extractor, current_time)

        # Determine final section
        system_section = categorize_email(email, entity, categorizer, timepoint)

        # Record result
        is_correct = system_section == user_section
        if is_correct:
            correct += 1
        total += 1

        results.append(
            {
                "email_id": email_row["email_id"],
                "subject": email_row["subject"][:60],
                "user_section": user_section,
                "system_section": system_section,
                "correct": is_correct,
                "importance": email.get("importance", ""),
                "has_entity": entity is not None,
            }
        )

        # Update confusion matrix
        key = (user_section, system_section)
        confusion_matrix[key] = confusion_matrix.get(key, 0) + 1

    # Calculate accuracy
    accuracy = (correct / total * 100) if total > 0 else 0

    print(f"✅ Accuracy: {correct}/{total} ({accuracy:.1f}%)")
    print()

    # Show confusion matrix
    print("CONFUSION MATRIX:")
    print("-" * 80)
    sections = ["critical", "today", "coming_up", "worth_knowing", "everything_else", "skip"]

    # Header
    header = "User \\ System"
    print(f"{header:<20}", end="")
    for sec in sections:
        print(f"{sec[:8]:<10}", end="")
    print()
    print("-" * 80)

    # Rows
    for user_sec in sections:
        print(f"{user_sec:<20}", end="")
        for sys_sec in sections:
            count = confusion_matrix.get((user_sec, sys_sec), 0)
            if count > 0:
                marker = "✓" if user_sec == sys_sec else "✗"
                print(f"{marker}{count:<9}", end="")
            else:
                print(f"{' ':<10}", end="")
        print()

    print()

    # Show misclassifications
    misclassified = [r for r in results if not r["correct"]]
    if misclassified:
        print(f"MISCLASSIFICATIONS ({len(misclassified)}):")
        print("-" * 80)
        for i, r in enumerate(misclassified[:10], 1):  # Show first 10
            print(f"{i}. {r['subject']}")
            print(f"   User: {r['user_section']} | System: {r['system_section']}")
            print(f"   Importance: {r['importance']} | Has entity: {r['has_entity']}")
            print()

        if len(misclassified) > 10:
            print(f"   ... and {len(misclassified) - 10} more")
        print()

    return {
        "timepoint": timepoint,
        "accuracy": accuracy,
        "correct": correct,
        "total": total,
        "results": results,
        "confusion_matrix": confusion_matrix,
    }


def generate_report(evaluations):
    """Generate comprehensive comparison report."""
    print("\n" + "=" * 80)
    print("TEMPORAL DECAY EVALUATION REPORT")
    print("=" * 80 + "\n")

    print("ACCURACY BY TIMEPOINT:")
    print("-" * 80)
    for eval_result in evaluations:
        tp = eval_result["timepoint"].upper()
        acc = eval_result["accuracy"]
        correct = eval_result["correct"]
        total = eval_result["total"]
        print(f"{tp:<6} {acc:>5.1f}%  ({correct}/{total} correct)")

    print()

    # Temporal decay insights
    if len(evaluations) >= 2:
        print("TEMPORAL DECAY INSIGHTS:")
        print("-" * 80)

        t0_results = evaluations[0]["results"]

        for eval_result in evaluations[1:]:
            tp = eval_result["timepoint"].upper()
            tp_results = eval_result["results"]

            # Find emails that changed sections
            changed = []
            for t0_r in t0_results:
                tp_r = next((r for r in tp_results if r["email_id"] == t0_r["email_id"]), None)
                if tp_r and t0_r["user_section"] != tp_r["user_section"]:
                    changed.append(
                        {
                            "email_id": t0_r["email_id"],
                            "subject": t0_r["subject"],
                            "t0": t0_r["user_section"],
                            tp.lower(): tp_r["user_section"],
                        }
                    )

            if changed:
                print(f"\n{tp} Section Changes (User Labels):")
                for c in changed[:5]:  # Show first 5
                    print(f"  • {c['subject']}")
                    print(f"    T0: {c['t0']} → {tp}: {c[tp.lower()]}")
                if len(changed) > 5:
                    print(f"    ... and {len(changed) - 5} more")

        print()

    # Save detailed results to CSV
    output_path = Path(__file__).parent.parent / "reports" / "temporal_evaluation_results.csv"
    all_results = []
    for eval_result in evaluations:
        for r in eval_result["results"]:
            all_results.append(
                {
                    "timepoint": eval_result["timepoint"],
                    "email_id": r["email_id"],
                    "subject": r["subject"],
                    "user_section": r["user_section"],
                    "system_section": r["system_section"],
                    "correct": r["correct"],
                    "importance": r["importance"],
                    "has_entity": r["has_entity"],
                }
            )

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(output_path, index=False)

    print(f"📊 Detailed results saved to: {output_path}")
    print()


def main():
    print("=" * 80)
    print("TEMPORAL DECAY EVALUATOR")
    print("=" * 80)
    print()

    # Load golden dataset
    df = load_golden_dataset()
    if df is None:
        return 1

    print(f"✅ Loaded {len(df)} emails from golden dataset")
    print()

    # Count labeled emails per timepoint
    t0_labeled = sum(1 for _, row in df.iterrows() if get_user_section(row, "t0") is not None)
    t1_labeled = sum(1 for _, row in df.iterrows() if get_user_section(row, "t1") is not None)
    t2_labeled = sum(1 for _, row in df.iterrows() if get_user_section(row, "t2") is not None)

    print("Labeled emails:")
    print(f"  T0 (Just received): {t0_labeled}/{len(df)}")
    print(f"  T1 (+24 hours):     {t1_labeled}/{len(df)}")
    print(f"  T2 (+72 hours):     {t2_labeled}/{len(df)}")
    print()

    # Evaluate each timepoint
    evaluations = []

    if t0_labeled > 0:
        t0_result = evaluate_timepoint(df, "t0", hours_offset=0)
        evaluations.append(t0_result)

    if t1_labeled > 0:
        t1_result = evaluate_timepoint(df, "t1", hours_offset=24)
        evaluations.append(t1_result)

    if t2_labeled > 0:
        t2_result = evaluate_timepoint(df, "t2", hours_offset=72)
        evaluations.append(t2_result)

    # Generate report
    if evaluations:
        generate_report(evaluations)

    return 0


if __name__ == "__main__":
    sys.exit(main())
