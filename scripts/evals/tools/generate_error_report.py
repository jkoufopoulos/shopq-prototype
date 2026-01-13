# ruff: noqa
"""
Generate structured error report with taxonomy alignment analysis.

Output format:
email_id | subject | LLM decision | GDS decision | Taxonomy alignment | Severity

Broken down by: Type, Importance, Client Label
"""

import csv
import json
from pathlib import Path

# Taxonomy definitions for alignment checking
TAXONOMY = {
    "type": {
        "otp": {
            "definition": "One-time passcodes, verification codes, and 2FA codes",
            "signals": ["verification code", "OTP", "2FA", "login code"],
        },
        "event": {
            "definition": "Emails tied to attending something at a specific date/time",
            "signals": ["invitation", "event", "class", "meetup", "calendar"],
        },
        "notification": {
            "definition": "Operational updates about account, security, or system status (NOT purchases)",
            "signals": ["alert", "update", "status", "account", "security"],
        },
        "receipt": {
            "definition": "All emails related to purchases and money movement",
            "signals": ["order", "shipped", "delivery", "payment", "refund", "tracking"],
        },
        "newsletter": {
            "definition": "Editorial, informational, or educational content",
            "signals": ["newsletter", "digest", "weekly", "editorial"],
        },
        "promotion": {
            "definition": "Commercial emails primarily intended to sell",
            "signals": ["sale", "discount", "offer", "deal", "% off"],
        },
        "message": {
            "definition": "Direct human-to-human communication",
            "signals": ["reply", "thread", "conversation"],
        },
    },
    "importance": {
        "critical": {
            "definition": "Real-world risk, loss, or serious consequence if ignored",
            "includes": ["fraud alerts", "security alerts", "OTPs", "compromised accounts"],
        },
        "time_sensitive": {
            "definition": "Has a deadline or event time",
            "includes": ["calendar events", "deliveries", "appointments", "bills with due dates"],
        },
        "routine": {
            "definition": "Low-consequence, informational, no deadline",
            "includes": ["newsletters", "promos", "order confirmations", "receipts"],
        },
    },
    "client_label": {
        "action-required": {
            "definition": "User must take action to avoid negative consequence",
            "includes": ["failed payments", "subscription warnings", "service interruptions"],
        },
        "receipts": {
            "definition": "All purchase-related emails",
            "includes": ["payments", "refunds", "orders", "shipping", "delivery"],
        },
        "messages": {
            "definition": "Personal/conversational threads with humans",
            "includes": ["one-to-one emails", "small group threads"],
        },
        "everything-else": {
            "definition": "Default bucket for remaining emails",
            "includes": ["notifications", "newsletters", "promotions", "events"],
        },
    },
}


# Severity scoring based on error type
SEVERITY_MATRIX = {
    "type": {
        # receipt -> notification is HIGH because it affects user's mental model of purchases
        ("receipt", "notification"): "HIGH",
        ("notification", "receipt"): "MEDIUM",
        # event misclassifications can cause missed events
        ("event", "notification"): "HIGH",
        ("event", "newsletter"): "HIGH",
        ("notification", "event"): "MEDIUM",
        ("newsletter", "event"): "MEDIUM",
        # otp misclassifications are critical
        ("otp", "notification"): "CRITICAL",
        ("notification", "otp"): "HIGH",
        # message misclassifications affect personal communication
        ("message", "notification"): "MEDIUM",
        ("message", "receipt"): "MEDIUM",
        # newsletter/promotion confusion is low impact
        ("newsletter", "promotion"): "LOW",
        ("promotion", "newsletter"): "LOW",
    },
    "importance": {
        # Critical downgraded is very bad
        ("critical", "routine"): "CRITICAL",
        ("critical", "time_sensitive"): "HIGH",
        # Time-sensitive downgraded can cause missed deadlines
        ("time_sensitive", "routine"): "HIGH",
        # Upgrading importance is less severe
        ("routine", "time_sensitive"): "MEDIUM",
        ("routine", "critical"): "MEDIUM",
        ("time_sensitive", "critical"): "LOW",
    },
    "client_label": {
        # Action-required missed is high severity
        ("action-required", "everything-else"): "HIGH",
        ("action-required", "receipts"): "MEDIUM",
        # Receipts going to wrong bucket
        ("receipts", "everything-else"): "MEDIUM",
        ("receipts", "messages"): "LOW",
        # Messages misrouted
        ("messages", "everything-else"): "MEDIUM",
        ("messages", "receipts"): "LOW",
        # False positives for action-required
        ("everything-else", "action-required"): "MEDIUM",
        ("receipts", "action-required"): "LOW",
    },
}


