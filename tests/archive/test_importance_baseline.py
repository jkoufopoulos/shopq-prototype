from __future__ import annotations

from collections import Counter

import pytest

from mailq.classification.importance_classifier import ImportanceClassifier
from tests.fixtures.gds_utils import load_labels, load_messages

GOLDEN_MESSAGES = load_messages()
GOLDEN_LABELS = load_labels()


@pytest.fixture(scope="module")
def importance_classifier() -> ImportanceClassifier:
    return ImportanceClassifier()


@pytest.mark.parametrize(
    "text,email_type,attention,expected",
    [
        (
            "Your login code is 123456. Use this verification code to sign in.",
            "notification",
            "action_required",
            "routine",
        ),
        (
            "AutoPay scheduled: your Metro Power autopay will run tonight.",
            "notification",
            "none",
            "routine",
        ),
        (
            "Weekend highlights newsletter: art fairs, shows, and recaps.",
            "newsletter",
            "none",
            "routine",
        ),
        (
            "Action required by Nov 20: respond by tomorrow to avoid suspension.",
            "notification",
            "action_required",
            "time_sensitive",
        ),
    ],
)
def test_regressions_hold(importance_classifier, text, email_type, attention, expected):
    """Lock critical regression fixes (OTP, autopay, newsletters, deadlines)."""
    assert (
        importance_classifier.classify(text, email_type=email_type, attention=attention) == expected
    )


def test_golden_set_accuracy(importance_classifier):
    """Golden set must stay balanced and match expected importance labels."""
    assert len(GOLDEN_MESSAGES) >= 200
    per_class_totals = Counter(label["importance"] for label in GOLDEN_LABELS.values())

    total = sum(per_class_totals.values())
    assert total == len(GOLDEN_MESSAGES)

    # Class balance guard: no single class over 60% of total
    share_ceiling = max(per_class_totals.values()) / total
    assert share_ceiling <= 0.60

    per_class_correct = Counter()
    misclassified = []

    for message in GOLDEN_MESSAGES:
        expected = GOLDEN_LABELS[message["id"]]["importance"]
        text = f"{message['subject']} {message['snippet']}"
        predicted = importance_classifier.classify(
            text,
            email_type=message.get("type"),
            attention=message.get("attention"),
        )
        if predicted == expected:
            per_class_correct[expected] += 1
        else:
            misclassified.append(
                (
                    message["id"],
                    expected,
                    predicted,
                    message["subject"],
                )
            )

    if misclassified:
        details = "\n".join(
            f"{mid}: expected {exp} got {got} — {subject}"
            for mid, exp, got, subject in misclassified[:5]
        )
        pytest.fail(f"Golden set drift detected ({len(misclassified)} errors):\n{details}")

    for klass, total_count in per_class_totals.items():
        assert per_class_correct[klass] == total_count, (
            f"{klass} accuracy regressed ({per_class_correct[klass]}/{total_count})"
        )
