#!/usr/bin/env python3
"""
Generate the IDEAL digest based on user's manual review.

This creates a reference digest showing what the output SHOULD look like,
based on the user's categorization of 99 emails.

No hardcoding - this is a test oracle we iterate against.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


def load_user_review():
    """Load user's manual categorization from CSV"""
    csv_path = Path(__file__).parent.parent / "inbox_review_with notes - inbox_review.csv"

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    # Separate featured vs not featured
    featured = [e for e in emails if e["should_feature"].strip().lower() in ["yes", "y"]]
    not_featured = [e for e in emails if e["should_feature"].strip().lower() in ["no", "n"]]

    return emails, featured, not_featured


def categorize_featured_emails(featured):
    """
    Categorize featured emails based on user's reasoning/notes.

    This mimics what the digest SHOULD do.
    """
    categories = {"critical": [], "today": [], "coming_up": [], "worth_knowing": []}

    for email in featured:
        email.get("subject", "")
        reasoning = (email.get("reasoning", "") + " " + email.get("notes", "")).lower()

        # Critical: Bills, financial alerts, security, large charges
        if any(
            kw in reasoning
            for kw in ["bill", "statement", "balance", "charge", "financial alert", "security"]
        ):
            categories["critical"].append(email)

        # Today: Deliveries, items outside
        elif any(kw in reasoning for kw in ["delivered", "delivery", "outside", "shipped"]):
            categories["today"].append(email)

        # Coming up: Future appointments, events, hired someone
        elif any(kw in reasoning for kw in ["appointment", "event", "hired", "scheduled"]):
            categories["coming_up"].append(email)

        # Worth knowing: Job alerts, receipts, personal
        elif any(kw in reasoning for kw in ["job", "work opportunity", "receipt", "personal"]):
            categories["worth_knowing"].append(email)

        # Default: worth knowing
        else:
            categories["worth_knowing"].append(email)

    return categories


def categorize_noise(not_featured):
    """Categorize noise emails for transparent summary"""
    categories = defaultdict(list)

    for email in not_featured:
        reasoning = (email.get("reasoning", "") + " " + email.get("notes", "")).lower()

        if (
            "promotional" in reasoning
            or "promo" in reasoning
            or "survey" in reasoning
            or "event promotion" in reasoning
        ):
            categories["promotional"].append(email)
        elif "newsletter" in reasoning:
            categories["newsletters"].append(email)
        elif "receipt" in reasoning or "uber" in reasoning:
            categories["receipts"].append(email)
        elif "past event" in reasoning or "expired" in reasoning or "old email" in reasoning:
            categories["past_events"].append(email)
        elif "mailq" in reasoning:
            categories["shopq_self"].append(email)
        else:
            categories["updates"].append(email)

    return categories


def generate_ideal_digest_text(categories_featured, categories_noise, _total_emails):
    """
    Generate the ideal digest text based on user categorization.

    This is what the digest SHOULD look like.
    """
    lines = []

    lines.append("Your Inbox — Saturday, November 01 at 8:00 AM")
    lines.append("")

    # Critical section
    if categories_featured["critical"]:
        lines.append("🚨 CRITICAL")
        for email in categories_featured["critical"][:5]:  # Top 5
            subject = email.get("subject", "")[:80]
            reasoning = email.get("reasoning", "") or email.get("notes", "") or "Important"
            lines.append(f"• {subject}")
            if reasoning and reasoning != subject:
                lines.append(f"  → {reasoning[:60]}")
        lines.append("")

    # Today section
    if categories_featured["today"]:
        lines.append("📦 TODAY")
        for email in categories_featured["today"][:5]:
            subject = email.get("subject", "")[:80]
            reasoning = email.get("reasoning", "") or email.get("notes", "")
            lines.append(f"• {subject}")
            if "outside" in reasoning.lower():
                lines.append("  → might be outside 📍")
        lines.append("")

    # Coming up section
    if categories_featured["coming_up"]:
        lines.append("📅 COMING UP")
        for email in categories_featured["coming_up"][:7]:
            subject = email.get("subject", "")[:80]
            lines.append(f"• {subject}")
        lines.append("")

    # Worth knowing section
    if categories_featured["worth_knowing"]:
        lines.append("💼 WORTH KNOWING")
        for email in categories_featured["worth_knowing"][:5]:
            subject = email.get("subject", "")[:80]
            lines.append(f"• {subject}")
        lines.append("")

    # Separator
    lines.append("━" * 60)
    lines.append("")

    # Noise summary
    total_noise = sum(len(emails) for emails in categories_noise.values())
    lines.append(f"Everything else ({total_noise} emails):")

    if categories_noise["promotional"]:
        lines.append(f"  • {len(categories_noise['promotional'])} promotional")
    if categories_noise["newsletters"]:
        lines.append(f"  • {len(categories_noise['newsletters'])} newsletters")
    if categories_noise["receipts"]:
        lines.append(f"  • {len(categories_noise['receipts'])} receipts")
    if categories_noise["past_events"]:
        lines.append(f"  • {len(categories_noise['past_events'])} past events (filtered)")
    if categories_noise["shopq_self"]:
        lines.append(f"  • {len(categories_noise['shopq_self'])} ShopQ digest (filtered)")
    if categories_noise["updates"]:
        lines.append(f"  • {len(categories_noise['updates'])} updates & notifications")

    lines.append("")
    lines.append("[View all →]")

    return "\n".join(lines)


