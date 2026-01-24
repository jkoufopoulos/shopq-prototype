#!/usr/bin/env python3
"""
Interactive CLI for labeling emails as purchase-related or not.

This script:
1. Loads emails from data/labeling/emails_to_label.json
2. Uses ShopQ's filter logic to SUGGEST labels (you accept/reject)
3. Saves labeled results to data/labeling/labeled_emails.json

For each email, you see a suggestion and can:
- [Y] Accept the suggestion
- [N] Reject and flip the label
- [V] View full body
- [E] Extract purchase details (for purchases)
- [S] Skip this email
- [Q] Quit and save

Usage:
    python scripts/labeling/label_emails.py [--resume] [--input FILE] [--output FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from shopq.returns.filters import MerchantDomainFilter
from shopq.returns.returnability_classifier import ReturnabilityClassifier


# ANSI color codes for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def clear_screen():
    """Clear terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def truncate(text: str, max_len: int = 100) -> str:
    """Truncate text to max length."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def extract_domain(from_address: str) -> str:
    """Extract domain from email address."""
    match = re.search(r"@([a-zA-Z0-9.-]+)", from_address)
    if match:
        return match.group(1).lower()
    return ""


def suggest_label_rules(email: dict, domain_filter: MerchantDomainFilter) -> tuple[str, str, float]:
    """
    Use rules-based filter for quick suggestion (fallback).

    Returns:
        (suggested_label, reason, confidence)
    """
    from_address = email.get("from_address", "")
    subject = email.get("subject", "")
    body = email.get("body_text", "") or email.get("snippet", "")

    # Run through the domain filter
    result = domain_filter.filter(from_address, subject, body)

    if result.is_candidate:
        confidence = 0.7 if result.match_type in ("allowlist", "heuristic_delivery") else 0.5
        return "PURCHASE", f"[Rules] {result.reason}", confidence
    else:
        confidence = 0.9 if result.match_type in ("blocklist", "grocery") else 0.6
        return "NOT_PURCHASE", f"[Rules] {result.reason}", confidence


def suggest_label_llm(
    email: dict,
    classifier: ReturnabilityClassifier,
    domain_filter: MerchantDomainFilter,
) -> tuple[str, str, float]:
    """
    Use LLM classifier for AI-powered suggestion.

    Returns:
        (suggested_label, reason, confidence)
    """
    from_address = email.get("from_address", "")
    subject = email.get("subject", "")
    body = email.get("body_text", "") or email.get("snippet", "")

    # First check rules filter (fast, free)
    filter_result = domain_filter.filter(from_address, subject, body)

    # If rules are very confident it's NOT a purchase, use that
    if filter_result.match_type in ("blocklist", "grocery"):
        return "NOT_PURCHASE", filter_result.reason, 0.95

    # Otherwise, use LLM
    try:
        result = classifier.classify(from_address, subject, body)

        if result.is_returnable:
            # Simplify reason - just show the core insight
            return "PURCHASE", result.reason, result.confidence
        else:
            return "NOT_PURCHASE", result.reason, result.confidence

    except Exception as e:
        # Fallback to rules if LLM fails
        print(f"  LLM error, using rules fallback: {e}")
        return suggest_label_rules(email, domain_filter)


def display_email(email: dict, index: int, total: int, suggestion: str, reason: str, confidence: float):
    """Display email with suggestion for labeling."""
    print("\n" + "=" * 70)
    print(f"{Colors.BOLD}EMAIL {index + 1} of {total}{Colors.RESET}")
    print("=" * 70)

    # Show suggestion prominently with color
    conf_pct = int(confidence * 100)
    if suggestion == "PURCHASE":
        print(f"\n{Colors.BOLD}{Colors.GREEN}>>> SUGGESTED: PURCHASE ({conf_pct}% confident){Colors.RESET}")
    else:
        print(f"\n{Colors.BOLD}{Colors.YELLOW}>>> SUGGESTED: NOT PURCHASE ({conf_pct}% confident){Colors.RESET}")
    print(f"{Colors.DIM}    Reason: {reason}{Colors.RESET}")

    print(f"\n{Colors.CYAN}From:{Colors.RESET}     {email.get('from_address', 'N/A')}")
    print(f"{Colors.CYAN}Domain:{Colors.RESET}   {Colors.BOLD}{extract_domain(email.get('from_address', ''))}{Colors.RESET}")
    print(f"{Colors.CYAN}Subject:{Colors.RESET}  {email.get('subject', 'N/A')}")
    print(f"{Colors.CYAN}Date:{Colors.RESET}     {email.get('date', email.get('received_at', 'N/A'))}")

    print("\n--- Snippet ---")
    print(email.get("snippet", "No snippet available"))

    # Show body preview if available
    body = email.get("body_text", "") or email.get("body_html", "")
    if body:
        # Clean HTML if needed
        if email.get("body_html") and not email.get("body_text"):
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()

        print("\n--- Body Preview (first 300 chars) ---")
        print(truncate(body, 300))

    print("\n" + "-" * 70)


def get_user_choice(suggestion: str) -> str:
    """Get user's choice for the suggested label."""
    if suggestion == "PURCHASE":
        print(f"\n{Colors.GREEN}[Enter/Y] Accept as PURCHASE{Colors.RESET}")
        print(f"{Colors.YELLOW}[N] Change to NOT_PURCHASE{Colors.RESET}")
    else:
        print(f"\n{Colors.GREEN}[Enter/Y] Accept as NOT_PURCHASE{Colors.RESET}")
        print(f"{Colors.CYAN}[N] Change to PURCHASE{Colors.RESET}")

    print(f"{Colors.DIM}[V] View full body{Colors.RESET}")
    print(f"{Colors.DIM}[S] Skip{Colors.RESET}")
    print(f"{Colors.DIM}[Q] Quit and save{Colors.RESET}")
    print()

    while True:
        choice = input(f"{Colors.BOLD}Your choice [Enter/N/V/S/Q]: {Colors.RESET}").strip().upper()
        # Enter (empty) = accept
        if choice == "":
            return "Y"
        if choice in ("Y", "N", "V", "S", "Q"):
            return choice
        print(f"{Colors.RED}Invalid choice. Press Enter to accept, or N/V/S/Q.{Colors.RESET}")


