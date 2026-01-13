#!/usr/bin/env python3
"""
Manual labeling interface for golden dataset emails.

Labels match MailQ's actual importance_classifier.py patterns and Phase 4
deterministic up-rank rules from the classification refactor plan.

Quick keys: c (critical), t (time_sensitive), r (routine), s (skip), q (quit)
Saves progress incrementally so you can resume.
"""

import csv
from collections import Counter
from pathlib import Path


def suggest_importance(subject: str, snippet: str) -> tuple:
    """
    Suggest importance based on MailQ's actual classification patterns.
    Returns (suggested_importance, reason)

    Based on mailq/importance_classifier.py and Phase 4 deterministic up-ranks.
    """
    combined = f"{subject} {snippet}".lower()

    # CRITICAL patterns (from importance_classifier.py)

    # Bills - payment due, overdue, failed
    if any(
        pattern in combined
        for pattern in [
            "bill due",
            "payment due",
            "invoice due",
            "balance due",
            "overdue",
            "past due",
            "final notice",
            "late fee",
            "payment failed",
            "payment declined",
            "payment unsuccessful",
            "balance is low",
            "low balance",
            "balance alert",
        ]
    ):
        return ("critical", "Bills/payment due or failed")

    # Financial alerts - fraud, unauthorized, breach
    if any(
        pattern in combined
        for pattern in [
            "suspicious transaction",
            "unauthorized charge",
            "fraud alert",
            "unusual activity",
            "account flagged",
            "locked account",
            "scam attempt",
            "phishing attempt",
            "suspicious login",
            "data breach",
            "account compromised",
            "personal data exposed",
            "security incident",
            "unauthorized access",
        ]
    ):
        return ("critical", "Fraud/security alert")

    # Refunds - money back is critical
    if any(
        pattern in combined
        for pattern in [
            "refund issued",
            "refund processed",
            "refund detected",
            "money back",
            "credit issued",
            "reimbursement",
        ]
    ):
        return ("critical", "Refund issued")

    # Delivery urgent - arriving today
    if any(
        pattern in combined
        for pattern in [
            "arriving today",
            "out for delivery",
            "delivery attempted",
            "delivery exception",
            "requires signature",
            "delivery today",
            "arrives today",
        ]
    ):
        return ("critical", "Delivery today")

    # Cancellations - need immediate rebooking
    if any(
        pattern in combined
        for pattern in [
            "cancelled",
            "canceled",
            "flight cancelled",
            "appointment cancelled",
            "reservation cancelled",
            "booking cancelled",
            "event cancelled",
        ]
    ):
        return ("critical", "Cancellation - needs action")

    # Account issues - locked, suspended
    if any(
        pattern in combined
        for pattern in [
            "account locked",
            "account suspended",
            "account deactivated",
            "verify account security",
            "security verification required",
        ]
    ):
        return ("critical", "Account locked/suspended")

    # Critical deadlines - due today
    if any(pattern in combined for pattern in ["due today", "payment due today", "bill due today"]):
        return ("critical", "Due today")

    # TIME-SENSITIVE patterns (from importance_classifier.py)

    # Events soon - tomorrow, in 1-2 days, this week
    if any(
        pattern in combined
        for pattern in [
            "tomorrow",
            "in 1 day",
            "in 2 days",
            "this week",
            "starts tomorrow",
            "begins tomorrow",
            "coming up",
        ]
    ):
        return ("time_sensitive", "Event/deadline soon (≤7 days)")

    # Deadlines and urgency
    if any(
        pattern in combined
        for pattern in [
            "expires today",
            "ends today",
            "deadline today",
            "urgent",
            "time sensitive",
            "immediate action",
            "action required",
            "respond by",
            "required by",
        ]
    ):
        return ("time_sensitive", "Urgent deadline/action required")

    # Expiring soon - final hours
    if any(
        pattern in combined
        for pattern in [
            "ending soon",
            "final hours",
            "expires soon",
            "deadline approaching",
            "expiring soon",
            "last chance",
        ]
    ):
        return ("time_sensitive", "Expiring soon")

    # Shipment arriving (not today)
    if any(
        pattern in combined
        for pattern in [
            "arriving",
            "estimated delivery",
            "on its way",
            "on the way",
            "shipped",
            "tracking",
            "shipment",
        ]
    ):
        return ("time_sensitive", "Shipment/delivery arriving soon")

    # Appointments and bookings
    if any(
        pattern in combined
        for pattern in [
            "appointment",
            "booking confirmation",
            "reservation confirmed",
            "reminder",
            "upcoming",
        ]
    ):
        return ("time_sensitive", "Appointment/booking reminder")

    # Flight confirmations
    if any(
        pattern in combined
        for pattern in ["flight", "boarding pass", "check-in", "gate", "confirmation"]
    ) and any(word in combined for word in ["flight", "airline", "airport"]):
        return ("time_sensitive", "Flight confirmation")

    # Job opportunities
    if (
        any(
            pattern in combined
            for pattern in ["job opening", "hiring", "interview", "opportunity", "application"]
        )
        and "job" in combined
    ):
        return ("time_sensitive", "Job opportunity")

    # Medical/insurance claims
    if any(
        pattern in combined
        for pattern in ["claim", "policy", "authorization", "medical", "insurance"]
    ) and any(word in combined for word in ["claim", "policy"]):
        return ("time_sensitive", "Medical/insurance claim")

    # ROUTINE patterns (default or forced down-rank)

    # OTPs/verification codes - MUST be routine (guardrail)
    if any(
        pattern in combined
        for pattern in [
            "verification code",
            "otp",
            "2fa",
            "two-factor",
            "security code",
            "login code",
            "authenticate",
        ]
    ):
        return ("routine", "OTP/verification code (force_non_critical)")

    # Autopay - automated payments are FYI only
    if "autopay" in combined or "auto-pay" in combined or "automatic payment" in combined:
        return ("routine", "Autopay confirmation (force_non_critical)")

    # Newsletters
    if any(
        pattern in combined
        for pattern in ["newsletter", "unsubscribe", "weekly digest", "monthly update"]
    ):
        return ("routine", "Newsletter/digest")

    # Promotions (non-expiring)
    if any(
        pattern in combined for pattern in ["sale", "discount", "% off", "promotion", "deal"]
    ) and not any(urgent in combined for urgent in ["ending soon", "last chance", "expires"]):
        return ("routine", "Promotion (non-urgent)")

    # Social notifications
    if any(
        pattern in combined
        for pattern in [
            "liked your",
            "commented on",
            "new connection",
            "friend request",
            "new follower",
            "mentioned you",
        ]
    ):
        return ("routine", "Social notification")

    # Subscription renewals
    if any(
        pattern in combined
        for pattern in ["subscription renewed", "auto-renewed", "renewal confirmation"]
    ):
        return ("routine", "Subscription renewal")

    # Receipts (without issues)
    if any(
        pattern in combined
        for pattern in [
            "receipt",
            "order confirmation",
            "purchase confirmed",
            "thank you for your order",
        ]
    ) and not any(issue in combined for issue in ["refund", "cancelled", "failed"]):
        return ("routine", "Receipt (no issues)")

    return ("routine", "Default (no strong signals)")


