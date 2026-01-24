#!/usr/bin/env python3
"""
Phase 2: Create consolidated ReturnCard entities from labeled PURCHASE emails.

This script:
1. Loads PURCHASE-labeled emails from Phase 1
2. Uses AI (LLM) to extract purchase details from each email
3. Groups related emails (same order: confirmation → shipped → delivered)
4. Lets you review/edit each consolidated entity
5. Exports final ReturnCards to JSON

Usage:
    python scripts/labeling/create_entities.py [--input FILE] [--output FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from shopq.returns.models import ReturnCard, ReturnStatus, ReturnConfidence
from shopq.returns.field_extractor import ReturnFieldExtractor


def load_merchant_rules() -> dict:
    """Load merchant return rules from config."""
    rules_path = project_root / "config" / "merchant_rules.yaml"
    if not rules_path.exists():
        return {"_default": {"days": 30, "anchor": "delivery"}}

    import yaml
    with open(rules_path, "r") as f:
        data = yaml.safe_load(f)

    return data.get("merchants", {"_default": {"days": 30, "anchor": "delivery"}})


def get_merchant_rule(domain: str, rules: dict) -> dict:
    """Get return window rule for a merchant domain."""
    if domain in rules:
        return rules[domain]

    parts = domain.split(".")
    if len(parts) > 2:
        base_domain = ".".join(parts[-2:])
        if base_domain in rules:
            return rules[base_domain]

    return rules.get("_default", {"days": 30, "anchor": "delivery"})


def parse_date(date_str: str | None) -> datetime | None:
    """Parse date string to datetime."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None


def extract_domain(from_address: str) -> str:
    """Extract domain from email address."""
    match = re.search(r"@([a-zA-Z0-9.-]+)", from_address)
    if match:
        return match.group(1).lower()
    return ""


def extract_details_with_llm(email: dict, extractor: ReturnFieldExtractor, rules: dict) -> dict:
    """
    Use LLM to extract purchase details from email.

    Returns dict with: merchant, item_summary, order_number, amount, order_date, delivery_date, return_by_date
    """
    from_address = email.get("from_address", "")
    subject = email.get("subject", "")
    body = email.get("body_text", "") or email.get("snippet", "")
    domain = extract_domain(from_address)

    try:
        # Use the field extractor
        result = extractor.extract(from_address, subject, body, rules)

        return {
            "source_email_id": email.get("message_id", ""),
            "email_subject": subject,
            "email_from": from_address,
            "email_received_at": email.get("received_at", ""),
            "merchant": result.merchant_name or domain.replace(".com", "").title(),
            "merchant_domain": domain,
            "item_summary": result.item_summary or "Unknown item",
            "order_number": result.order_number,
            "amount": result.amount,
            "currency": result.currency or "USD",
            "order_date": result.order_date,
            "delivery_date": result.delivery_date,
            "return_by_date": result.return_by_date,
            "return_portal_link": result.return_portal_link,
            "extraction_method": result.extraction_method,
        }
    except Exception as e:
        print(f"    LLM extraction failed: {e}")
        # Return basic info from email headers
        return {
            "source_email_id": email.get("message_id", ""),
            "email_subject": subject,
            "email_from": from_address,
            "email_received_at": email.get("received_at", ""),
            "merchant": domain.replace(".com", "").replace("mail.", "").title(),
            "merchant_domain": domain,
            "item_summary": subject[:100] if subject else "Unknown item",
            "order_number": None,
            "amount": None,
            "order_date": None,
            "delivery_date": None,
            "return_by_date": None,
            "extraction_method": "fallback",
        }


