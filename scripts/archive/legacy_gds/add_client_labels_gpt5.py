#!/usr/bin/env python3
"""
Add client_label field to existing GDS using GPT-5-mini

This script ONLY adds the client_label field, preserving all existing labels.

Usage:
    uv run python scripts/add_client_labels_gpt5.py \
        --input tests/golden_set/gds-2.0-gpt5-prelabeled.csv \
        --output tests/golden_set/gds-2.0-with-client-labels.csv
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load environment
script_dir = Path(__file__).parent
project_root = script_dir.parent
env_file = project_root / ".env"

if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    print("❌ openai package not installed. Run: uv pip install openai")
    sys.exit(1)


CLIENT_LABEL_PROMPT = """You are labeling emails for MailQ, a Gmail assistant.

Your task: Assign ONE client_label that determines what the user sees in Gmail.

CLIENT LABELS (choose from these 4 options):

1. ACTION-REQUIRED: Real-world consequences if ignored
   Critical Test: "If I ignore this email, is there a REAL-WORLD consequence for me?"
   Think: money, access, commitments, important logistics

   YES - Action Required:
   - Bills that need to be paid (and are not auto-paid)
   - Important RSVPs or confirmations with real consequences
   - Account or security issues requiring action
   - Trials or subscriptions that will start billing if ignored
   - Service disruptions or access issues

   NO - Not Action Required:
   - Ordinary marketing offers or generic sales (even if they "expire")
   - Informational updates with no action needed
   - OTPs/verification codes (critical at arrival, but one-time use)

2. RECEIPTS: Purchase confirmations and payment records
   Examples: Order confirmations, invoices, payment receipts, shipping updates
   Mental Model: "Archive for records, rarely re-read"
   Typically: email_type = receipt

3. MESSAGES: Person-to-person or small-group communication
   Examples: Real humans emailing each other (friends, colleagues, recruiters)
   NOT: Bulk automated systems or newsletters
   Mental Model: "Human conversation, deserves attention"
   Typically: email_type = message

4. EVERYTHING-ELSE: Low-value automated emails
   Examples:
   - OTP / verification codes (one-time use, quickly expire)
   - Most promotions and marketing campaigns
   - Routine notifications and info-only emails
   - Generic updates and announcements
   - Newsletters (NOT action-required, just content)

SPECIAL RULES:
- OTP / one-time verification codes → ALWAYS "everything-else"
  (They are critical at arrival but should NOT live in 'action-required')

- Bills / required payments → "action-required" when ignoring causes real consequences
  (late fees, service disruption, etc.)

- Receipts AFTER successful payment → "receipts"

- Event invites:
  - If asking to RSVP/confirm AND missing it matters → "action-required"
  - If just FYI or informational reminder → "everything-else"

- Newsletters/content → "everything-else" (NOT digest - that's reserved for MailQ's own summaries)

IMPORTANT: "digest" is RESERVED for MailQ's own summary emails ONLY.
Do NOT assign "digest" to regular emails. Choose from: action-required, receipts, messages, everything-else.

Email to classify:
---
From: {from_email}
Subject: {subject}
Snippet: {snippet}
Current Type: {email_type}
Current Importance: {importance}
---

Respond with valid JSON only:
{{
  "client_label": "one of: action-required, receipts, messages, everything-else",
  "confidence": 0.95,
  "reasoning": "Brief explanation (1-2 sentences)"
}}"""


def classify_client_label(client: OpenAI, email: dict) -> dict:
    """Classify single email's client_label using GPT-5-mini"""

    prompt = CLIENT_LABEL_PROMPT.format(
        from_email=email["from_email"],
        subject=email["subject"],
        snippet=email.get("snippet", "")[:300],
        email_type=email.get("email_type", "notification"),
        importance=email.get("importance", "routine"),
    )

    try:
        json_prompt = (
            prompt
            + "\n\nYou MUST respond with ONLY valid JSON. No explanations, no markdown, just the JSON object."
        )

        start_time = time.time()
        response = client.responses.create(
            model="gpt-5-mini",
            input=json_prompt,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            timeout=30.0,
        )
        elapsed = time.time() - start_time

        # Extract output text
        output_text = response.output_text.strip()

        # Parse JSON from output
        if output_text.startswith("```"):
            output_text = output_text.split("```")[1]
            if output_text.startswith("json"):
                output_text = output_text[4:]
            output_text = output_text.strip()
        elif "{" in output_text:
            start = output_text.find("{")
            end = output_text.rfind("}") + 1
            output_text = output_text[start:end]

        result = json.loads(output_text)

        # Validate (digest is reserved for MailQ's own emails)
        valid_labels = {"action-required", "receipts", "messages", "everything-else"}
        if result["client_label"] not in valid_labels:
            raise ValueError(f"Invalid client_label: {result['client_label']}")

        return result

    except Exception as e:
        print(f"   ⚠️  Error classifying: {e}")
        return {
            "client_label": "everything-else",
            "confidence": 0.0,
            "reasoning": f"Error: {str(e)}",
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Add client_label field with GPT-5-mini")
    parser.add_argument("--input", required=True, help="Input GDS CSV")
    parser.add_argument("--output", required=True, help="Output CSV with client_label")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in .env file")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    print("🤖 Adding client_label field with GPT-5-mini...")
    print(f"📖 Reading {input_path}...\n")

    # Read GDS
    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    # Ensure client_label field exists
    for email in emails:
        if "client_label" not in email:
            email["client_label"] = ""

    # Filter to emails without client_label
    to_classify = [e for e in emails if not e.get("client_label")]

    print(f"   Total emails: {len(emails)}")
    print(f"   Already have client_label: {len(emails) - len(to_classify)}")
    print(f"   To classify: {len(to_classify)}\n")

    if len(to_classify) == 0:
        print("✅ All emails already have client_label!")
        sys.exit(0)

    # Classify each email
    start_overall = time.time()
    for i, email in enumerate(to_classify, 1):
        print(f"[{i}/{len(to_classify)}] {email['subject'][:50]}...", end=" ", flush=True)

        classification = classify_client_label(client, email)

        # Update ONLY client_label field
        email["client_label"] = classification["client_label"]

        # Progress indicator
        print(f"✓ ({classification['client_label']})", flush=True)

        # Show estimated completion every 10 emails
        if i % 10 == 0:
            elapsed = time.time() - start_overall
            avg_per_email = elapsed / i
            remaining = (len(to_classify) - i) * avg_per_email
            print(
                f"   ⏱️  Avg: {avg_per_email:.1f}s/email | Est. remaining: {remaining / 60:.1f}min\n",
                flush=True,
            )

    # Write output CSV
    print(f"\n💾 Writing results to {output_path}...")

    # Ensure fieldnames include client_label
    fieldnames = list(emails[0].keys())
    if "client_label" not in fieldnames:
        # Insert client_label after importance
        if "importance" in fieldnames:
            idx = fieldnames.index("importance") + 1
            fieldnames.insert(idx, "client_label")
        else:
            fieldnames.append("client_label")

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emails)

    print("\n✅ Client labeling complete!")
    print(f"   Classified {len(to_classify)} emails")
    print(f"   Output: {output_path}")

    # Stats
    label_counts = {}
    for email in to_classify:
        label = email["client_label"]
        label_counts[label] = label_counts.get(label, 0) + 1

    print("\n📊 Client Label Distribution:")
    for client_label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        print(f"   {client_label:20} {count:3} ({count / len(to_classify) * 100:.1f}%)")


if __name__ == "__main__":
    main()
