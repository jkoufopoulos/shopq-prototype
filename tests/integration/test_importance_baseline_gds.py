"""
Test importance baseline and quality gates against Golden Dataset (gds-1.0.csv)

This file validates MVP Quality Gates from ROADMAP.md:
- Critical precision ≥95%
- Critical recall ≥85%
- OTP in CRITICAL == 0
- Event-newsletter noise ≤2%
- Importance distribution stable (±5pp)

Usage:
    pytest tests/test_importance_baseline_gds.py -v
    pytest tests/test_importance_baseline_gds.py::test_critical_precision -v

Purpose:
    Detect drift and ensure quality standards before shipping features
"""

from pathlib import Path

import pandas as pd
import pytest

# Import refactored pipeline (matches production)
try:
    from mailq.classification.pipeline_wrapper import RefactoredPipelineClassifier
except ImportError:
    pytest.skip("MailQ modules not available", allow_module_level=True)


@pytest.fixture(scope="module")
def gds():
    """Load Golden Dataset from CSV"""
    gds_path = Path(__file__).parent / "golden_set" / "gds-1.0.csv"

    if not gds_path.exists():
        pytest.skip(f"GDS not found at {gds_path}")

    df = pd.read_csv(gds_path)
    print(f"\n✅ Loaded {len(df)} emails from gds-1.0.csv")
    return df


@pytest.fixture(scope="module")
def classifier():
    """
    Initialize classifier with importance mapper (matches production)

    This wraps RefactoredPipelineClassifier with the importance mapper
    to match the actual /api/organize code path that the extension uses.
    """
    try:
        from mailq.classification.importance_mapping.guardrails import GuardrailMatcher
        from mailq.classification.importance_mapping.mapper import BridgeImportanceMapper

        base_classifier = RefactoredPipelineClassifier()
        guardrails = GuardrailMatcher()
        importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)

        class ClassifierWithMapper:
            """Wrapper that adds importance mapping to classifier"""

            def classify(self, subject, snippet, from_field, **kwargs):
                result = base_classifier.classify(subject, snippet, from_field, **kwargs)
                # Add subject/snippet to result for mapper (required for pattern matching)
                result["subject"] = subject
                result["snippet"] = snippet
                # Map importance (matches api_organize.py integration)
                try:
                    decision = importance_mapper.map_email(result)
                    result["importance"] = decision.importance or "routine"
                    result["importance_reason"] = decision.reason
                    result["importance_source"] = decision.source
                    if decision.rule_name:
                        result["importance_rule"] = decision.rule_name
                    if decision.guardrail:
                        result["importance_guardrail"] = decision.guardrail
                except Exception as e:
                    # Fail gracefully (match production behavior)
                    result["importance"] = "routine"
                    result["importance_reason"] = f"mapper_error: {e}"
                    result["importance_source"] = "fallback"
                return result

        return ClassifierWithMapper()
    except Exception as e:
        pytest.skip(f"Could not initialize classifier with importance mapper: {e}")


@pytest.fixture(scope="module")
def predictions(gds, classifier):
    """
    Run classifier on all GDS emails and cache results

    This is expensive, so we cache it at module scope
    """
    print(f"\n🔄 Classifying {len(gds)} emails from GDS...")

    results = []
    errors = 0

    for _idx, email in gds.iterrows():
        try:
            result = classifier.classify(
                subject=email["subject"], snippet=email["snippet"], from_field=email["from_email"]
            )

            results.append(
                {
                    "message_id": email["message_id"],
                    "predicted_importance": result.get("importance", "routine"),
                    "ground_truth_importance": email["importance"],
                    "predicted_type": result.get("type", "update"),
                    "ground_truth_type": email["email_type"],
                    "subject": email["subject"],
                    "from_email": email["from_email"],
                }
            )

        except Exception as e:
            errors += 1
            # Default to routine if classification fails
            results.append(
                {
                    "message_id": email["message_id"],
                    "predicted_importance": "routine",
                    "ground_truth_importance": email["importance"],
                    "predicted_type": "update",
                    "ground_truth_type": email["email_type"],
                    "subject": email["subject"],
                    "from_email": email["from_email"],
                    "error": str(e),
                }
            )

    print(f"✅ Classified {len(results)} emails ({errors} errors)")

    return pd.DataFrame(results)