def get_severity(error_type: str, gds: str, llm: str) -> str:
    """Get severity for a misclassification based on the error matrix."""
    matrix = SEVERITY_MATRIX.get(error_type, {})
    severity = matrix.get((gds, llm))
    if severity:
        return severity
    # Default severity based on error type
    if error_type == "importance":
        return "MEDIUM"
    return "LOW"


def check_taxonomy_alignment(error_type: str, llm_decision: str, subject: str, snippet: str) -> str:
    """
    Check if LLM decision aligns with taxonomy definition.
    Returns assessment of alignment.
    """
    taxonomy_def = TAXONOMY.get(error_type, {}).get(llm_decision, {})
    if not taxonomy_def:
        return "UNKNOWN"

    definition = taxonomy_def.get("definition", "")
    signals = taxonomy_def.get("signals", [])
    includes = taxonomy_def.get("includes", [])

    # Check if any taxonomy signals appear in subject/snippet
    text = (subject + " " + snippet).lower()
    matching_signals = [s for s in signals if s.lower() in text]
    matching_includes = [i for i in includes if i.lower() in text]

    if matching_signals or matching_includes:
        return f"PARTIAL - LLM saw: {', '.join(matching_signals + matching_includes)[:50]}"

    return "MISALIGNED - No taxonomy signals match"


def load_errors(csv_path: str) -> list[dict]:
    """Load errors from CSV file."""
    errors = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            errors.append(row)
    return errors


def generate_report_section(
    error_type: str,
    errors: list[dict],
    output_lines: list[str],
) -> None:
    """Generate a report section for a specific error type."""
    output_lines.append(f"\n{'=' * 80}")
    output_lines.append(f"## {error_type.upper()} ERRORS ({len(errors)} total)")
    output_lines.append(f"{'=' * 80}\n")

    # Group by error pattern
    patterns: dict[str, list[dict]] = {}
    for error in errors:
        pattern = error.get("error_pattern", "unknown")
        if pattern not in patterns:
            patterns[pattern] = []
        patterns[pattern].append(error)

    # Sort patterns by count (descending)
    sorted_patterns = sorted(patterns.items(), key=lambda x: -len(x[1]))

    for pattern, pattern_errors in sorted_patterns:
        output_lines.append(f"\n### Pattern: {pattern} ({len(pattern_errors)} errors)")
        output_lines.append("-" * 60)
        output_lines.append(
            f"{'ID':<6} | {'Subject':<40} | {'LLM':<12} | {'GDS':<12} | {'Taxonomy':<25} | {'Severity':<8}"
        )
        output_lines.append("-" * 120)

        for error in pattern_errors:
            email_id = error.get("email_id", "?")
            subject = error.get("subject", "")[:38]
            llm = error.get("predicted", "?")
            gds = error.get("actual", "?")
            snippet = error.get("snippet", "")

            taxonomy_check = check_taxonomy_alignment(error_type, llm, subject, snippet)
            severity = get_severity(error_type, gds, llm)

            # Truncate taxonomy check for display
            taxonomy_display = taxonomy_check[:23] if len(taxonomy_check) > 25 else taxonomy_check

            output_lines.append(
                f"{email_id:<6} | {subject:<40} | {llm:<12} | {gds:<12} | {taxonomy_display:<25} | {severity:<8}"
            )


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

    output_lines = []

    # Header
    output_lines.append("# Classification Error Report")
    output_lines.append(f"Generated from: {results.get('experiment_name', 'unknown')}")
    output_lines.append(f"Timestamp: {results.get('timestamp', 'unknown')}")
    output_lines.append(f"Git commit: {results.get('git_commit', 'unknown')}")
    output_lines.append("")

    # Summary
    metrics = results.get("metrics", {})
    output_lines.append("## Summary")
    output_lines.append(f"- Type Accuracy: {metrics.get('type_accuracy', 0):.1f}%")
    output_lines.append(f"- Importance Accuracy: {metrics.get('importance_accuracy', 0):.1f}%")
    output_lines.append(f"- Client Label Accuracy: {metrics.get('client_label_accuracy', 0):.1f}%")
    output_lines.append("")

    # Load and process each error type
    error_files = results.get("error_csv_files", {})

    for error_type in ["type", "importance", "client_label"]:
        csv_path = error_files.get(error_type)
        if csv_path and Path(csv_path).exists():
            errors = load_errors(csv_path)
            generate_report_section(error_type, errors, output_lines)

    # Output report
    report = "\n".join(output_lines)
    print(report)

    # Save to file
    report_path = experiments_dir / f"{latest_json.stem}_error_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\n\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
