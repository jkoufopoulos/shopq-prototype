# ruff: noqa
#!/usr/bin/env python3
"""
Importance Review Tool

Interactive terminal tool for reviewing importance classification discrepancies.
Shows LLM vs GDS classifications and lets you decide which is correct.

Usage:
    python3 scripts/evals/tools/importance_review_tool.py

Side Effects:
- Reads importance errors from CSV
- Writes decisions to data/evals/classification/importance_review_decisions.csv
"""

import csv
import sys
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


# Taxonomy rules for importance (from mailq taxonomy)
IMPORTANCE_TAXONOMY = {
    "critical": {
        "description": "Requires immediate action, security implications, or significant financial impact",
        "examples": [
            "Security alerts (unauthorized access, password reset required)",
            "Fraud alerts",
            "Account lockout notifications",
            "Payment failures requiring immediate action",
        ],
    },
    "time_sensitive": {
        "description": "Has a deadline or time-bound relevance, but not critical",
        "examples": [
            "Event reminders with specific dates",
            "Bills due soon (not on autopay)",
            "Expiring offers with clear deadlines",
            "Flight check-in reminders",
            "Appointment confirmations",
        ],
    },
    "routine": {
        "description": "Informational, no deadline, can be reviewed at leisure",
        "examples": [
            "Shipping notifications (shipped, in transit)",
            "Delivery confirmations",
            "Receipts and order confirmations",
            "Newsletters and marketing",
            "Account statements",
            "AutoPay confirmations (payment already scheduled)",
        ],
    },
}


# Pattern-based taxonomy hints
def get_taxonomy_hint(subject: str, snippet: str, email_type: str) -> str:
    """Return taxonomy guidance based on email patterns"""
    subject_lower = subject.lower()
    snippet_lower = snippet.lower()
    combined = subject_lower + " " + snippet_lower

    hints = []

    # ==========================================================================
    # ORDER LIFECYCLE RULE (most common confusion)
    # Only 5 delivery states are time_sensitive, everything else is routine
    # ==========================================================================
    time_sensitive_delivery_states = [
        "out for delivery",
        "arriving today",
        "today by",
        "delivery attempted",
        "held at facility",
        "delivery exception",
        "unable to deliver",
        "delivery failed",
        "customs hold",
    ]
    routine_order_states = [
        "order confirmed",
        "order placed",
        "shipped",
        "has shipped",
        "in transit",
        "on the way",
        "on its way",
        "delivered",
        "has been delivered",
        "was delivered",
    ]

    # Check for time_sensitive delivery states first
    if any(state in combined for state in time_sensitive_delivery_states):
        hints.append(
            "ORDER LIFECYCLE: time_sensitive (out_for_delivery/arriving_today/attempted/held/exception)"
        )
    # Then check for routine order states
    elif any(state in combined for state in routine_order_states):
        hints.append(
            "ORDER LIFECYCLE: routine (ordered/shipped/in_transit/delivered are ALL routine)"
        )
        hints.append(
            "  -> Only out_for_delivery, arriving_today, attempted, held, exception = time_sensitive"
        )

    # AutoPay patterns
    if "autopay" in subject_lower or "automatic payment" in subject_lower:
        hints.append("Taxonomy: AutoPay notifications = routine (payment already scheduled)")

    # Security patterns
    if any(
        word in subject_lower
        for word in ["security alert", "unusual activity", "was this you", "sign-in"]
    ):
        hints.append("Taxonomy: Security alerts = critical (account safety)")

    # Billing patterns
    if any(word in subject_lower for word in ["invoice", "statement", "bill is ready"]):
        hints.append("Taxonomy: Billing notifications = routine (unless action required)")

    # Event/Webinar patterns
    if any(word in subject_lower for word in ["webinar", "register for", "you're invited"]):
        hints.append("Taxonomy: Marketing webinars = routine (optional, no deadline pressure)")

    # Travel patterns
    if any(
        word in subject_lower
        for word in ["booking confirmation", "reservation confirmed", "eticket"]
    ):
        hints.append("Taxonomy: Booking confirmations = routine (informational)")

    if any(word in subject_lower for word in ["check-in", "flight to", "notification: flight"]):
        hints.append("Taxonomy: Flight notifications = time_sensitive (action may be needed)")

    # Budget alerts
    if "budget" in subject_lower and ("update" in subject_lower or "alert" in subject_lower):
        hints.append("Taxonomy: Budget updates = routine (informational)")

    # Storm/Weather
    if "storm" in subject_lower or "weather" in subject_lower:
        hints.append("Taxonomy: Weather alerts = time_sensitive (safety relevance)")

    return "\n".join(hints) if hints else "No specific taxonomy rule matched"


