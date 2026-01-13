#!/usr/bin/env python3
"""
Re-extract temporality for all GDS emails using improved GPT-5 prompt.
This updates temporal_start and temporal_end fields without changing other classifications.
"""

import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env
load_dotenv()

TEMPORALITY_PROMPT = """You are an email temporality extractor.

Each input email will provide:
- subject: the email subject line
- snippet: a short preview of the body
- received_at: the timestamp when the email was received, in ISO 8601 format (UTC)

Your job:
Decide whether the email contains a specific, extractable real-world date or time
for an event, deadline, or delivery, and return temporal_start and temporal_end.

Use these rules:

1. Only assign temporality when you can derive a concrete calendar moment
   using the text PLUS received_at. Otherwise, both fields must be null.

2. Valid temporality cases include:
   - Events/appointments with a clear date and/or time:
       "Saturday, 8/23 at 6pm", "June 21 @ 6pm", "Nov 20", "March 3, 2026"
   - Bills or deadlines with a clear due date:
       "Payment due Nov 20", "Submit by 2025-11-20"
   - Deliveries with a clear delivery date:
       "Delivery arriving Nov 18"
       "Your order will be delivered on Friday, June 5"
   - Application or permit windows with clear start AND end dates:
       "Window open Aug 18–25, 2025"

3. Relative dates that CAN use received_at:
   - Phrases like "this Sunday", "this Saturday", "tomorrow", "tonight"
     may be converted to a specific date using received_at IF:
       - The phrase refers to a single upcoming day within 7 days of received_at.
   - Example:
       received_at = 2025-08-18T10:00:00Z and snippet says
       "event this Sunday at 6pm" → use the next Sunday after received_at.

4. Relative or vague phrases that must NOT produce temporality:
   - "this weekend", "next week", "later this month", "this fall", "soon"
   - "events happening all week", "Fridays at Union Market"
   - Generic marketing like "Today only!" or "Sale ends soon" when no actual
     calendar date is given
   In these cases, both temporal_start and temporal_end must be null.

5. Special rules for deliveries:
   - If the email clearly says "out for delivery" or similar, and there is
     NO explicit delivery date, assume delivery is on the same calendar day
     as received_at.
   - For deliveries, use:
       temporal_start = delivery_date at 09:00:00 (local-day morning)
       temporal_end   = delivery_date at 21:00:00 (local-day evening)

6. Special rules for OTPs and short-lived codes:
   - Do NOT treat OTP expiration windows ("expires in 5 minutes",
     "valid for 24 hours") as temporality.
   - In those emails, temporality must be null.

7. Time window defaults:
   - Events/appointments with a start time but no end time:
       temporal_start = event start
       temporal_end   = event start + 1 hour (assumed duration)
   - All-day deadlines (e.g., "due Nov 20"):
       temporal_start = that date at 00:00:00
       temporal_end   = that date at 23:59:59

8. If you cannot confidently derive a specific date/time range using the subject,
   snippet, and received_at, set both fields to null.

Output format:
Return ONLY a JSON object with exactly these fields:

{{
  "temporal_start": "...",
  "temporal_end": "..."
}}

Use null for each field when there is no valid temporality.
Do NOT include any other fields, text, or explanations.

Email to analyze:
Subject: {subject}
Snippet: {snippet}
Received at: {received_at}
"""


def extract_temporality_gpt5(client, subject, snippet, received_at):
    """Extract temporality using GPT-5 with improved prompt"""
    prompt = TEMPORALITY_PROMPT.format(subject=subject, snippet=snippet, received_at=received_at)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"    ⚠️  Error: {e}")
        return None


def parse_received_date_to_iso(received_date):
    """Convert email date to ISO 8601 UTC format for GPT-5"""
    # Format: "Sat, 24 May 2025 12:23:37 +0000 (UTC)"
    from datetime import datetime

    try:
        date_obj = datetime.strptime(received_date.split(" (")[0], "%a, %d %b %Y %H:%M:%S %z")
        return date_obj.isoformat()
    except (ValueError, IndexError):
        return None


def main():
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")  # pragma: allowlist secret
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")  # pragma: allowlist secret
        print("   Run: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    csv_path = Path("data/gds/gds-2.0-manually-reviewed.csv")

    # Read CSV
    print(f"📖 Loading {csv_path}...", flush=True)
    with open(csv_path, encoding="utf-8") as f:
        emails = list(csv.DictReader(f))

    # Only process emails that don't already have temporal data
    # Check if temporal_start exists AND is not empty/null
    already_have_temporal = [
        e for e in emails if e.get("temporal_start") and e.get("temporal_start").strip()
    ]
    need_temporality = [
        e for e in emails if not (e.get("temporal_start") and e.get("temporal_start").strip())
    ]

    print(f"   Total emails: {len(emails)}", flush=True)
    print(f"   Already have temporal data: {len(already_have_temporal)}", flush=True)
    print(f"   Need temporality extraction: {len(need_temporality)}", flush=True)

    if len(need_temporality) == 0:
        print("\n✅ No emails to process!")
        return

    print("\n🤖 Re-extracting temporality with improved GPT-5 prompt...", flush=True)
    print(f"   This will take ~2-3 minutes for {len(need_temporality)} emails...", flush=True)

    # Re-extract temporality for each email
    success_count = 0
    for i, email in enumerate(need_temporality, 1):
        # Progress indicator every 25 emails
        if i % 25 == 1 or i == len(need_temporality):
            print(
                f"   [{i}/{len(need_temporality)}] {email.get('subject', '')[:60]}...",
                end=" ",
                flush=True,
            )

        # Convert received_date to ISO format for GPT-5
        received_at_iso = parse_received_date_to_iso(email.get("received_date", ""))
        if not received_at_iso:
            if i % 25 == 1 or i == len(need_temporality):
                print("⚠️  (no date)")
            continue

        result = extract_temporality_gpt5(
            client, email.get("subject", ""), email.get("snippet", ""), received_at_iso
        )

        if result:
            # Update temporal fields
            email["temporal_start"] = result.get("temporal_start") or ""
            email["temporal_end"] = result.get("temporal_end") or ""
            success_count += 1
            if i % 25 == 1 or i == len(need_temporality):
                print("✅", flush=True)
        else:
            if i % 25 == 1 or i == len(need_temporality):
                print("❌", flush=True)

        # Auto-save every 50 emails to prevent data loss
        if i % 50 == 0:
            print(f"\n   💾 Auto-saving progress ({i}/{len(need_temporality)})...", flush=True)
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(emails[0].keys()))
                writer.writeheader()
                writer.writerows(emails)

    # Save updated CSV
    print("\n💾 Saving updated CSV...", flush=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(emails[0].keys()))
        writer.writeheader()
        writer.writerows(emails)

    print(
        f"✅ Successfully re-extracted temporality for {success_count}/{len(need_temporality)} emails",
        flush=True,
    )
    print("\nAll 500 emails now have improved temporal extraction!", flush=True)
    print("Run ./scripts/review_gds.sh to start labeling.", flush=True)


if __name__ == "__main__":
    main()
