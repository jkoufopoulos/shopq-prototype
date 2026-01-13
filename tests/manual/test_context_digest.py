"""

from __future__ import annotations

Test Context Digest end-to-end with fixtures

Tests all three scenarios:
1. Quiet inbox (8 emails)
2. Busy inbox with critical notification (50 emails)
3. Email storm (200 emails)
"""

import sys

sys.path.insert(0, "/Users/justinkoufopoulos/Projects/mailq-prototype")

from fixtures.test_busy_inbox import BUSY_INBOX_EMAILS, EXPECTED_CHARACTERISTICS_BUSY
from fixtures.test_email_storm import EMAIL_STORM_EMAILS, EXPECTED_CHARACTERISTICS_EMAIL_STORM
from fixtures.test_quiet_inbox import EXPECTED_CHARACTERISTICS_QUIET, QUIET_INBOX_EMAILS

from mailq.digest.context_digest import ContextDigest


def test_quiet_inbox():
    """Test with quiet inbox fixture (8 emails)"""
    print("\n" + "=" * 60)
    print("TEST 1: Quiet Inbox (8 emails)")
    print("=" * 60)

    digest = ContextDigest(verbose=True)
    result = digest.generate(QUIET_INBOX_EMAILS)

    print("\n📊 Results:")
    print(
        f"   Word count: {result['word_count']} (expected: {EXPECTED_CHARACTERISTICS_QUIET['word_count']})"
    )
    print(f"   Entities extracted: {result['entities_count']}")
    print(
        f"   Featured: {result['featured_count']} (expected: {EXPECTED_CHARACTERISTICS_QUIET['featured_entities']})"
    )
    print(f"   Critical: {result['critical_count']}")
    print(f"   Time-sensitive: {result['time_sensitive_count']}")
    print(f"   Routine: {result['routine_count']}")
    print(f"   Verified: {result['verified']}")

    if result.get("errors"):
        print("\n⚠️  Verification errors:")
        for error in result["errors"]:
            print(f"   - {error}")

    print("\n📧 Generated Digest:")
    print(result["text"])

    # Save HTML
    output_path = "test_output_quiet.html"
    digest.generate_and_save(QUIET_INBOX_EMAILS, output_path)

    return result


def test_busy_inbox():
    """Test with busy inbox fixture (50 emails)"""
    print("\n" + "=" * 60)
    print("TEST 2: Busy Inbox (50 emails, 1 critical)")
    print("=" * 60)

    digest = ContextDigest(verbose=True)
    result = digest.generate(BUSY_INBOX_EMAILS)

    print("\n📊 Results:")
    print(
        f"   Word count: {result['word_count']} (expected: {EXPECTED_CHARACTERISTICS_BUSY['word_count']})"
    )
    print(f"   Entities extracted: {result['entities_count']}")
    print(
        f"   Featured: {result['featured_count']} (expected: {EXPECTED_CHARACTERISTICS_BUSY['featured_entities']})"
    )
    print(
        f"   Critical: {result['critical_count']} (expected: {EXPECTED_CHARACTERISTICS_BUSY['critical_items']})"
    )
    print(f"   Time-sensitive: {result['time_sensitive_count']}")
    print(f"   Routine: {result['routine_count']}")
    print(f"   Noise breakdown: {result['noise_breakdown']}")
    print(f"   Verified: {result['verified']}")

    if result.get("errors"):
        print("\n⚠️  Verification errors:")
        for error in result["errors"]:
            print(f"   - {error}")

    print("\n📧 Generated Digest:")
    print(result["text"])

    # Save HTML
    output_path = "test_output_busy.html"
    digest.generate_and_save(BUSY_INBOX_EMAILS, output_path)

    # Check that critical item surfaced
    if result["critical_count"] > 0:
        print("\n✅ Critical item detected and should be featured first")

    return result


def test_email_storm():
    """Test with email storm fixture (200 emails)"""
    print("\n" + "=" * 60)
    print("TEST 3: Email Storm (200 emails, 2 critical)")
    print("=" * 60)

    digest = ContextDigest(verbose=True)
    result = digest.generate(EMAIL_STORM_EMAILS)

    print("\n📊 Results:")
    print(
        f"   Word count: {result['word_count']} (expected: {EXPECTED_CHARACTERISTICS_EMAIL_STORM['word_count']})"
    )
    print(f"   Entities extracted: {result['entities_count']}")
    print(
        f"   Featured: {result['featured_count']} (expected: {EXPECTED_CHARACTERISTICS_EMAIL_STORM['featured_entities']})"
    )
    print(
        f"   Critical: {result['critical_count']} (expected: {EXPECTED_CHARACTERISTICS_EMAIL_STORM['critical_items']})"
    )
    print(f"   Time-sensitive: {result['time_sensitive_count']}")
    print(f"   Routine: {result['routine_count']}")
    print(f"   Noise breakdown: {result['noise_breakdown']}")
    print(f"   Verified: {result['verified']}")

    if result.get("errors"):
        print("\n⚠️  Verification errors:")
        for error in result["errors"]:
            print(f"   - {error}")

    print("\n📧 Generated Digest:")
    print(result["text"])

    # Save HTML
    output_path = "test_output_storm.html"
    digest.generate_and_save(EMAIL_STORM_EMAILS, output_path)

    # Check compression
    min_words, max_words = EXPECTED_CHARACTERISTICS_EMAIL_STORM["word_count"]
    if result["word_count"] <= max_words:
        print(f"\n✅ Compression successful: {result['word_count']} ≤ {max_words} words")
    else:
        print(f"\n⚠️  Compression may need tuning: {result['word_count']} > {max_words} words")

    return result


def run_all_tests():
    """Run all three test scenarios"""
    print("\n🚀 Starting Context Digest End-to-End Tests")
    print("=" * 60)

    results = []

    try:
        # Test 1: Quiet inbox
        result1 = test_quiet_inbox()
        results.append(("Quiet", result1))
    except Exception as e:
        print(f"\n❌ Test 1 failed: {e}")
        import traceback

        traceback.print_exc()

    try:
        # Test 2: Busy inbox
        result2 = test_busy_inbox()
        results.append(("Busy", result2))
    except Exception as e:
        print(f"\n❌ Test 2 failed: {e}")
        import traceback

        traceback.print_exc()

    try:
        # Test 3: Email storm
        result3 = test_email_storm()
        results.append(("Storm", result3))
    except Exception as e:
        print(f"\n❌ Test 3 failed: {e}")
        import traceback

        traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for name, result in results:
        print(f"\n{name} inbox:")
        print(f"   Word count: {result['word_count']}")
        print(f"   Entities: {result['entities_count']}")
        print(f"   Featured: {result['featured_count']}")
        print(f"   Verified: {'✅' if result['verified'] else '❌'}")

    print("\n🎉 All tests complete!")
    print("\nGenerated files:")
    print("   - test_output_quiet.html")
    print("   - test_output_busy.html")
    print("   - test_output_storm.html")


if __name__ == "__main__":
    run_all_tests()
