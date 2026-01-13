import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

LOG_DIR = Path("logs/bridge_mode")
BUDGET_PATH = Path("config/budgets.yaml")
OTP_PATTERNS = ["verification code", "otp", "login code", "one-time password"]


def load_logs() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in LOG_DIR.glob("*.jsonl"):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
    return entries


def compute_metrics(entries: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "critical_predicted": 0,
        "critical_actual": 0,
        "critical_tp": 0,
        "otp_misfires": 0,
        "event_noise": 0,
        "event_total": 0,
        "latencies": [],
        "costs": [],
    }

    for entry in entries:
        bridge = entry.get("bridge_importance")
        pattern = entry.get("pattern_importance")
        subject = entry.get("subject", "").lower()

        if bridge == "critical":
            metrics["critical_predicted"] = metrics["critical_predicted"] + 1
        if pattern == "critical":
            metrics["critical_actual"] = metrics["critical_actual"] + 1
        if bridge == "critical" and pattern == "critical":
            metrics["critical_tp"] = metrics["critical_tp"] + 1

        if any(pattern in subject for pattern in OTP_PATTERNS) and bridge == "critical":
            metrics["otp_misfires"] = metrics["otp_misfires"] + 1

        if entry.get("email_type") == "event":
            metrics["event_total"] = metrics["event_total"] + 1
            if bridge == "routine":
                metrics["event_noise"] = metrics["event_noise"] + 1

        latency = entry.get("processing_time_ms")
        if latency is not None:
            metrics["latencies"].append(latency)  # type: ignore[union-attr]

        cost = entry.get("cost_usd")
        if cost is not None:
            metrics["costs"].append(cost)  # type: ignore[union-attr]

    return metrics


def summarize(metrics: dict, budgets: dict) -> tuple[list[str], dict]:
    failures = []
    perfs = {}

    pred = metrics["critical_predicted"]
    actual = metrics["critical_actual"]
    tp = metrics["critical_tp"]
    precision = tp / pred if pred else 1.0
    recall = tp / actual if actual else 1.0
    precision_budget = budgets["budgets"]["critical_precision"]
    recall_budget = budgets["budgets"]["critical_recall"]
    perfs["critical_precision"] = precision
    perfs["critical_recall"] = recall
    if precision < precision_budget:
        failures.append(f"critical precision {precision:.3f} < budget {precision_budget:.3f}")
    if recall < recall_budget:
        failures.append(f"critical recall {recall:.3f} < budget {recall_budget:.3f}")

    perfs["otp_misfires"] = metrics["otp_misfires"]
    otp_budget = budgets["budgets"]["otp_misfires_max"]
    if metrics["otp_misfires"] > otp_budget:
        failures.append(f"OTP misfires {metrics['otp_misfires']} > budget {otp_budget}")

    event_noise = metrics["event_noise"] / metrics["event_total"] if metrics["event_total"] else 0.0
    perfs["event_noise"] = event_noise
    event_noise_budget = budgets["budgets"]["event_noise_max"]
    if event_noise > event_noise_budget:
        failures.append(f"Event noise {event_noise:.3f} > budget {event_noise_budget}")

    latency_budget = budgets["budgets"]["p95_latency_ms"]
    if metrics["latencies"]:
        sorted_latencies = sorted(metrics["latencies"])
        idx = max(0, int(0.95 * len(sorted_latencies)) - 1)
        perfs["p95_latency_ms"] = sorted_latencies[idx]
        if perfs["p95_latency_ms"] > latency_budget:
            failures.append(f"P95 latency {perfs['p95_latency_ms']}ms > budget {latency_budget}ms")
    else:
        perfs["p95_latency_ms"] = 0

    cost_budget = budgets["budgets"]["cost_per_email_usd"]
    if metrics["costs"]:
        perfs["cost_per_email_usd"] = sum(metrics["costs"]) / len(metrics["costs"])
    else:
        perfs["cost_per_email_usd"] = 0.0
    if perfs["cost_per_email_usd"] > cost_budget:
        failures.append(
            f"Cost per email ${perfs['cost_per_email_usd']:.6f} > budget ${cost_budget:.6f}"
        )

    return failures, perfs


def main() -> int:
    if not LOG_DIR.exists():
        print("No bridge_mode logs found (logs/bridge_mode). Skipping metrics.")
        return 0

    budgets = yaml.safe_load(BUDGET_PATH.read_text(encoding="utf-8"))
    logs = load_logs()
    metrics = compute_metrics(logs)
    failures, perfs = summarize(metrics, budgets)

    print("Bridge mode metrics:")
    for key, value in perfs.items():
        print(f"  {key}: {value}")

    print("Budgets:", budgets["budgets"])

    if failures:
        print("\nBudget violations:")
        for failure in failures:
            print("  -", failure)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