def print_email_preview(email: dict, index: int, total: int):
    """Print email info for labeling."""
    print("\n" + "=" * 80)
    print(f"Email {index + 1}/{total}")
    print("=" * 80)
    print(f"From: {email.get('from_email', 'Unknown')}")
    print(f"Subject: {email.get('subject', 'No subject')}")
    if email.get("snippet"):
        print(f"Snippet: {email.get('snippet', '')[:200]}...")
    else:
        print("Snippet: (not available)")
    print(f"Date: {email.get('received_date', 'Unknown')}")

    # Show suggestion
    suggested, reason = suggest_importance(email.get("subject", ""), email.get("snippet", ""))
    print(f"\n💡 Suggested: {suggested} ({reason})")


def get_label_input(can_undo=False):
    """Get importance label from user."""
    print("\nLabel this email:")
    print("  [c] Critical      - Bills due, fraud, refunds, delivery today, cancellations")
    print("  [t] Time-sensitive - Events ≤7d, deadlines ≤48h, shipments, jobs, claims")
    print("  [r] Routine       - Newsletters, promos, receipts, OTPs, social, autopay")
    print("  [s] Skip          - Move to next")
    if can_undo:
        print("  [u] Undo          - Go back to previous email")
    print("  [q] Quit          - Save and exit")
    print("  [?] Help          - Show detailed guidelines")

    return input("\nYour choice: ").strip().lower()


