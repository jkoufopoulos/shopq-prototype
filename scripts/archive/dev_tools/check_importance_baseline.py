#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.golden_set.utils import load_labels, load_messages  # type: ignore  # noqa: E402

from mailq.classification.importance_classifier import (
    ImportanceClassifier,  # type: ignore  # noqa: E402
)

BASELINE_PATH = Path("eval/baseline.json")
FLOAT_EPSILON = 1e-9


@dataclass(frozen=True)
class Metrics:
    generated_at: str
    total_messages: int
    class_distribution: dict[str, int]
    overall_accuracy: float
    per_class_accuracy: dict[str, float]
    confusion: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "total_messages": self.total_messages,
            "class_distribution": self.class_distribution,
            "overall_accuracy": self.overall_accuracy,
            "per_class_accuracy": self.per_class_accuracy,
            "confusion": self.confusion,
        }


def _compute_metrics() -> Metrics:
    classifier = ImportanceClassifier()
    messages = load_messages()
    labels = load_labels()

    confusion = defaultdict(int)
    totals = Counter()
    correct = Counter()

    for message in messages:
        expected = labels[message["id"]]["importance"]
        text = f"{message['subject']} {message['snippet']}"
        predicted = classifier.classify(
            text,
            email_type=message.get("type"),
            attention=message.get("attention"),
        )
        totals[expected] += 1
        if predicted == expected:
            correct[expected] += 1
        confusion[f"{expected}->{predicted}"] += 1

    total_messages = len(messages)
    overall_accuracy = sum(correct.values()) / total_messages if total_messages else 0.0

    per_class_accuracy = {}
    for klass, count in totals.items():
        per_class_accuracy[klass] = correct[klass] / count if count else 0.0

    return Metrics(
        generated_at="",
        total_messages=total_messages,
        class_distribution={k: int(v) for k, v in totals.items()},
        overall_accuracy=overall_accuracy,
        per_class_accuracy=per_class_accuracy,
        confusion=dict(confusion),
    )


def _float_equal(lhs: float, rhs: float, *, eps: float = FLOAT_EPSILON) -> bool:
    return math.isclose(lhs, rhs, rel_tol=eps, abs_tol=eps)


def _compare_dicts(lhs: dict, rhs: dict) -> Iterable[str]:
    keys = sorted(set(lhs) | set(rhs))
    for key in keys:
        if key not in lhs:
            yield f"Missing key in current metrics: {key}"
            continue
        if key not in rhs:
            yield f"Extra key in current metrics: {key}"
            continue
        if lhs[key] != rhs[key]:
            yield f"Mismatch for {key}: expected {rhs[key]!r}, got {lhs[key]!r}"


def _compare_metrics(current: Metrics, baseline: Metrics) -> Iterable[str]:
    if current.total_messages != baseline.total_messages:
        yield (
            "Total messages differ: "
            f"expected {baseline.total_messages}, got {current.total_messages}"
        )

    yield from _compare_dicts(current.class_distribution, baseline.class_distribution)
    yield from _compare_dicts(current.confusion, baseline.confusion)

    if not _float_equal(current.overall_accuracy, baseline.overall_accuracy):
        yield (
            f"Overall accuracy differs: expected {baseline.overall_accuracy:.6f}, "
            f"got {current.overall_accuracy:.6f}"
        )

    for klass in set(current.per_class_accuracy) | set(baseline.per_class_accuracy):
        curr_value = current.per_class_accuracy.get(klass)
        base_value = baseline.per_class_accuracy.get(klass)
        if curr_value is None or base_value is None:
            yield f"Per-class accuracy missing for {klass}"
            continue
        if not _float_equal(curr_value, base_value):
            yield (f"Accuracy drift for {klass}: expected {base_value:.6f}, got {curr_value:.6f}")


def _load_metrics(path: Path) -> Metrics:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Metrics(
        generated_at=data.get("generated_at", ""),
        total_messages=data["total_messages"],
        class_distribution=data["class_distribution"],
        overall_accuracy=data["overall_accuracy"],
        per_class_accuracy=data["per_class_accuracy"],
        confusion=data["confusion"],
    )


def _write_metrics(path: Path, metrics: Metrics) -> None:
    payload = metrics.to_dict()
    payload["generated_at"] = payload["generated_at"] or ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check golden-set importance baseline drift.")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Overwrite baseline.json with current metrics (use intentionally).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BASELINE_PATH,
        help="Path to baseline metrics JSON (default: eval/baseline.json).",
    )
    args = parser.parse_args()

    current = _compute_metrics()

    if args.update:
        _write_metrics(args.baseline, current)
        print(f"Baseline updated at {args.baseline}")
        return 0

    if not args.baseline.exists():
        print(
            f"Baseline file not found at {args.baseline}. Run with --update to create it.",
            file=sys.stderr,
        )
        return 1

    baseline = _load_metrics(args.baseline)
    drifts = list(_compare_metrics(current, baseline))
    if drifts:
        print("Golden set regression detected:")
        for drift in drifts:
            print(f"  - {drift}")
        print(
            "\nRun `scripts/check_importance_baseline.py --update` only if you "
            "intentionally accept the new behavior."
        )
        return 1

    print("Golden set check passed: metrics match eval/baseline.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
