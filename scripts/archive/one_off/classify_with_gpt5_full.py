#!/usr/bin/env python3
"""
Classify emails with GPT-5.1 (full taxonomy including temporality)

Reads GDS CSV and classifies emails using GPT-5.1 with complete taxonomy.
Outputs labeled CSV ready for manual review.

Usage:
    uv run python scripts/classify_with_gpt5_full.py \
        --input tests/golden_set/gds-2.0-unlabeled.csv \
        --output tests/golden_set/gds-2.0-gpt5.1-prelabeled.csv
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


CLASSIFICATION_PROMPT = """You are an email classifier. Use ONLY the subject and snippet to assign four fields:

1. type
   Choose exactly one:
   - notification
   - receipt
   - event
   - message
   - newsletter
   - promotion
   - other

2. importance
   Choose exactly one:
   - critical          (real-world consequence if ignored)
   - time_sensitive    (matters soon, not existential)
   - routine           (low consequence or informational)

3. temporality
   Extract only if the email clearly contains a real date/time for an event, deadline, or delivery.
   Provide:
     temporal_start: ISO 8601 datetime or null
     temporal_end:   ISO 8601 datetime or null
   If no real date/time → both fields are null.
   Do NOT treat OTP expiration windows ("expires in 5 minutes") as temporality.

4. client_label   (Gmail UI bucket)
   Choose exactly one:
   - action-required   (real-world consequence if ignored)
   - receipts          (purchases, invoices, payments)
   - messages          (person-to-person communication)
   - everything-else   (all other automated emails)
   - digest            (ONLY for ShopQ-generated digests)

Special rules:
- OTP / verification code emails → type=notification, importance=critical, temporality=null, client_label=everything-else.
- Receipts / order confirmations → client_label=receipts.
- 1:1 human emails → type=message → client_label=messages.
- Events with RSVP required → importance=time_sensitive or critical depending on context → client_label=action-required.
- Newsletters, promos, marketing → routine + everything-else.
- Flight, reservation, appointment, bill due → extract true temporality if present.

Output each email as a compact JSON object with fields:
{{
  "type": "...",
  "importance": "...",
  "temporal_start": "...",
  "temporal_end": "...",
  "client_label": "..."
}}

If temporal fields don't exist, output them as null.
Do NOT add extra commentary.

Email to classify:
---
From: {from_email}
Subject: {subject}
Snippet: {snippet}
---

