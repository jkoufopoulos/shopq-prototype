#!/usr/bin/env python3
"""
Test digest format analyzer with Nov 1 example

This test verifies the digest format analyzer correctly identifies the issues
from the Nov 1 digest that were documented in ACTUAL_VS_IDEAL_COMPARISON.md
"""

from __future__ import annotations

import sys

from digest_format_analyzer import DigestFormatAnalyzer

# Simulated Nov 1 actual digest HTML (numbered list format)
NOV1_ACTUAL_DIGEST = """
<html>
<body>
<h2>Your Inbox - Saturday, November 01 at 04:00 PM</h2>

1. Security alert
2. AutoPay for Brooklinen
3. Time to vote, make every share count
4. Last chance feedback about Vanguard
5. Appointment Midtown Dental (Nov 7, 2:00 PM)
6. J & V Catch-up (Nov 7, 2:05 PM)
7. J & V Catch-up from yesterday (Oct 31, 2 PM)
8. Check out Drawing Hive
9. A meeting has adjourned

<p>Plus, there are 65 routine notifications.</p>
</body>
</html>
"""

# Simulated input emails for Nov 1
NOV1_INPUT_EMAILS = [
    {"subject": "Security alert", "importance": "critical"},
    {"subject": "AutoPay for Brooklinen", "importance": "routine"},
    {"subject": "Time to vote, make every share count", "importance": "routine"},
    {"subject": "Last chance feedback about Vanguard", "importance": "routine"},
    {"subject": "Appointment Midtown Dental (Nov 7, 2:00 PM)", "importance": "time_sensitive"},
    {"subject": "J & V Catch-up (Nov 7, 2:05 PM)", "importance": "time_sensitive"},
    {"subject": "J & V Catch-up from yesterday (Oct 31, 2 PM)", "importance": "routine"},
    {"subject": "Check out Drawing Hive", "importance": "routine"},
    {"subject": "A meeting has adjourned", "importance": "routine"},
]


def test_nov1_digest():
    """Test digest format analyzer with Nov 1 example"""

    print("=" * 80)
    print("Testing Digest Format Analyzer with Nov 1 Example")
    print("=" * 80)
    print()

    analyzer = DigestFormatAnalyzer()

    # Analyze
    issues = analyzer.analyze_digest_html(NOV1_ACTUAL_DIGEST, NOV1_INPUT_EMAILS)

    print(f"Found {len(issues)} format issues:\n")

    for i, issue in enumerate(issues, 1):
        print(f"{i}. [{issue['severity'].upper()}] {issue['pattern']}")
        print(f"   Category: {issue['category']}")
        print(f"   Evidence: {issue['evidence']}")
        print(f"   Root Cause: {issue['root_cause']}")
        print(f"   Suggested Fix: {issue['suggested_fix']}")
        print()

    # Expected issues:
    # 1. HIGH - Missing categorized sections (using numbered list)
    # 2. MEDIUM - Promotional items in featured ("vote", "Vanguard")
    # 3. MEDIUM - Past events in featured ("yesterday", "adjourned")

    print("=" * 80)
    print("Expected Issues vs Detected Issues")
    print("=" * 80)
    print()

    expected_issues = [
        "Missing categorized sections",
        "Promotional/noise items featured",
        "Past/concluded events featured",
    ]

    detected_patterns = [issue["pattern"] for issue in issues]

    print("Expected:")
    for exp in expected_issues:
        found = any(exp.lower() in p.lower() for p in detected_patterns)
        status = "✅" if found else "❌"
        print(f"  {status} {exp}")

    print()
    print("Detected:")
    for pattern in detected_patterns:
        print(f"  ✅ {pattern}")

    print()

    # Verify we caught the major issues
    has_format_issue = any(
        "numbered list" in issue["pattern"].lower() or "missing" in issue["pattern"].lower()
        for issue in issues
    )
    has_noise_issue = any(
        "promotional" in issue["pattern"].lower() or "noise" in issue["pattern"].lower()
        for issue in issues
    )
    has_past_event_issue = any(
        "past" in issue["pattern"].lower() or "concluded" in issue["pattern"].lower()
        for issue in issues
    )

    if has_format_issue and (has_noise_issue or has_past_event_issue):
        print("✅ TEST PASSED: Format analyzer correctly identified major issues")
        return 0
    print("❌ TEST FAILED: Format analyzer missed critical issues")
    if not has_format_issue:
        print("  - Missing: Format structure issue (numbered list vs sections)")
    if not has_noise_issue:
        print("  - Missing: Noise/promotional items issue")
    if not has_past_event_issue:
        print("  - Missing: Past events issue")
    return 1


if __name__ == "__main__":
    sys.exit(test_nov1_digest())
