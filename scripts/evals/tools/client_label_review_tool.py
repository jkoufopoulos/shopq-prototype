# ruff: noqa
#!/usr/bin/env python3
"""
Client Label Review Tool

Interactive terminal tool for reviewing client_label classification discrepancies.
Shows LLM vs GDS classifications and lets you decide which is correct.

Usage:
    python3 scripts/evals/tools/client_label_review_tool.py
    python3 scripts/evals/tools/client_label_review_tool.py --pattern "everything-else -> receipts"
    python3 scripts/evals/tools/client_label_review_tool.py --list-patterns

Side Effects:
- Reads client_label errors from CSV
- Writes decisions to data/evals/classification/client_label_review_decisions.csv
"""

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


# Terminal colors
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GRAY = "\033[90m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    ORANGE = "\033[38;5;208m"


def clear_screen():
    """Clear terminal screen"""
    print("\033[2J\033[H", end="")


# Taxonomy rules for client labels (from mailq/storage/classification.py)
CLIENT_LABEL_TAXONOMY = {
    "receipts": {
        "description": "All purchase-related emails (orders, shipping, payments, refunds)",
        "rule": "type=receipt -> receipts",
        "examples": [
            "Order confirmation",
            "Shipping notification",
            "Delivery confirmation",
            "Payment receipt",
            "Invoice",
            "Refund confirmation",
        ],
    },
    "action-required": {
        "description": "User must act to avoid negative consequence",
        "rule": "importance=critical -> action-required",
        "examples": [
            "Security alerts (unauthorized access)",
            "Payment failures requiring action",
            "Account verification needed",
            "Fraud alerts",
        ],
    },
    "messages": {
        "description": "Personal/conversational threads with real humans",
        "rule": "type=message -> messages",
        "examples": [
            "Email from a person",
            "Reply thread",
            "Personal correspondence",
        ],
    },
    "everything-else": {
        "description": "Newsletters, promotions, events, notifications - anything not in above categories",
        "rule": "Default bucket for non-receipt, non-message, non-critical",
        "examples": [
            "Newsletters",
            "Promotional emails",
            "Event invitations",
            "Account notifications",
            "OTPs (ephemeral, don't need special handling)",
        ],
    },
}


# Pattern-based taxonomy hints
def get_taxonomy_hint(subject: str, snippet: str, email_type: str, importance: str) -> str:
    """Return taxonomy guidance based on email patterns and classification"""
    subject_lower = subject.lower()
    hints = []

    # Rule 1: type=receipt -> receipts
    if email_type == "receipt":
        hints.append("Rule: type=receipt -> receipts (all purchase lifecycle)")

    # Rule 2: type=message -> messages
    if email_type == "message":
        hints.append("Rule: type=message -> messages (human conversations)")

    # Rule 3: importance=critical -> action-required
    if importance == "critical":
        hints.append("Rule: importance=critical -> action-required (user must act)")

    # Rule 4: type=otp -> everything-else (despite being critical)
    if email_type == "otp":
        hints.append(
            "Rule: type=otp -> everything-else (OTPs are ephemeral, don't need special handling)"
        )

    # Common patterns
    if any(
        word in subject_lower
        for word in ["order", "shipped", "delivered", "invoice", "payment", "receipt"]
    ):
        hints.append("Pattern: Purchase/shipping/payment emails -> receipts")

    if any(
        word in subject_lower
        for word in ["security alert", "unauthorized", "verify your", "action required"]
    ):
        hints.append("Pattern: Security/action-needed emails -> action-required")

    if any(
        word in subject_lower
        for word in ["newsletter", "digest", "weekly", "promo", "% off", "sale"]
    ):
        hints.append("Pattern: Marketing/newsletter emails -> everything-else")

    return "\n".join(hints) if hints else "No specific taxonomy rule matched"


def load_client_label_errors(csv_path: str) -> list[dict]:
    """Load client_label errors from CSV"""
    errors = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            errors.append(row)
    return errors


def load_previous_decisions(decisions_path: Path) -> dict:
    """Load previously made decisions"""
    decisions = {}
    if decisions_path.exists():
        with open(decisions_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                decisions[int(row["email_id"])] = row
    return decisions


def save_decisions(decisions_path: Path, decisions: list[dict]):
    """Save decisions to CSV"""
    if not decisions:
        return

    fieldnames = [
        "email_id",
        "subject",
        "llm_client_label",
        "gds_client_label",
        "decision",
        "correct_value",
        "note",
        "reviewed_at",
    ]

    with open(decisions_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(decisions)


def display_email(error: dict, index: int, total: int, taxonomy_hint: str, pattern_info: str = ""):
    """Display email for review"""
    email_id = error.get("email_id", "?")
    pattern = error.get("error_pattern", "")

    # Parse pattern (e.g., "actual -> predicted" which is "GDS -> LLM")
    parts = pattern.split(" -> ")
    gds_says = parts[0] if len(parts) > 0 else "?"
    llm_says = parts[1] if len(parts) > 1 else "?"

    print(f"\n{Colors.BOLD}Email ID {email_id}{Colors.RESET} ({index} of {total})")
    if pattern_info:
        print(f"{Colors.ORANGE}Pattern: {pattern_info}{Colors.RESET}")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")

    # Email details
    print(f"{Colors.BOLD}Subject:{Colors.RESET} {error.get('subject', '')}")
    print(f"{Colors.BOLD}From:{Colors.RESET} {error.get('from', '')}")
    print(f"{Colors.BOLD}Type:{Colors.RESET} {error.get('email_type', '')}")
    print(f"{Colors.BOLD}Importance:{Colors.RESET} {error.get('importance', '')}")

    snippet = error.get("snippet", "")[:300]
    print(f"{Colors.BOLD}Snippet:{Colors.RESET} {snippet}")

    print(f"{Colors.GRAY}{'-' * 80}{Colors.RESET}")

    # Taxonomy hint
    print(f"\n{Colors.CYAN}{taxonomy_hint}{Colors.RESET}")

    print(f"{Colors.GRAY}{'-' * 80}{Colors.RESET}")

    # Classification comparison
    print(f"\n{Colors.BOLD}CLIENT LABEL CLASSIFICATION:{Colors.RESET}")
    print(f"  {Colors.BLUE}LLM says:{Colors.RESET}  {llm_says}")
    print(f"  {Colors.MAGENTA}GDS says:{Colors.RESET}  {gds_says}")

    return llm_says, gds_says


VALID_LABELS = ["receipts", "action-required", "messages", "everything-else"]


def main():
    """
    Main review loop.

    Side Effects:
    - Reads client_label errors CSV
    - Writes decisions to CSV
    """
    # Parse arguments
    parser = argparse.ArgumentParser(description="Review client_label classification errors")
    parser.add_argument(
        "--pattern",
        type=str,
        help='Filter to specific error pattern (e.g., "everything-else -> receipts")',
    )
    parser.add_argument(
        "--list-patterns",
        action="store_true",
        help="List all error patterns with counts and exit",
    )
    args = parser.parse_args()

    # Find the most recent client_label errors file
    reports_dir = Path("reports/experiments")
    label_files = sorted(reports_dir.glob("*_client_label_errors.csv"), reverse=True)

    if not label_files:
        print("Error: No client_label error files found in reports/experiments/")
        sys.exit(1)

    errors_path = label_files[0]
    print(f"{Colors.BOLD}Client Label Review Tool{Colors.RESET}")
    print(f"Loading: {errors_path.name}")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")

    # Load errors
    errors = load_client_label_errors(str(errors_path))
    total = len(errors)
    print(f"Found {total} client_label discrepancies to review")

    # Load previous decisions
    decisions_path = Path("data/evals/classification/client_label_review_decisions.csv")
    previous_decisions = load_previous_decisions(decisions_path)

    # Filter out already reviewed
    errors_to_review = []
    for error in errors:
        email_id = int(error.get("email_id", 0))
        if email_id not in previous_decisions:
            errors_to_review.append(error)

    already_reviewed = total - len(errors_to_review)
    print(f"Already reviewed: {already_reviewed}")
    print(f"Remaining: {len(errors_to_review)}")

    # Count patterns for display
    pattern_counts = Counter(e.get("error_pattern", "unknown") for e in errors_to_review)

    # Handle --list-patterns
    if args.list_patterns:
        print(f"\n{Colors.BOLD}Error Patterns (sorted by count):{Colors.RESET}")
        print(f"{Colors.GRAY}{'-' * 60}{Colors.RESET}")
        for pattern, count in pattern_counts.most_common():
            print(f"  {count:3d}  {pattern}")
        print(f"{Colors.GRAY}{'-' * 60}{Colors.RESET}")
        print(f'\nUse --pattern "<pattern>" to review a specific pattern')
        sys.exit(0)

    # Show pattern summary
    print(f"\n{Colors.BOLD}Error Patterns:{Colors.RESET}")
    for pattern, count in pattern_counts.most_common():
        print(f"  {count:3d}  {pattern}")

    # Filter by pattern if specified
    if args.pattern:
        errors_to_review = [e for e in errors_to_review if e.get("error_pattern") == args.pattern]
        print(f"\n{Colors.YELLOW}Filtering to pattern: {args.pattern}{Colors.RESET}")
        print(f"Matching errors: {len(errors_to_review)}")
    else:
        # Sort by pattern so similar errors are grouped together
        errors_to_review = sorted(
            errors_to_review,
            key=lambda e: (
                # Sort by count (most common first), then by pattern name
                -pattern_counts.get(e.get("error_pattern", ""), 0),
                e.get("error_pattern", ""),
            ),
        )

    if not errors_to_review:
        print(f"\n{Colors.GREEN}All client_label errors have been reviewed!{Colors.RESET}")
        sys.exit(0)

    print(f"\n{Colors.BOLD}Controls:{Colors.RESET}")
    print("  1 = LLM is correct")
    print("  2 = GDS is correct")
    print("  3 = Other (you'll specify)")
    print("  s = Skip (review later)")
    print("  q = Quit and save")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")
    input("Press ENTER to start...")

    # Collect all decisions (previous + new)
    all_decisions = list(previous_decisions.values())
    new_decisions = []

    current_pattern = None
    pattern_index = 0

    for i, error in enumerate(errors_to_review, 1):
        clear_screen()

        email_id = int(error.get("email_id", 0))
        subject = error.get("subject", "")
        snippet = error.get("snippet", "")
        email_type = error.get("email_type", "")
        importance = error.get("importance", "")
        error_pattern = error.get("error_pattern", "")

        # Track pattern changes
        if error_pattern != current_pattern:
            current_pattern = error_pattern
            pattern_index = 1
            pattern_total = pattern_counts.get(current_pattern, 0)
        else:
            pattern_index += 1

        pattern_info = f"{current_pattern} ({pattern_index}/{pattern_total})"

        taxonomy_hint = get_taxonomy_hint(subject, snippet, email_type, importance)
        llm_says, gds_says = display_email(
            error, i, len(errors_to_review), taxonomy_hint, pattern_info
        )

        # Input loop - keep prompting until valid response
        while True:
            print(f"\n{Colors.DIM}[1]=LLM  [2]=GDS  [3]=Other  [s]=Skip  [q]=Quit{Colors.RESET}")
            response = input("-> ").strip().lower()

            if response == "q":
                break
            if response == "s":
                print(f"{Colors.YELLOW}Skipped{Colors.RESET}")
                break
            if response == "1":
                decision = "llm"
                correct_value = llm_says
                print(f"{Colors.GREEN}Selected: LLM ({llm_says}){Colors.RESET}")
                break
            elif response == "2":
                decision = "gds"
                correct_value = gds_says
                print(f"{Colors.GREEN}Selected: GDS ({gds_says}){Colors.RESET}")
                break
            elif response == "3":
                print(f"Enter correct client_label ({', '.join(VALID_LABELS)}):")
                correct_value = input("-> ").strip().lower()
                if correct_value not in VALID_LABELS:
                    print(f"{Colors.RED}Invalid value. Try again.{Colors.RESET}")
                    continue
                decision = "other"
                print(f"{Colors.GREEN}Selected: Other ({correct_value}){Colors.RESET}")
                break
            else:
                print(
                    f"{Colors.RED}Invalid input '{response}'. Use 1, 2, 3, s, or q.{Colors.RESET}"
                )
                continue

        # Handle quit
        if response == "q":
            break
        # Handle skip
        if response == "s":
            continue

        # Get optional note
        note = input(f"{Colors.DIM}Note (optional): {Colors.RESET}").strip()

        # Record decision
        decision_record = {
            "email_id": email_id,
            "subject": subject[:100],
            "llm_client_label": llm_says,
            "gds_client_label": gds_says,
            "decision": decision,
            "correct_value": correct_value,
            "note": note,
            "reviewed_at": datetime.now().isoformat(),
        }
        new_decisions.append(decision_record)
        all_decisions.append(decision_record)

        # Auto-save every 5 decisions
        if len(new_decisions) % 5 == 0:
            print(f"{Colors.CYAN}Auto-saving ({len(new_decisions)} new decisions)...{Colors.RESET}")
            save_decisions(decisions_path, all_decisions)

    # Final save
    clear_screen()
    print(f"\n{Colors.BOLD}Summary{Colors.RESET}")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")
    print(f"New decisions this session: {len(new_decisions)}")
    print(f"Total decisions: {len(all_decisions)}")

    if new_decisions:
        save_decisions(decisions_path, all_decisions)
        print(f"{Colors.GREEN}Saved to: {decisions_path}{Colors.RESET}")

        # Show breakdown
        llm_correct = sum(1 for d in new_decisions if d["decision"] == "llm")
        gds_correct = sum(1 for d in new_decisions if d["decision"] == "gds")
        other_correct = sum(1 for d in new_decisions if d["decision"] == "other")

        print("\nThis session:")
        print(f"  LLM correct: {llm_correct}")
        print(f"  GDS correct: {gds_correct}")
        print(f"  Other: {other_correct}")


if __name__ == "__main__":
    main()