def view_full_body(email: dict):
    """Display full email body."""
    clear_screen()
    print("=" * 70)
    print("FULL EMAIL BODY")
    print("=" * 70)

    body = email.get("body_text", "") or email.get("body_html", "")
    if body:
        if email.get("body_html") and not email.get("body_text"):
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()
        print(body[:5000])
    else:
        print("No body available")

    print("\n" + "=" * 70)
    input("\nPress Enter to continue...")


def extract_purchase_info(email: dict) -> dict:
    """Prompt user to extract purchase info from email."""
    print("\n" + "-" * 40)
    print("EXTRACT PURCHASE DETAILS")
    print("-" * 40)

    domain = extract_domain(email.get("from_address", ""))

    # Try to suggest merchant name from domain
    suggested_merchant = domain.replace(".com", "").replace(".co", "").replace("mail.", "").replace("email.", "").title()

    merchant = input(f"Merchant name [{suggested_merchant}]: ").strip()
    if not merchant:
        merchant = suggested_merchant

    item_summary = input("Item summary (brief description): ").strip()

    order_number = input("Order number (if visible): ").strip() or None

    amount_str = input("Amount (e.g., 29.99): ").strip()
    amount = float(amount_str) if amount_str else None

    order_date = input("Order date (YYYY-MM-DD, if visible): ").strip() or None
    delivery_date = input("Delivery date (YYYY-MM-DD, if visible): ").strip() or None
    return_by_date = input("Return-by date (YYYY-MM-DD, if visible): ").strip() or None

    return {
        "merchant": merchant,
        "merchant_domain": domain,
        "item_summary": item_summary or "Unknown item",
        "order_number": order_number,
        "amount": amount,
        "order_date": order_date,
        "delivery_date": delivery_date,
        "return_by_date": return_by_date,
    }


