"""
Interactive digest review tool.

Shows emails one at a time and lets you mark which digest section they belong in.
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


def show_email(idx, total, email):
    """Display email details."""
    clear_screen()

    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}"
    )
    print(f"{Colors.CYAN}Email {idx + 1} of {total}{Colors.END}")
    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}\n"
    )

    print(f"{Colors.BOLD}From:{Colors.END} {email['from']}")
    print(f"{Colors.BOLD}Subject:{Colors.END} {email['subject']}\n")
    print(f"{Colors.BOLD}Preview:{Colors.END}")
    print(f"{email['snippet']}\n")

    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}"
    )
    print(f"{Colors.YELLOW}System prediction:{Colors.END}")
    print(f"  Importance: {Colors.BOLD}{email['predicted_importance']}{Colors.END}")
    print(f"  Type: {email['predicted_type']}")
    print(
        f"{Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}\n"
    )


def get_user_choice():
    """Get user's section choice."""
    print(f"{Colors.GREEN}Which section should this email be in?{Colors.END}\n")
    print(f"  {Colors.RED}[1] 🚨 CRITICAL{Colors.END}       - Urgent: fraud, security, deadlines")
    print(f"  {Colors.YELLOW}[2] 📅 COMING UP{Colors.END}      - Events, deliveries, appointments")
    print(f"  {Colors.BLUE}[3] 💡 WORTH KNOWING{Colors.END}  - Receipts, confirmations, updates")
    print(
        f"  {Colors.CYAN}[4] 📬 EVERYTHING ELSE{Colors.END} - Promotions, newsletters, past events"
    )
    print(f"  {Colors.BOLD}[5] ⏭️  SKIP{Colors.END}           - Don't show in digest at all")
    print(f"  {Colors.CYAN}[n] Notes{Colors.END}          - Add a note about this email")
    print(f"  {Colors.CYAN}[q] Quit{Colors.END}           - Save and exit")
    print(f"  {Colors.CYAN}[b] Back{Colors.END}           - Go to previous email\n")

    choice = input(f"{Colors.BOLD}Your choice: {Colors.END}").lower().strip()

    # Handle note option
    if choice == "n":
        note = input(f"\n{Colors.CYAN}Enter note: {Colors.END}")
        return "note", note

    return choice, None


def save_progress(csv_path, df):
    """Save current progress to CSV."""
    df.to_csv(csv_path, index=False)
    print(f"\n{Colors.GREEN}✅ Progress saved!{Colors.END}")


def main():
    # Load CSV
    csv_path = Path(__file__).parent.parent / "reports" / "digest_review_100_emails.csv"

    if not csv_path.exists():
        print(f"{Colors.RED}❌ CSV not found. Run create_digest_review_csv.py first.{Colors.END}")
        return

    df = pd.read_csv(csv_path)

    # Track current position
    current_idx = 0
    total = len(df)

    # Main review loop
    while current_idx < total:
        email = df.iloc[current_idx]

        show_email(current_idx, total, email)
        choice, note = get_user_choice()

        if choice == "q":
            save_progress(csv_path, df)
            print(
                f"\n{Colors.CYAN}Progress saved. You reviewed {current_idx + 1}/{total} emails.{Colors.END}"
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
            df.at[current_idx, "notes"] = note
            print(f"\n{Colors.GREEN}✅ Note saved!{Colors.END}")
            input("Press Enter to continue...")
            continue
        if choice == "1":
            df.at[current_idx, "your_critical"] = "X"
            df.at[current_idx, "your_coming_up"] = ""
            df.at[current_idx, "your_worth_knowing"] = ""
            df.at[current_idx, "your_everything_else"] = ""
            df.at[current_idx, "your_skip"] = ""
            current_idx += 1
        elif choice == "2":
            df.at[current_idx, "your_critical"] = ""
            df.at[current_idx, "your_coming_up"] = "X"
            df.at[current_idx, "your_worth_knowing"] = ""
            df.at[current_idx, "your_everything_else"] = ""
            df.at[current_idx, "your_skip"] = ""
            current_idx += 1
        elif choice == "3":
            df.at[current_idx, "your_critical"] = ""
            df.at[current_idx, "your_coming_up"] = ""
            df.at[current_idx, "your_worth_knowing"] = "X"
            df.at[current_idx, "your_everything_else"] = ""
            df.at[current_idx, "your_skip"] = ""
            current_idx += 1
        elif choice == "4":
            df.at[current_idx, "your_critical"] = ""
            df.at[current_idx, "your_coming_up"] = ""
            df.at[current_idx, "your_worth_knowing"] = ""
            df.at[current_idx, "your_everything_else"] = "X"
            df.at[current_idx, "your_skip"] = ""
            current_idx += 1
        elif choice == "5":
            df.at[current_idx, "your_critical"] = ""
            df.at[current_idx, "your_coming_up"] = ""
            df.at[current_idx, "your_worth_knowing"] = ""
            df.at[current_idx, "your_everything_else"] = ""
            df.at[current_idx, "your_skip"] = "X"
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
        print(f"\n{Colors.GREEN}🎉 All {total} emails reviewed!{Colors.END}")

        # Show summary
        print(f"\n{Colors.BOLD}SUMMARY{Colors.END}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        critical_count = (df["your_critical"] == "X").sum()
        coming_up_count = (df["your_coming_up"] == "X").sum()
        worth_knowing_count = (df["your_worth_knowing"] == "X").sum()
        everything_else_count = (df["your_everything_else"] == "X").sum()
        skip_count = (df["your_skip"] == "X").sum()

        print(f"🚨 CRITICAL:       {critical_count} emails")
        print(f"📅 COMING UP:      {coming_up_count} emails")
        print(f"💡 WORTH KNOWING:  {worth_knowing_count} emails")
        print(f"📬 EVERYTHING ELSE: {everything_else_count} emails")
        print(f"⏭️  SKIP:           {skip_count} emails")

        # Compare to system predictions
        print(f"\n{Colors.BOLD}AGREEMENT WITH SYSTEM{Colors.END}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Calculate agreement for critical
        system_critical = df["predicted_importance"] == "critical"
        user_critical = df["your_critical"] == "X"
        critical_agreement = (system_critical == user_critical).sum() / total * 100

        # Calculate agreement for time_sensitive
        system_time_sensitive = df["predicted_importance"] == "time_sensitive"
        user_coming_up = df["your_coming_up"] == "X"
        time_sensitive_agreement = (system_time_sensitive == user_coming_up).sum() / total * 100

        # Calculate agreement for routine
        system_routine = df["predicted_importance"] == "routine"
        user_worth_knowing = df["your_worth_knowing"] == "X"
        routine_agreement = (system_routine == user_worth_knowing).sum() / total * 100

        print(f"Critical agreement:       {critical_agreement:.1f}%")
        print(f"Time-sensitive agreement: {time_sensitive_agreement:.1f}%")
        print(f"Routine agreement:        {routine_agreement:.1f}%")

        print(f"\n{Colors.CYAN}Results saved to: {csv_path}{Colors.END}\n")


if __name__ == "__main__":
    main()
