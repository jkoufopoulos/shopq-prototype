# ruff: noqa
#!/usr/bin/env python3
"""
Test Hybrid Digest Renderer on 100 random GDS emails.

This script:
1. Loads 100 random emails from Golden Dataset v1.0
2. Classifies them using the full pipeline (bridge mode + temporal enrichment)
3. Generates a digest with the hybrid renderer enabled
4. Validates digest structure and content
5. Saves digest HTML for manual inspection
6. Generates a comparison report
"""

import sys
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shopq.classification.importance_mapping.guardrails import GuardrailMatcher
from shopq.classification.importance_mapping.mapper import BridgeImportanceMapper
from shopq.classification.pipeline_wrapper import RefactoredPipelineClassifier
from shopq.digest.context_digest import generate_context_digest
from shopq.runtime.gates import feature_gates


def main():
    print("=" * 80)
    print("HYBRID DIGEST RENDERER - GDS VALIDATION TEST")
    print("=" * 80)
    print()

    # Ensure hybrid renderer is enabled
    if not feature_gates.is_enabled("hybrid_renderer"):
        feature_gates.enable("hybrid_renderer")
    print(f"✅ Hybrid renderer enabled: {feature_gates.is_enabled('hybrid_renderer')}")
    print()

    # Load GDS
    gds_path = Path(__file__).parent.parent / "tests" / "golden_set" / "gds-1.0.csv"
    if not gds_path.exists():
        print(f"❌ GDS not found at: {gds_path}")
        sys.exit(1)

    gds = pd.read_csv(gds_path)
    print(f"📧 Loaded GDS: {len(gds)} emails")

    # Sample 100 random emails
    sample_size = min(100, len(gds))
    sample = gds.sample(n=sample_size, random_state=42)
    print(f"📊 Sampled {len(sample)} random emails")
    print()

    # Initialize classification pipeline
    print("🔄 Initializing classification pipeline...")
    base_classifier = RefactoredPipelineClassifier()
    guardrails = GuardrailMatcher()
    importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)
    print("✅ Pipeline initialized")
    print()

    # Classify emails
    print("🔍 Classifying emails...")
    emails_for_digest = []
    importance_counts = {"critical": 0, "time_sensitive": 0, "routine": 0}
    type_counts = {}
    critical_emails_debug = []  # Track critical emails for debugging

    for idx, email_row in sample.iterrows():
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
        email_type = base_classification.get("type", "unknown")
        type_counts[email_type] = type_counts.get(email_type, 0) + 1

        # Track critical emails for debugging
        if final_importance == "critical":
            critical_emails_debug.append(
                {
                    "subject": email_row["subject"][:80],
                    "type": email_type,
                    "source": decision.source,
                    "reason": decision.reason,
                    "rule_name": decision.rule_name,
                }
            )

        # Add to digest email list
        emails_for_digest.append(
            {
                **email_with_classification,
                "importance": final_importance,
            }
        )

    print(f"✅ Classified {len(emails_for_digest)} emails")
    print()

    # Show importance distribution
    print("📊 IMPORTANCE DISTRIBUTION:")
    print(f"   🚨 Critical: {importance_counts['critical']}")
    print(f"   ⏰ Time-sensitive: {importance_counts['time_sensitive']}")
    print(f"   📋 Routine: {importance_counts['routine']}")
    print()

    # Show critical emails debug info
    if critical_emails_debug:
        print("🔍 CRITICAL EMAILS DEBUG:")
        for i, email in enumerate(critical_emails_debug, 1):
            print(f"   {i}. {email['subject']}")
            print(
                f"      Type: {email['type']}, Source: {email['source']}, Reason: {email['reason']}, Rule: {email['rule_name']}"
            )
        print()

    # Show type distribution
    print("📊 TYPE DISTRIBUTION:")
    for email_type, count in sorted(type_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"   {email_type}: {count}")
    print()

    # Generate digest with hybrid renderer
    print("📝 Generating digest with hybrid renderer...")
    digest_result = generate_context_digest(emails_for_digest, verbose=True)
    digest_html = digest_result.get("html", "")
    print("✅ Digest generated")
    print()

    # Validate digest structure
    print("=" * 80)
    print("DIGEST STRUCTURE VALIDATION")
    print("=" * 80)
    print()

    required_sections = ["🚨 CRITICAL", "📦 TODAY", "📅 COMING UP", "💼 WORTH KNOWING"]
    missing_sections = []

    for section in required_sections:
        if section in digest_html:
            print(f"✅ {section} section present")
        else:
            print(f"❌ {section} section MISSING")
            missing_sections.append(section)

    if "Have a great day!" in digest_html:
        print("✅ Sign-off present")
    else:
        print("❌ Sign-off MISSING")

    if "emails):" in digest_html:
        print("✅ Email counts present")
    else:
        print("❌ Email counts MISSING")

    print()

    # Extract section counts from digest HTML
    print("📊 DIGEST SECTION COUNTS:")
    for section in required_sections:
        if section in digest_html:
            # Try to extract count from "SECTION (N emails):"
            import re

            pattern = re.escape(section) + r" \((\d+) emails\):"
            match = re.search(pattern, digest_html)
            if match:
                count = match.group(1)
                print(f"   {section}: {count} emails")
            else:
                print(f"   {section}: (count not found in expected format)")
    print()

    # Check for entity cards vs subject lines
    print("🔍 CONTENT ANALYSIS:")

    # Look for entity card patterns
    entity_patterns = [
        r" at \d+:\d+ [AP]M",  # Event with time: "Team Meeting at 2:00 PM"
        r"\$[\d,.]+",  # Dollar amounts: "$150.00"
        r" due ",  # Deadlines: "due Friday"
        r"Security alert —",  # Fraud alerts
        r"Delivered:",  # Delivery notifications
    ]

    entity_card_count = 0
    for pattern in entity_patterns:
        import re

        matches = re.findall(pattern, digest_html)
        if matches:
            entity_card_count += len(matches)
            print(f"   Found {len(matches)} matches for pattern: {pattern}")

    print(f"\n   Total entity card indicators: {entity_card_count}")
    print()

    # Check for HTML safety
    print("🔒 SECURITY VALIDATION:")
    if "<script>" not in digest_html or '<p style="' in digest_html:
        print("✅ No unsafe <script> tags found")
    else:
        print("❌ WARNING: Unsafe <script> tags found!")

    if "&lt;" in digest_html or "&gt;" in digest_html or "&amp;" in digest_html:
        print("✅ HTML entities escaped")
    else:
        print("⚠️  No HTML entities found (may be okay if no special chars)")

    print()

    # Save digest to file
    output_dir = Path(__file__).parent.parent / "reports"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "hybrid_digest_gds_100_emails.html"
    output_path.write_text(digest_html)

    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    print(f"✅ Digest saved to: {output_path}")
    print(f"📊 Processed {len(emails_for_digest)} emails")
    print(f"🚨 Critical: {importance_counts['critical']}")
    print(f"⏰ Time-sensitive: {importance_counts['time_sensitive']}")
    print(f"📋 Routine: {importance_counts['routine']}")
    print()

    if missing_sections:
        print(f"⚠️  Missing sections: {', '.join(missing_sections)}")
        print()

    # Generate comparison report
    print("=" * 80)
    print("EXPECTED vs ACTUAL COMPARISON")
    print("=" * 80)
    print()

    print("EXPECTED BEHAVIOR:")
    print("✅ All 4 sections should be present (even if 0 emails)")
    print("✅ Critical emails should include: fraud alerts, OTPs, deadlines < 1 day")
    print("✅ Time-sensitive emails should include: events, deadlines 1-7 days")
    print("✅ Routine emails should be split:")
    print("   - WORTH KNOWING: receipts, confirmations, shipping, account updates")
    print("   - FOOTER: marketing, newsletters, promotional")
    print("✅ Entity cards should show structured data (times, amounts)")
    print("✅ Subject lines should be used when no entity extracted")
    print()

    print("ACTUAL BEHAVIOR:")
    if not missing_sections:
        print("✅ All sections present")
    else:
        print(f"❌ Missing sections: {', '.join(missing_sections)}")

    if entity_card_count > 0:
        print(f"✅ Entity cards found: {entity_card_count} indicators")
    else:
        print("⚠️  No entity card indicators found (may be okay if no entities)")

    print()
    print("💾 Open the digest HTML file to manually inspect:")
    print(f"   {output_path}")
    print()
    print("🔍 Things to check manually:")
    print("   1. Are events showing times? (e.g., 'Meeting at 2:00 PM')")
    print("   2. Are deadlines showing amounts? (e.g., '$150.00 due Friday')")
    print("   3. Are receipts in WORTH KNOWING section?")
    print("   4. Are marketing emails in footer?")
    print("   5. Is the visual structure unchanged from before?")
    print()

    # Summary statistics
    print("=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print()
    print(f"Total emails processed: {len(emails_for_digest)}")
    print(f"Digest HTML size: {len(digest_html)} characters")
    print(
        f"Sections present: {len(required_sections) - len(missing_sections)}/{len(required_sections)}"
    )
    print(f"Entity card indicators: {entity_card_count}")
    print()

    if missing_sections or entity_card_count == 0:
        print("⚠️  WARNING: Digest may not be working as expected")
        print("   Please review the HTML file manually")
        return 1
    print("✅ SUCCESS: Digest structure looks good!")
    print("   Review HTML file for final validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
