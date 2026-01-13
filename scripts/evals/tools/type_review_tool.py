# ruff: noqa
#!/usr/bin/env python3
"""
Type Review Tool

Interactive terminal tool for reviewing email type classification discrepancies.
Shows LLM vs GDS classifications and lets you decide which is correct.

Usage:
    python3 scripts/evals/tools/type_review_tool.py

Side Effects:
- Reads type errors from CSV
- Writes decisions to data/evals/classification/type_review_decisions.csv
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


# Taxonomy rules for email type (from mailq/storage/classification.py)
TYPE_TAXONOMY = {
    "otp": {
        "description": "One-time passcodes, verification codes, 2FA codes",
        "examples": [
            "Your verification code is 123456",
            "2FA code for login",
            "Confirm your email address (with code)",
        ],
    },
    "newsletter": {
        "description": "Editorial, informational, or educational content sent to subscribers",
        "examples": [
            "Weekly digest from publication",
            "Industry news roundup",
            "Blog post updates",
            "Product changelog/release notes",
        ],
    },
    "notification": {
        "description": "Operational updates about accounts, services, or status changes",
        "examples": [
            "Your password was changed",
            "New sign-in detected",
            "Account settings updated",
            "Service status alert",
        ],
    },
    "receipt": {
        "description": "Documentation of completed financial transactions (orders, payments, refunds)",
        "examples": [
            "Order confirmation",
            "Payment received",
            "Invoice/bill",
            "Subscription renewal",
            "Shipping confirmation",
            "Delivery notification",
        ],
    },
    "event": {
        "description": "Emails tied to attending something at a specific date/time",
        "examples": [
            "Calendar invite",
            "Webinar registration",
            "Flight itinerary",
            "Concert/show tickets",
            "Appointment reminder",
        ],
    },
    "promotion": {
        "description": "Commercial emails intended to sell products/services",
        "examples": [
            "Sale announcement",
            "Discount offer",
            "New product launch",
            "Abandoned cart reminder",
        ],
    },
    "message": {
        "description": "Direct human-to-human or small-group communication",
        "examples": [
            "Email from a person (not a company)",
            "Reply to your email",
            "Personal correspondence",
        ],
    },
    "uncategorized": {
        "description": "Doesn't fit any other category",
        "examples": [
            "Ambiguous automated emails",
            "Unusual format emails",
        ],
    },
}


# Pattern-based taxonomy hints
def get_taxonomy_hint(subject: str, snippet: str, from_field: str) -> str:
    """Return taxonomy guidance based on email patterns"""
    subject_lower = subject.lower()
    snippet_lower = snippet.lower()
    from_lower = from_field.lower()

    hints = []

    # OTP patterns
    if any(
        word in subject_lower
        for word in [
            "verification code",
            "verify your",
            "one-time",
            "2fa",
            "otp",
            "confirm your email",
        ]
    ):
        hints.append("Taxonomy: Verification/OTP codes = otp")

    # Receipt patterns
    if any(
        word in subject_lower
        for word in [
            "order confirm",
            "your order",
            "payment received",
            "invoice",
            "receipt",
            "shipped",
            "delivered",
        ]
    ):
        hints.append("Taxonomy: Order/payment/shipping emails = receipt")

    # Event patterns (KEY: must have specific date/time)
    if any(
        word in subject_lower
        for word in ["invitation", "you're invited", "rsvp", "calendar", "webinar", "register for"]
    ):
        hints.append(
            "Taxonomy: Events with date/time = event. Marketing webinars without RSVP = newsletter"
        )

    # Newsletter vs Promotion distinction
    if any(
        word in subject_lower
        for word in ["% off", "sale", "discount", "deal", "save", "limited time"]
    ):
        hints.append("Taxonomy: Sales/discounts = promotion")

    if any(
        word in subject_lower
        for word in ["weekly", "digest", "roundup", "news", "update from", "what's new"]
    ):
        hints.append("Taxonomy: Regular content updates = newsletter")

    # Notification patterns
    if any(
        word in subject_lower
        for word in [
            "password changed",
            "new sign-in",
            "security alert",
            "account update",
            "settings changed",
        ]
    ):
        hints.append("Taxonomy: Account/security updates = notification")

    # Message patterns
    if "noreply" not in from_lower and "no-reply" not in from_lower:
        if any(word in subject_lower for word in ["re:", "fwd:", "replied"]):
            hints.append("Taxonomy: Email replies/forwards from humans = message")

    # Common confusions
    if "event" in subject_lower or "webinar" in subject_lower:
        hints.append(
            "NOTE: event vs newsletter - does it have a specific date/time the user attends?"
        )

    if "shipped" in subject_lower or "delivery" in subject_lower:
        hints.append(
            "NOTE: Shipping notifications are receipt (purchase lifecycle), not notification"
        )

    return "\n".join(hints) if hints else "No specific taxonomy rule matched"


def load_type_errors(csv_path: str) -> list[dict]:
    """Load type errors from CSV"""
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
        "llm_type",
        "gds_type",
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

    # Parse pattern (e.g., "receipt -> newsletter")
    parts = pattern.split(" -> ")
    llm_says = parts[0] if len(parts) > 0 else "?"
    gds_says = parts[1] if len(parts) > 1 else "?"

    print(f"\n{Colors.BOLD}Email ID {email_id}{Colors.RESET} ({index} of {total})")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")

    # Email details
    print(f"{Colors.BOLD}Subject:{Colors.RESET} {error.get('subject', '')}")
    print(f"{Colors.BOLD}From:{Colors.RESET} {error.get('from', '')}")

    snippet = error.get("snippet", "")[:300]
    print(f"{Colors.BOLD}Snippet:{Colors.RESET} {snippet}")

    print(f"{Colors.GRAY}{'-' * 80}{Colors.RESET}")

    # Taxonomy hint
    print(f"\n{Colors.CYAN}{taxonomy_hint}{Colors.RESET}")

    print(f"{Colors.GRAY}{'-' * 80}{Colors.RESET}")

    # Classification comparison
    print(f"\n{Colors.BOLD}TYPE CLASSIFICATION:{Colors.RESET}")
    print(f"  {Colors.BLUE}LLM says:{Colors.RESET}  {llm_says}")
    print(f"  {Colors.MAGENTA}GDS says:{Colors.RESET}  {gds_says}")

    return llm_says, gds_says


VALID_TYPES = [
    "otp",
    "newsletter",
    "notification",
    "receipt",
    "event",
    "promotion",
    "message",
    "uncategorized",
]


def main():
    """
    Main review loop.

    Side Effects:
    - Reads type errors CSV
    - Writes decisions to CSV
    """
    # Find the most recent type errors file
    reports_dir = Path("reports/experiments")
    type_files = sorted(reports_dir.glob("*_type_errors.csv"), reverse=True)

    if not type_files:
        print("Error: No type error files found in reports/experiments/")
        sys.exit(1)

    errors_path = type_files[0]
    print(f"{Colors.BOLD}Type Review Tool{Colors.RESET}")
    print(f"Loading: {errors_path.name}")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")

    # Load errors
    errors = load_type_errors(str(errors_path))
    total = len(errors)
    print(f"Found {total} type discrepancies to review")

    # Load previous decisions
    decisions_path = Path("data/evals/classification/type_review_decisions.csv")
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
        print(f"\n{Colors.GREEN}All type errors have been reviewed!{Colors.RESET}")
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
        from_field = error.get("from", "")

        taxonomy_hint = get_taxonomy_hint(subject, snippet, from_field)
        llm_says, gds_says = display_email(error, i, len(errors_to_review), taxonomy_hint)

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
                print(f"Enter correct type ({', '.join(VALID_TYPES)}):")
                correct_value = input("-> ").strip().lower()
                if correct_value not in VALID_TYPES:
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
            "llm_type": llm_says,
            "gds_type": gds_says,
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
