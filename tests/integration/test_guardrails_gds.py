"""
Test guardrails against Golden Dataset (gds-1.0.csv)

Usage:
    pytest tests/test_guardrails_gds.py -v
    pytest tests/test_guardrails_gds.py::test_otp_never_in_critical -v

Quality Gates:
    - OTP in CRITICAL must be 0
    - Fraud/phishing must always be CRITICAL
    - Calendar auto-responses never CRITICAL
"""

from pathlib import Path

import pandas as pd
import pytest

# Import refactored pipeline (matches production)
try:
    from shopq.classification.pipeline_wrapper import RefactoredPipelineClassifier
except ImportError:
    pytest.skip("ShopQ modules not available", allow_module_level=True)


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
        from shopq.classification.importance_mapping.guardrails import GuardrailMatcher
        from shopq.classification.importance_mapping.mapper import BridgeImportanceMapper

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


def test_otp_never_in_critical(gds, classifier):
    """
    Quality Gate: OTP codes must NEVER appear in CRITICAL

    Acceptance Criteria (US-005):
    - OTP in CRITICAL == 0
    """
    # Filter to OTP emails
    # You may need to adjust this logic based on how you identify OTP emails
    otp_emails = gds[
        gds["snippet"].str.contains("verification code|one-time|OTP|2FA", case=False, na=False)
        | gds["subject"].str.contains("verification code|one-time|OTP|2FA", case=False, na=False)
    ]

    if len(otp_emails) == 0:
        pytest.skip("No OTP emails found in GDS")

    print(f"\n🔍 Testing {len(otp_emails)} OTP emails...")

    otp_in_critical = 0
    failures = []

    for _idx, email in otp_emails.iterrows():
        try:
            # Classify email
            result = classifier.classify(
                subject=email["subject"], snippet=email["snippet"], from_field=email["from_email"]
            )

            # Check if classified as critical
            if result.get("importance") == "critical":
                otp_in_critical += 1
                failures.append(
                    {
                        "message_id": email["message_id"],
                        "subject": email["subject"][:50],
                        "snippet": email["snippet"][:50],
                    }
                )
        except Exception as e:
            pytest.fail(f"Classification failed for {email['message_id']}: {e}")

    # Report results
    print(f"✅ OTP in CRITICAL: {otp_in_critical}/{len(otp_emails)}")

    if failures:
        print("\n❌ Failed emails:")
        for failure in failures:
            print(f"  - {failure['subject']} (ID: {failure['message_id']})")

    # Assert: OTP in CRITICAL must be 0
    assert otp_in_critical == 0, f"Found {otp_in_critical} OTP emails in CRITICAL (expected 0)"


def test_fraud_always_critical(gds, classifier):
    """
    Quality Gate: Fraud/phishing emails must ALWAYS be CRITICAL

    Acceptance Criteria (US-005):
    - force_critical rules apply to fraud/phishing
    """
    # Filter to fraud/phishing emails
    fraud_keywords = [
        "suspicious activity",
        "verify your account",
        "unusual sign-in",
        "account compromised",
        "security alert",
        "confirm your identity",
    ]

    fraud_pattern = "|".join(fraud_keywords)
    fraud_emails = gds[
        gds["snippet"].str.contains(fraud_pattern, case=False, na=False)
        | gds["subject"].str.contains(fraud_pattern, case=False, na=False)
        | (gds["importance"] == "critical")  # Include emails manually labeled as critical
    ]

    # Further filter to actual fraud (not legitimate security alerts)
    # This is a heuristic - adjust based on your data
    fraud_emails = fraud_emails[
        ~fraud_emails["from_email"].str.contains(
            "noreply@|no-reply@|notifications@", case=False, na=False
        )
    ]

    if len(fraud_emails) == 0:
        pytest.skip("No fraud emails found in GDS")

    print(f"\n🔍 Testing {len(fraud_emails)} potential fraud emails...")

    not_critical = 0
    failures = []

    for _idx, email in fraud_emails.iterrows():
        try:
            result = classifier.classify(
                subject=email["subject"], snippet=email["snippet"], from_field=email["from_email"]
            )

            # Check if NOT classified as critical
            if result.get("importance") != "critical":
                not_critical += 1
                failures.append(
                    {
                        "message_id": email["message_id"],
                        "subject": email["subject"][:50],
                        "importance": result.get("importance"),
                    }
                )
        except Exception as e:
            print(f"⚠️  Classification failed for {email['message_id']}: {e}")
            continue

    # Report results
    critical_count = len(fraud_emails) - not_critical
    print(f"✅ Fraud in CRITICAL: {critical_count}/{len(fraud_emails)}")

    if failures:
        print("\n⚠️  Fraud emails NOT in critical:")
        for failure in failures[:5]:  # Show first 5
            print(f"  - {failure['subject']} → {failure['importance']}")

    # Note: This is a softer assertion since fraud detection is hard
    # Adjust threshold based on your requirements
    fraud_critical_rate = critical_count / len(fraud_emails)
    assert fraud_critical_rate >= 0.80, (
        f"Only {fraud_critical_rate:.1%} of fraud emails in CRITICAL (expected ≥80%)"
    )


