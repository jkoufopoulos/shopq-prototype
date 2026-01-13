"""
Test extension → backend → Gmail label flow against GDS.

This simulates what the extension does:
1. Load GDS emails
2. Call backend API (like extension does)
3. Map classifications to Gmail labels (like extension mapper.js does)
4. Compare to GDS ground truth
"""

import sys
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.classification.importance_mapping.guardrails import GuardrailMatcher
from mailq.classification.importance_mapping.mapper import BridgeImportanceMapper
from mailq.classification.pipeline_wrapper import RefactoredPipelineClassifier

# Gmail label mapping (matches extension/modules/mapper.js)
TYPE_TO_LABEL = {
    "newsletter": "MailQ/Newsletters",
    "notification": "MailQ/Notifications",
    "receipt": "MailQ/Receipts",
    "event": "MailQ/Events",
    "promotion": "MailQ/Promotions",
    "message": "MailQ/Messages",
    "update": "MailQ/Notifications",  # Backend uses "update", extension treats as notification
}

DOMAIN_TO_LABEL = {
    "finance": "MailQ/Finance",
    "shopping": "MailQ/Shopping",
    "professional": "MailQ/Work",
    "personal": "MailQ/Personal",
}


def map_classification_to_labels(classification: dict) -> list[str]:
    """
    Map backend classification to Gmail labels (simulates extension mapper.js).

    Args:
        classification: Backend classification dict

    Returns:
        List of Gmail label names
    """
    labels = []

    # Type → Label
    email_type = classification.get("type")
    if email_type in TYPE_TO_LABEL:
        labels.append(TYPE_TO_LABEL[email_type])

    # Domains → Labels
    domains = classification.get("domains", [])
    for domain in domains:
        if domain in DOMAIN_TO_LABEL:
            labels.append(DOMAIN_TO_LABEL[domain])

    # Importance → Action-Required (use importance, not attention, to respect guardrails)
    if classification.get("importance") == "critical":
        labels.append("MailQ/Action-Required")

    # Fallback
    if not labels:
        labels.append("MailQ/Review-Later")

    return labels