def load_importance_errors(csv_path: str) -> list[dict]:
    """Load importance errors from CSV"""
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
        "llm_importance",
        "gds_importance",
        "decision",
        "correct_value",
        "note",
        "reviewed_at",
    ]

    with open(decisions_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(decisions)


def display_email(error: dict, index: int, total: int, taxonomy_hint: str):
    """Display email for review"""
    email_id = error.get("email_id", "?")
    pattern = error.get("error_pattern", "")

    # Parse pattern (e.g., "routine -> time_sensitive")
    parts = pattern.split(" -> ")
    llm_says = parts[0] if len(parts) > 0 else "?"
    gds_says = parts[1] if len(parts) > 1 else "?"

    print(f"\n{Colors.BOLD}Email ID {email_id}{Colors.RESET} ({index} of {total})")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")

    # Email details
    print(f"{Colors.BOLD}Subject:{Colors.RESET} {error.get('subject', '')}")
    print(f"{Colors.BOLD}From:{Colors.RESET} {error.get('from', '')}")
    print(f"{Colors.BOLD}Type:{Colors.RESET} {error.get('email_type', '')}")

    snippet = error.get("snippet", "")[:300]
    print(f"{Colors.BOLD}Snippet:{Colors.RESET} {snippet}")

    print(f"{Colors.GRAY}{'-' * 80}{Colors.RESET}")

    # Taxonomy hint
    print(f"\n{Colors.CYAN}{taxonomy_hint}{Colors.RESET}")

    print(f"{Colors.GRAY}{'-' * 80}{Colors.RESET}")

    # Classification comparison
    print(f"\n{Colors.BOLD}IMPORTANCE CLASSIFICATION:{Colors.RESET}")
    print(f"  {Colors.BLUE}LLM says:{Colors.RESET}  {llm_says}")
    print(f"  {Colors.MAGENTA}GDS says:{Colors.RESET}  {gds_says}")

    return llm_says, gds_says


def main():
    """
    Main review loop.

    Side Effects:
    - Reads importance errors CSV
    - Writes decisions to CSV
    """
    # Find the most recent importance errors file
    reports_dir = Path("reports/experiments")
    importance_files = sorted(reports_dir.glob("*_importance_errors.csv"), reverse=True)

    if not importance_files:
        print("Error: No importance error files found in reports/experiments/")
        sys.exit(1)

    errors_path = importance_files[0]
    print(f"{Colors.BOLD}Importance Review Tool{Colors.RESET}")
    print(f"Loading: {errors_path.name}")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")

    # Load errors
    errors = load_importance_errors(str(errors_path))
    total = len(errors)
    print(f"Found {total} importance discrepancies to review")

    # Load previous decisions
    decisions_path = Path("data/evals/classification/importance_review_decisions.csv")
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

    if not errors_to_review:
        print(f"\n{Colors.GREEN}All importance errors have been reviewed!{Colors.RESET}")
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

    for i, error in enumerate(errors_to_review, 1):
        clear_screen()

        email_id = int(error.get("email_id", 0))
        subject = error.get("subject", "")
        snippet = error.get("snippet", "")
        email_type = error.get("email_type", "")

        taxonomy_hint = get_taxonomy_hint(subject, snippet, email_type)
        llm_says, gds_says = display_email(error, i, len(errors_to_review), taxonomy_hint)

        # Input loop - keep prompting until valid response
        while True:
            print(f"\n{Colors.DIM}[1]=LLM  [2]=GDS  [3]=Other  [s]=Skip  [q]=Quit{Colors.RESET}")
            response = input("→ ").strip().lower()

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
                print("Enter correct importance (critical/time_sensitive/routine):")
                correct_value = input("→ ").strip().lower()
                if correct_value not in ["critical", "time_sensitive", "routine"]:
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
            "llm_importance": llm_says,
            "gds_importance": gds_says,
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
