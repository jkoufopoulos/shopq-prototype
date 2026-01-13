#!/usr/bin/env python3
"""
Classify emails using GPT-5-mini (OpenAI)

Reads GDS CSV and classifies unlabeled emails using GPT-5-mini.
Outputs pre-labeled CSV ready for manual review.

Usage:
    uv run python scripts/classify_with_gpt5.py \
        --input tests/golden_set/gds-2.0-labeled.csv \
        --output tests/golden_set/gds-2.0-gpt5-prelabeled.csv
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


CLASSIFICATION_PROMPT = """You are an email classifier for ShopQ, a Gmail assistant.

Classify this email into ONE type and ONE importance level.

EMAIL TYPES:
- promotion: Marketing, sales, deals
- receipt: Order confirmations, purchase receipts, invoices
- newsletter: Content emails, articles, updates
- message: Person-to-person emails from individuals
- notification: System notifications, alerts, updates (default)
- event: Calendar invites, event notifications
- other: Doesn't fit above

IMPORTANCE LEVELS (at receipt time):
- critical: Security threats, fraud alerts, account lockouts (NOT OTPs)
- time_sensitive: Needs action soon (events, OTPs, deliveries)
- routine: Can review later (most emails ~70%)

TEMPORALITY:
- If event/delivery/deadline: Extract temporal_start and temporal_end in ISO format (YYYY-MM-DDTHH:MM:SS)
- Otherwise: Leave temporal fields null

Email to classify:
---
From: {from_email}
Subject: {subject}
Snippet: {snippet}
---

Respond with valid JSON only:
{{
  "type": "one of: promotion, receipt, newsletter, message, notification, event, other",
  "importance": "one of: critical, time_sensitive, routine",
  "temporal_start": "ISO timestamp or null",
  "temporal_end": "ISO timestamp or null",
  "confidence": 0.95,
  "reasoning": "Brief explanation (1-2 sentences)"
}}"""


def classify_email(client: OpenAI, from_email: str, subject: str, snippet: str) -> dict:
    """Classify single email using GPT-5-mini"""

    prompt = CLASSIFICATION_PROMPT.format(
        from_email=from_email, subject=subject, snippet=snippet[:300]
    )

    try:
        # Use GPT-5 responses API with explicit JSON instruction
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
            timeout=30.0,  # 30 second timeout per API call
        )
        elapsed = time.time() - start_time

        # Extract output text
        output_text = response.output_text.strip()

        # Parse JSON from output
        # Handle various formats: raw JSON, markdown blocks, or mixed text
        if output_text.startswith("```"):
            # Extract from markdown code block
            output_text = output_text.split("```")[1]
            if output_text.startswith("json"):
                output_text = output_text[4:]
            output_text = output_text.strip()
        elif "{" in output_text:
            # Extract JSON object from mixed text
            start = output_text.find("{")
            end = output_text.rfind("}") + 1
            output_text = output_text[start:end]

        result = json.loads(output_text)

        # Validate
        valid_types = {
            "promotion",
            "receipt",
            "newsletter",
            "message",
            "notification",
            "event",
            "other",
        }
        valid_importance = {"critical", "time_sensitive", "routine"}

        if result["type"] not in valid_types:
            raise ValueError(f"Invalid type: {result['type']}")
        if result["importance"] not in valid_importance:
            raise ValueError(f"Invalid importance: {result['importance']}")

        return result

    except Exception as e:
        print(f"   ⚠️  Error classifying: {e}")
        return {
            "type": "notification",
            "importance": "routine",
            "temporal_start": None,
            "temporal_end": None,
            "confidence": 0.0,
            "reasoning": f"Error: {str(e)}",
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Classify emails with GPT-5-mini")
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
        print("   1. Ensure .env file exists in project root")
        print("   2. Copy .env.example to .env if needed")
        print("   3. Add OPENAI_API_KEY to .env file")
        print("   4. NEVER use 'export' commands with real API keys")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    print("🤖 Classifying emails with GPT-5-mini...")
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

        # Update email with GPT-5 labels
        email["email_type"] = classification["type"]
        email["importance"] = classification["importance"]
        email["temporal_start"] = classification.get("temporal_start") or ""
        email["temporal_end"] = classification.get("temporal_end") or ""
        email["decider"] = "gpt5_mini_prelabel"
        email["importance_reason"] = classification.get("reasoning", "")

        # Progress indicator
        print(f"✓ ({classification['type']}/{classification['importance']})", flush=True)

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
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = list(emails[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emails)

    print("\n✅ GPT-5-mini pre-labeling complete!")
    print(f"   Classified {len(to_classify)} emails")
    print(f"   Output: {output_path}")

    # Stats
    type_counts = {}
    importance_counts = {}
    for email in to_classify:
        t = email["email_type"]
        i = email["importance"]
        type_counts[t] = type_counts.get(t, 0) + 1
        importance_counts[i] = importance_counts.get(i, 0) + 1

    print("\n📊 Type Distribution:")
    for email_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"   {email_type:15} {count:3} ({count / len(to_classify) * 100:.1f}%)")

    print("\n📊 Importance Distribution:")
    for importance, count in sorted(importance_counts.items(), key=lambda x: -x[1]):
        print(f"   {importance:15} {count:3} ({count / len(to_classify) * 100:.1f}%)")


if __name__ == "__main__":
    main()
