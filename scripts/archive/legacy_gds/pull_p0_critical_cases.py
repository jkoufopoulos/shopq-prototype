#!/usr/bin/env python3
"""
Pull P0 critical test cases from Gmail for golden dataset.

These are the most important guardrail validation cases:
- 40 OTPs/2FA codes (MUST be routine, test force_non_critical)
- 25 Fraud/phishing alerts (test force_critical)
- 25 Security alerts (test critical importance)

Total: 90 emails
"""

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def get_gmail_service():
    """Get authenticated Gmail API service."""
    creds = Credentials.from_authorized_user_file("credentials/token_gmail_api.json")
    return build("gmail", "v1", credentials=creds)


def get_existing_message_ids(dataset_path: Path) -> set[str]:
    """Get set of message IDs already in dataset."""
    existing_ids = set()
    if dataset_path.exists():
        with open(dataset_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(row["message_id"])
    return existing_ids


def classify_p0_email(subject: str, snippet: str) -> dict[str, str]:
    """
    Manually classify P0 critical cases based on patterns.
    These are deterministic guardrail cases.
    """
    subject_lower = subject.lower()
    snippet_lower = snippet.lower()
    combined = f"{subject_lower} {snippet_lower}"

    # OTP/2FA patterns (force_non_critical)
    otp_patterns = [
        r"\b\d{4,8}\b.*\b(code|otp|verification|2fa|authenticat)",
        r"\b(verification|security|login)\s+code\b",
        r"\byour\s+(one-time|temporary)\s+(code|password|pin)\b",
        r"\b2fa\b",
        r"\btwo.?factor\b",
    ]

    if any(re.search(pattern, combined) for pattern in otp_patterns):
        return {
            "email_type": "notification",
            "importance": "routine",
            "importance_reason": "P0_test_force_non_critical_otp",
            "category": "otp_2fa",
        }

    # Fraud/phishing patterns (force_critical)
    fraud_patterns = [
        r"\b(fraud|fraudulent)\s+(alert|activity|transaction)\b",
        r"\b(suspicious|unusual)\s+(activity|login|charge|transaction)\b",
        r"\baccount\s+(compromised|hacked|breach)\b",
        r"\bdata\s+breach\b",
        r"\bunauthorized\s+(access|login|transaction|charge)\b",
        r"\bphishing\s+(attempt|alert)\b",
    ]

    if any(re.search(pattern, combined) for pattern in fraud_patterns):
        return {
            "email_type": "notification",
            "importance": "critical",
            "importance_reason": "P0_test_force_critical_fraud",
            "category": "fraud_phishing",
        }

    # Security alert patterns (critical)
    security_patterns = [
        r"\bsecurity\s+(alert|warning|notification)\b",
        r"\bnew\s+(login|device|location|sign.?in)\b",
        r"\bpassword\s+(changed|reset|updated)\b",
        r"\baccount\s+(security|settings\s+changed)\b",
        r"\bsign.?in\s+from\s+new\b",
    ]

    if any(re.search(pattern, combined) for pattern in security_patterns):
        return {
            "email_type": "notification",
            "importance": "critical",
            "importance_reason": "P0_test_critical_security_alert",
            "category": "security_alert",
        }

    # Default: uncategorized
    return {
        "email_type": "notification",
        "importance": "routine",
        "importance_reason": "P0_uncategorized",
        "category": "other",
    }


def fetch_p0_emails(service, exclude_ids: set[str], targets: dict[str, int]) -> list[dict]:
    """
    Fetch P0 critical test case emails from Gmail.

    targets = {
        'otp_2fa': 40,
        'fraud_phishing': 25,
        'security_alert': 25
    }
    """
    emails = []
    seen_ids = set()
    category_counts = Counter()

    # Query patterns for each P0 category
    queries = {
        "otp_2fa": [
            "subject:(verification code)",
            "subject:(security code)",
            "subject:(2FA OR two-factor)",
            "subject:(OTP OR one-time)",
            "subject:(login code)",
            "subject:(authenticate)",
        ],
        "fraud_phishing": [
            "subject:(fraud alert)",
            "subject:(suspicious activity)",
            "subject:(unusual activity)",
            "subject:(account compromised)",
            "subject:(data breach)",
            "subject:(unauthorized)",
        ],
        "security_alert": [
            "subject:(security alert)",
            "subject:(new login)",
            "subject:(new device)",
            "subject:(password changed)",
            "subject:(sign-in from)",
            "subject:(account security)",
        ],
    }

    for category, target_count in targets.items():
        print(f"\n📬 Searching for {category} (target: {target_count})")

        for query in queries.get(category, []):
            if category_counts[category] >= target_count:
                break

            try:
                print(f"   Query: {query}")
                results = (
                    service.users().messages().list(userId="me", q=query, maxResults=100).execute()
                )

                messages = results.get("messages", [])
                print(f"   Found {len(messages)} messages")

                for msg_ref in messages:
                    if category_counts[category] >= target_count:
                        break

                    msg_id = msg_ref["id"]

                    # Skip if already in dataset or already seen
                    if msg_id in exclude_ids or msg_id in seen_ids:
                        continue

                    seen_ids.add(msg_id)

                    # Fetch full message
                    msg = (
                        service.users()
                        .messages()
                        .get(userId="me", id=msg_id, format="full")
                        .execute()
                    )

                    # Extract fields
                    payload = msg.get("payload", {})
                    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
                    snippet = msg.get("snippet", "")

                    subject = headers.get("Subject", "")
                    from_email = headers.get("From", "")
                    date = headers.get("Date", "")

                    # Classify using P0 patterns
                    classification = classify_p0_email(subject, snippet)

                    # Only keep if it matches the target category
                    if classification["category"] != category:
                        continue

                    category_counts[category] += 1

                    emails.append(
                        {
                            "message_id": msg_id,
                            "thread_id": msg.get("threadId", msg_id),
                            "from_email": from_email,
                            "subject": subject,
                            "snippet": snippet,
                            "received_date": date,
                            "email_type": classification["email_type"],
                            "type_confidence": "1.0",  # Manual classification
                            "attention": "",
                            "relationship": "",
                            "domains": "",
                            "domain_confidence": "",
                            "importance": classification["importance"],
                            "importance_reason": classification["importance_reason"],
                            "decider": "manual_p0_pattern",
                            "verifier_used": "",
                            "verifier_verdict": "",
                            "verifier_reason": "",
                            "entity_extracted": "",
                            "entity_type": "",
                            "entity_confidence": "",
                            "entity_details": "",
                            "in_digest": "",
                            "in_featured": "",
                            "in_orphaned": "",
                            "in_noise": "",
                            "noise_category": "",
                            "summary_line": "",
                            "summary_linked": "",
                            "session_id": "",
                            "timestamp": "",
                            "p0_category": category,
                        }
                    )

                    print(f"   ✅ Added {category} email: {subject[:60]}...")

            except Exception as e:
                print(f"   ⚠️  Error with query '{query}': {e}")
                continue

        print(f"   📊 {category}: {category_counts[category]}/{target_count}")

    return emails


def main():
    parser = argparse.ArgumentParser(description="Pull P0 critical test cases from Gmail")
    parser.add_argument(
        "--existing-dataset", type=Path, default=Path("tests/golden_set/golden_dataset.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("tests/golden_set/p0_critical_cases.csv")
    )
    parser.add_argument(
        "--otp-target", type=int, default=40, help="Target number of OTP/2FA emails"
    )
    parser.add_argument(
        "--fraud-target", type=int, default=25, help="Target number of fraud/phishing emails"
    )
    parser.add_argument(
        "--security-target", type=int, default=25, help="Target number of security alert emails"
    )

    args = parser.parse_args()

    print("🚀 Pulling P0 critical test cases from Gmail...")
    print(
        f"   Targets: OTP={args.otp_target}, "
        f"Fraud={args.fraud_target}, Security={args.security_target}"
    )
    print()

    # Get existing IDs
    print("📂 Loading existing dataset to avoid duplicates...")
    existing_ids = get_existing_message_ids(args.existing_dataset)
    print(f"   Found {len(existing_ids)} existing message IDs")
    print()

    # Authenticate
    print("🔐 Authenticating with Gmail API...")
    service = get_gmail_service()
    print("✅ Authenticated")

    # Fetch emails
    targets = {
        "otp_2fa": args.otp_target,
        "fraud_phishing": args.fraud_target,
        "security_alert": args.security_target,
    }

    emails = fetch_p0_emails(service, existing_ids, targets)

    if not emails:
        print("\n❌ No P0 emails fetched!")
        return

    print(f"\n✅ Fetched {len(emails)} P0 critical test case emails")

    # Show distribution
    category_dist = Counter(e["p0_category"] for e in emails)
    importance_dist = Counter(e["importance"] for e in emails)

    print("\n📊 Category distribution:")
    for cat, count in category_dist.items():
        target = targets[cat]
        pct = (count / target * 100) if target > 0 else 0
        print(f"   {cat}: {count}/{target} ({pct:.1f}%)")

    print("\n📊 Importance distribution:")
    for imp in ["routine", "time_sensitive", "critical"]:
        count = importance_dist.get(imp, 0)
        pct = (count / len(emails) * 100) if emails else 0
        print(f"   {imp}: {count} ({pct:.1f}%)")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        if emails:
            writer = csv.DictWriter(f, fieldnames=emails[0].keys())
            writer.writeheader()
            writer.writerows(emails)

    print(f"\n✅ Wrote {len(emails)} P0 emails to {args.output}")
    print("\n📝 Next step: Review these emails manually to verify classifications")


if __name__ == "__main__":
    main()