def show_guidelines():
    """Show detailed labeling guidelines based on MailQ's actual system."""
    print("\n" + "=" * 80)
    print("MAILQ IMPORTANCE LABELING GUIDELINES")
    print("Based on importance_classifier.py + Phase 4 deterministic up-ranks")
    print("=" * 80)

    print("\n🔴 CRITICAL (7-15% of emails) - ALWAYS surface, require immediate action")
    print("-" * 80)
    print("Bills & Payments:")
    print("  • Bill due, payment due, invoice due, balance due")
    print("  • Overdue, past due, final notice, late fee")
    print("  • Payment failed, payment declined, balance is low")
    print()
    print("Fraud & Security:")
    print("  • Suspicious transaction, unauthorized charge, fraud alert")
    print("  • Unusual activity, data breach, account compromised")
    print("  • Phishing attempt, security incident, unauthorized access")
    print()
    print("Refunds (Money back is critical!):")
    print("  • Refund issued, refund processed, money back, credit issued")
    print()
    print("Delivery Today:")
    print("  • Arriving today, out for delivery, delivery attempted")
    print("  • Delivery exception, requires signature")
    print()
    print("Cancellations (Require rebooking):")
    print("  • Flight cancelled, appointment cancelled, reservation cancelled")
    print("  • Event cancelled, booking cancelled")
    print()
    print("Account Issues:")
    print("  • Account locked, account suspended, account deactivated")
    print("  • Security verification required")
    print()

    print("\n🟡 TIME-SENSITIVE (25-35%) - Conditionally surface, time-bound value")
    print("-" * 80)
    print("Events Soon (≤7 days via Phase 4 deterministic up-rank):")
    print("  • Tomorrow, in 1-2 days, this week, starts tomorrow, coming up")
    print()
    print("Deadlines (≤48h via Phase 4 deterministic up-rank):")
    print("  • Expires today, ends today, deadline today")
    print("  • Urgent, action required, immediate action, respond by")
    print()
    print("Expiring Soon:")
    print("  • Ending soon, final hours, expires soon, last chance")
    print()
    print("Deliveries (not today):")
    print("  • Arriving, estimated delivery, on the way, shipped, tracking")
    print()
    print("Appointments & Confirmations:")
    print("  • Appointment reminder, booking confirmation, reservation confirmed")
    print()
    print("Flights:")
    print("  • Flight confirmation, boarding pass, check-in, gate assignment")
    print()
    print("Job Opportunities:")
    print("  • Job opening, hiring, interview, application opportunity")
    print()
    print("Medical/Insurance:")
    print("  • Claim deadline, policy authorization, medical appointment")
    print()

    print("\n⚪ ROUTINE (50-60%) - Background, no urgency, transparent grouping")
    print("-" * 80)
    print("FORCE Non-Critical (Guardrails - NEVER critical):")
    print("  • OTPs, verification codes, 2FA, security codes")
    print("  • Autopay confirmations, auto-renewed, automatic payment")
    print()
    print("Newsletters & Digests:")
    print("  • Newsletter, weekly digest, monthly update, unsubscribe")
    print()
    print("Promotions (non-urgent):")
    print("  • Sale, discount, % off (without 'ending soon' or 'last chance')")
    print()
    print("Receipts (no issues):")
    print("  • Order confirmation, receipt, purchase confirmed")
    print("  • (If has refund/cancellation → escalate to critical)")
    print()
    print("Social Notifications:")
    print("  • Liked your post, new connection, friend request, mentioned you")
    print()
    print("Subscription Renewals:")
    print("  • Subscription renewed, auto-renewed, renewal confirmation")
    print()
    print("Calendar Responses (auto-skip):")
    print("  • Accepted, declined, tentative responses")
    print()

    print("=" * 80)
    print("\n💡 KEY PRINCIPLES:")
    print("  1. Money matters → CRITICAL (bills, refunds, fraud)")
    print("  2. Time-bound urgency → TIME-SENSITIVE (≤7d events, ≤48h deadlines)")
    print("  3. Forced down-ranks → ROUTINE (OTPs, autopay, regardless of language)")
    print("  4. When in doubt → Check current importance_classifier.py patterns")
    print("=" * 80)
    input("\nPress Enter to continue...")