def group_by_purchase(extracted: list[dict]) -> list[list[dict]]:
    """
    Group related emails into purchases.

    Grouping strategy:
    1. Same merchant domain + same order number → same purchase
    2. Same merchant domain without order number → separate purchases
    """
    by_merchant: dict[str, list[dict]] = defaultdict(list)
    for item in extracted:
        domain = item.get("merchant_domain", "unknown")
        by_merchant[domain].append(item)

    groups = []

    for domain, emails in by_merchant.items():
        by_order: dict[str, list[dict]] = defaultdict(list)
        no_order = []

        for email in emails:
            order_num = email.get("order_number")
            if order_num:
                by_order[order_num].append(email)
            else:
                no_order.append(email)

        # Add order-based groups
        for order_emails in by_order.values():
            groups.append(order_emails)

        # Each email without order number is its own group
        for email in no_order:
            groups.append([email])

    return groups


def merge_group(emails: list[dict]) -> dict:
    """Merge multiple emails about same purchase."""
    if len(emails) == 1:
        return emails[0].copy()

    merged = {
        "source_email_ids": [e.get("source_email_id", "") for e in emails],
        "email_subjects": [e.get("email_subject", "") for e in emails],
    }

    # Collect all values
    merchants = [e["merchant"] for e in emails if e.get("merchant")]
    items = [e["item_summary"] for e in emails if e.get("item_summary") and e["item_summary"] != "Unknown item"]
    order_numbers = [e["order_number"] for e in emails if e.get("order_number")]
    amounts = [e["amount"] for e in emails if e.get("amount")]
    order_dates = [e["order_date"] for e in emails if e.get("order_date")]
    delivery_dates = [e["delivery_date"] for e in emails if e.get("delivery_date")]
    return_dates = [e["return_by_date"] for e in emails if e.get("return_by_date")]
    return_links = [e["return_portal_link"] for e in emails if e.get("return_portal_link")]

    # Pick best values
    merged["merchant"] = merchants[0] if merchants else "Unknown"
    merged["merchant_domain"] = emails[0].get("merchant_domain", "")
    merged["item_summary"] = max(items, key=len) if items else "Unknown item"
    merged["order_number"] = order_numbers[0] if order_numbers else None
    merged["amount"] = amounts[0] if amounts else None
    merged["order_date"] = min(order_dates) if order_dates else None  # Earliest
    merged["delivery_date"] = max(delivery_dates) if delivery_dates else None  # Latest
    merged["return_by_date"] = return_dates[0] if return_dates else None
    merged["return_portal_link"] = return_links[0] if return_links else None

    return merged


def compute_return_by_date(purchase: dict, rules: dict) -> tuple[datetime | None, ReturnConfidence]:
    """Compute return-by date based on purchase info and merchant rules."""
    # Check for explicit return-by date
    if purchase.get("return_by_date"):
        return_date = parse_date(purchase["return_by_date"])
        if return_date:
            return return_date, ReturnConfidence.EXACT

    # Use merchant rules
    domain = purchase.get("merchant_domain", "")
    rule = get_merchant_rule(domain, rules)
    days = rule.get("days", 30)

    # Prefer delivery date, fall back to order date
    anchor_date = None
    if purchase.get("delivery_date"):
        anchor_date = parse_date(purchase["delivery_date"])
    if not anchor_date and purchase.get("order_date"):
        anchor_date = parse_date(purchase["order_date"])

    if anchor_date:
        return_date = anchor_date + timedelta(days=days)
        return return_date, ReturnConfidence.ESTIMATED

    return None, ReturnConfidence.UNKNOWN


