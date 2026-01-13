#!/usr/bin/env python3
"""
Compare actual digest output vs ideal digest to identify gaps.

This script analyzes what went wrong in the actual digest generation
compared to the user's manual review (ideal digest).

Outputs actionable fixes needed.
"""

from __future__ import annotations

import csv
import re
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


def parse_actual_digest():
    """Parse the actual digest output to identify what was featured"""
    actual_path = Path(__file__).parent.parent / "actual_digest_output.txt"

    with open(actual_path) as f:
        content = f.read()

    # Extract items that were featured (numbered items in the digest)
    featured_items = []

    # Pattern: "... (1). ..." or "... (2). ..."
    pattern = r"\((\d+)\)\."
    matches = re.finditer(pattern, content)

    for match in matches:
        # Get context around the match
        start = max(0, match.start() - 100)
        end = min(len(content), match.end() + 100)
        context = content[start:end]
        featured_items.append({"number": match.group(1), "context": context.strip()})

    return featured_items, content


def identify_false_positives(featured_items, actual_content, not_featured):
    """Find emails that were featured but shouldn't be"""
    false_positives = []

    for item in featured_items:
        context = item["context"].lower()

        # Check against user's "not featured" list
        for email in not_featured:
            subject = email.get("subject", "").lower()
            reasoning = (email.get("reasoning", "") + " " + email.get("notes", "")).lower()

            # Try to match by keywords
            if any(word in context for word in subject.split() if len(word) > 4):
                false_positives.append(
                    {
                        "item_number": item["number"],
                        "context": item["context"][:100],
                        "email_subject": email.get("subject", ""),
                        "why_wrong": reasoning or email.get("reasoning", ""),
                    }
                )
                break

    # Check for specific known false positives
    if "vanguard" in actual_content.lower():
        false_positives.append(
            {
                "item_number": "4",
                "context": "last chance to provide feedback about Vanguard",
                "email_subject": "Vanguard feedback survey",
                "why_wrong": "Promotional survey - should be noise",
            }
        )

    if "drawing hive" in actual_content.lower():
        false_positives.append(
            {
                "item_number": "9",
                "context": "Check out Drawing Hive",
                "email_subject": "Drawing Hive event",
                "why_wrong": "Past event - should be filtered",
            }
        )

    if "meeting has adjourned" in actual_content.lower():
        false_positives.append(
            {
                "item_number": "10",
                "context": "A meeting has adjourned and needs your vote",
                "email_subject": "Meeting vote notification",
                "why_wrong": "Past event (adjourned = already happened)",
            }
        )

    return false_positives


def identify_false_negatives(actual_content, featured):
    """Find emails that should be featured but weren't"""
    false_negatives = []

    for email in featured:
        subject = email.get("subject", "").lower()
        reasoning = email.get("reasoning", "") or email.get("notes", "")

        # Check if email appears in actual digest
        # Use keywords from subject
        keywords = [word for word in subject.split() if len(word) > 4]

        found = False
        for keyword in keywords[:3]:  # Check first 3 meaningful words
            if keyword in actual_content.lower():
                found = True
                break

        if not found:
            category = _determine_category(email)
            false_negatives.append(
                {
                    "subject": email.get("subject", ""),
                    "category": category,
                    "reasoning": reasoning,
                    "priority": _determine_priority(email, reasoning),
                }
            )

    return false_negatives


def _determine_category(email):
    """Determine what category email should be in"""
    reasoning = (email.get("reasoning", "") + " " + email.get("notes", "")).lower()

    if any(
        kw in reasoning
        for kw in ["bill", "statement", "balance", "charge", "financial alert", "security"]
    ):
        return "🚨 CRITICAL"
    if any(kw in reasoning for kw in ["delivered", "delivery", "outside", "shipped"]):
        return "📦 TODAY"
    if any(kw in reasoning for kw in ["appointment", "event", "hired", "scheduled"]):
        return "📅 COMING UP"
    return "💼 WORTH KNOWING"


