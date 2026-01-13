#!/usr/bin/env python3
"""
Add temporality fields to existing GDS using GPT-5.1-mini

This script ONLY adds temporal_start and temporal_end fields.
All existing labels (email_type, importance, client_label) are preserved.

Usage:
    uv run python scripts/add_temporality_gpt5.1.py \
        --input tests/golden_set/gds-2.0-with-client-labels.csv \
        --output tests/golden_set/gds-2.0-with-temporality.csv
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


TEMPORALITY_PROMPT = """You are an email classifier extracting temporal information.

Extract temporality ONLY if the email clearly contains a real date/time for an event, deadline, or delivery.

Provide:
  temporal_start: ISO 8601 datetime or null
  temporal_end:   ISO 8601 datetime or null

If no real date/time → both fields are null.

Special rules:
- Do NOT treat OTP expiration windows ("expires in 5 minutes") as temporality.
- Flight, reservation, appointment, bill due → extract true temporality if present.
- Receipts / order confirmations → null (unless specific delivery date mentioned).
- Newsletters, promos, marketing → null.
- Events with specific dates/times → extract temporality.

Examples:
✓ Has temporality:
  - "Flight on November 15, 2025 at 3:00 PM" → "2025-11-15T15:00:00"
  - "Package arriving Nov 18" → "2025-11-18T09:00:00" to "2025-11-18T21:00:00"
  - "Bill due December 1, 2025" → "2025-12-01T00:00:00" to "2025-12-01T23:59:59"
  - "Meeting Friday Nov 22 at 2pm" → "2025-11-22T14:00:00" to "2025-11-22T15:00:00"

✗ No temporality:
  - "Order confirmation" → null (no delivery date)
  - "Your code expires in 5 minutes" → null (OTP expiration)
  - "Sale ends soon" → null (vague)
  - "Weekly newsletter" → null (recurring)

Current context:
- Email type: {email_type}
- Importance: {importance}
- Today's date: November 17, 2025

Email to analyze:
---
From: {from_email}
Subject: {subject}
Snippet: {snippet}
---

Respond with ONLY valid JSON (no markdown, no extra commentary):
{{
  "temporal_start": "ISO 8601 or null",
  "temporal_end": "ISO 8601 or null"
}}"""


def extract_temporality(client: OpenAI, email: dict) -> dict:
    """Extract temporality using GPT-5-mini"""

    prompt = TEMPORALITY_PROMPT.format(
        from_email=email["from_email"],
        subject=email["subject"],
        snippet=email.get("snippet", "")[:300],
        email_type=email.get("email_type", "notification"),
        importance=email.get("importance", "routine"),
    )

    try:
        start_time = time.time()
        response = client.responses.create(
            model="gpt-5-mini",
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

        # Normalize null values
        if "temporal_start" not in result or result["temporal_start"] in ["", "null"]:
            result["temporal_start"] = None
        if "temporal_end" not in result or result["temporal_end"] in ["", "null"]:
            result["temporal_end"] = None

        return result

    except Exception as e:
        print(f"   ⚠️  Error extracting temporality: {e}")
        return {"temporal_start": None, "temporal_end": None, "reasoning": f"Error: {str(e)}"}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Add temporality fields with GPT-5.1-mini")
    parser.add_argument("--input", required=True, help="Input GDS CSV")
    parser.add_argument("--output", required=True, help="Output CSV with temporality")
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

    print("🤖 Adding temporality fields with GPT-5-mini...")
    print(f"📖 Reading {input_path}...\n")

    # Read GDS
    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    # Fix taxonomy inconsistency: promo → promotion
    for email in emails:
        if email.get("email_type") == "promo":
            email["email_type"] = "promotion"

    # Ensure temporal fields exist (will be overwritten)
    for email in emails:
        if "temporal_start" not in email:
            email["temporal_start"] = ""
        if "temporal_end" not in email:
            email["temporal_end"] = ""

    # Process ALL emails (ignore existing temporal fields)
    to_process = emails

    print(f"   Total emails to process: {len(to_process)}")
    print("   Note: Re-extracting temporality for ALL emails\n")

    # Extract temporality for each email
    start_overall = time.time()
    temporal_found = 0

    for i, email in enumerate(to_process, 1):
        print(f"[{i}/{len(to_process)}] {email['subject'][:50]}...", end=" ", flush=True)

        temporality = extract_temporality(client, email)

        # Update ONLY temporal fields (preserve all other labels)
        email["temporal_start"] = temporality.get("temporal_start") or ""
        email["temporal_end"] = temporality.get("temporal_end") or ""

        has_temporal = bool(temporality.get("temporal_start"))
        if has_temporal:
            temporal_found += 1
            print(f"✓ (temporal: {temporality['temporal_start'][:10]})", flush=True)
        else:
            print("✓ (no temporal data)", flush=True)

        # Show estimated completion every 10 emails
        if i % 10 == 0:
            elapsed = time.time() - start_overall
            avg_per_email = elapsed / i
            remaining = (len(to_process) - i) * avg_per_email
            pct_temporal = (temporal_found / i) * 100
            print(
                f"   ⏱️  Avg: {avg_per_email:.1f}s/email | Est. remaining: {remaining / 60:.1f}min | Temporal: {pct_temporal:.1f}%\n",
                flush=True,
            )

    # Write output CSV
    print(f"\n💾 Writing results to {output_path}...")

    # Ensure fieldnames include temporal fields
    fieldnames = list(emails[0].keys())
    if "temporal_start" not in fieldnames:
        # Insert after importance if possible
        if "importance" in fieldnames:
            idx = fieldnames.index("importance") + 1
            fieldnames.insert(idx, "temporal_start")
            fieldnames.insert(idx + 1, "temporal_end")
        else:
            fieldnames.extend(["temporal_start", "temporal_end"])

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emails)

    print("\n✅ Temporality extraction complete!")
    print(f"   Processed {len(to_process)} emails")
    print(f"   Found temporality: {temporal_found} ({temporal_found / len(to_process) * 100:.1f}%)")
    print(
        f"   No temporality: {len(to_process) - temporal_found} ({(len(to_process) - temporal_found) / len(to_process) * 100:.1f}%)"
    )
    print(f"   Output: {output_path}")


if __name__ == "__main__":
    main()
