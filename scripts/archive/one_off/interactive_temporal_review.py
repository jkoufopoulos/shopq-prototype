"""
Interactive temporal digest review tool.

Shows emails one at a time and lets you mark which digest section they belong in
at different timepoints (T0, T1, T2) to validate temporal decay logic.
"""

from pathlib import Path

import pandas as pd


# Terminal colors
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def clear_screen():
    """Clear terminal screen."""
    print("\033[2J\033[H", end="")


def show_email(idx, total, email, timepoint):
    """Display email details."""
    clear_screen()

    timepoint_names = {"t0": "T0 (Just Received)", "t1": "T1 (+24 hours)", "t2": "T2 (+1 week)"}
    timepoint_desc = timepoint_names.get(timepoint, timepoint.upper())

    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}"
    )
    print(
        f"{Colors.CYAN}Email {idx + 1} of {total}  |  {Colors.YELLOW}{timepoint_desc}{Colors.END}"
    )
    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}\n"
    )

    print(f"{Colors.BOLD}From:{Colors.END} {email['from']}")
    print(f"{Colors.BOLD}Subject:{Colors.END} {email['subject']}")

    # Show received date with temporal context (convert to EST for readability)
    received_date = email.get("received_date", "")
    if received_date and str(received_date) != "nan":
        # Try to parse and convert to EST
        try:
            from zoneinfo import ZoneInfo

            import pandas as pd

            # Parse the UTC timestamp
            dt_utc = pd.to_datetime(received_date, utc=True)

            # Convert to EST
            dt_est = dt_utc.astimezone(ZoneInfo("America/New_York"))

            # Format nicely
            received_est = dt_est.strftime("%a, %d %b %Y %I:%M:%S %p %Z")
            print(f"{Colors.BOLD}Received:{Colors.END} {received_est}")
        except Exception:
            # Fallback to original if conversion fails
            print(f"{Colors.BOLD}Received:{Colors.END} {received_date}")

        # Show temporal context for T1/T2
        if timepoint == "t1":
            print(f"{Colors.CYAN}  (You're reviewing this 24 hours after it arrived){Colors.END}")
        elif timepoint == "t2":
            print(f"{Colors.CYAN}  (You're reviewing this 72 hours after it arrived){Colors.END}")

    print(f"\n{Colors.BOLD}Preview:{Colors.END}")
    print(f"{email['snippet']}\n")

    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}"
    )
    print(f"{Colors.YELLOW}System prediction:{Colors.END}")
    print(f"  Importance: {Colors.BOLD}{email['predicted_importance']}{Colors.END}")
    print(f"  Type: {email['predicted_type']}")
    print(f"  Category: {email['predicted_category']}")

    # Show predicted section if available
    predicted_section_col = f"predicted_section_{timepoint}"
    if predicted_section_col in email and email[predicted_section_col]:
        section_name = _format_section_name(email[predicted_section_col])
        print(f"  {Colors.BOLD}→ Predicted Section: {section_name}{Colors.END}")

    # Show temporal hints if available
    if email.get("temporal_hints") and str(email["temporal_hints"]).strip():
        print(f"\n{Colors.CYAN}Temporal hints: {email['temporal_hints']}{Colors.END}")

    # Show previous timepoint labels for reference
    if timepoint == "t1" and email.get("t0_critical"):
        t0_section = _get_marked_section(email, "t0")
        print(f"\n{Colors.CYAN}T0 label: {t0_section}{Colors.END}")
    elif timepoint == "t2":
        t0_section = _get_marked_section(email, "t0")
        t1_section = _get_marked_section(email, "t1")
        if t0_section:
            print(f"\n{Colors.CYAN}T0 label: {t0_section}{Colors.END}")
        if t1_section:
            print(f"{Colors.CYAN}T1 label: {t1_section}{Colors.END}")

    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}\n"
    )


def _get_marked_section(email, timepoint):
    """Get the section marked for a given timepoint."""
    if email.get(f"{timepoint}_critical") == "X":
        return "🚨 CRITICAL"
    if email.get(f"{timepoint}_today") == "X":
        return "📦 TODAY"
    if email.get(f"{timepoint}_coming_up") == "X":
        return "📅 COMING UP"
    if email.get(f"{timepoint}_worth_knowing") == "X":
        return "💼 WORTH KNOWING"
    if email.get(f"{timepoint}_everything_else") == "X":
        return "📬 EVERYTHING ELSE"
    if email.get(f"{timepoint}_skip") == "X":
        return "⏭️  SKIP"
    return None