def test_critical_precision(predictions):
    """
    Quality Gate: Critical precision must be ≥95%

    Precision = True Positives / (True Positives + False Positives)
    = How many predicted criticals are actually critical
    """
    # Filter to predicted critical
    predicted_critical = predictions[predictions["predicted_importance"] == "critical"]

    if len(predicted_critical) == 0:
        pytest.skip("No emails predicted as critical")

    # True positives: predicted critical AND ground truth critical
    tp = len(predicted_critical[predicted_critical["ground_truth_importance"] == "critical"])

    # False positives: predicted critical BUT ground truth NOT critical
    fp = len(predicted_critical[predicted_critical["ground_truth_importance"] != "critical"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    print("\n📊 Critical Precision:")
    print(f"  True Positives: {tp}")
    print(f"  False Positives: {fp}")
    print(f"  Precision: {precision:.1%}")

    if fp > 0:
        print("\n⚠️  False Positive examples (first 5):")
        fp_examples = predicted_critical[
            predicted_critical["ground_truth_importance"] != "critical"
        ]
        for _idx, row in fp_examples.head(5).iterrows():
            print(f"  - {row['subject'][:60]} (actually {row['ground_truth_importance']})")

    # MVP Quality Gate: ≥95%
    assert precision >= 0.95, f"Critical precision {precision:.1%} < 95% (TP={tp}, FP={fp})"


def test_critical_recall(predictions):
    """
    Quality Gate: Critical recall must be ≥85%

    Recall = True Positives / (True Positives + False Negatives)
    = How many actual criticals are we catching
    """
    # Filter to ground truth critical
    actual_critical = predictions[predictions["ground_truth_importance"] == "critical"]

    if len(actual_critical) == 0:
        pytest.skip("No emails labeled as critical in GDS")

    # True positives: predicted critical AND ground truth critical
    tp = len(actual_critical[actual_critical["predicted_importance"] == "critical"])

    # False negatives: predicted NOT critical BUT ground truth IS critical
    fn = len(actual_critical[actual_critical["predicted_importance"] != "critical"])

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    print("\n📊 Critical Recall:")
    print(f"  True Positives: {tp}")
    print(f"  False Negatives: {fn}")
    print(f"  Recall: {recall:.1%}")

    if fn > 0:
        print("\n⚠️  False Negative examples (first 5):")
        fn_examples = actual_critical[actual_critical["predicted_importance"] != "critical"]
        for _idx, row in fn_examples.head(5).iterrows():
            print(f"  - {row['subject'][:60]} (predicted {row['predicted_importance']})")

    # MVP Quality Gate: ≥85%
    assert recall >= 0.85, f"Critical recall {recall:.1%} < 85% (TP={tp}, FN={fn})"


def test_otp_in_critical_equals_zero(gds, predictions):
    """
    Quality Gate: OTP in CRITICAL must be exactly 0

    This is a hard constraint - NO exceptions
    """
    # Identify OTP emails (same logic as test_guardrails_gds.py)
    otp_pattern = "verification code|one-time|OTP|2FA"
    otp_mask = gds["snippet"].str.contains(otp_pattern, case=False, na=False) | gds[
        "subject"
    ].str.contains(otp_pattern, case=False, na=False)

    otp_message_ids = set(gds[otp_mask]["message_id"])

    # Check predictions for OTP emails
    otp_predictions = predictions[predictions["message_id"].isin(otp_message_ids)]

    if len(otp_predictions) == 0:
        pytest.skip("No OTP emails found in GDS")

    otp_in_critical = len(otp_predictions[otp_predictions["predicted_importance"] == "critical"])

    print("\n📊 OTP in CRITICAL:")
    print(f"  Total OTP emails: {len(otp_predictions)}")
    print(f"  OTP in CRITICAL: {otp_in_critical}")

    if otp_in_critical > 0:
        print("\n❌ OTP emails incorrectly in CRITICAL:")
        critical_otp = otp_predictions[otp_predictions["predicted_importance"] == "critical"]
        for _idx, row in critical_otp.iterrows():
            print(f"  - {row['subject'][:60]}")

    # MVP Quality Gate: Must be 0
    assert otp_in_critical == 0, f"Found {otp_in_critical} OTP emails in CRITICAL (must be 0)"


def test_importance_distribution_stable(predictions):
    """
    Quality Gate: Importance distribution must stay within ±5pp of baseline

    This detects unintended distribution shifts (e.g., bug that makes everything critical)
    """
    # Calculate current distribution
    importance_counts = predictions["predicted_importance"].value_counts()
    total = len(predictions)

    current_dist = {
        "critical": importance_counts.get("critical", 0) / total,
        "time_sensitive": importance_counts.get("time_sensitive", 0) / total,
        "routine": importance_counts.get("routine", 0) / total,
    }

    # Baseline distribution (from gds-1.0 ground truth, updated 2025-11-11)
    # After fixing 8 canceled event labels (critical → time_sensitive)
    baseline_dist = {
        "critical": 0.022,  # 2.2% (11/500 emails)
        "time_sensitive": 0.068,  # 6.8% (34/500 emails)
        "routine": 0.910,  # 91.0% (455/500 emails)
    }

    print("\n📊 Importance Distribution:")
    print(f"  {'Category':<15} {'Baseline':<10} {'Current':<10} {'Drift':<10}")
    print(f"  {'-' * 45}")

    drifts = {}
    for importance in ["critical", "time_sensitive", "routine"]:
        baseline = baseline_dist[importance]
        current = current_dist[importance]
        drift = abs(current - baseline)
        drifts[importance] = drift

        status = "✅" if drift <= 0.05 else "❌"
        print(f"  {status} {importance:<13} {baseline:>7.1%}   {current:>7.1%}   {drift:>7.1%}")

    # MVP Quality Gate: ±5pp (0.05)
    for importance, drift in drifts.items():
        assert drift <= 0.05, f"{importance} drifted by {drift:.1%} (>5pp limit)"


def test_event_newsletter_noise(gds, predictions):
    """
    Quality Gate: Event newsletters in time_sensitive must be ≤2%

    Event newsletters (e.g., "Upcoming events near you") should NOT be in COMING UP
    """
    # Identify event newsletters
    # This is a heuristic - adjust based on your data
    event_newsletter_pattern = (
        "upcoming events|events near you|happening this week|"
        "events you might like|recommended events|event newsletter"
    )

    event_newsletter_mask = gds["subject"].str.contains(
        event_newsletter_pattern, case=False, na=False
    ) | gds["snippet"].str.contains(event_newsletter_pattern, case=False, na=False)

    event_newsletter_ids = set(gds[event_newsletter_mask]["message_id"])

    if len(event_newsletter_ids) == 0:
        pytest.skip("No event newsletters found in GDS")

    # Check predictions
    event_newsletter_predictions = predictions[predictions["message_id"].isin(event_newsletter_ids)]

    in_time_sensitive = len(
        event_newsletter_predictions[
            event_newsletter_predictions["predicted_importance"] == "time_sensitive"
        ]
    )

    noise_rate = in_time_sensitive / len(event_newsletter_predictions)

    print("\n📊 Event Newsletter Noise:")
    print(f"  Total event newsletters: {len(event_newsletter_predictions)}")
    print(f"  In time_sensitive: {in_time_sensitive}")
    print(f"  Noise rate: {noise_rate:.1%}")

    if in_time_sensitive > 0:
        print("\n⚠️  Event newsletters in time_sensitive (first 3):")
        noisy = event_newsletter_predictions[
            event_newsletter_predictions["predicted_importance"] == "time_sensitive"
        ]
        for _idx, row in noisy.head(3).iterrows():
            print(f"  - {row['subject'][:60]}")

    # MVP Quality Gate: ≤2%
    assert noise_rate <= 0.02, f"Event newsletter noise {noise_rate:.1%} > 2%"


def test_classification_success_rate(predictions):
    """
    Sanity check: Classification should succeed for >99% of emails

    This catches issues with classifier initialization, missing dependencies, etc.
    """
    errors = predictions["error"].notna().sum() if "error" in predictions.columns else 0
    success_rate = 1.0 - (errors / len(predictions))

    print("\n📊 Classification Success Rate:")
    print(f"  Total emails: {len(predictions)}")
    print(f"  Errors: {errors}")
    print(f"  Success rate: {success_rate:.1%}")

    assert success_rate >= 0.99, (
        f"Classification success rate {success_rate:.1%} < 99% ({errors} errors)"
    )


def test_print_summary_report(predictions):
    """
    Print a comprehensive summary report

    This always passes - it's just for visibility
    """
    print("\n" + "=" * 60)
    print("GDS BASELINE SUMMARY REPORT")
    print("=" * 60)

    # Confusion matrix for importance
    confusion = pd.crosstab(
        predictions["ground_truth_importance"], predictions["predicted_importance"], margins=True
    )

    print("\nImportance Confusion Matrix:")
    print(confusion)

    # Per-class metrics
    for importance in ["critical", "time_sensitive", "routine"]:
        predicted = predictions[predictions["predicted_importance"] == importance]
        actual = predictions[predictions["ground_truth_importance"] == importance]

        if len(actual) > 0:
            tp = len(predicted[predicted["ground_truth_importance"] == importance])
            fp = len(predicted[predicted["ground_truth_importance"] != importance])
            fn = len(actual[actual["predicted_importance"] != importance])

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            )

            print(f"\n{importance.upper()}:")
            print(f"  Precision: {precision:.1%}")
            print(f"  Recall: {recall:.1%}")
            print(f"  F1: {f1:.1%}")

    print("\n" + "=" * 60)

    # Always pass - this is just for reporting
    assert True


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v"])
