#!/usr/bin/env python3
"""
Review Digest Quality - Compare actual digest against input emails

This script helps you:
1. Review the input emails that went into the digest
2. See what the digest actually produced
3. Manually determine what SHOULD have been featured (the ideal)
4. Compare actual vs your ideal to identify gaps

Usage:
    python review_digest_quality.py [timestamp]

    # Review latest digest
    python review_digest_quality.py

    # Review specific digest
    python review_digest_quality.py 20251106_120000
"""

from __future__ import annotations

import json
from pathlib import Path


def find_latest_files():
    """Find the most recent input_emails_*.json file"""
    quality_logs_dir = Path("quality_logs")
    if not quality_logs_dir.exists():
        print("❌ quality_logs/ directory not found")
        print("   Generate a digest first to create logs")
        return None, None

    # Find all input_emails_*.json files
    email_files = sorted(quality_logs_dir.glob("input_emails_*.json"), reverse=True)

    if not email_files:
        print("❌ No input_emails_*.json files found in quality_logs/")
        print("   Generate a digest first to create logs")
        return None, None

    latest_email_file = email_files[0]

    # Extract timestamp from filename
    # input_emails_20251106_120000.json -> 20251106_120000
    timestamp = latest_email_file.stem.replace("input_emails_", "")

    # Find corresponding digest HTML
    digest_file = quality_logs_dir / f"actual_digest_{timestamp}.html"

    if not digest_file.exists():
        print(f"⚠️  Warning: Found {latest_email_file.name} but no matching digest HTML")
        return latest_email_file, None

    return latest_email_file, digest_file


def load_input_emails(json_file):
    """Load and parse input emails"""
    with open(json_file, encoding="utf-8") as f:
        return json.load(f)


def display_input_emails(data):
    """Display input emails in readable format"""
    print(f"\n{'=' * 80}")
    print(f"INPUT EMAILS ({data['email_count']} total)")
    print(f"Timestamp: {data['timestamp']}")
    print(f"{'=' * 80}\n")

    # Group by classification
    by_type = {}
    for email in data["emails"]:
        email_type = email.get("type", "unknown")
        if email_type not in by_type:
            by_type[email_type] = []
        by_type[email_type].append(email)

    # Display by type
    for email_type, emails in sorted(by_type.items()):
        print(f"\n📧 {email_type.upper()} ({len(emails)} emails)")
        print("-" * 80)

        for i, email in enumerate(emails, 1):
            subject = email.get("subject", "No subject")
            from_addr = email.get("from", "Unknown sender")
            snippet = email.get("snippet", "")
            attention = email.get("attention", "none")
            domains = ", ".join(email.get("domains", []))

            print(f"\n  {i}. {subject}")
            print(f"     From: {from_addr}")
            if snippet:
                print(f"     Preview: {snippet[:100]}...")
            if attention != "none":
                print(f"     ⚠️  Attention: {attention}")
            if domains:
                print(f"     🏷️  Domains: {domains}")


def extract_digest_summary(html_file):
    """Extract key stats from digest HTML"""
    with open(html_file, encoding="utf-8") as f:
        content = f.read()

    # Extract metadata from comments
    featured = critical = 0
    for line in content.split("\n")[:10]:
        if "Featured:" in line:
            featured = int(line.split("Featured:")[1].split("-->")[0].strip())
        elif "Critical:" in line:
            critical = int(line.split("Critical:")[1].split("-->")[0].strip())

    return {"featured": featured, "critical": critical}


def display_digest_summary(digest_file):
    """Display what the digest actually produced"""
    if not digest_file:
        return

    stats = extract_digest_summary(digest_file)

    print(f"\n{'=' * 80}")
    print("ACTUAL DIGEST OUTPUT")
    print(f"{'=' * 80}\n")

    print(f"Featured items: {stats['featured']}")
    print(f"Critical items: {stats['critical']}")
    print(f"\nFull HTML: {digest_file}")
    print(f"\nTo view: open {digest_file}")


def prompt_for_ideal():
    """Interactive prompt to help determine ideal"""
    print(f"\n{'=' * 80}")
    print("DETERMINE YOUR IDEAL")
    print(f"{'=' * 80}\n")

    print("Now that you've reviewed the INPUT emails and seen the ACTUAL output,")
    print("think about what SHOULD have been featured:\n")

    print("Questions to ask:")
    print("1. Are there CRITICAL items (bills, security alerts) that were missed?")
    print("2. Are there deliveries arriving TODAY that should be featured?")
    print("3. Are there COMING UP events in the next few days?")
    print("4. What's WORTH KNOWING (jobs, shipments, financial notifications)?")
    print("5. Were any NOISE items featured that shouldn't be (promotions, past events)?")

    print(f"\n{'=' * 80}")
    print("NEXT STEPS")
    print(f"{'=' * 80}\n")

    print("1. Review the input emails above")
    print("2. Open the actual digest HTML to see what was featured")
    print("3. Manually list what SHOULD have been in each section:")
    print("   - CRITICAL (8 or fewer)")
    print("   - TODAY (deliveries, urgent deadlines)")
    print("   - COMING UP (events, appointments)")
    print("   - WORTH KNOWING (jobs, shipments, etc.)")
    print("4. Update docs/ACTUAL_VS_IDEAL_COMPARISON.md with your ideal")
    print("5. Compare and identify gaps")
    print("6. Fix classification issues")


def main():
    print("🔍 Digest Quality Review Tool\n")

    # Find files
    email_file, digest_file = find_latest_files()

    if not email_file:
        return 1

    print("✅ Found files:")
    print(f"   Input:  {email_file.name}")
    if digest_file:
        print(f"   Output: {digest_file.name}")

    # Load and display input emails
    data = load_input_emails(email_file)
    display_input_emails(data)

    # Display digest summary
    if digest_file:
        display_digest_summary(digest_file)

    # Prompt for ideal determination
    prompt_for_ideal()

    return 0


if __name__ == "__main__":
    exit(main())