def _determine_priority(_email, reasoning):
    """Determine priority level"""
    if any(kw in reasoning.lower() for kw in ["bill", "security", "alert", "balance"]):
        return "HIGH"
    if any(kw in reasoning.lower() for kw in ["delivered", "appointment"]):
        return "MEDIUM"
    return "LOW"


def check_filter_failures(actual_content):
    """Check if filters failed to run"""
    failures = []

    # Check 1: Self-email (ShopQ digest appearing in itself)
    if "your inbox --" in actual_content.lower():
        failures.append(
            {
                "filter": "Self-Email Filter",
                "failure": "ShopQ digest is featuring itself",
                "evidence": '"Your Inbox --Saturday, November 01 at 01:03 AM"',
                "expected": "Should be filtered by self_emails.py",
            }
        )

    # Check 2: Past events
    past_event_patterns = [
        r"october \d+",
        r"oct \d+",
        r"adjourned",
    ]

    for pattern in past_event_patterns:
        if re.search(pattern, actual_content.lower()):
            failures.append(
                {
                    "filter": "Time-Decay Filter",
                    "failure": "Past event not filtered",
                    "evidence": f"Pattern: {pattern}",
                    "expected": "Should be filtered by time_decay.py",
                }
            )

    return failures


def generate_report(false_positives, false_negatives, filter_failures):
    """Generate comprehensive comparison report"""
    lines = []

    lines.append("=" * 80)
    lines.append("ACTUAL vs IDEAL DIGEST COMPARISON")
    lines.append("=" * 80)
    lines.append("")

    # Summary
    lines.append("📊 SUMMARY")
    lines.append("")
    lines.append(f"  ❌ False Positives: {len(false_positives)} emails featured that shouldn't be")
    lines.append(
        f"  ❌ False Negatives: {len(false_negatives)} emails missing that should be featured"
    )
    lines.append(f"  ❌ Filter Failures: {len(filter_failures)} filters not working correctly")
    lines.append("")

    # Filter Failures (Most Critical)
    if filter_failures:
        lines.append("=" * 80)
        lines.append("🚨 CRITICAL: FILTER FAILURES")
        lines.append("=" * 80)
        lines.append("")
        lines.append("These filters are not working despite passing tests:")
        lines.append("")

        for i, failure in enumerate(filter_failures, 1):
            lines.append(f"{i}. {failure['filter']}")
            lines.append(f"   Problem: {failure['failure']}")
            lines.append(f"   Evidence: {failure['evidence']}")
            lines.append(f"   Expected: {failure['expected']}")
            lines.append("")

        lines.append("🔍 DIAGNOSIS:")
        lines.append("   Filters work in tests but not in production.")
        lines.append("   Possible causes:")
        lines.append("   1. Filters running on wrong email set")
        lines.append("   2. Emails re-fetched after filtering")
        lines.append("   3. Filter integration not working in context_digest.py")
        lines.append("   4. Date parsing issues in production data")
        lines.append("")

    # False Positives
    if false_positives:
        lines.append("=" * 80)
        lines.append("❌ FALSE POSITIVES (Noise Being Featured)")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Found {len(false_positives)} emails that were featured but shouldn't be:")
        lines.append("")

        for i, fp in enumerate(false_positives, 1):
            lines.append(f"{i}. Item #{fp.get('item_number', '?')}")
            lines.append(f"   Featured: {fp['context'][:80]}...")
            lines.append(f"   Subject: {fp['email_subject']}")
            lines.append(f"   Why Wrong: {fp['why_wrong']}")
            lines.append("")

    # False Negatives
    if false_negatives:
        lines.append("=" * 80)
        lines.append("❌ FALSE NEGATIVES (Important Emails Missing)")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Found {len(false_negatives)} emails that should be featured but aren't:")
        lines.append("")

        # Group by category
        by_category = defaultdict(list)
        for fn in false_negatives:
            by_category[fn["category"]].append(fn)

        for category, emails in sorted(by_category.items()):
            lines.append(f"{category} ({len(emails)} missing):")
            lines.append("")

            for email in emails[:5]:  # Show first 5
                lines.append(f"  • {email['subject'][:70]}")
                lines.append(f"    Why important: {email['reasoning'][:60]}")
                lines.append(f"    Priority: {email['priority']}")
                lines.append("")

            if len(emails) > 5:
                lines.append(f"  ... and {len(emails) - 5} more")
                lines.append("")

    # Action Items
    lines.append("=" * 80)
    lines.append("🎯 ACTION ITEMS (Priority Order)")
    lines.append("=" * 80)
    lines.append("")

    lines.append("1. FIX FILTER INTEGRATION (CRITICAL)")
    lines.append("   Problem: Filters not running in production")
    lines.append("   Action: Debug context_digest.py filter integration")
    lines.append("   Check: Cloud Run logs for filter output")
    lines.append("")

    lines.append("2. FIX TIME-DECAY FILTER")
    lines.append("   Problem: Past events (Oct 31) still appearing")
    lines.append("   Action: Verify date parsing with production data")
    lines.append("   Test: Run filter on actual Oct 31 event emails")
    lines.append("")

    lines.append("3. FIX SELF-EMAIL FILTER")
    lines.append("   Problem: ShopQ digest appearing in itself")
    lines.append("   Action: Verify 'Your Inbox --' pattern detection")
    lines.append("   Test: Run filter on actual ShopQ digest email")
    lines.append("")

    lines.append("4. FIX IMPORTANCE CLASSIFICATION")
    lines.append("   Problem: Wrong emails being featured")
    lines.append("   Action: Review importance scoring in context_digest.py")
    lines.append(f"   Examples: {len(false_positives)} noise items featured")
    lines.append("")

    lines.append("5. FIX MISSING EMAILS")
    lines.append("   Problem: Important emails not appearing")
    lines.append("   Action: Lower thresholds for critical/time_sensitive")
    lines.append(f"   Examples: {len(false_negatives)} important emails missing")
    lines.append("")

    # Next Steps
    lines.append("=" * 80)
    lines.append("🔧 DEBUGGING STEPS")
    lines.append("=" * 80)
    lines.append("")
    lines.append("Step 1: Check if filters ran")
    lines.append("  gcloud run services logs read shopq-api --limit 100 | grep 'Phase 1'")
    lines.append("")
    lines.append("Step 2: Test filters on actual data")
    lines.append("  python3 scripts/validate_phase1_filters.py")
    lines.append("")
    lines.append("Step 3: Check digest generation")
    lines.append('  python3 -c "from shopq.digest.context_digest import ContextDigest; ...')
    lines.append("")
    lines.append("Step 4: If filters aren't running, check integration")
    lines.append("  - Verify lines 110-149 in shopq/context_digest.py")
    lines.append("  - Check if emails are being re-fetched after filtering")
    lines.append("  - Verify filter imports are correct")
    lines.append("")

    return "\n".join(lines)


