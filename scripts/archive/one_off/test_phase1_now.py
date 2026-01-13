#!/usr/bin/env python3
"""
Test Phase 1 filters RIGHT NOW using actual inbox emails.

This script:
1. Fetches current inbox emails (same 99 from ground truth)
2. Runs them through context_digest with filters
3. Shows what gets filtered
4. Compares to ideal output

No need to wait for scheduled digest.
"""

from __future__ import annotations

import csv
from pathlib import Path


def load_emails_from_csv():
    """Load the 99 emails from ground truth CSV"""
    csv_path = Path(__file__).parent.parent / "inbox_review_with notes - inbox_review.csv"

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    # Convert to format expected by context_digest
    formatted_emails = []
    for email in emails:
        formatted_emails.append(
            {
                "id": email.get("id", ""),
                "thread_id": email.get("thread_id", ""),
                "subject": email.get("subject", ""),
                "snippet": email.get("snippet", ""),
                "date": email.get("date", ""),
                "from": email.get("from", ""),
                "to": "jkoufopoulos@gmail.com",  # User's email
                "labels": [],
                "type": email.get("type", "message"),
                "attention": email.get("attention", "none"),
            }
        )

    return formatted_emails


def test_filters_only(emails):
    """Test Phase 1 filters in isolation"""
    from shopq.filters import filter_expired_events, filter_self_emails

    print("=" * 80)
    print("TESTING PHASE 1 FILTERS IN ISOLATION")
    print("=" * 80)
    print()

    print(f"📧 Starting with {len(emails)} emails")
    print()

    # Test time-decay filter
    print("🔍 Testing Time-Decay Filter...")
    before = len(emails)
    emails_after_time = filter_expired_events(emails)
    expired_count = before - len(emails_after_time)

    print(f"  Filtered: {expired_count} expired events")
    print(f"  Remaining: {len(emails_after_time)} emails")

    if expired_count > 0:
        print()
        print("  Filtered emails:")
        for email in emails:
            if email not in emails_after_time:
                print(f"    ❌ {email['subject'][:70]}")
                print(f"       Date: {email['date'][:30]}")

    print()

    # Test self-email filter
    print("🔍 Testing Self-Email Filter...")
    before = len(emails_after_time)
    emails_final = filter_self_emails(emails_after_time, "jkoufopoulos@gmail.com")
    self_count = before - len(emails_final)

    print(f"  Filtered: {self_count} ShopQ digest emails")
    print(f"  Remaining: {len(emails_final)} emails")

    if self_count > 0:
        print()
        print("  Filtered emails:")
        for email in emails_after_time:
            if email not in emails_final:
                print(f"    ❌ {email['subject'][:70]}")

    print()
    total_filtered = expired_count + self_count
    percent_filtered = total_filtered / len(emails) * 100
    print(f"📊 Total filtered: {total_filtered} emails ({percent_filtered:.1f}%)")
    print()

    return emails_final, expired_count, self_count


def test_full_digest(emails):
    """Test full digest generation with filters"""
    from shopq.digest.context_digest import ContextDigest

    print("=" * 80)
    print("TESTING FULL DIGEST GENERATION")
    print("=" * 80)
    print()

    digest_gen = ContextDigest(verbose=True)

    print(f"📧 Generating digest for {len(emails)} emails...")
    print()

    result = digest_gen.generate(emails)

    print()
    print("=" * 80)
    print("DIGEST OUTPUT")
    print("=" * 80)
    print()
    print(result["text"])
    print()

    print("=" * 80)
    print("DIGEST STATS")
    print("=" * 80)
    print()
    print(f"  Featured: {result.get('featured_count', 0)} emails")
    print(f"  Entities: {result.get('entities_count', 0)}")
    print(f"  Word count: {result.get('word_count', 0)}")
    print()

    return result


def compare_to_ideal(filtered_emails):
    """Compare filtered emails to user's ground truth"""
    csv_path = Path(__file__).parent.parent / "inbox_review_with notes - inbox_review.csv"

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        ground_truth = list(reader)

    print("=" * 80)
    print("COMPARISON TO GROUND TRUTH")
    print("=" * 80)
    print()

    # Emails that should have been filtered
    should_filter = []
    for email in ground_truth:
        reasoning = (email.get("reasoning", "") + " " + email.get("notes", "")).lower()
        if "past event" in reasoning or "expired" in reasoning or "mailq" in reasoning:
            should_filter.append(email)

    print(f"📊 Ground truth says {len(should_filter)} emails should be filtered:")
    print()

    # Check if we filtered them
    filtered_subjects = {e["subject"] for e in filtered_emails}

    correct = 0
    incorrect = 0

    for email in should_filter:
        subject = email.get("subject", "")
        if subject in filtered_subjects:
            # Good - we didn't filter it (it's still there)
            incorrect += 1
            print(f"  ❌ NOT FILTERED: {subject[:60]}")
            rationale = (email.get("reasoning", "") + " " + email.get("notes", ""))[:50]
            print(f"     Why should filter: {rationale}")
        else:
            # Good - we filtered it
            correct += 1
            print(f"  ✅ FILTERED: {subject[:60]}")

    print()
    accuracy = correct / len(should_filter) * 100 if should_filter else 0
    print(f"📊 Filter accuracy: {correct}/{len(should_filter)} ({accuracy:.1f}%)")
    print()


def main():
    print("🎯 Testing Phase 1 Filters with Ground Truth Data")
    print()

    # Load emails
    emails = load_emails_from_csv()
    print(f"✅ Loaded {len(emails)} emails from ground truth CSV")
    print()

    # Test filters in isolation
    filtered_emails, expired_count, self_count = test_filters_only(emails)

    # Compare to ideal
    compare_to_ideal(filtered_emails)

    # Test full digest
    print("=" * 80)
    print("NOW TESTING FULL DIGEST PIPELINE")
    print("=" * 80)
    print()

    result = test_full_digest(emails)

    # Save output
    output_path = Path(__file__).parent.parent / "actual_digest_output_v2.txt"
    with open(output_path, "w") as f:
        f.write("ACTUAL DIGEST (Produced by Current System with Phase 1)\n")
        f.write("=" * 80 + "\n\n")
        f.write(result["text"])

    print()
    print(f"💾 Saved digest to: {output_path}")
    print()
    print("🎯 Next: Run scripts/compare_actual_vs_ideal.py to see detailed comparison")


if __name__ == "__main__":
    main()