def main():
    """Test extension → backend → Gmail label flow."""
    print("=" * 60)
    print("EXTENSION → BACKEND → GMAIL LABEL INTEGRATION TEST")
    print("=" * 60)
    print()

    # Load GDS
    gds_path = Path(__file__).parent / "golden_set" / "gds-1.0.csv"
    gds = pd.read_csv(gds_path)
    print(f"✅ Loaded {len(gds)} emails from GDS\n")

    # Initialize backend classifier + importance mapper (same flow as extension)
    base_classifier = RefactoredPipelineClassifier()
    guardrails = GuardrailMatcher()
    importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)
    print("✅ Initialized backend classifier + importance mapper\n")

    # Classify all emails
    print("🔄 Classifying emails via backend API...\n")
    results = []

    for _, email in gds.iterrows():
        # Call backend classifier (simulates extension API call)
        base_classification = base_classifier.classify(
            subject=email["subject"],
            snippet=email["snippet"],
            from_field=email["from_email"],
        )

        # Apply importance mapping (simulates backend importance mapper)
        # Merge email data with classification for mapper
        email_with_classification = {
            "subject": email["subject"],
            "snippet": email["snippet"],
            "from": email["from_email"],
            **base_classification,  # includes type, attention, domains, decider
        }

        try:
            importance_decision = importance_mapper.map_email(email_with_classification)
            classification = {
                **base_classification,
                "importance": importance_decision.importance or "routine",
                "importance_reason": importance_decision.reason,
                "importance_source": importance_decision.source,
            }
        except Exception as e:
            classification = {
                **base_classification,
                "importance": "routine",
                "importance_reason": f"mapper_error: {e}",
                "importance_source": "error",
            }

        # Map to Gmail labels (simulates extension mapper.js)
        gmail_labels = map_classification_to_labels(classification)

        results.append(
            {
                "message_id": email["message_id"],
                "subject": email["subject"],
                "snippet": email["snippet"],
                "from_email": email["from_email"],
                "ground_truth_importance": email["importance"],
                "ground_truth_type": email["email_type"],
                "predicted_importance": classification.get("importance", "routine"),
                "predicted_type": classification.get("type", "update"),
                "gmail_labels": gmail_labels,
            }
        )

    results_df = pd.DataFrame(results)
    print(f"✅ Classified {len(results_df)} emails\n")

    # Analyze Gmail label accuracy
    print("=" * 60)
    print("GMAIL LABEL ANALYSIS")
    print("=" * 60)
    print()

    # Check if critical emails get MailQ/Action-Required label
    critical_emails = results_df[results_df["ground_truth_importance"] == "critical"]
    critical_with_action_required = critical_emails[
        critical_emails["gmail_labels"].apply(lambda labels: "MailQ/Action-Required" in labels)
    ]

    critical_recall = (
        len(critical_with_action_required) / len(critical_emails) if len(critical_emails) > 0 else 0
    )

    print("📊 Critical → MailQ/Action-Required:")
    print(f"   Total critical emails: {len(critical_emails)}")
    print(f"   With Action-Required label: {len(critical_with_action_required)}")
    print(f"   Recall: {critical_recall:.1%}")
    print()

    if critical_recall < 0.85:
        print("⚠️  Missing Action-Required labels (first 3):")
        missing = critical_emails[
            ~critical_emails["gmail_labels"].apply(lambda labels: "MailQ/Action-Required" in labels)
        ]
        for _, row in missing.head(3).iterrows():
            print(f"   - {row['subject'][:60]}")
            print(f"     Labels: {', '.join(row['gmail_labels'])}")
        print()

    # Check if event newsletters get MailQ/Events label (should NOT)
    event_newsletter_pattern = "lineup|festival|upcoming events"
    event_newsletters = results_df[
        (
            results_df["subject"].str.contains(event_newsletter_pattern, case=False, na=False)
            | results_df["snippet"].str.contains(event_newsletter_pattern, case=False, na=False)
        )
        & (results_df["ground_truth_type"] == "promotion")
    ]

    event_newsletters_with_events_label = event_newsletters[
        event_newsletters["gmail_labels"].apply(lambda labels: "MailQ/Events" in labels)
    ]

    event_newsletter_noise = (
        len(event_newsletters_with_events_label) / len(event_newsletters)
        if len(event_newsletters) > 0
        else 0
    )

    print("📊 Event Newsletters → MailQ/Events (should be 0%):")
    print(f"   Total event newsletters: {len(event_newsletters)}")
    print(f"   With MailQ/Events label: {len(event_newsletters_with_events_label)}")
    print(f"   Noise rate: {event_newsletter_noise:.1%}")
    print()

    if event_newsletter_noise > 0.02:
        print("⚠️  Event newsletters incorrectly labeled (first 3):")
        for _, row in event_newsletters_with_events_label.head(3).iterrows():
            print(f"   - {row['subject'][:60]}")
            print(f"     Labels: {', '.join(row['gmail_labels'])}")
        print()

    # Label distribution
    print("📊 Gmail Label Distribution:")
    all_labels = [label for labels in results_df["gmail_labels"] for label in labels]
    label_counts = pd.Series(all_labels).value_counts()

    for label, count in label_counts.head(10).items():
        print(f"   {label}: {count} ({count / len(results_df) * 100:.1f}%)")
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()

    status_emoji = "✅" if critical_recall >= 0.85 and event_newsletter_noise <= 0.02 else "⚠️"
    print(f"{status_emoji} Critical → Action-Required: {critical_recall:.1%} (target ≥85%)")
    print(
        f"{'✅' if event_newsletter_noise <= 0.02 else '⚠️'} Event Newsletter Noise: {event_newsletter_noise:.1%} (target ≤2%)"
    )
    print()

    # Save detailed results
    output_path = Path(__file__).parent / "extension_backend_integration_results.csv"
    results_df.to_csv(output_path, index=False)
    print(f"💾 Saved detailed results to: {output_path.name}")


if __name__ == "__main__":
    main()
