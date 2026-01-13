#!/usr/bin/env python3
"""
Test LLM-based digest format analysis with Nov 1 example

This test verifies the LLM-based digest analyzer correctly identifies issues
by comparing actual digest HTML against the ideal format structure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from quality_monitor import QualityMonitor

# Simulated Nov 1 actual digest HTML (numbered list format - from ACTUAL_VS_IDEAL_COMPARISON.md)
NOV1_ACTUAL_DIGEST = """
<html>
<body>
<h2>Your Inbox - Saturday, November 01 at 04:00 PM</h2>

<div class="digest-summary">
1. Security alert ✅
2. AutoPay for Brooklinen ❌
3. Time to vote, make every share count ❌
4. Last chance feedback about Vanguard ❌
5. Appointment Midtown Dental (Nov 7, 2:00 PM) ✅
6. J & V Catch-up (Nov 7, 2:05 PM) ✅
7. J & V Catch-up from yesterday (Oct 31, 2 PM) ❌
8. Check out Drawing Hive ❌
9. A meeting has adjourned ❌

<p>Plus, there are 65 routine notifications.</p>
</div>
</body>
</html>
"""


def test_llm_digest_analysis():
    """Test LLM-based digest format analyzer with Nov 1 example"""

    print("=" * 80)
    print("Testing LLM-Based Digest Format Analyzer with Nov 1 Example")
    print("=" * 80)
    print()

    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set - skipping test")
        print("   Set ANTHROPIC_API_KEY environment variable to run this test")
        return 1

    # Create quality monitor
    monitor = QualityMonitor()

    # Analyze with LLM
    print("Calling Claude API to analyze digest format...")
    print()

    issues = monitor.analyze_digest_format_with_llm(NOV1_ACTUAL_DIGEST)

    print(f"Found {len(issues)} format issues:\n")

    for i, issue in enumerate(issues, 1):
        print(f"{i}. [{issue['severity'].upper()}] {issue['pattern']}")
        print(f"   Category: {issue.get('category', 'digest_format')}")
        print(f"   Evidence: {issue['evidence']}")
        print(f"   Root Cause: {issue['root_cause']}")
        print(f"   Suggested Fix: {issue['suggested_fix']}")
        print()

    # Expected issues from ACTUAL_VS_IDEAL_COMPARISON.md:
    # 1. HIGH - Using numbered list instead of categorized sections (🚨📦📅💼)
    # 2. MEDIUM - Promotional items featured ("vote", "Vanguard survey")
    # 3. MEDIUM - Past events featured ("yesterday", "adjourned")
    # 4. Missing CRITICAL section (only 1/8 critical items featured)
    # 5. Missing TODAY section (deliveries)
    # 6. Missing WORTH KNOWING section

    print("=" * 80)
    print("Expected Issues vs Detected Issues")
    print("=" * 80)
    print()

    expected_issues = [
        "numbered list",  # Should use sections instead
        "categorized sections",  # Missing sections
        "promotional",  # Noise in featured
        "past event",  # Past events featured
        "missing sections",  # Structural issue
    ]

    detected_patterns_lower = [issue["pattern"].lower() for issue in issues]
    all_text_lower = " ".join([str(v).lower() for issue in issues for v in issue.values()])

    print("Expected issues to detect:")
    for exp in expected_issues:
        found = any(exp in p for p in detected_patterns_lower) or exp in all_text_lower
        status = "✅" if found else "❌"
        print(f"  {status} {exp}")

    print()
    print("Detected patterns:")
    for issue in issues:
        print(f"  • [{issue['severity'].upper()}] {issue['pattern']}")

    print()

    # Verify we caught major structural issues
    has_format_issue = any(
        "numbered" in p or "list" in p or "section" in p or "categor" in p
        for p in detected_patterns_lower
    )

    has_content_issue = (
        "promotional" in all_text_lower
        or "past" in all_text_lower
        or "noise" in all_text_lower
        or "vote" in all_text_lower
        or "yesterday" in all_text_lower
    )

    if has_format_issue or has_content_issue:
        print("✅ TEST PASSED: LLM analyzer identified issues in Nov 1 digest")
        if has_format_issue:
            print("   ✅ Detected format/structure issues")
        if has_content_issue:
            print("   ✅ Detected content/categorization issues")
        return 0
    print("❌ TEST FAILED: LLM analyzer did not identify expected issues")
    print(f"   Issues found: {len(issues)}")
    print(f"   Format issue detected: {has_format_issue}")
    print(f"   Content issue detected: {has_content_issue}")
    return 1


if __name__ == "__main__":
    sys.exit(test_llm_digest_analysis())
