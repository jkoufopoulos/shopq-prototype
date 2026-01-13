# ruff: noqa
"""
Generate error report organized by error SOURCE.

Error sources:
1. Fix LLM - GDS is correct, LLM needs improvement
2. Fix GDS - GDS label appears incorrect
3. Review Needed - Genuinely ambiguous cases

This helps prioritize what to fix next.
"""

import csv
import json
from pathlib import Path
from typing import Literal

ErrorSource = Literal["fix_llm", "fix_gds", "review_needed"]


# Known patterns where GDS is correct and LLM needs fixing
FIX_LLM_PATTERNS = {
    "type": {
        # Shipping/billing emails that LLM misclassifies as notification
        ("notification", "receipt"): {
            "signals": [
                "shipped",
                "shipment",
                "tracking",
                "delivery",
                "bill",
                "invoice",
                "autopay",
                "statement",
                "payment scheduled",
            ],
            "reason": "LLM sees 'update/status' language, misses order/billing lifecycle",
        },
        # Event lineup marketing that LLM misclassifies as event
        ("event", "newsletter"): {
            "signals": ["event lineup", "personalized lineup", "trending events"],
            "reason": "LLM sees 'event' keyword, misses marketing context",
        },
        # Review requests misclassified
        ("receipt", "notification"): {
            "signals": ["recently bought", "tell us", "review"],
            "reason": "Review requests are notifications, not receipts",
        },
    },
    "importance": {
        # Shipping over-upgraded to time_sensitive
        ("time_sensitive", "routine"): {
            "signals": ["shipped", "in transit", "on the way"],
            "reason": "Shipping updates without delivery date are routine",
        },
    },
    "client_label": {
        # Billing going to everything-else instead of receipts
        ("everything-else", "receipts"): {
            "signals": ["autopay", "bill ready", "statement", "invoice"],
            "reason": "Billing lifecycle should go to receipts",
        },
        # Action-required signals being missed
        ("everything-else", "action-required"): {
            "signals": ["flight", "check in", "security alert", "card waiting", "activate"],
            "reason": "Action-required signals being missed",
        },
    },
}


def determine_error_source(
    error_type: str, llm_decision: str, gds_decision: str, subject: str, snippet: str
) -> tuple[ErrorSource, str]:
    """
    Determine the source of the error.

    Returns:
        tuple: (error_source, reason)
    """
    text = (subject + " " + snippet).lower()

    # Check known FIX_LLM patterns
    pattern_info = FIX_LLM_PATTERNS.get(error_type, {}).get((llm_decision, gds_decision))
    if pattern_info:
        signals = pattern_info["signals"]
        matching = [s for s in signals if s.lower() in text]
        if matching:
            return "fix_llm", f"{pattern_info['reason']} (signals: {', '.join(matching[:3])})"
        return "fix_llm", pattern_info["reason"]

    # Known ambiguous cases
    ambiguous_patterns = [
        # Event vs newsletter for listserv emails
        (error_type == "type" and gds_decision == "event" and "listserv" in text.lower()),
        # Calendar invites that could be events or messages
        (error_type == "type" and "calendar" in text and gds_decision in ["event", "message"]),
        # Importance for marketing events
        (error_type == "importance" and "event" in text and "marketing" in text),
    ]

    if any(ambiguous_patterns):
        return "review_needed", "Genuinely ambiguous case"

    # Default: assume LLM needs fixing (most common case)
    return "fix_llm", "LLM classification doesn't match taxonomy"


def load_errors(csv_path: str) -> list[dict]:
    """Load errors from CSV file."""
    errors = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            errors.append(row)
    return errors


