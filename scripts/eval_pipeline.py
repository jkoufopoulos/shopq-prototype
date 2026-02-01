#!/usr/bin/env python3
"""
Evaluate the extraction pipeline against the golden dataset CSV.

Feeds fetched emails through the 3-stage pipeline, then compares
the resulting ReturnCards against the manually labeled golden orders.

Usage:
    uv run python scripts/eval_pipeline.py

Inputs:
    data/labeling/emails_full.json                              - Fetched emails (151 emails, 60 days)
    data/labeling/60-days-gds-11-30-2025--1-31-2026 - Sheet1.csv - Golden dataset orders

Output:
    Prints comparison report to stdout.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from shopq.returns.extractor import ReturnableReceiptExtractor
from shopq.utils.html import html_to_text


def load_emails(path: Path) -> list[dict]:
    """Load fetched emails and convert to pipeline input format."""
    with open(path) as f:
        data = json.load(f)

    emails = []
    empty_body_count = 0
    html_fallback_count = 0
    for e in data["emails"]:
        received_at = None
        if e.get("received_at"):
            try:
                received_at = datetime.fromisoformat(e["received_at"])
            except (ValueError, TypeError):
                pass

        body = e.get("body_text", "")
        body_html = e.get("body_html", "")

        if not body:
            empty_body_count += 1

        emails.append({
            "id": e["message_id"],
            "from": e.get("from_address", ""),
            "subject": e.get("subject", ""),
            "body": body,
            "body_html": body_html,
            "received_at": received_at,
        })

    print(f"  Emails with empty body_text: {empty_body_count}/{len(emails)}")
    if html_fallback_count:
        print(f"  HTML fallback applied: {html_fallback_count}")
    return emails


def load_golden_csv(path: Path) -> list[dict]:
    """Load the golden dataset CSV."""
    orders = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            orders.append({
                "vendor": row.get("Vendor", "").strip(),
                "order_name": row.get("Order Name", "").strip(),
                "order_number": row.get("Order Number", "").strip(),
                "delivery_date": row.get("Date delivered (relevant for computing return window)", "").strip(),
            })
    return orders


def _vendor_matches(golden_vendor: str, card_merchant: str, card_domain: str) -> bool:
    """Check if golden vendor name matches card merchant or domain."""
    gv = golden_vendor.lower().strip()
    cm = card_merchant.lower().strip()
    cd = card_domain.lower().strip()
    if not gv:
        return False
    return gv in cm or gv in cd or cm.startswith(gv)


def _order_num_matches(golden_num: str, card_num: str) -> bool:
    """Check if order numbers match (non-empty substring match)."""
    if not golden_num or golden_num == "Unknown" or not card_num:
        return False
    return golden_num in card_num or card_num in golden_num


def match_golden_to_cards(golden_orders: list[dict], cards: list) -> dict:
    """Two-pass matching: order number first, then vendor-name fallback.

    Returns dict mapping golden order index -> matched card (or None).
    Each card is matched at most once.
    """
    matches: dict[int, object] = {}
    used_card_ids: set[int] = set()

    # Pass 1: Match by order number
    for gi, order in enumerate(golden_orders):
        for ci, c in enumerate(cards):
            if ci in used_card_ids:
                continue
            if _order_num_matches(order["order_number"], c.order_number or ""):
                matches[gi] = c
                used_card_ids.add(ci)
                break

    # Pass 2: Match remaining by vendor name
    for gi, order in enumerate(golden_orders):
        if gi in matches:
            continue
        for ci, c in enumerate(cards):
            if ci in used_card_ids:
                continue
            if _vendor_matches(order["vendor"], c.merchant or "", c.merchant_domain or ""):
                matches[gi] = c
                used_card_ids.add(ci)
                break

    return matches


def match_cards_to_golden(cards: list, golden_orders: list[dict]) -> dict:
    """Two-pass matching from card perspective for precision.

    Returns dict mapping card index -> matched golden order (or None).
    Each golden order is matched at most once.
    """
    matches: dict[int, dict] = {}
    used_golden_ids: set[int] = set()

    # Pass 1: Match by order number
    for ci, c in enumerate(cards):
        for gi, order in enumerate(golden_orders):
            if gi in used_golden_ids:
                continue
            if _order_num_matches(order["order_number"], c.order_number or ""):
                matches[ci] = order
                used_golden_ids.add(gi)
                break

    # Pass 2: Match remaining by vendor name
    for ci, c in enumerate(cards):
        if ci in matches:
            continue
        for gi, order in enumerate(golden_orders):
            if gi in used_golden_ids:
                continue
            if _vendor_matches(order["vendor"], c.merchant or "", c.merchant_domain or ""):
                matches[ci] = order
                used_golden_ids.add(gi)
                break

    return matches


def main():
    emails_path = project_root / "data" / "labeling" / "emails_full.json"
    golden_path = project_root / "data" / "labeling" / "60-days-gds-11-30-2025--1-31-2026 - Sheet1.csv"

    print("=" * 80)
    print("PIPELINE EVALUATION")
    print("=" * 80)

    # Load data
    emails = load_emails(emails_path)
    golden_orders = load_golden_csv(golden_path)
    print(f"Loaded {len(emails)} emails, {len(golden_orders)} golden orders")
    print()

    # Disable budget limits for eval runs by patching check_budget everywhere
    import shopq.infrastructure.llm_budget as budget_mod
    import shopq.returns.extractor as extractor_mod
    _orig_check = budget_mod.check_budget
    _unlocked = lambda user_id, **kw: _orig_check(user_id, user_limit=100000, global_limit=100000)
    budget_mod.check_budget = _unlocked
    extractor_mod.check_budget = _unlocked

    # Run pipeline
    print("Running extraction pipeline...")
    print("-" * 80)
    extractor = ReturnableReceiptExtractor()
    results = extractor.process_email_batch("eval_batch_run", emails)

    # Categorize results
    completed = [r for r in results if r.success and r.card]
    rejected_filter = [r for r in results if r.stage_reached == "filter"]
    rejected_classifier = [r for r in results if r.stage_reached == "classifier"]
    errors = [r for r in results if not r.success and r.stage_reached not in ("filter", "classifier")]

    print()
    print("=" * 80)
    print("PIPELINE RESULTS SUMMARY")
    print("=" * 80)
    print(f"Total emails processed:     {len(results)}")
    print(f"Rejected at filter (S1):    {len(rejected_filter)}")
    print(f"Rejected at classifier (S2):{len(rejected_classifier)}")
    print(f"ReturnCards created (S3):   {len(completed)}")
    print(f"Errors/other:               {len(errors)}")
    print()

    # Show all created ReturnCards
    print("=" * 80)
    print("RETURN CARDS CREATED BY PIPELINE")
    print("=" * 80)
    for r in completed:
        c = r.card
        conf = c.confidence.value if hasattr(c.confidence, 'value') else str(c.confidence)
        print(f"  {c.merchant:<25} | order#: {(c.order_number or 'none'):<25} | "
              f"return_by: {str(c.return_by_date)[:10] if c.return_by_date else 'none':<12} | "
              f"conf: {conf}")
        print(f"    items: {(c.item_summary or '')[:70]}")
        print(f"    emails: {c.source_email_ids}")
        print()

    # Match against golden dataset
    print("=" * 80)
    print("COMPARISON: Pipeline Output vs Golden Dataset")
    print("=" * 80)
    print()

    # Deduplicate cards by merchant + order/item (pipeline may create one per email)
    unique_cards = {}
    for r in completed:
        c = r.card
        key = (c.merchant_domain or "", c.order_number or c.item_summary or "")
        if key not in unique_cards:
            unique_cards[key] = c

    card_list = list(unique_cards.values())

    # RECALL: For each golden order, check if pipeline found it
    print("RECALL: Did the pipeline find each golden order?")
    print("-" * 80)
    recall_matches = match_golden_to_cards(golden_orders, card_list)
    found = 0
    for gi, order in enumerate(golden_orders):
        matched_card = recall_matches.get(gi)
        if matched_card:
            found += 1
            marker = "HIT"
            match_type = "order#" if _order_num_matches(order["order_number"], matched_card.order_number or "") else "vendor"
            detail = f"-> {matched_card.merchant} [{match_type}], return_by: {str(matched_card.return_by_date)[:10] if matched_card.return_by_date else 'none'}"
        else:
            marker = "MISS"
            detail = ""

        print(f"  [{marker:4}] {order['vendor']:<18} {order['order_number']:<25} {detail}")

    print()
    print(f"Recall: {found}/{len(golden_orders)} golden orders found ({100*found//len(golden_orders)}%)")
    print()

    # PRECISION: For each pipeline card, check if it matches a golden order
    print("PRECISION: Are pipeline cards real orders?")
    print("-" * 80)
    precision_matches = match_cards_to_golden(card_list, golden_orders)
    true_pos = 0
    false_pos = 0
    for ci, c in enumerate(card_list):
        card_order_num = c.order_number or ""
        matched_order = precision_matches.get(ci)
        if matched_order:
            true_pos += 1
            match_type = "order#" if _order_num_matches(matched_order["order_number"], card_order_num) else "vendor"
            marker = f"TP:{match_type}"
        else:
            false_pos += 1
            marker = "FP"

        print(f"  [{marker:<10}] {(c.merchant or '?'):<25} order#: {card_order_num:<25} {(c.item_summary or '')[:40]}")

    print()
    total_cards = true_pos + false_pos
    if total_cards > 0:
        print(f"Precision: {true_pos}/{total_cards} cards are real golden orders ({100*true_pos//total_cards}%)")
    print()

    # Summary
    print("=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    print(f"Golden orders:    {len(golden_orders)}")
    print(f"Pipeline cards:   {len(unique_cards)} (deduplicated)")
    print(f"Recall:           {found}/{len(golden_orders)} ({100*found//len(golden_orders)}%)")
    if total_cards > 0:
        print(f"Precision:        {true_pos}/{total_cards} ({100*true_pos//total_cards}%)")
    print()

    # Show what got filtered/rejected
    print("=" * 80)
    print("FILTER/CLASSIFIER REJECTIONS (sample)")
    print("=" * 80)
    for r in rejected_filter[:10]:
        fr = r.filter_result
        email_id = r.card.source_email_ids[0] if r.card else "?"
        # Find original email
        orig = next((e for e in emails if e["id"] == email_id), None)
        if not orig:
            # Try to get from rejection info
            print(f"  [FILTER] {r.rejection_reason}")
        else:
            print(f"  [FILTER] {orig['from'][:40]:<40} | {orig['subject'][:40]}")

    print("  ...")
    print(f"  ({len(rejected_filter)} total filter rejections)")
    print()
    for r in rejected_classifier[:10]:
        print(f"  [CLASSF] {r.rejection_reason}")
    print(f"  ({len(rejected_classifier)} total classifier rejections)")


if __name__ == "__main__":
    main()