def label_emails(input_path: str, output_path: str, resume: bool = True, use_llm: bool = True):
    """Main labeling loop with AI suggestions."""
    # Load emails
    print(f"Loading emails from {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    emails = data.get("emails", [])
    metadata = data.get("metadata", {})

    print(f"Found {len(emails)} emails to label")

    # Initialize the domain filter for suggestions
    print("Loading filter rules...")
    domain_filter = MerchantDomainFilter()

    # Initialize LLM classifier if enabled
    classifier = None
    if use_llm:
        print("Initializing AI classifier (Gemini)...")
        try:
            classifier = ReturnabilityClassifier()
            print("AI classifier ready!")
        except Exception as e:
            print(f"Warning: Could not initialize AI classifier: {e}")
            print("Falling back to rules-based suggestions.")
            use_llm = False

    # Load existing labels if resuming
    labeled = {}
    purchases = []

    if resume and os.path.exists(output_path):
        print(f"Loading existing labels from {output_path}...")
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
            for item in existing.get("labeled_emails", []):
                labeled[item["message_id"]] = item
            purchases = existing.get("purchases", [])
            print(f"  Loaded {len(labeled)} existing labels, {len(purchases)} purchases")

    # Find unlabeled emails
    unlabeled = [e for e in emails if e["message_id"] not in labeled]
    print(f"\n{len(unlabeled)} emails remaining to label")

    if not unlabeled:
        print("All emails have been labeled!")
        return

    input("\nPress Enter to start labeling...")

    # Label emails
    try:
        for i, email in enumerate(unlabeled):
            # Get suggestion (LLM if available, otherwise rules)
            if use_llm and classifier:
                suggestion, reason, confidence = suggest_label_llm(email, classifier, domain_filter)
            else:
                suggestion, reason, confidence = suggest_label_rules(email, domain_filter)

            clear_screen()
            display_email(email, i, len(unlabeled), suggestion, reason, confidence)

            while True:
                choice = get_user_choice(suggestion)

                if choice == "V":
                    view_full_body(email)
                    display_email(email, i, len(unlabeled), suggestion, reason, confidence)
                    continue

                if choice == "Q":
                    raise KeyboardInterrupt

                if choice == "S":
                    # Skip without labeling
                    print("Skipped")
                    break

                # Determine final label
                if choice == "Y":
                    label = suggestion
                elif choice == "N":
                    label = "PURCHASE" if suggestion == "NOT_PURCHASE" else "NOT_PURCHASE"
                else:
                    continue

                # Record the label (no detail extraction - that happens in Phase 2)
                labeled_item = {
                    "message_id": email["message_id"],
                    "from_address": email.get("from_address", ""),
                    "subject": email.get("subject", ""),
                    "snippet": email.get("snippet", ""),
                    "body_text": email.get("body_text", ""),
                    "received_at": email.get("received_at", ""),
                    "label": label,
                    "suggested_label": suggestion,
                    "suggestion_reason": reason,
                    "suggestion_accepted": (choice == "Y"),
                    "labeled_at": datetime.now(UTC).isoformat(),
                }

                labeled[email["message_id"]] = labeled_item

                if label == "PURCHASE":
                    purchases.append(labeled_item)
                break

            # Save progress after each email
            save_results(output_path, labeled, purchases, metadata)
            print(f"{Colors.GREEN}{Colors.BOLD}✓ SAVED{Colors.RESET} {Colors.DIM}({len(labeled)} labeled, {len(purchases)} purchases){Colors.RESET}")

    except KeyboardInterrupt:
        print("\n\nSaving progress...")

    # Final save
    save_results(output_path, labeled, purchases, metadata)

    # Summary
    print("\n" + "=" * 60)
    print(f"{Colors.BOLD}LABELING SUMMARY{Colors.RESET}")
    print("=" * 60)

    labels_count = {"PURCHASE": 0, "NOT_PURCHASE": 0}
    accepted = 0
    rejected = 0

    for item in labeled.values():
        labels_count[item["label"]] += 1
        if item.get("suggestion_accepted"):
            accepted += 1
        else:
            rejected += 1

    print(f"\nTotal labeled: {Colors.BOLD}{len(labeled)}{Colors.RESET}")
    print(f"  {Colors.GREEN}PURCHASE:{Colors.RESET}     {labels_count['PURCHASE']}")
    print(f"  {Colors.YELLOW}NOT_PURCHASE:{Colors.RESET} {labels_count['NOT_PURCHASE']}")
    print(f"\nSuggestion accuracy: {Colors.GREEN}{accepted} accepted{Colors.RESET}, {Colors.RED}{rejected} rejected{Colors.RESET}")
    print(f"\n{Colors.GREEN}{Colors.BOLD}✓ Results saved to:{Colors.RESET} {output_path}")

    if labels_count["PURCHASE"] > 0:
        print(f"\n{Colors.CYAN}Next step:{Colors.RESET} uv run python scripts/labeling/create_entities.py")


def save_results(output_path: str, labeled: dict, purchases: list, metadata: dict):
    """Save labeling results to JSON."""
    output_data = {
        "metadata": {
            **metadata,
            "labeling_status": "in_progress",
            "last_updated": datetime.now(UTC).isoformat(),
            "total_labeled": len(labeled),
        },
        "labeled_emails": list(labeled.values()),
        "purchases": purchases,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Label emails with AI suggestions")
    parser.add_argument(
        "--input",
        type=str,
        default=str(project_root / "data" / "labeling" / "emails_to_label.json"),
        help="Input JSON file with emails",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(project_root / "data" / "labeling" / "labeled_emails.json"),
        help="Output JSON file for labeled results",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh (don't resume from existing labels)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use rules-based suggestions instead of AI",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        print("Run 'python scripts/labeling/fetch_emails.py' first to fetch emails.")
        sys.exit(1)

    print("=" * 60)
    print("ShopQ Email Labeling Tool (with AI Suggestions)")
    print("=" * 60)

    label_emails(args.input, args.output, resume=not args.no_resume, use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