def generate_comparison_report(categories_featured, categories_noise):
    """Generate a detailed report for comparison"""
    lines = []

    lines.append("=" * 80)
    lines.append("IDEAL DIGEST COMPOSITION (Based on User Review)")
    lines.append("=" * 80)
    lines.append("")

    # Featured breakdown
    total_featured = sum(len(emails) for emails in categories_featured.values())
    lines.append(f"📊 FEATURED ({total_featured} emails):")
    lines.append("")

    for category, emails in categories_featured.items():
        if emails:
            lines.append(f"  {category.upper()}: {len(emails)} emails")
            for email in emails[:3]:  # Show first 3
                subject = email.get("subject", "")[:60]
                reasoning = email.get("reasoning", "") or email.get("notes", "")
                lines.append(f"    • {subject}...")
                if reasoning:
                    lines.append(f"      Why: {reasoning[:70]}")
            if len(emails) > 3:
                lines.append(f"    ... and {len(emails) - 3} more")
            lines.append("")

    # Noise breakdown
    total_noise = sum(len(emails) for emails in categories_noise.values())
    lines.append(f"🗑️  NOT FEATURED ({total_noise} emails):")
    lines.append("")

    for category, emails in categories_noise.items():
        if emails:
            lines.append(f"  {category.upper()}: {len(emails)} emails")
            # Show examples
            for email in emails[:2]:
                subject = email.get("subject", "")[:60]
                reasoning = email.get("reasoning", "") or email.get("notes", "")
                lines.append(f"    • {subject}...")
                if reasoning:
                    lines.append(f"      Why: {reasoning[:70]}")
            if len(emails) > 2:
                lines.append(f"    ... and {len(emails) - 2} more")
            lines.append("")

    # Summary stats
    lines.append("=" * 80)
    lines.append("SUMMARY STATISTICS")
    lines.append("=" * 80)
    lines.append(f"Total emails: {total_featured + total_noise}")
    lines.append(
        f"Featured: {total_featured} ({total_featured / (total_featured + total_noise) * 100:.1f}%)"
    )
    lines.append(
        f"Not featured: {total_noise} ({total_noise / (total_featured + total_noise) * 100:.1f}%)"
    )
    lines.append("")

    return "\n".join(lines)


def main():
    print("🎯 Generating IDEAL digest based on user review...")
    print()

    # Load user's manual review
    all_emails, featured, not_featured = load_user_review()

    print(f"📊 Loaded {len(all_emails)} emails from user review")
    print(f"  - Featured: {len(featured)}")
    print(f"  - Not featured: {len(not_featured)}")
    print()

    # Categorize featured emails
    categories_featured = categorize_featured_emails(featured)

    # Categorize noise
    categories_noise = categorize_noise(not_featured)

    # Generate ideal digest text
    ideal_digest = generate_ideal_digest_text(
        categories_featured, categories_noise, len(all_emails)
    )

    # Generate comparison report
    comparison = generate_comparison_report(categories_featured, categories_noise)

    # Output
    print("=" * 80)
    print("IDEAL DIGEST OUTPUT")
    print("=" * 80)
    print()
    print(ideal_digest)
    print()
    print()
    print(comparison)

    # Save to file
    output_path = Path(__file__).parent.parent / "ideal_digest_output.txt"
    with open(output_path, "w") as f:
        f.write("IDEAL DIGEST (Based on User Review)\n")
        f.write("=" * 80 + "\n\n")
        f.write(ideal_digest)
        f.write("\n\n\n")
        f.write(comparison)

    print()
    print(f"💾 Saved to: {output_path}")
    print()
    print("🎯 This is the TARGET digest. Iterate until actual output matches this.")


if __name__ == "__main__":
    main()