def _format_section_name(section):
    """Format section name with emoji."""
    section_map = {
        "critical": "🚨 CRITICAL",
        "today": "📦 TODAY",
        "coming_up": "📅 COMING UP",
        "worth_knowing": "💼 WORTH KNOWING",
        "everything_else": "📬 EVERYTHING ELSE",
        "skip": "⏭️  SKIP",
    }
    return section_map.get(section, section.upper())


def get_user_choice(timepoint):
    """Get user's section choice."""
    print(f"{Colors.GREEN}Which section should this email be in?{Colors.END}\n")
    print(f"  {Colors.RED}[1] 🚨 CRITICAL{Colors.END}        - Urgent: fraud, security, bills due")
    print(
        f"  {Colors.YELLOW}[2] 📦 TODAY{Colors.END}           - Deliveries today, deadlines today"
    )
    print(f"  {Colors.BLUE}[3] 📅 COMING UP{Colors.END}       - Events, appointments 1-7 days")
    print(f"  {Colors.CYAN}[4] 💼 WORTH KNOWING{Colors.END}   - Receipts, confirmations, updates")
    print(
        f"  {Colors.BOLD}[5] 📬 EVERYTHING ELSE{Colors.END}  - Promotions, newsletters, past events"
    )
    print(f"  {Colors.BOLD}[6] ⏭️  SKIP{Colors.END}            - Don't show in digest at all")
    print(f"  {Colors.CYAN}[n] Notes{Colors.END}           - Add a note about this email")
    print(
        f"  {Colors.CYAN}[t] Temporal hint{Colors.END}   - Add temporal context (e.g., 'event tomorrow')"
    )
    print(f"  {Colors.CYAN}[s] Switch timepoint{Colors.END} - Switch between T0/T1/T2")
    print(f"  {Colors.CYAN}[q] Quit{Colors.END}            - Save and exit")
    print(f"  {Colors.CYAN}[b] Back{Colors.END}            - Go to previous email\n")

    choice = input(f"{Colors.BOLD}Your choice: {Colors.END}").lower().strip()

    # Handle note option
    if choice == "n":
        note = input(f"\n{Colors.CYAN}Enter note: {Colors.END}")
        return "note", note
    if choice == "t":
        hint = input(
            f"\n{Colors.CYAN}Enter temporal hint (e.g., 'event tomorrow', 'delivery today'): {Colors.END}"
        )
        return "temporal_hint", hint

    return choice, None


def save_progress(csv_path, df):
    """Save current progress to CSV."""
    df.to_csv(csv_path, index=False)
    print(f"\n{Colors.GREEN}✅ Progress saved!{Colors.END}")


def choose_dataset():
    """Let user choose which dataset to label."""
    clear_screen()
    print(f"\n{Colors.BOLD}Choose dataset to label:{Colors.END}\n")

    # Find available datasets
    reports_dir = Path(__file__).parent.parent / "reports"
    datasets = sorted(reports_dir.glob("dataset*.csv"))

    if not datasets:
        print(
            f"{Colors.RED}❌ No temporal datasets found. Run create_temporal_digest_review.py first.{Colors.END}"
        )
        return None

    for idx, dataset_path in enumerate(datasets, 1):
        # Extract descriptive name from filename
        name = dataset_path.stem.replace("dataset", "Dataset ").replace("_", " ")
        print(f"  [{idx}] {name}")

    print("  [q] Quit\n")

    choice = input(f"{Colors.BOLD}Your choice: {Colors.END}").strip()

    if choice == "q":
        return None

    try:
        choice_idx = int(choice) - 1
        if 0 <= choice_idx < len(datasets):
            return datasets[choice_idx]
    except ValueError:
        pass

    # Default to first dataset
    return datasets[0] if datasets else None


def choose_timepoint():
    """Let user choose which timepoint to label."""
    clear_screen()
    print(f"\n{Colors.BOLD}Choose timepoint to label:{Colors.END}\n")
    print("  [1] T0 - Just Received (emails just arrived)")
    print("  [2] T1 - +24 Hours (1 day after emails arrived)")
    print("  [3] T2 - +1 Week (7 days after emails arrived)")
    print("  [q] Quit\n")

    choice = input(f"{Colors.BOLD}Your choice: {Colors.END}").strip()

    if choice == "1":
        return "t0"
    if choice == "2":
        return "t1"
    if choice == "3":
        return "t2"
    if choice == "q":
        return None
    return "t0"  # Default


