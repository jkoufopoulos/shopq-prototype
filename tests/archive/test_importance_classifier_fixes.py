"""

from __future__ import annotations

Test cases for importance classifier quality fixes

Tests for issues #13, #14, #15:
- Issue #13: Shipment notifications over-classified as time-sensitive
- Issue #14: Policy updates misclassified using medical_claims pattern
- Issue #15: Promotional emails with action_required elevated incorrectly
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from mailq.classification.importance_classifier import ImportanceClassifier


def test_issue_13_shipment_notifications():
    """
    Issue #13: Shipment notifications should be split by urgency

    FYI updates → Routine
    Upcoming deliveries → Time-sensitive
    Urgent delivery issues → Critical
    """
    print("\n" + "=" * 80)
    print("TEST ISSUE #13: Shipment Notification Classification")
    print("=" * 80)

    classifier = ImportanceClassifier()

    test_cases = [
        # ROUTINE: Passive FYI notifications
        {
            "text": "Your Amazon order has shipped",
            "email_type": "notification",
            "expected": "routine",
            "description": "Order shipped notification (FYI only)",
        },
        {
            "text": "Package delivered: Your order #12345",
            "email_type": "notification",
            "expected": "routine",
            "description": "Delivery confirmation (FYI only)",
        },
        {
            "text": "Here's your tracking number: 1Z999AA10123456784",
            "email_type": "notification",
            "expected": "routine",
            "description": "Tracking number provided (FYI only)",
        },
        {
            "text": "Your order has been delivered to your front door",
            "email_type": "notification",
            "expected": "routine",
            "description": "Delivered notification (FYI only)",
        },
        # TIME-SENSITIVE: Upcoming deliveries
        {
            "text": "Your package is arriving tomorrow",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Package arriving soon (useful to know)",
        },
        {
            "text": "Estimated delivery: Thursday",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Upcoming delivery date (useful to know)",
        },
        {
            "text": "Your order is on its way",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Package in transit (useful to know)",
        },
        # CRITICAL: Urgent delivery issues
        {
            "text": "Package arriving today - signature required",
            "email_type": "notification",
            "expected": "critical",
            "description": "Arriving today with action needed (critical)",
        },
        {
            "text": "Delivery attempted - nobody home",
            "email_type": "notification",
            "expected": "critical",
            "description": "Failed delivery attempt (critical)",
        },
        {
            "text": "Out for delivery today",
            "email_type": "notification",
            "expected": "critical",
            "description": "Arriving today (critical)",
        },
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        result = classifier.classify(
            test["text"], email_type=test["email_type"], attention=test.get("attention")
        )

        status = "✅" if result == test["expected"] else "❌"
        if result == test["expected"]:
            passed += 1
        else:
            failed += 1

        print(f"\n{status} {test['description']}")
        print(f'   Text: "{test["text"]}"')
        print(f"   Expected: {test['expected']}, Got: {result}")

    print(f"\n{'=' * 80}")
    print(f"Issue #13 Results: {passed} passed, {failed} failed")
    print(f"{'=' * 80}")

    return failed == 0


def test_issue_14_policy_updates():
    """
    Issue #14: Generic policy updates misclassified as medical

    Medical/insurance policies → Time-sensitive
    Generic privacy/terms policies → Routine
    """
    print("\n" + "=" * 80)
    print("TEST ISSUE #14: Policy Update Classification")
    print("=" * 80)

    classifier = ImportanceClassifier()

    test_cases = [
        # ROUTINE: Generic policy updates
        {
            "text": "We've updated our privacy policy",
            "email_type": "notification",
            "expected": "routine",
            "description": "Privacy policy update (routine)",
        },
        {
            "text": "Meta Privacy Policy Changes",
            "email_type": "notification",
            "expected": "routine",
            "description": "Social media privacy update (routine)",
        },
        {
            "text": "Terms of Service Update",
            "email_type": "notification",
            "expected": "routine",
            "description": "ToS update (routine)",
        },
        {
            "text": "Updated Privacy - What's Changed",
            "email_type": "notification",
            "expected": "routine",
            "description": "Privacy changes notification (routine)",
        },
        # TIME-SENSITIVE: Medical/insurance policies
        {
            "text": "Your health insurance policy has been updated",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Health insurance policy (time-sensitive)",
        },
        {
            "text": "Important: Insurance policy renewal",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Insurance policy renewal (time-sensitive)",
        },
        {
            "text": "Medical claim submitted for review",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Medical claim status (time-sensitive)",
        },
        {
            "text": "Your insurance claim has been processed",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Insurance claim processed (time-sensitive)",
        },
        {
            "text": "EOB - Explanation of Benefits",
            "email_type": "notification",
            "expected": "time_sensitive",
            "description": "Medical EOB (time-sensitive)",
        },
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        result = classifier.classify(
            test["text"], email_type=test["email_type"], attention=test.get("attention")
        )

        status = "✅" if result == test["expected"] else "❌"
        if result == test["expected"]:
            passed += 1
        else:
            failed += 1

        print(f"\n{status} {test['description']}")
        print(f'   Text: "{test["text"]}"')
        print(f"   Expected: {test['expected']}, Got: {result}")

    print(f"\n{'=' * 80}")
    print(f"Issue #14 Results: {passed} passed, {failed} failed")
    print(f"{'=' * 80}")

    return failed == 0


def test_issue_15_promotional_action_required():
    """
    Issue #15: Promotional emails with action_required should stay routine

    Promotions with vague urgency → Routine
    Promotions with concrete deadlines → Time-sensitive
    """
    print("\n" + "=" * 80)
    print("TEST ISSUE #15: Promotional Email Classification")
    print("=" * 80)

    classifier = ImportanceClassifier()

    test_cases = [
        # ROUTINE: Marketing with vague urgency
        {
            "text": "URGENT: Holiday Season Essentials",
            "email_type": "promotion",
            "attention": "action_required",
            "expected": "routine",
            "description": "Promotional urgency without deadline (routine)",
        },
        {
            "text": "Vote for Lower Fees!",
            "email_type": "promotion",
            "attention": "action_required",
            "expected": "routine",
            "description": "Marketing CTA (routine)",
        },
        {
            "text": "Don't miss out - Limited Time Offer",
            "email_type": "newsletter",
            "attention": "action_required",
            "expected": "routine",
            "description": "Newsletter with marketing urgency (routine)",
        },
        {
            "text": "Act now - Special discount inside",
            "email_type": "promotion",
            "expected": "routine",
            "description": "Generic promotional urgency (routine)",
        },
        {
            "text": "Time sensitive offer for you",
            "email_type": "promotion",
            "expected": "routine",
            "description": "Vague time-sensitive marketing (routine)",
        },
        # TIME-SENSITIVE: Promotions with concrete deadlines
        {
            "text": "Sale ends today - 50% off everything",
            "email_type": "promotion",
            "expected": "time_sensitive",
            "description": "Sale ending today (time-sensitive)",
        },
        {
            "text": "Your coupon expires today",
            "email_type": "promotion",
            "expected": "time_sensitive",
            "description": "Coupon expiring today (time-sensitive)",
        },
        {
            "text": "Flash sale - deadline today at midnight",
            "email_type": "promotion",
            "expected": "time_sensitive",
            "description": "Concrete deadline today (time-sensitive)",
        },
        # TIME-SENSITIVE: Non-promotional action_required
        {
            "text": "Action required: Confirm your account",
            "email_type": "notification",
            "attention": "action_required",
            "expected": "time_sensitive",
            "description": "Non-promotional action required (time-sensitive)",
        },
        {
            "text": "Please respond by Friday",
            "email_type": "message",
            "attention": "action_required",
            "expected": "time_sensitive",
            "description": "Non-promotional response needed (time-sensitive)",
        },
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        result = classifier.classify(
            test["text"], email_type=test["email_type"], attention=test.get("attention")
        )

        status = "✅" if result == test["expected"] else "❌"
        if result == test["expected"]:
            passed += 1
        else:
            failed += 1

        print(f"\n{status} {test['description']}")
        print(f'   Text: "{test["text"]}"')
        print(f"   Expected: {test['expected']}, Got: {result}")

    print(f"\n{'=' * 80}")
    print(f"Issue #15 Results: {passed} passed, {failed} failed")
    print(f"{'=' * 80}")

    return failed == 0


def run_all_tests():
    """Run all test suites and report results"""
    print("\n" + "🧪 " + "=" * 78)
    print("RUNNING IMPORTANCE CLASSIFIER QUALITY FIX TESTS")
    print("=" * 80 + "\n")

    results = {
        "Issue #13 (Shipment)": test_issue_13_shipment_notifications(),
        "Issue #14 (Policy)": test_issue_14_policy_updates(),
        "Issue #15 (Promotional)": test_issue_15_promotional_action_required(),
    }

    print("\n" + "📊 " + "=" * 78)
    print("FINAL RESULTS")
    print("=" * 80)

    all_passed = True
    for issue, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {issue}")
        if not passed:
            all_passed = False

    print("=" * 80)

    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    print("\n❌ Some tests failed - review output above")
    return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