def generate_source_report(results: dict, experiments_dir: Path) -> str:
    """Generate error report organized by source."""
    output_lines = []

    # Header
    output_lines.append("# Error Report by Source")
    output_lines.append(f"**Experiment:** {results.get('experiment_name', 'unknown')}")
    output_lines.append(f"**Timestamp:** {results.get('timestamp', 'unknown')}")
    output_lines.append(f"**Git Commit:** {results.get('git_commit', 'unknown')}")
    output_lines.append("")

    # Metrics
    metrics = results.get("metrics", {})
    output_lines.append("## Accuracy Metrics")
    output_lines.append(f"- Type: {metrics.get('type_accuracy', 0):.1f}%")
    output_lines.append(f"- Importance: {metrics.get('importance_accuracy', 0):.1f}%")
    output_lines.append(f"- Client Label: {metrics.get('client_label_accuracy', 0):.1f}%")
    output_lines.append("")

    # Categorize all errors by source
    errors_by_source: dict[ErrorSource, list[dict]] = {
        "fix_llm": [],
        "fix_gds": [],
        "review_needed": [],
    }

    error_files = results.get("error_csv_files", {})

    for error_type in ["type", "importance", "client_label"]:
        csv_path = error_files.get(error_type)
        if not csv_path or not Path(csv_path).exists():
            continue

        errors = load_errors(csv_path)
        for error in errors:
            llm = error.get("predicted", "")
            gds = error.get("actual", "")
            subject = error.get("subject", "")
            snippet = error.get("snippet", "")

            source, reason = determine_error_source(error_type, llm, gds, subject, snippet)

            error["_error_type"] = error_type
            error["_source_reason"] = reason
            errors_by_source[source].append(error)

    # Summary table
    output_lines.append("## Summary by Source")
    output_lines.append("")
    output_lines.append("| Source | Count | Action |")
    output_lines.append("|--------|-------|--------|")
    output_lines.append(
        f"| **Fix LLM** | {len(errors_by_source['fix_llm'])} | Update prompt rules |"
    )
    output_lines.append(
        f"| **Fix GDS** | {len(errors_by_source['fix_gds'])} | Correct ground truth |"
    )
    output_lines.append(
        f"| **Review Needed** | {len(errors_by_source['review_needed'])} | Human judgment |"
    )
    output_lines.append("")

    # Detailed sections
    output_lines.append("---")
    output_lines.append("")
    output_lines.append("# 1. FIX LLM (Update Prompt)")
    output_lines.append("")

    if errors_by_source["fix_llm"]:
        # Group by error type and pattern
        by_type_pattern: dict[str, dict[str, list]] = {}
        for error in errors_by_source["fix_llm"]:
            etype = error["_error_type"]
            pattern = error.get("error_pattern", "unknown")
            if etype not in by_type_pattern:
                by_type_pattern[etype] = {}
            if pattern not in by_type_pattern[etype]:
                by_type_pattern[etype][pattern] = []
            by_type_pattern[etype][pattern].append(error)

        for etype in ["type", "importance", "client_label"]:
            if etype not in by_type_pattern:
                continue
            output_lines.append(f"## {etype.upper()} Errors")
            output_lines.append("")

            patterns = by_type_pattern[etype]
            sorted_patterns = sorted(patterns.items(), key=lambda x: -len(x[1]))

            for pattern, pattern_errors in sorted_patterns:
                output_lines.append(f"### {pattern} ({len(pattern_errors)} errors)")
                output_lines.append("")
                output_lines.append("| ID | Subject | Reason |")
                output_lines.append("|----|---------|--------|")
                for err in pattern_errors[:10]:  # Show first 10
                    email_id = err.get("email_id", "?")
                    subject = err.get("subject", "")[:40]
                    reason = err.get("_source_reason", "")[:50]
                    output_lines.append(f"| {email_id} | {subject} | {reason} |")
                if len(pattern_errors) > 10:
                    output_lines.append(f"| ... | *{len(pattern_errors) - 10} more* | |")
                output_lines.append("")
    else:
        output_lines.append("*No errors in this category*")
        output_lines.append("")

    output_lines.append("---")
    output_lines.append("")
    output_lines.append("# 2. FIX GDS (Correct Ground Truth)")
    output_lines.append("")

    if errors_by_source["fix_gds"]:
        output_lines.append("| ID | Subject | LLM | GDS | Suggested |")
        output_lines.append("|----|---------|-----|-----|-----------|")
        for err in errors_by_source["fix_gds"]:
            email_id = err.get("email_id", "?")
            subject = err.get("subject", "")[:35]
            llm = err.get("predicted", "?")
            gds = err.get("actual", "?")
            output_lines.append(f"| {email_id} | {subject} | {llm} | {gds} | {llm} |")
        output_lines.append("")
    else:
        output_lines.append("*No errors in this category*")
        output_lines.append("")

    output_lines.append("---")
    output_lines.append("")
    output_lines.append("# 3. REVIEW NEEDED (Human Judgment)")
    output_lines.append("")

    if errors_by_source["review_needed"]:
        output_lines.append("| ID | Subject | LLM | GDS | Notes |")
        output_lines.append("|----|---------|-----|-----|-------|")
        for err in errors_by_source["review_needed"]:
            email_id = err.get("email_id", "?")
            subject = err.get("subject", "")[:35]
            llm = err.get("predicted", "?")
            gds = err.get("actual", "?")
            reason = err.get("_source_reason", "")[:30]
            output_lines.append(f"| {email_id} | {subject} | {llm} | {gds} | {reason} |")
        output_lines.append("")
    else:
        output_lines.append("*No errors in this category*")
        output_lines.append("")

    return "\n".join(output_lines)


def main():
    # Find the most recent experiment results
    experiments_dir = Path(__file__).parent.parent.parent.parent / "reports" / "experiments"

    # Find most recent JSON file
    json_files = sorted(experiments_dir.glob("*.json"), reverse=True)
    if not json_files:
        print("No experiment results found in reports/experiments/")
        return

    latest_json = json_files[0]
    print(f"Using results from: {latest_json.name}")

    with open(latest_json) as f:
        results = json.load(f)

    report = generate_source_report(results, experiments_dir)
    print(report)

    # Save to file
    report_path = experiments_dir / f"{latest_json.stem}_by_source.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\n\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
