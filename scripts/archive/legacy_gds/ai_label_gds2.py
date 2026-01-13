#!/usr/bin/env python3
"""
AI-Assisted GDS-2.0 Labeling Tool

Analyzes the 363 placeholder emails and suggests email_type and importance labels.
Flags uncertain cases for manual review.

Usage:
    python scripts/ai_label_gds2.py --input ~/Desktop/gds2_REVIEW.csv --output ~/Desktop/gds2_labeled.csv
"""

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Type definitions
# User's taxonomy: promotion, receipt, newsletter, message, notification
# (event is also valid per ClassificationContract but user wants to focus on the 5 above)
EmailType = Literal[
    "promotion", "receipt", "newsletter", "message", "notification", "event", "other"
]
Importance = Literal["critical", "time_sensitive", "routine"]


@dataclass
class EmailLabel:
    """Suggested label for an email"""

    email_type: EmailType
    importance: Importance
    confidence: Literal["high", "medium", "low"]
    reasoning: str


def classify_email(from_addr: str, subject: str, snippet: str) -> EmailLabel:
    """
    Classify email using deterministic rules (mimics ShopQ Type Mapper logic).

    Precedence:
    1. Calendar events (Google Calendar)
    2. Receipts (order confirmations, payments)
    3. Deadlines (bills, appointments)
    4. Promos (marketing emails)
    5. Thread updates (replies, forwards)
    6. Notifications (everything else)
    """
    from_lower = from_addr.lower()
    subject_lower = subject.lower()
    snippet_lower = snippet.lower()

    # ========== MESSAGES (person-to-person) ==========
    # Calendar invites from individuals (typically message-like)
    if any(word in subject_lower for word in ["invitation:", "updated invitation:", "canceled:"]):
        # From personal email domains (gmail.com, etc.)
        if any(
            domain in from_lower
            for domain in ["@gmail.com", "@yahoo.com", "@hotmail.com", "@outlook.com"]
        ):
            return EmailLabel(
                email_type="message",
                importance="time_sensitive",
                confidence="high",
                reasoning="Personal calendar invite from individual → message, time_sensitive",
            )
        # From work/professional domains
        return EmailLabel(
            email_type="message",
            importance="time_sensitive",
            confidence="medium",
            reasoning="Calendar invite → message, time_sensitive",
        )

    # ========== EVENTS (system-generated calendar) ==========
    # Google Calendar automated notifications
    if "calendar-notification@google.com" in from_lower:
        return EmailLabel(
            email_type="event",
            importance="time_sensitive",
            confidence="high",
            reasoning="Google Calendar notification → event, time_sensitive (T0 rule)",
        )

    # ========== RECEIPTS ==========
    # Order confirmations
    if any(
        word in subject_lower
        for word in ["ordered:", "order #", "order confirmed", "receipt", "order of "]
    ):
        return EmailLabel(
            email_type="receipt",
            importance="routine",
            confidence="high",
            reasoning="Order confirmation → receipt, routine",
        )

    # Uber Eats receipts
    if "uber" in from_lower and any(
        word in subject_lower for word in ["order with uber", "receipt"]
    ):
        return EmailLabel(
            email_type="receipt",
            importance="routine",
            confidence="high",
            reasoning="Uber Eats receipt → receipt, routine",
        )

    # Payment receipts
    if (
        any(word in from_lower for word in ["paypal", "affirm", "shop pay"])
        and "payment" in snippet_lower
    ):
        return EmailLabel(
            email_type="receipt",
            importance="routine",
            confidence="high",
            reasoning="Payment receipt → receipt, routine",
        )

    # Store purchase receipts
    if any(phrase in subject_lower for phrase in ["thank you for shopping", "you recently bought"]):
        return EmailLabel(
            email_type="receipt",
            importance="routine",
            confidence="high",
            reasoning="Store purchase receipt → receipt, routine",
        )

    # Delivery notifications (shipped, delivered)
    if any(word in subject_lower for word in ["shipped:", "delivered:", "out for delivery"]):
        return EmailLabel(
            email_type="notification",
            importance="routine",
            confidence="high",
            reasoning="Delivery update → notification, routine (tracking info)",
        )

    # ========== TIME-SENSITIVE NOTIFICATIONS ==========
    # Appointments (dental, medical)
    if "appointment" in subject_lower and "today" in subject_lower:
        return EmailLabel(
            email_type="notification",
            importance="critical",
            confidence="high",
            reasoning="Appointment today → notification, critical (imminent)",
        )

    if "appointment" in subject_lower:
        return EmailLabel(
            email_type="notification",
            importance="time_sensitive",
            confidence="high",
            reasoning="Upcoming appointment → notification, time_sensitive",
        )

    # Bills and invoices
    if any(word in subject_lower for word in ["invoice", "billing", "payment"]):
        return EmailLabel(
            email_type="notification",
            importance="time_sensitive",
            confidence="medium",
            reasoning="Bill/invoice → notification, time_sensitive (payment due)",
        )

    # ========== NEWSLETTERS ==========
    # Content newsletters (Stratechery, elsewhere, etc.)
    if any(word in from_lower for word in ["stratechery", "elsewhere", "substack"]):
        return EmailLabel(
            email_type="newsletter",
            importance="routine",
            confidence="high",
            reasoning="Content newsletter → newsletter, routine",
        )

    if any(word in subject_lower for word in ["weekly show", "this week in", "weekly", "digest"]):
        return EmailLabel(
            email_type="newsletter",
            importance="routine",
            confidence="high",
            reasoning="Weekly content → newsletter, routine",
        )

    # ========== PROMOTIONS ==========
    # Marketing emails with clear promo signals
    if any(
        word in subject_lower
        for word in ["cash back", "sale", "discount", "% off", "join us at", "join", "event"]
    ):
        return EmailLabel(
            email_type="promotion",
            importance="routine",
            confidence="high",
            reasoning="Marketing/promotional content → promotion, routine",
        )

    # Marketing sender addresses
    if any(word in from_lower for word in ["email@", "send@", "ship@", "team@", "info@"]):
        if not any(word in subject_lower for word in ["order", "receipt", "invoice"]):
            return EmailLabel(
                email_type="promotion",
                importance="routine",
                confidence="medium",
                reasoning="Marketing sender address → promotion, routine",
            )

    # ========== NOTIFICATIONS (default) ==========
    # Financial notifications
    if any(
        word in from_lower
        for word in ["bank of america", "chase", "schwab", "vanguard", "experian", "rocket money"]
    ):
        if any(
            word in subject_lower
            for word in ["statement", "alert", "score", "balance", "transaction"]
        ):
            return EmailLabel(
                email_type="notification",
                importance="time_sensitive",
                confidence="high",
                reasoning="Financial account notification → notification, time_sensitive",
            )

    # Transaction notifications
    if "uncategorized transaction" in subject_lower or "transaction refund" in subject_lower:
        return EmailLabel(
            email_type="notification",
            importance="routine",
            confidence="high",
            reasoning="Transaction notification → notification, routine",
        )

    # Review requests
    if "rate" in subject_lower or "review" in subject_lower:
        return EmailLabel(
            email_type="notification",
            importance="routine",
            confidence="high",
            reasoning="Review request → notification, routine",
        )

    # Service updates
    if "important update" in subject_lower or "important information" in subject_lower:
        return EmailLabel(
            email_type="notification",
            importance="time_sensitive",
            confidence="medium",
            reasoning="Important update → notification, time_sensitive (service change)",
        )

    # Weekly/monthly updates
    if any(word in subject_lower for word in ["weekly", "monthly", "spending update"]):
        return EmailLabel(
            email_type="notification",
            importance="routine",
            confidence="high",
            reasoning="Periodic update → notification, routine",
        )

    # Support/issue notifications
    if "uber support" in from_lower or "wrong or missing" in subject_lower:
        return EmailLabel(
            email_type="notification",
            importance="time_sensitive",
            confidence="high",
            reasoning="Support issue → notification, time_sensitive (needs action)",
        )

    # Utility notifications
    if any(word in from_lower for word in ["coned", "con edison"]):
        return EmailLabel(
            email_type="notification",
            importance="routine",
            confidence="high",
            reasoning="Utility notification → notification, routine",
        )

    # Default: generic notification (medium confidence now)
    return EmailLabel(
        email_type="notification",
        importance="routine",
        confidence="medium",
        reasoning="Default classification → notification, routine (no specific patterns matched)",
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI-assisted GDS-2.0 labeling")
    parser.add_argument("--input", required=True, help="Input CSV (gds2_REVIEW.csv)")
    parser.add_argument("--output", required=True, help="Output CSV with suggested labels")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    # Read input CSV
    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"📧 Loaded {len(rows)} emails from {input_path}")
    print("🤖 Classifying emails using deterministic rules...\n")

    # Process each email
    labeled_rows = []
    uncertain_cases = []

    for i, row in enumerate(rows, 1):
        from_addr = row["from"]
        subject = row["subject"]
        snippet = row["snippet"]

        # Get suggested label
        label = classify_email(from_addr, subject, snippet)

        # Add suggestions to row
        row["YOUR_type"] = label.email_type
        row["YOUR_importance"] = label.importance
        row["AI_confidence"] = label.confidence
        row["AI_reasoning"] = label.reasoning

        labeled_rows.append(row)

        # Track uncertain cases
        if label.confidence == "low":
            uncertain_cases.append(
                {
                    "id": row["id"],
                    "from": from_addr,
                    "subject": subject,
                    "suggested_type": label.email_type,
                    "suggested_importance": label.importance,
                    "reasoning": label.reasoning,
                }
            )

        # Progress indicator
        if i % 50 == 0:
            print(f"  Processed {i}/{len(rows)} emails...")

    # Write output CSV
    fieldnames = list(labeled_rows[0].keys())
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(labeled_rows)

    print(f"\n✅ Labeled CSV written to: {output_path}")
    print("📊 Statistics:")
    print(f"   Total emails: {len(rows)}")
    print(f"   High confidence: {sum(1 for r in labeled_rows if r['AI_confidence'] == 'high')}")
    print(f"   Medium confidence: {sum(1 for r in labeled_rows if r['AI_confidence'] == 'medium')}")
    print(f"   Low confidence (needs review): {len(uncertain_cases)}")

    # Write uncertain cases report
    if uncertain_cases:
        report_path = output_path.parent / "gds2_UNCERTAIN_CASES.csv"
        with open(report_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "from",
                    "subject",
                    "suggested_type",
                    "suggested_importance",
                    "reasoning",
                ],
            )
            writer.writeheader()
            writer.writerows(uncertain_cases)
        print(f"\n⚠️  Uncertain cases report: {report_path}")
        print(f"   Please review {len(uncertain_cases)} low-confidence cases")

    # Summary by type
    print("\n📋 Label Distribution:")
    type_counts = {}
    importance_counts = {}
    for row in labeled_rows:
        email_type = row["YOUR_type"]
        importance = row["YOUR_importance"]
        type_counts[email_type] = type_counts.get(email_type, 0) + 1
        importance_counts[importance] = importance_counts.get(importance, 0) + 1

    print("\n   Email Types:")
    for email_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = count / len(rows) * 100
        print(f"      {email_type:15} {count:3} ({pct:5.1f}%)")

    print("\n   Importance:")
    for importance, count in sorted(importance_counts.items(), key=lambda x: -x[1]):
        pct = count / len(rows) * 100
        print(f"      {importance:15} {count:3} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
