#!/usr/bin/env python3
"""
Classify emails using Claude (Anthropic API)

Reads sample CSV and classifies each email using Claude Sonnet 4.5.
Outputs labels in JSON format for comparison.

Usage:
    # Add your API key to .env file (see .env.example)
    # NEVER use export commands with real API keys
    python scripts/classify_with_claude.py \
        --input ~/Desktop/GDS_MULTI_MODEL_SAMPLE.csv \
        --output ~/Desktop/claude_labels.csv
"""

import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
script_dir = Path(__file__).parent
project_root = script_dir.parent
env_file = project_root / ".env"

if env_file.exists():
    load_dotenv(env_file)
else:
    # Fallback: try loading from current directory
    load_dotenv()

try:
    from anthropic import Anthropic
except ImportError:
    print("❌ anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)


CLASSIFICATION_PROMPT = """You are an email classifier for an email management system.

Classify this email into ONE of these types:
- **promotion**: Marketing or sales emails
- **receipt**: Order confirmations, purchase receipts
- **newsletter**: Content emails (articles, updates, newsletters)
- **message**: Person-to-person emails from individuals
- **notification**: System notifications, alerts, updates (default)
- **event**: Calendar invites, event notifications
- **other**: Doesn't fit above categories

Also assign importance:
- **critical**: Urgent, requires immediate action
- **time_sensitive**: Important, should be reviewed soon
- **routine**: Can be reviewed later

Email to classify:
---
From: {from_email}
Subject: {subject}
Snippet: {snippet}
---

Respond ONLY with valid JSON in this exact format:
{{
  "type": "one of: promotion, receipt, newsletter, message, notification, event, other",
  "importance": "one of: critical, time_sensitive, routine",
  "confidence": 0.95,
  "reasoning": "Brief explanation (1-2 sentences)"
}}"""


def classify_email(client: Anthropic, from_email: str, subject: str, snippet: str) -> dict:
    """Classify single email using Claude"""

    prompt = CLASSIFICATION_PROMPT.format(
        from_email=from_email,
        subject=subject,
        snippet=snippet[:300],  # Limit snippet length
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",  # Latest Sonnet
            max_tokens=500,
            temperature=0,  # Deterministic
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract JSON from response
        content = response.content[0].text.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        result = json.loads(content)

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
            "type": "other",
            "importance": "routine",
            "confidence": 0.0,
            "reasoning": f"Error: {str(e)}",
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Classify emails with Claude")
    parser.add_argument("--input", required=True, help="Input sample CSV")
    parser.add_argument("--output", required=True, help="Output labels CSV")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in .env file")
        print("   1. Ensure .env file exists in project root")
        print("   2. Copy .env.example to .env if needed")
        print("   3. Add ANTHROPIC_API_KEY to .env file")
        print("   4. NEVER use 'export' commands with real API keys")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    print("🤖 Classifying emails with Claude Sonnet 4.5...")
    print(f"📖 Reading {input_path}...\n")

    # Read sample
    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    print(f"   Total emails to classify: {len(emails)}\n")

    # Classify each email
    results = []
    for i, email in enumerate(emails, 1):
        sample_id = email["sample_id"]
        from_email = email["from_email"]
        subject = email["subject"]
        snippet = email["snippet"]

        print(f"[{i}/{len(emails)}] {sample_id}: {subject[:50]}...")

        classification = classify_email(client, from_email, subject, snippet)

        results.append(
            {
                "sample_id": sample_id,
                "message_id": email["message_id"],
                "claude_type": classification["type"],
                "claude_importance": classification["importance"],
                "claude_confidence": classification.get("confidence", 0.0),
                "claude_reasoning": classification["reasoning"],
            }
        )

    # Write results
    print(f"\n💾 Writing results to {output_path}...")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print("\n✅ Classification complete!")
    print(f"   Classified {len(results)} emails")

    # Stats
    type_counts = {}
    for r in results:
        t = r["claude_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\n📊 Distribution:")
    for email_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"   {email_type:15} {count:2}")


if __name__ == "__main__":
    main()