Respond with ONLY valid JSON. No explanations, no markdown, just the JSON object."""


def classify_email(client: OpenAI, from_email: str, subject: str, snippet: str) -> dict:
    """Classify single email using GPT-5.1"""

    prompt = CLASSIFICATION_PROMPT.format(
        from_email=from_email, subject=subject, snippet=snippet[:300]
    )

    try:
        start_time = time.time()
        response = client.responses.create(
            model="gpt-5.1-mini",
            input=prompt,
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

        # Validate
        valid_types = {
            "notification",
            "receipt",
            "event",
            "message",
            "newsletter",
            "promotion",
            "other",
        }
        valid_importance = {"critical", "time_sensitive", "routine"}
        valid_client_labels = {
            "action-required",
            "receipts",
            "messages",
            "everything-else",
            "digest",
        }

        if result["type"] not in valid_types:
            raise ValueError(f"Invalid type: {result['type']}")
        if result["importance"] not in valid_importance:
            raise ValueError(f"Invalid importance: {result['importance']}")
        if result["client_label"] not in valid_client_labels:
            raise ValueError(f"Invalid client_label: {result['client_label']}")

        # Ensure temporal fields are null if not present
        if "temporal_start" not in result or result["temporal_start"] == "":
            result["temporal_start"] = None
        if "temporal_end" not in result or result["temporal_end"] == "":
            result["temporal_end"] = None

        return result

    except Exception as e:
        print(f"   ⚠️  Error classifying: {e}")
        return {
            "type": "notification",
            "importance": "routine",
            "temporal_start": None,
            "temporal_end": None,
            "client_label": "everything-else",
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Classify emails with GPT-5.1 (full taxonomy)")
    parser.add_argument("--input", required=True, help="Input GDS CSV")
    parser.add_argument("--output", required=True, help="Output pre-labeled CSV")
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

    print("🤖 Classifying emails with GPT-5.1 (full taxonomy)...")
    print(f"📖 Reading {input_path}...\n")

    # Read GDS
    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    # Filter to unlabeled emails
    to_classify = [e for e in emails if e.get("decider") not in ["manual", "manual_p0_pattern"]]

    print(f"   Total emails: {len(emails)}")
    print(f"   Already hand-labeled: {len(emails) - len(to_classify)}")
    print(f"   To classify: {len(to_classify)}\n")

    if len(to_classify) == 0:
        print("✅ All emails already manually labeled!")
        sys.exit(0)

    # Classify each email
    start_overall = time.time()
    for i, email in enumerate(to_classify, 1):
        print(f"[{i}/{len(to_classify)}] {email['subject'][:50]}...", end=" ", flush=True)

        classification = classify_email(
            client, email["from_email"], email["subject"], email.get("snippet", "")
        )

        # Update email with GPT-5.1 labels
        email["email_type"] = classification["type"]
        email["importance"] = classification["importance"]
        email["temporal_start"] = classification.get("temporal_start") or ""
        email["temporal_end"] = classification.get("temporal_end") or ""
        email["client_label"] = classification["client_label"]
        email["decider"] = "gpt5.1_mini_prelabel"

        # Progress indicator
        print(
            f"✓ ({classification['type']}/{classification['importance']}/{classification['client_label']})",
            flush=True,
        )

        # Show estimated completion every 10 emails
        if i % 10 == 0:
            elapsed = time.time() - start_overall
            avg_per_email = elapsed / i
            remaining = (len(to_classify) - i) * avg_per_email
            print(
                f"   ⏱️  Avg: {avg_per_email:.1f}s/email | Est. remaining: {remaining / 60:.1f}min\n",
                flush=True,
            )

    # Write pre-labeled CSV
    print(f"\n💾 Writing pre-labeled results to {output_path}...")

    # Ensure all required fields exist
    required_fields = [
        "message_id",
        "thread_id",
        "from_email",
        "subject",
        "snippet",
        "received_date",
        "email_type",
        "importance",
        "temporal_start",
        "temporal_end",
        "client_label",
        "decider",
    ]

    fieldnames = required_fields.copy()
    # Add any extra fields from input
    for email in emails:
        for key in email.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emails)

    print("\n✅ GPT-5.1 pre-labeling complete!")
    print(f"   Classified {len(to_classify)} emails")
    print(f"   Output: {output_path}")

    # Stats
    type_counts = {}
    importance_counts = {}
    client_label_counts = {}
    temporal_count = 0

    for email in to_classify:
        t = email["email_type"]
        i = email["importance"]
        c = email["client_label"]
        type_counts[t] = type_counts.get(t, 0) + 1
        importance_counts[i] = importance_counts.get(i, 0) + 1
        client_label_counts[c] = client_label_counts.get(c, 0) + 1
        if email.get("temporal_start"):
            temporal_count += 1

    print("\n📊 Type Distribution:")
    for email_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"   {email_type:15} {count:3} ({count / len(to_classify) * 100:.1f}%)")

    print("\n📊 Importance Distribution:")
    for importance, count in sorted(importance_counts.items(), key=lambda x: -x[1]):
        print(f"   {importance:15} {count:3} ({count / len(to_classify) * 100:.1f}%)")

    print("\n📊 Client Label Distribution:")
    for client_label, count in sorted(client_label_counts.items(), key=lambda x: -x[1]):
        print(f"   {client_label:20} {count:3} ({count / len(to_classify) * 100:.1f}%)")

    print("\n⏰ Temporality:")
    print(
        f"   With temporal data: {temporal_count} ({temporal_count / len(to_classify) * 100:.1f}%)"
    )
    print(
        f"   No temporal data:   {len(to_classify) - temporal_count} ({(len(to_classify) - temporal_count) / len(to_classify) * 100:.1f}%)"
    )


if __name__ == "__main__":
    main()
