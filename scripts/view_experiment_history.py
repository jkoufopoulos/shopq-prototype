"""
View Experiment History

Lists all saved experiments and compares accuracy metrics between runs.

Usage:
    python scripts/view_experiment_history.py [--compare EXP1 EXP2]
"""

import argparse
import json
from pathlib import Path


def load_experiments() -> list[dict]:
    """Load all experiment results from reports/experiments/"""
    experiments_dir = Path(__file__).parent.parent / "reports" / "experiments"

    if not experiments_dir.exists():
        return []

    experiments = []
    for json_file in sorted(experiments_dir.glob("*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
                data["_file"] = json_file.name
                experiments.append(data)
        except Exception as e:
            print(f"Error loading {json_file}: {e}")

    return experiments


def list_experiments(experiments: list[dict]):
    """List all experiments with basic metrics"""
    if not experiments:
        print("No experiments found in reports/experiments/")
        print("Run: python scripts/evaluate_classification_accuracy.py --save-results")
        return

    print("\n" + "=" * 80)
    print("EXPERIMENT HISTORY")
    print("=" * 80)

    print(f"\n{'Date':<20} {'Name':<25} {'Type':<8} {'Import':<8} {'Client':<8} {'Emails':<8}")
    print("-" * 80)

    for exp in experiments:
        timestamp = exp.get("timestamp", "")[:16].replace("T", " ")
        name = exp.get("experiment_name", "unknown")[:24]
        metrics = exp.get("metrics", {})

        type_acc = metrics.get("type_accuracy", 0)
        import_acc = metrics.get("importance_accuracy", 0)
        client_acc = metrics.get("client_label_accuracy", 0)
        num_emails = exp.get("config", {}).get("num_emails", 0)

        print(
            f"{timestamp:<20} {name:<25} {type_acc:>5.1f}%  {import_acc:>5.1f}%  {client_acc:>5.1f}%  {num_emails:>6}"
        )

    print("\n")


def compare_experiments(experiments: list[dict], name1: str, name2: str):
    """Compare two experiments by name"""
    exp1 = None
    exp2 = None

    for exp in experiments:
        if name1.lower() in exp.get("experiment_name", "").lower():
            exp1 = exp
        if name2.lower() in exp.get("experiment_name", "").lower():
            exp2 = exp

    if not exp1:
        print(f"Experiment '{name1}' not found")
        return
    if not exp2:
        print(f"Experiment '{name2}' not found")
        return

    print("\n" + "=" * 60)
    print("EXPERIMENT COMPARISON")
    print("=" * 60)

    m1 = exp1.get("metrics", {})
    m2 = exp2.get("metrics", {})

    print(
        f"\n{'Metric':<25} {exp1['experiment_name'][:15]:<15} {exp2['experiment_name'][:15]:<15} {'Delta':<10}"
    )
    print("-" * 60)

    for field in ["type_accuracy", "importance_accuracy", "client_label_accuracy"]:
        v1 = m1.get(field, 0)
        v2 = m2.get(field, 0)
        delta = v2 - v1
        sign = "+" if delta > 0 else ""

        label = field.replace("_", " ").title()
        print(f"{label:<25} {v1:>5.1f}%         {v2:>5.1f}%         {sign}{delta:>5.1f}%")

    print("\n")

    # Show error pattern changes
    print("Top Error Pattern Changes:")
    print("-" * 60)

    errors1 = {p: c for p, c in exp1.get("top_errors", {}).get("type", [])}
    errors2 = {p: c for p, c in exp2.get("top_errors", {}).get("type", [])}

    all_patterns = set(errors1.keys()) | set(errors2.keys())

    for pattern in sorted(all_patterns, key=lambda p: errors2.get(p, 0) - errors1.get(p, 0)):
        c1 = errors1.get(pattern, 0)
        c2 = errors2.get(pattern, 0)
        if c1 != c2:
            delta = c2 - c1
            sign = "+" if delta > 0 else ""
            print(f"  {pattern}: {c1} -> {c2} ({sign}{delta})")

    print("\n")


def main():
    parser = argparse.ArgumentParser(description="View experiment history")
    parser.add_argument(
        "--compare", nargs=2, metavar=("EXP1", "EXP2"), help="Compare two experiments by name"
    )
    args = parser.parse_args()

    experiments = load_experiments()

    if args.compare:
        compare_experiments(experiments, args.compare[0], args.compare[1])
    else:
        list_experiments(experiments)


if __name__ == "__main__":
    main()