def display_entity(merged: dict, index: int, total: int, rules: dict, num_emails: int):
    """Display a consolidated entity for review."""
    print("\n" + "=" * 70)
    print(f"ENTITY {index + 1} of {total}")
    if num_emails > 1:
        print(f"(consolidated from {num_emails} emails)")
    print("=" * 70)

    # Show source emails if multiple
    if merged.get("email_subjects"):
        print("\nSource emails:")
        for i, subj in enumerate(merged["email_subjects"][:5]):
            print(f"  {i+1}. {subj[:60]}")
        if len(merged.get("email_subjects", [])) > 5:
            print(f"  ... and {len(merged['email_subjects']) - 5} more")

    print(f"\n--- Extracted Details ---")
    print(f"Merchant:      {merged.get('merchant', 'Unknown')}")
    print(f"Item:          {merged.get('item_summary', 'Unknown')}")
    print(f"Order #:       {merged.get('order_number') or 'N/A'}")
    print(f"Amount:        ${merged.get('amount') or 'N/A'}")
    print(f"Order Date:    {merged.get('order_date') or 'N/A'}")
    print(f"Delivery Date: {merged.get('delivery_date') or 'N/A'}")

    # Compute and show return-by date
    return_by, confidence = compute_return_by_date(merged, rules)
    if return_by:
        days_left = (return_by - datetime.now(UTC)).days
        status = "EXPIRED" if days_left < 0 else ("EXPIRING SOON" if days_left <= 7 else "ACTIVE")
        print(f"Return By:     {return_by.strftime('%Y-%m-%d')} ({confidence.value}, {days_left}d, {status})")
    else:
        print(f"Return By:     Unknown")

    if merged.get("return_portal_link"):
        print(f"Return Link:   {merged['return_portal_link'][:50]}...")

    print("-" * 70)


def edit_entity(merged: dict) -> dict:
    """Allow user to edit entity details."""
    print("\n--- Edit (Enter to keep current) ---")
    edited = merged.copy()

    for field, prompt in [
        ("merchant", "Merchant"),
        ("item_summary", "Item"),
        ("order_number", "Order #"),
        ("order_date", "Order date (YYYY-MM-DD)"),
        ("delivery_date", "Delivery date (YYYY-MM-DD)"),
        ("return_by_date", "Return-by date (YYYY-MM-DD)"),
    ]:
        current = merged.get(field, "")
        val = input(f"{prompt} [{current}]: ").strip()
        if val:
            edited[field] = val

    amount_str = input(f"Amount [{merged.get('amount', '')}]: ").strip()
    if amount_str:
        try:
            edited["amount"] = float(amount_str)
        except ValueError:
            pass

    return edited


def create_return_card(merged: dict, rules: dict, user_id: str) -> ReturnCard:
    """Create a ReturnCard from merged data."""
    return_by_date, confidence = compute_return_by_date(merged, rules)

    email_ids = merged.get("source_email_ids", [])
    if isinstance(email_ids, str):
        email_ids = [email_ids]
    elif not email_ids and merged.get("source_email_id"):
        email_ids = [merged["source_email_id"]]

    card = ReturnCard(
        id=str(uuid.uuid4()),
        user_id=user_id,
        merchant=merged.get("merchant", "Unknown"),
        merchant_domain=merged.get("merchant_domain", ""),
        item_summary=merged.get("item_summary", "Unknown item"),
        status=ReturnStatus.ACTIVE,
        confidence=confidence,
        source_email_ids=email_ids,
        order_number=merged.get("order_number"),
        amount=merged.get("amount"),
        order_date=parse_date(merged.get("order_date")),
        delivery_date=parse_date(merged.get("delivery_date")),
        return_by_date=return_by_date,
        return_portal_link=merged.get("return_portal_link"),
    )

    card.status = card.compute_status()
    return card


