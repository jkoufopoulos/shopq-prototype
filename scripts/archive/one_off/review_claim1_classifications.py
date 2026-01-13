#!/usr/bin/env python3
"""
Review Claim 1 Corrected Emails

Shows classification details for the 52 emails that were corrected
from type=notification → type=receipt in GDS.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shopq.classification.memory_classifier import MemoryClassifier

# Email IDs that were corrected
CORRECTED_IDS = {
    108,
    125,
    129,
    138,
    142,
    146,
    161,
    166,
    170,
    178,
    179,
    230,
    237,
    238,
    239,
    240,
    241,
    242,
    243,
    244,
    245,
    246,
    247,
    252,
    255,
    257,
    258,
    259,
    260,
    261,
    262,
    263,
    264,
    265,
    266,
    267,
    268,
    269,
    270,
    307,
    308,
    417,
    419,
    420,
    430,
    441,
    442,
    445,
    446,
    451,
    453,
    500,
}


def load_gds(csv_path: str) -> list[dict]:
    """Load GDS from CSV"""
    emails = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emails.append(row)
    return emails


def main():
    gds_path = "data/gds/gds-2.0-manually-reviewed.csv"
    emails = load_gds(gds_path)

    # Filter to corrected emails
    corrected_emails = [e for e in emails if int(e.get("email_id", 0)) in CORRECTED_IDS]
    corrected_emails.sort(key=lambda x: int(x.get("email_id", 0)))

    print(f"Reviewing {len(corrected_emails)} corrected emails\n")
    print("=" * 120)

    classifier = MemoryClassifier()

    for i, email in enumerate(corrected_emails, 1):
        email_id = email.get("email_id", "N/A")
        subject = email.get("subject", "")
        snippet = email.get("snippet", "")
        from_email = email.get("from_email", "")

        # Current GDS labels (after correction)
        gds_type = email.get("email_type", "")
        gds_importance = email.get("importance", "")
        gds_client_label = email.get("client_label", "")

        # Get classifier prediction
        try:
            result = classifier.classify(
                subject=subject,
                snippet=snippet,
                from_field=from_email,
            )

            pred_type = result.get("type", "")
            pred_importance = result.get("importance", "")
            pred_client_label = result.get("client_label", "")
            confidence = result.get("type_conf", 0.0)
            reason = result.get("reason", "")

        except Exception as e:
            pred_type = "ERROR"
            pred_importance = "ERROR"
            pred_client_label = "ERROR"
            confidence = 0.0
            reason = str(e)

        # Check if classifier agrees with corrected GDS
        type_match = "✅" if pred_type == gds_type else "❌"

        print(f"\n[{i}/{len(corrected_emails)}] EMAIL ID: {email_id}")
        print("=" * 120)
        print(f"From: {from_email}")
        print(f"Subject: {subject[:80]}")
        print(f"Snippet: {snippet[:200]}...")
        print("\nGDS Labels (corrected):")
        print(f"  type: {gds_type}")
        print(f"  importance: {gds_importance}")
        print(f"  client_label: {gds_client_label}")
        print("\nClassifier Prediction:")
        print(f"  type: {pred_type} {type_match} (confidence: {confidence:.2f})")
        print(f"  importance: {pred_importance}")
        print(f"  client_label: {pred_client_label}")
        print(f"  reason: {reason}")
        print("=" * 120)

        # Wait for user input to continue
        if i < len(corrected_emails):
            response = input("\nPress Enter for next email, 'q' to quit: ").strip().lower()
            if response == "q":
                print("\nExiting review...")
                break

    # Summary
    print(f"\n\nReview complete. Reviewed {i} of {len(corrected_emails)} emails.")


if __name__ == "__main__":
    main()
