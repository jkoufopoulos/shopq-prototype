#!/usr/bin/env python3
"""
Run GPT-5 classification on emails that have decider='manual' or 'manual_p0_pattern'.
This ensures ALL 500 emails have GPT-5 pre-fills for consistent labeling.
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

   Deterministic temporal patterns (extract from email date):
   - "out for delivery" → temporal_start = email_date 09:00, temporal_end = email_date 21:00
   - "arriving today" → temporal_start = email_date 09:00, temporal_end = email_date 21:00
   - "delivered today" → temporal_start = email_date 00:00, temporal_end = email_date 23:59

4. client_label   (Gmail UI bucket)
   Choose exactly one:
   - action-required   (real-world consequence if ignored)
   - receipts          (purchases, invoices, payments)
   - messages          (person-to-person communication)
   - everything-else   (all other automated emails)
   - digest            (ONLY for MailQ-generated digests)

Special rules:
- OTP / verification code emails → type=notification, importance=critical, temporality=null, client_label=everything-else.
- Receipts / order confirmations → client_label=receipts.
- 1:1 human emails → type=message → client_label=messages.
- Events with RSVP required → importance=time_sensitive or critical depending on context → client_label=action-required.
- Newsletters, promos, marketing → routine + everything-else.
- Flight, reservation, appointment, bill due → extract true temporality if present.
- Delivery notifications ("out for delivery", "arriving today") → extract temporal window based on email date.

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
From: {from_email}
Subject: {subject}
Snippet: {snippet}
"""


def classify_with_gpt5(client, from_email, subject, snippet):
    """Classify email using GPT-5 (gpt-4o-mini)"""
    prompt = CLASSIFICATION_PROMPT.format(from_email=from_email, subject=subject, snippet=snippet)

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
    print(f"📖 Loading {csv_path}...")
    with open(csv_path, encoding="utf-8") as f:
        emails = list(csv.DictReader(f))

    # Find emails that need GPT-5 classification
    need_gpt5 = [e for e in emails if e.get("decider") in ["manual", "manual_p0_pattern"]]

    print(f"   Total emails: {len(emails)}")
    print(f"   Already have GPT-5: {len(emails) - len(need_gpt5)}")
    print(f"   Need GPT-5 classification: {len(need_gpt5)}")

    if len(need_gpt5) == 0:
        print("\n✅ All emails already have GPT-5 pre-fills!")
        return

    print(f"\n🤖 Classifying {len(need_gpt5)} emails with GPT-5 (gpt-4o-mini)...")
    print("   This will take ~1-2 minutes...")

    # Classify each email
    success_count = 0
    for i, email in enumerate(need_gpt5, 1):
        print(f"   [{i}/{len(need_gpt5)}] {email.get('subject', '')[:50]}...", end=" ")

        result = classify_with_gpt5(
            client, email.get("from_email", ""), email.get("subject", ""), email.get("snippet", "")
        )

        if result:
            # Update email with GPT-5 classification
            email["email_type"] = result.get("type", "notification")
            email["importance"] = result.get("importance", "routine")
            email["client_label"] = result.get("client_label", "everything-else")
            email["temporal_start"] = result.get("temporal_start") or ""
            email["temporal_end"] = result.get("temporal_end") or ""
            email["decider"] = "gpt5_mini_prelabel"  # Mark as GPT-5 classified
            success_count += 1
            print("✅")
        else:
            print("❌")

    # Save updated CSV
    print("\n💾 Saving updated CSV...")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(emails[0].keys()))
        writer.writeheader()
        writer.writerows(emails)

    print(f"✅ Successfully classified {success_count}/{len(need_gpt5)} emails")
    print("\nNow ALL 500 emails have GPT-5 pre-fills!")
    print("Run ./scripts/review_gds.sh to start labeling with consistent AI suggestions.")


if __name__ == "__main__":
    main()