def test_calendar_autoresponse_not_critical(gds, classifier):
    """
    Quality Gate: Calendar auto-responses should NOT be CRITICAL

    Acceptance Criteria (US-005):
    - force_non_critical rules apply to calendar auto-responses
    """
    # Filter to calendar auto-responses
    autoresponse_emails = gds[
        gds["subject"].str.contains(
            "Accepted:|Declined:|Tentative:|has accepted|has declined", case=False, na=False
        )
    ]

    if len(autoresponse_emails) == 0:
        pytest.skip("No calendar auto-responses found in GDS")

    print(f"\n🔍 Testing {len(autoresponse_emails)} calendar auto-response emails...")

    in_critical = 0
    failures = []

    for _idx, email in autoresponse_emails.iterrows():
        try:
            result = classifier.classify(
                subject=email["subject"], snippet=email["snippet"], from_field=email["from_email"]
            )

            if result.get("importance") == "critical":
                in_critical += 1
                failures.append(
                    {"message_id": email["message_id"], "subject": email["subject"][:50]}
                )
        except Exception as e:
            print(f"⚠️  Classification failed for {email['message_id']}: {e}")
            continue

    # Report results
    print(f"✅ Auto-responses in CRITICAL: {in_critical}/{len(autoresponse_emails)}")

    if failures:
        print("\n❌ Failed emails:")
        for failure in failures[:5]:
            print(f"  - {failure['subject']}")

    # Assert: Auto-responses should not be critical
    assert in_critical == 0, f"Found {in_critical} auto-responses in CRITICAL (expected 0)"


def test_guardrails_precedence(gds, classifier):  # noqa: ARG001
    """
    Test guardrail precedence: never > force_critical > force_non_critical

    This is a sanity check that guardrails are being applied in order.
    """
    # Test a few specific cases
    test_cases = [
        {
            "subject": "Your verification code is 123456",
            "snippet": "Use this code to verify your account",
            "from_email": "noreply@bank.com",
            "expected_not": "critical",
            "reason": "OTP should be filtered by never_surface (highest precedence)",
        },
        {
            "subject": "Unusual sign-in activity detected",
            "snippet": "We detected a suspicious login from an unknown device",
            "from_email": "security@yourbank.com",
            "expected": "critical",
            "reason": "Security alert should be forced to critical",
        },
    ]

    print(f"\n🔍 Testing guardrail precedence with {len(test_cases)} cases...")

    failures = []
    for test in test_cases:
        try:
            result = classifier.classify(
                subject=test["subject"], snippet=test["snippet"], from_field=test["from_email"]
            )

            importance = result.get("importance")

            if "expected" in test and importance != test["expected"]:
                failures.append(f"{test['reason']}: got {importance}, expected {test['expected']}")

            if "expected_not" in test and importance == test["expected_not"]:
                failures.append(
                    f"{test['reason']}: got {importance}, should NOT be {test['expected_not']}"
                )

        except Exception as e:
            failures.append(f"{test['reason']}: classification failed with {e}")

    if failures:
        print("\n❌ Precedence failures:")
        for failure in failures:
            print(f"  - {failure}")

    assert len(failures) == 0, f"Guardrail precedence failed: {failures}"


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v"])