def main():
    print("🔍 Comparing actual vs ideal digest...")
    print()

    # Load data
    all_emails, featured, not_featured = load_user_review()
    featured_items, actual_content = parse_actual_digest()

    print("📊 Data loaded:")
    print(f"  - {len(all_emails)} total emails in ground truth")
    print(f"  - {len(featured)} should be featured")
    print(f"  - {len(not_featured)} should not be featured")
    print(f"  - {len(featured_items)} items in actual digest")
    print()

    # Analyze
    print("🔍 Analyzing gaps...")
    false_positives = identify_false_positives(featured_items, actual_content, not_featured)
    false_negatives = identify_false_negatives(actual_content, featured)
    filter_failures = check_filter_failures(actual_content)

    print(f"  - Found {len(false_positives)} false positives")
    print(f"  - Found {len(false_negatives)} false negatives")
    print(f"  - Found {len(filter_failures)} filter failures")
    print()

    # Generate report
    report = generate_report(false_positives, false_negatives, filter_failures)

    # Output
    print("=" * 80)
    print(report)

    # Save to file
    output_path = Path(__file__).parent.parent / "digest_comparison_report.txt"
    with open(output_path, "w") as f:
        f.write(report)

    print()
    print(f"💾 Saved to: {output_path}")
    print()
    print("🎯 Next: Fix filter integration issues before iterating on classification")


if __name__ == "__main__":
    main()
