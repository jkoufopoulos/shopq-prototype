#!/usr/bin/env python3
"""
Interactive Terminal-Based GDS Label Reviewer

A simple tool for manually reviewing and labeling email classification ground truth data.

Usage:
    # Resume labeling with AI pre-fills and pattern overrides:
    ./scripts/review_gds.sh

    # Or manually:
    uv run python scripts/evals/tools/manual_label.py \
        --input data/evals/classification/gds-2.0.csv \
        --output data/evals/classification/gds-2.0.csv \
        --use-existing-labels \
        --skip-completed 19

Principles Applied:
- P1: UI logic only - pattern rules imported from mailq.classification.patterns
- P2: Side effects explicit (auto-save every 5 emails)
- P3: Typed EmailLabel for compile-time safety
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

# Import pattern rules from canonical home (P1: Concepts Are Rooms)
from mailq.classification.patterns import EmailLabel, apply_pattern_overrides


# Terminal colors for UX
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


def display_email(
    email: dict, index: int, total: int, ai_label: EmailLabel | None = None, next_position: int = 0
):
    """Display email with AI suggestions"""
    email_id = email.get("email_id", index + 1)
    existing_position = email.get("labeling_position", "")
    position_display = existing_position if existing_position else f"→{next_position}"
    print(
        f"\n{Colors.BOLD}Email ID {email_id} | Position {position_display} ({index + 1} of {total} remaining){Colors.RESET}"
    )
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}Date:{Colors.RESET} {email.get('received_date', 'Unknown')}")
    print(f"{Colors.BOLD}From:{Colors.RESET} {email['from_email']}")
    print(f"{Colors.BOLD}Subject:{Colors.RESET} {email['subject']}")
    print(f"{Colors.BOLD}Snippet:{Colors.RESET} {email['snippet'][:200]}")
    print(f"{Colors.GRAY}{'=' * 80}{Colors.RESET}")

    if ai_label:
        print(f"\n{Colors.ORANGE}🤖 AI SUGGESTION:{Colors.RESET}")
        print(f"   Type: {Colors.ORANGE}{ai_label.email_type}{Colors.RESET}")
        print(f"   Importance: {Colors.ORANGE}{ai_label.importance}{Colors.RESET}")
        print(f"   Client Label: {Colors.ORANGE}{ai_label.client_label or 'null'}{Colors.RESET}")
        if "Pattern" in ai_label.reasoning:
            print(f"   {Colors.YELLOW}⚡ {ai_label.reasoning}{Colors.RESET}")


def get_user_input(prompt: str, valid_options: list[str], default: str = "") -> str:
    """Get validated user input"""
    while True:
        user_input = input(prompt).strip().lower()
        if user_input == "" and default:
            return default
        if user_input in valid_options:
            return user_input
        print(f"{Colors.RED}Invalid option. Choose from: {', '.join(valid_options)}{Colors.RESET}")


def label_email_interactive(email: dict, ai_label: EmailLabel) -> dict:
    """
    Interactive labeling for one email with field-level undo support.

    State machine that allows undoing individual field changes.
    Press 'u' to go back to previous field, keep pressing to go back further.
    If you undo past the first field, it goes to the previous email.

    Returns: Dict with email_type, importance, client_label, temporal_start, temporal_end
    """

    # State: track which fields have been set
    state = {
        "email_type": None,
        "importance": None,
        "client_label": None,
        "temporal_start": None,
        "temporal_end": None,
    }

    # Field order
    current_step = 0  # 0=type, 1=importance, 2=client_label, 3=temporal

    while True:
        # Step 0: Email Type
        if current_step == 0:
            print(f"\n{Colors.BOLD}EMAIL TYPE{Colors.RESET}")
            if state["email_type"]:
                print(f"  {Colors.GREEN}Current: {state['email_type']}{Colors.RESET}")
            print(f"  {Colors.ORANGE}ENTER) {ai_label.email_type}{Colors.RESET} (AI suggestion)")
            print("  1) notification  2) receipt  3) event")
            print("  4) newsletter    5) promotion  6) message  7) other")
            print("  u) UNDO to previous email  q) QUIT and save")

            choice = get_user_input(
                "Choice: ", ["", "1", "2", "3", "4", "5", "6", "7", "u", "q"], ""
            )

            if choice == "u":
                return {"email_type": "UNDO"}  # Go to previous email
            if choice == "q":
                return {"email_type": "QUIT"}

            type_map = {
                "": ai_label.email_type,
                "1": "notification",
                "2": "receipt",
                "3": "event",
                "4": "newsletter",
                "5": "promotion",
                "6": "message",
                "7": "other",
            }
            state["email_type"] = type_map[choice]
            current_step = 1
            continue

        # Step 1: Importance
        if current_step == 1:
            print(f"\n{Colors.BOLD}IMPORTANCE{Colors.RESET}")
            if state["importance"]:
                print(f"  {Colors.GREEN}Current: {state['importance']}{Colors.RESET}")
            print(f"  {Colors.ORANGE}ENTER) {ai_label.importance}{Colors.RESET} (AI suggestion)")
            print("  1) critical  2) time_sensitive  3) routine")
            print("  u) UNDO to email type")

            choice = get_user_input("Choice: ", ["", "1", "2", "3", "u"], "")

            if choice == "u":
                current_step = 0  # Go back to email type
                continue

            importance_map = {
                "": ai_label.importance,
                "1": "critical",
                "2": "time_sensitive",
                "3": "routine",
            }
            state["importance"] = importance_map[choice]
            current_step = 2
            continue

        # Step 2: Client Label
        if current_step == 2:
            print(f"\n{Colors.BOLD}CLIENT LABEL{Colors.RESET} (Gmail label user sees)")
            if state["client_label"]:
                print(f"  {Colors.GREEN}Current: {state['client_label']}{Colors.RESET}")
            print(
                f"  {Colors.ORANGE}ENTER) {ai_label.client_label or 'everything-else'}{Colors.RESET} (AI suggestion)"
            )
            print("  1) action-required  2) receipts  3) messages  4) everything-else")
            print("  u) UNDO to importance")

            choice = get_user_input("Choice: ", ["", "1", "2", "3", "4", "u"], "")

            if choice == "u":
                current_step = 1  # Go back to importance
                continue

            client_map = {
                "": ai_label.client_label or "everything-else",
                "1": "action-required",
                "2": "receipts",
                "3": "messages",
                "4": "everything-else",
            }
            state["client_label"] = client_map[choice]
            current_step = 3
            continue

        # Step 3: Temporality (for ALL emails)
        if current_step == 3:
            print(f"\n{Colors.BOLD}TEMPORALITY{Colors.RESET}")

            if state["temporal_start"]:
                print(
                    f"  {Colors.GREEN}Current: {state['temporal_start']} to {state['temporal_end'] or 'null'}{Colors.RESET}"
                )

            # Show AI suggestion
            if ai_label.temporal_start:
                print(f"{Colors.ORANGE}AI suggestion: Has temporal data{Colors.RESET}")
                print(f"  temporal_start: {Colors.ORANGE}{ai_label.temporal_start}{Colors.RESET}")
                print(
                    f"  temporal_end:   {Colors.ORANGE}{ai_label.temporal_end or 'null'}{Colors.RESET}"
                )
                print(f"\n  {Colors.ORANGE}ENTER) Accept AI temporal data{Colors.RESET}")
                print("  y) Edit temporal fields")
                print("  n) No temporality (clear to null)")
                print("  u) UNDO to client label")

                choice = get_user_input("Choice: ", ["", "y", "n", "u"], "")

                if choice == "u":
                    current_step = 2
                    continue

                if choice == "":
                    # Accept AI suggestion
                    state["temporal_start"] = ai_label.temporal_start
                    state["temporal_end"] = ai_label.temporal_end
                elif choice == "y":
                    # Edit with pre-fill
                    print(
                        f"\n{Colors.DIM}Enter ISO 8601 timestamps (YYYY-MM-DDTHH:MM:SS or leave blank){Colors.RESET}"
                    )
                    ts = input(f"temporal_start [{ai_label.temporal_start}]: ").strip()
                    state["temporal_start"] = ts if ts else ai_label.temporal_start
                    te = input(f"temporal_end [{ai_label.temporal_end or ''}]: ").strip()
                    state["temporal_end"] = te if te else ai_label.temporal_end
                else:
                    # No temporality
                    state["temporal_start"] = None
                    state["temporal_end"] = None
            else:
                # AI found no temporal data
                print(f"{Colors.ORANGE}AI suggestion: No temporal data{Colors.RESET}")
                print(f"\n  {Colors.ORANGE}ENTER) Accept (no temporality){Colors.RESET}")
                print("  y) Add temporal fields manually")
                print("  u) UNDO to client label")

                choice = get_user_input("Choice: ", ["", "y", "u"], "")

                if choice == "u":
                    current_step = 2
                    continue

                if choice == "":
                    # Accept AI suggestion (null)
                    state["temporal_start"] = None
                    state["temporal_end"] = None
                elif choice == "y":
                    # Manually add temporal data
                    print(
                        f"\n{Colors.DIM}Enter ISO 8601 timestamps (YYYY-MM-DDTHH:MM:SS or leave blank for null){Colors.RESET}"
                    )
                    ts = input("temporal_start: ").strip()
                    state["temporal_start"] = ts if ts else None
                    te = input("temporal_end: ").strip()
                    state["temporal_end"] = te if te else None

            # Done - return the complete state
            return {
                "email_type": state["email_type"],
                "importance": state["importance"],
                "client_label": state["client_label"],
                "temporal_start": state["temporal_start"],
                "temporal_end": state["temporal_end"],
            }


def main():
    """
    Main labeling loop.

    Side Effects:
    - Reads CSV from --input
    - Writes CSV to --output (auto-save every 5 emails)
    - Modifies terminal display (clear screen)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Manual GDS labeling with AI pre-labels + pattern overrides"
    )
    parser.add_argument("--input", required=True, help="Input GDS CSV")
    parser.add_argument("--output", required=True, help="Output labeled CSV")
    parser.add_argument(
        "--use-existing-labels", action="store_true", help="Use existing labels from CSV"
    )
    parser.add_argument(
        "--fresh-session",
        action="store_true",
        help="Start fresh labeling session (clear session file)",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    print("📖 Loading GDS...")
    with open(input_path, encoding="utf-8") as f:
        emails = list(csv.DictReader(f))

    # Ensure required fields exist
    for email in emails:
        if "client_label" not in email:
            email["client_label"] = ""
        if "reviewed_at" not in email:
            email["reviewed_at"] = ""
        if "labeling_position" not in email:
            email["labeling_position"] = ""

    # Calculate next labeling_position (max existing + 1)
    existing_positions = [
        int(e["labeling_position"])
        for e in emails
        if e.get("labeling_position") and e["labeling_position"].strip().isdigit()
    ]
    next_labeling_position = max(existing_positions) + 1 if existing_positions else 1

    # Skip logic: Track completed emails in a session file
    session_file = input_path.parent / ".gds_session.txt"
    completed_today_ids = set()

    # Handle fresh session flag
    if args.fresh_session and session_file.exists():
        session_file.unlink()
        print("   🆕 Started fresh session (cleared session file)")

    # Load existing session file
    if session_file.exists():
        with open(session_file) as f:
            completed_today_ids = set(line.strip() for line in f if line.strip())
        print(f"   📝 Loaded session: {len(completed_today_ids)} emails completed this session")

    # Skip emails already reviewed in this session
    to_label = [e for e in emails if e["message_id"] not in completed_today_ids]

    print(f"   Total: {len(emails)}")
    print(f"   Reviewed this session: {len(completed_today_ids)}")
    print(f"   Remaining: {len(to_label)}")

    if len(to_label) == 0:
        print("\n✅ No emails to review!")
        sys.exit(0)

    # Smart sorting: Group similar emails together for faster labeling
    def sort_key(email):
        """Multi-level sort: type first, then sub-category within type"""
        email_type = email.get("email_type", "other")
        subject = email.get("subject", "").lower()
        snippet = email.get("snippet", "").lower()
        text = subject + " " + snippet

        # Primary sort: email type
        type_order = {
            "notification": 1,
            "receipt": 2,
            "event": 3,
            "newsletter": 4,
            "promotion": 5,
            "promo": 5,
            "message": 6,
            "other": 7,
        }
        primary = type_order.get(email_type, 99)

        # Secondary sort: sub-categories within notifications
        secondary = 99  # default
        if email_type == "notification":
            # OTPs first (easiest to label in bulk)
            if any(
                pattern in text
                for pattern in [
                    "verification code",
                    "code:",
                    "code is",
                    "otp",
                    "one-time",
                    "your code",
                    "login code",
                    "passcode",
                ]
            ):
                secondary = 1
            # Fraud/security alerts
            elif any(
                pattern in text
                for pattern in [
                    "suspicious",
                    "unusual",
                    "fraud",
                    "security alert",
                    "verify",
                    "confirm",
                    "unauthorized",
                    "breach",
                    "pwned",
                ]
            ):
                secondary = 2
            # Delivery notifications
            elif any(
                pattern in text
                for pattern in [
                    "delivered",
                    "delivery",
                    "shipped",
                    "tracking",
                    "out for delivery",
                    "package",
                    "order",
                ]
            ):
                secondary = 3
            # Other notifications
            else:
                secondary = 4

        return (primary, secondary)

    to_label.sort(key=sort_key)

    # Load existing labels and apply pattern overrides
    ai_labels = {}
    if args.use_existing_labels:
        print("\n🤖 Loading existing labels + applying pattern overrides...")
        for email in to_label:
            msg_id = email["message_id"]

            # Load existing label
            label = EmailLabel(
                email_type=email.get("email_type", "notification"),
                importance=email.get("importance", "routine"),
                client_label=email.get("client_label") or None,
                temporal_start=email.get("temporal_start") or None,
                temporal_end=email.get("temporal_end") or None,
                confidence=0.95,
                reasoning=f"Pre-labeled: {email.get('decider', 'unknown')}",
            )

            # Apply pattern overrides (P1: using canonical module)
            label = apply_pattern_overrides(
                subject=email.get("subject", ""),
                snippet=email.get("snippet", ""),
                from_email=email.get("from_email", ""),
                label=label,
                received_date=email.get("received_date", ""),
            )
            ai_labels[msg_id] = label

        pattern_count = sum(1 for lbl in ai_labels.values() if "Pattern" in lbl.reasoning)
        print(f"✅ Loaded {len(ai_labels)} labels, {pattern_count} pattern overrides applied")

    # Interactive review loop
    print(f"\n{'=' * 80}")
    print("INTERACTIVE LABELING")
    print(f"{'=' * 80}")
    print("  - Press ENTER to accept AI suggestions")
    print("  - Type 'u' to UNDO and go back")
    print("  - Auto-saves every 5 emails")
    print("\nPress ENTER to start...")
    input()

    undo_stack = []
    labeled_count = 0
    current_index = 0

    def save_progress():
        """Save progress to output file (Side Effect: file write)"""
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(emails[0].keys()))
            writer.writeheader()
            writer.writerows(emails)

    while current_index < len(to_label):
        clear_screen()

        email = to_label[current_index]
        msg_id = email["message_id"]
        ai_label = ai_labels.get(msg_id)

        display_email(email, current_index, len(to_label), ai_label, next_labeling_position)

        if undo_stack:
            print("\n💡 Type 'u' to undo last email")

        # Get user labels
        default_label = ai_label or EmailLabel("notification", "routine")
        labels = label_email_interactive(email, default_label)

        # Handle quit
        if labels.get("email_type") == "QUIT":
            print("\n💾 Saving progress before exit...")
            save_progress()
            print(f"\n✅ Saved! Exiting at email {current_index + 1}/{len(to_label)}")
            print(f"   Labeled: {labeled_count} emails")
            print("   To resume: Run the same command again (will skip completed emails)")
            sys.exit(0)

        # Handle undo
        if labels.get("email_type") == "UNDO":
            if undo_stack:
                prev_index, prev_state = undo_stack.pop()
                to_label[prev_index].update(prev_state)
                current_index = prev_index
                labeled_count -= 1
                continue
            print("\n❌ Nothing to undo!")
            continue

        # Save state for undo (keep only last email)
        current_state = {
            "email_type": email.get("email_type", ""),
            "importance": email.get("importance", ""),
            "client_label": email.get("client_label", ""),
            "temporal_start": email.get("temporal_start", ""),
            "temporal_end": email.get("temporal_end", ""),
            "decider": email.get("decider", ""),
        }
        undo_stack = [(current_index, current_state)]  # Keep only most recent

        # Update email in BOTH to_label AND emails list (for save to work)
        # Find this email in the full emails list by message_id
        review_timestamp = datetime.now().isoformat()
        for full_email in emails:
            if full_email["message_id"] == msg_id:
                full_email["email_type"] = labels["email_type"]
                full_email["importance"] = labels["importance"]
                full_email["client_label"] = labels["client_label"]
                full_email["temporal_start"] = labels["temporal_start"] or ""
                full_email["temporal_end"] = labels["temporal_end"] or ""
                full_email["reviewed_at"] = review_timestamp
                # Assign labeling_position if not already set
                if (
                    not full_email.get("labeling_position")
                    or not full_email["labeling_position"].strip()
                ):
                    full_email["labeling_position"] = str(next_labeling_position)
                    next_labeling_position += 1
                break

        # Also update the filtered list (for undo to work)
        email["email_type"] = labels["email_type"]
        email["importance"] = labels["importance"]
        email["client_label"] = labels["client_label"]
        email["temporal_start"] = labels["temporal_start"] or ""
        email["temporal_end"] = labels["temporal_end"] or ""
        # decider field removed - using session file tracking only

        labeled_count += 1
        current_index += 1

        # Track this email as completed in session file (SET-based, no duplicates)
        completed_today_ids.add(msg_id)
        # Write entire set to file (overwrites, prevents duplicates)
        with open(session_file, "w") as f:
            for completed_id in sorted(completed_today_ids):
                f.write(f"{completed_id}\n")

        # Auto-save every 5 emails (Side Effect: file write)
        if labeled_count % 5 == 0:
            print(f"\n💾 Auto-saving ({labeled_count}/{len(to_label)})...")
            save_progress()
            print("   ✅ Saved!")
            import time

            time.sleep(1)  # Brief pause to see the save message

    # Final save
    print("\n💾 Saving final results...")
    save_progress()

    print("\n✅ Labeling complete!")
    print(f"   Reviewed: {labeled_count} emails")
    print(f"   Output: {output_path}")


if __name__ == "__main__":
    main()