def export_cards(cards: list[ReturnCard], output_path: str):
    """Export ReturnCards to JSON."""
    output_data = {
        "metadata": {
            "exported_at": datetime.now(UTC).isoformat(),
            "total_cards": len(cards),
        },
        "return_cards": [card.to_db_dict() for card in cards],
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\nExported {len(cards)} ReturnCards to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Phase 2: Create entities from labeled purchases")
    parser.add_argument(
        "--input",
        type=str,
        default=str(project_root / "data" / "labeling" / "labeled_emails.json"),
        help="Input JSON from Phase 1",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(project_root / "data" / "labeling" / "return_cards.json"),
        help="Output JSON for ReturnCards",
    )
    parser.add_argument("--user-id", type=str, default="labeling_user")
    parser.add_argument("--auto", action="store_true", help="Skip interactive review")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found. Run Phase 1 first.")
        sys.exit(1)

    print("=" * 60)
    print("Phase 2: Entity Extraction & Consolidation")
    print("=" * 60)

    # Load Phase 1 results
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Get PURCHASE-labeled emails
    purchase_emails = [
        item for item in data.get("labeled_emails", [])
        if item.get("label") == "PURCHASE"
    ]

    # Also check purchases list
    purchases_list = data.get("purchases", [])
    for p in purchases_list:
        if not any(e.get("message_id") == p.get("message_id") for e in purchase_emails):
            purchase_emails.append(p)

    if not purchase_emails:
        print("\nNo PURCHASE-labeled emails found!")
        print("Run Phase 1 first: uv run python scripts/labeling/label_emails.py")
        sys.exit(1)

    print(f"\nFound {len(purchase_emails)} PURCHASE-labeled emails")

    # Load merchant rules
    rules = load_merchant_rules()
    print(f"Loaded rules for {len(rules)} merchants")

    # Initialize LLM extractor
    print("Initializing AI extractor...")
    try:
        extractor = ReturnFieldExtractor()
        print("AI extractor ready!")
    except Exception as e:
        print(f"Warning: Could not initialize AI extractor: {e}")
        extractor = None

    # Extract details from each email
    print(f"\nExtracting details from {len(purchase_emails)} emails...")
    extracted = []
    for i, email in enumerate(purchase_emails):
        print(f"  [{i+1}/{len(purchase_emails)}] {email.get('subject', 'No subject')[:50]}...")
        if extractor:
            details = extract_details_with_llm(email, extractor, rules)
        else:
            # Fallback without LLM
            domain = extract_domain(email.get("from_address", ""))
            details = {
                "source_email_id": email.get("message_id", ""),
                "email_subject": email.get("subject", ""),
                "merchant": domain.replace(".com", "").title(),
                "merchant_domain": domain,
                "item_summary": email.get("subject", "Unknown")[:100],
            }
        extracted.append(details)

    # Group by purchase
    print(f"\nGrouping related emails...")
    groups = group_by_purchase(extracted)
    print(f"Consolidated into {len(groups)} unique purchases")

    # Process groups
    cards: list[ReturnCard] = []

    if args.auto:
        for group in groups:
            merged = merge_group(group)
            card = create_return_card(merged, rules, args.user_id)
            cards.append(card)
            print(f"  Created: {card.merchant} - {card.item_summary}")
    else:
        print("\nReview each entity. Commands: [C]reate, [E]dit, [S]kip, [Q]uit\n")
        input("Press Enter to start...")

        for i, group in enumerate(groups):
            merged = merge_group(group)

            os.system("cls" if os.name == "nt" else "clear")
            display_entity(merged, i, len(groups), rules, len(group))

            while True:
                choice = input("\n[C]reate / [E]dit / [S]kip / [Q]uit: ").strip().upper()

                if choice == "Q":
                    break
                if choice == "S":
                    print("Skipped")
                    break
                if choice == "E":
                    merged = edit_entity(merged)
                    display_entity(merged, i, len(groups), rules, len(group))
                    continue
                if choice == "C":
                    card = create_return_card(merged, rules, args.user_id)
                    cards.append(card)
                    days = card.days_until_expiry()
                    print(f"\nCreated: {card.merchant} - {card.item_summary} ({card.status.value})")
                    input("Press Enter...")
                    break

            if choice == "Q":
                break

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Created {len(cards)} ReturnCards")

    if cards:
        print("\nReturnCards:")
        for card in cards:
            days = card.days_until_expiry()
            icon = {"active": "+", "expiring_soon": "!", "expired": "X"}.get(card.status.value, " ")
            days_str = f"{days}d" if days is not None else "?"
            print(f"  [{icon}] {card.merchant}: {card.item_summary} ({days_str})")

        export_cards(cards, args.output)


if __name__ == "__main__":
    main()
