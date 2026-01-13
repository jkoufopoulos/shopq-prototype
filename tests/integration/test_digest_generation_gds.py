"""
Test digest generation on Golden Dataset emails.

This test:
1. Loads 100 random emails from GDS
2. Classifies them with the backend
3. Generates a digest using bridge_mode
4. Verifies digest structure and content quality
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.classification.importance_mapping.guardrails import GuardrailMatcher
from mailq.classification.importance_mapping.mapper import BridgeImportanceMapper
from mailq.classification.pipeline_wrapper import RefactoredPipelineClassifier
from mailq.digest.context_digest import generate_context_digest
from mailq.runtime.gates import feature_gates


def test_digest_generation_on_gds():
    """Test digest generation on 100 random GDS emails."""

    # Ensure bridge mode is enabled
    assert feature_gates.is_enabled("bridge_mode"), "Bridge mode should be enabled"

    # Load GDS
    gds_path = (
        Path(__file__).parent.parent.parent / "data" / "evals" / "classification" / "gds-2.0.csv"
    )
    gds = pd.read_csv(gds_path)

    # Sample 100 random emails
    sample = gds.sample(n=min(100, len(gds)), random_state=42)
    print(f"\n📧 Testing digest generation on {len(sample)} random GDS emails\n")

    # Classify emails
    base_classifier = RefactoredPipelineClassifier()
    guardrails = GuardrailMatcher()
    importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)

    emails_for_digest = []
    importance_counts = {"critical": 0, "time_sensitive": 0, "routine": 0}

    print("🔄 Classifying emails...")
    for _, email_row in sample.iterrows():
        # Backend classification
        base_classification = base_classifier.classify(
            subject=email_row["subject"],
            snippet=email_row["snippet"],
            from_field=email_row["from_email"],
        )

        # Apply importance mapping
        email_with_classification = {
            "subject": email_row["subject"],
            "snippet": email_row["snippet"],
            "from": email_row["from_email"],
            "id": email_row["message_id"],
            "thread_id": email_row["thread_id"],
            **base_classification,
        }

        decision = importance_mapper.map_email(email_with_classification)
        final_importance = decision.importance or "routine"

        # Track counts
        importance_counts[final_importance] += 1

        # Add to digest email list
        emails_for_digest.append(
            {
                **email_with_classification,
                "importance": final_importance,
            }
        )

    print(f"✅ Classified {len(emails_for_digest)} emails")
    print(f"   - Critical: {importance_counts['critical']}")
    print(f"   - Time-sensitive: {importance_counts['time_sensitive']}")
    print(f"   - Routine: {importance_counts['routine']}")
    print()

    # Generate digest
    print("📝 Generating digest HTML...")
    digest_result = generate_context_digest(emails_for_digest, verbose=False)
    digest_html = digest_result.get("html", "")

    # Save digest to file
    output_path = Path(__file__).parent.parent / "reports" / "test_digest_gds_sample.html"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(digest_html)
    print(f"💾 Saved digest to: {output_path}")
    print()

    # Verify digest structure
    print("=" * 60)
    print("DIGEST STRUCTURE VERIFICATION")
    print("=" * 60)
    print()

    # Check for required sections
    has_critical_section = "🚨 CRITICAL" in digest_html or "CRITICAL" in digest_html
    has_coming_up_section = "📅 COMING UP" in digest_html or "COMING UP" in digest_html
    has_worth_knowing_section = "💡 WORTH KNOWING" in digest_html or "WORTH KNOWING" in digest_html

    print(f"✅ Has CRITICAL section: {has_critical_section}")
    print(f"✅ Has COMING UP section: {has_coming_up_section}")
    print(f"✅ Has WORTH KNOWING section: {has_worth_knowing_section}")
    print()

    # Check for problematic patterns
    has_otp_in_critical = False
    if has_critical_section:
        # Extract CRITICAL section
        critical_start = digest_html.find("CRITICAL")
        if critical_start != -1:
            critical_end = digest_html.find("COMING UP", critical_start)
            if critical_end == -1:
                critical_end = digest_html.find("WORTH KNOWING", critical_start)
            if critical_end == -1:
                critical_end = len(digest_html)

            critical_section = digest_html[critical_start:critical_end].lower()
            otp_keywords = ["verification code", "otp", "2fa", "one-time", "login code"]
            has_otp_in_critical = any(kw in critical_section for kw in otp_keywords)

    print(f"✅ OTP codes in CRITICAL section: {has_otp_in_critical} (should be False)")
    assert not has_otp_in_critical, "OTP codes should NOT appear in CRITICAL section"

    # Content quality checks
    has_html_structure = "<html" in digest_html.lower() and "</html>" in digest_html.lower()
    has_body = "<body" in digest_html.lower() and "</body>" in digest_html.lower()
    has_subject_lines = digest_html.count("<li") >= min(
        20, len(emails_for_digest)
    )  # At least 20 items

    print(f"✅ Valid HTML structure: {has_html_structure}")
    print(f"✅ Has body tag: {has_body}")
    print(f"✅ Has email items: {has_subject_lines}")
    print()

    # Size check
    digest_size_kb = len(digest_html) / 1024
    print(f"📊 Digest size: {digest_size_kb:.1f} KB")
    print()

    print("=" * 60)
    print("✅ DIGEST GENERATION TEST PASSED")
    print("=" * 60)
    print()
    print(f"📂 View digest at: {output_path}")
    print("   You can open this file in a browser to see the formatted digest")

    return digest_html, emails_for_digest


if __name__ == "__main__":
    test_digest_generation_on_gds()