def main():
    input_path = Path("tests/golden_set/golden_dataset_500.csv")
    output_path = Path("tests/golden_set/golden_dataset_500_labeled.csv")
    progress_path = Path("tests/golden_set/.labeling_progress.txt")

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return

    # Load dataset
    print(f"📂 Loading dataset from {input_path}")
    with open(input_path) as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    print(f"   Found {len(emails)} emails")

    # Load progress if exists
    labeled_count = 0
    if progress_path.exists():
        with open(progress_path) as f:
            labeled_count = int(f.read().strip())
        print(f"   Resuming from email #{labeled_count + 1}")

    # Filter to unlabeled emails
    # Need to label:
    # 1. Historical emails (placeholder labels from Gmail fetch)
    # 2. Existing emails (old MailQ logic, need gds-1.0 alignment)
    # Already labeled:
    # 3. P0 critical cases (manual_p0_pattern labels are trusted)
    # 4. Manually labeled emails (decider='manual')

    unlabeled = [
        (i, e)
        for i, e in enumerate(emails)
        if i >= labeled_count and e.get("decider") not in ["manual", "manual_p0_pattern"]
    ]

    if not unlabeled:
        print("✅ All emails are labeled!")
        return

    print(f"\n🎯 {len(unlabeled)} emails need labeling")
    print(f"   Progress: {labeled_count}/{len(emails)} total emails processed")

    importance_map = {"c": "critical", "t": "time_sensitive", "r": "routine"}

    stats = Counter()
    labeled_this_session = 0
    labeling_history = []  # Track history for undo

    try:
        idx = 0
        while idx < len(unlabeled):
            original_idx, email = unlabeled[idx]
            print_email_preview(email, idx, len(unlabeled))

            while True:
                can_undo = idx > 0  # Can undo if not on first email
                choice = get_label_input(can_undo)

                if choice == "q":
                    print("\n💾 Saving progress...")
                    raise KeyboardInterrupt

                if choice == "?":
                    show_guidelines()
                    print_email_preview(email, idx, len(unlabeled))
                    continue

                if choice == "s":
                    print("⏭️  Skipped")
                    idx += 1
                    break

                if choice == "u" and can_undo:
                    # Undo last label
                    if labeling_history:
                        last_action = labeling_history.pop()
                        prev_idx = last_action["idx"]
                        prev_email = last_action["email"]
                        prev_importance = last_action["old_importance"]

                        # Restore previous state
                        prev_email["importance"] = prev_importance
                        prev_email["importance_reason"] = last_action["old_reason"]
                        prev_email["decider"] = last_action["old_decider"]

                        # Update stats
                        if last_action["new_importance"] in stats:
                            stats[last_action["new_importance"]] -= 1
                        labeled_this_session -= 1

                        # Go back to previous email
                        idx = prev_idx
                        print(f"↩️  Undoing last label, going back to email #{idx + 1}")
                        break
                    print("❌ Nothing to undo")
                    continue

                if choice in importance_map:
                    importance = importance_map[choice]

                    # Save current state for undo
                    labeling_history.append(
                        {
                            "idx": idx,
                            "email": email,
                            "old_importance": email.get("importance"),
                            "old_reason": email.get("importance_reason"),
                            "old_decider": email.get("decider"),
                            "new_importance": importance,
                        }
                    )

                    # Apply new label
                    email["importance"] = importance
                    email["importance_reason"] = f"manual_label_{importance}"
                    email["decider"] = "manual"
                    stats[importance] += 1
                    labeled_this_session += 1
                    print(f"✅ Labeled as: {importance}")

                    # Save progress
                    labeled_count = original_idx + 1
                    with open(progress_path, "w") as f:
                        f.write(str(labeled_count))

                    idx += 1
                    break

                if choice == "u" and not can_undo:
                    print("❌ Can't undo - this is the first email")
                    continue

                print("❌ Invalid choice. Try again.")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")

    # Write labeled dataset
    print(f"\n💾 Saving labeled dataset to {output_path}...")
    with open(output_path, "w", newline="") as f:
        if emails:
            writer = csv.DictWriter(f, fieldnames=emails[0].keys())
            writer.writeheader()
            writer.writerows(emails)

    print(f"✅ Saved {len(emails)} emails")
    print("\n📊 Labeling Session Stats:")
    print(f"   Labeled this session: {labeled_this_session}")
    for imp, count in stats.items():
        print(f"   {imp}: {count}")

    # Final distribution
    final_dist = Counter(e["importance"] for e in emails)
    total_labeled = sum(
        1 for e in emails if e.get("decider") in ["manual", "mailq_db", "manual_p0_pattern"]
    )

    print("\n📊 Overall Dataset Status:")
    print(f"   Total emails: {len(emails)}")
    print(f"   Labeled: {total_labeled}/{len(emails)} ({total_labeled / len(emails) * 100:.1f}%)")
    print("\n   Importance distribution:")
    for imp in ["routine", "time_sensitive", "critical"]:
        count = final_dist.get(imp, 0)
        pct = (count / len(emails) * 100) if emails else 0
        balanced = "✅" if pct <= 60 else "⚠️ "
        print(f"     {balanced} {imp}: {count} ({pct:.1f}%)")

    remaining = len(emails) - total_labeled
    if remaining > 0:
        print(f"\n⚠️  {remaining} emails still need labeling")
        print("   Run this script again to continue")
    else:
        print("\n🎉 All emails are labeled! Dataset is ready for Phase 0.")
        # Copy to final location
        final_path = Path("tests/golden_set/golden_dataset.csv")
        with open(final_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=emails[0].keys())
            writer.writeheader()
            writer.writerows(emails)
        print(f"   ✅ Final dataset: {final_path}")


if __name__ == "__main__":
    main()
