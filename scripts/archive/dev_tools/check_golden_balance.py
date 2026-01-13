#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter

from tests.golden_set.utils import load_labels


def main() -> None:
    labels = load_labels()
    counts = Counter(label["importance"] for label in labels.values())
    total = sum(counts.values())
    ceiling = max(counts.values()) / total if total else 0.0

    print("Golden set balance summary")
    print(f"Total messages: {total}")
    for key in sorted(counts):
        count = counts[key]
        share = count / total if total else 0.0
        print(f"  {key:>13}: {count:3d} ({share:.1%})")
    print(f"Max class share: {ceiling:.1%}")


if __name__ == "__main__":
    main()