def main():
    # Choose dataset
    csv_path = choose_dataset()
    if csv_path is None:
        return

    # Load CSV
    df = pd.read_csv(csv_path)

    # Choose timepoint
    timepoint = choose_timepoint()
    if timepoint is None:
        return

    # Track current position
    current_idx = 0
    total = len(df)

    # Main review loop
    while current_idx < total:
        email = df.iloc[current_idx]

        show_email(current_idx, total, email, timepoint)
        choice, extra_data = get_user_choice(timepoint)

        if choice == "q":
            save_progress(csv_path, df)
            print(
                f"\n{Colors.CYAN}Progress saved. You reviewed {current_idx + 1}/{total} emails at {timepoint.upper()}.{Colors.END}"
            )
            break
        if choice == "b":
            if current_idx > 0:
                current_idx -= 1
            else:
                print(f"\n{Colors.YELLOW}Already at first email!{Colors.END}")
                input("Press Enter to continue...")
            continue
        if choice == "note":
            df.at[current_idx, "notes"] = extra_data
            print(f"\n{Colors.GREEN}✅ Note saved!{Colors.END}")
            input("Press Enter to continue...")
            continue
        if choice == "temporal_hint":
            df.at[current_idx, "temporal_hints"] = extra_data
            print(f"\n{Colors.GREEN}✅ Temporal hint saved!{Colors.END}")
            input("Press Enter to continue...")
            continue
        if choice == "s":
            # Save before switching
            save_progress(csv_path, df)
            # Choose new timepoint
            new_timepoint = choose_timepoint()
            if new_timepoint:
                timepoint = new_timepoint
                current_idx = 0  # Start from beginning for new timepoint
            continue

        # Clear all columns for this timepoint
        prefix = f"{timepoint}_"
        df.at[current_idx, f"{prefix}critical"] = ""
        df.at[current_idx, f"{prefix}today"] = ""
        df.at[current_idx, f"{prefix}coming_up"] = ""
        df.at[current_idx, f"{prefix}worth_knowing"] = ""
        df.at[current_idx, f"{prefix}everything_else"] = ""
        df.at[current_idx, f"{prefix}skip"] = ""

        # Mark chosen section
        if choice == "1":
            df.at[current_idx, f"{prefix}critical"] = "X"
            current_idx += 1
        elif choice == "2":
            df.at[current_idx, f"{prefix}today"] = "X"
            current_idx += 1
        elif choice == "3":
            df.at[current_idx, f"{prefix}coming_up"] = "X"
            current_idx += 1
        elif choice == "4":
            df.at[current_idx, f"{prefix}worth_knowing"] = "X"
            current_idx += 1
        elif choice == "5":
            df.at[current_idx, f"{prefix}everything_else"] = "X"
            current_idx += 1
        elif choice == "6":
            df.at[current_idx, f"{prefix}skip"] = "X"
            current_idx += 1
        else:
            print(f"\n{Colors.RED}Invalid choice. Please try again.{Colors.END}")
            input("Press Enter to continue...")
            continue

        # Auto-save every 10 emails
        if current_idx % 10 == 0:
            save_progress(csv_path, df)

    # Final save
    if current_idx >= total:
        save_progress(csv_path, df)
        print(
            f"\n{Colors.GREEN}🎉 All {total} emails reviewed for {timepoint.upper()}!{Colors.END}"
        )

        # Show summary
        print(f"\n{Colors.BOLD}SUMMARY FOR {timepoint.upper()}{Colors.END}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        prefix = f"{timepoint}_"
        critical_count = (df[f"{prefix}critical"] == "X").sum()
        today_count = (df[f"{prefix}today"] == "X").sum()
        coming_up_count = (df[f"{prefix}coming_up"] == "X").sum()
        worth_knowing_count = (df[f"{prefix}worth_knowing"] == "X").sum()
        everything_else_count = (df[f"{prefix}everything_else"] == "X").sum()
        skip_count = (df[f"{prefix}skip"] == "X").sum()

        print(f"🚨 CRITICAL:       {critical_count} emails")
        print(f"📦 TODAY:          {today_count} emails")
        print(f"📅 COMING UP:      {coming_up_count} emails")
        print(f"💼 WORTH KNOWING:  {worth_knowing_count} emails")
        print(f"📬 EVERYTHING ELSE: {everything_else_count} emails")
        print(f"⏭️  SKIP:           {skip_count} emails")

        print(f"\n{Colors.CYAN}Results saved to: {csv_path}{Colors.END}\n")

        # Prompt to label other timepoints
        if timepoint == "t0":
            print(
                f"{Colors.YELLOW}Next: Label T1 (+24 hours) and T2 (+72 hours) scenarios{Colors.END}"
            )
        elif timepoint == "t1":
            print(f"{Colors.YELLOW}Next: Label T2 (+72 hours) scenario{Colors.END}")


if __name__ == "__main__":
    main()
