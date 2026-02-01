#!/usr/bin/env python3
"""
Evaluate the extraction pipeline against the golden dataset CSV.

Feeds fetched emails through the 3-stage pipeline, then compares
the resulting ReturnCards against the manually labeled golden orders.

Evaluates: recall, precision, date accuracy, and item summary quality.
Writes structured JSON output for cross-run diffing.

Usage:
    uv run python scripts/eval_pipeline.py

Inputs:
    data/labeling/emails_full.json  - Fetched emails (151 emails, 60 days)
    data/labeling/60-days-gds-11-30-2025--1-31-2026 - Sheet1.csv  - Golden orders

Output:
    Prints comparison report to stdout.
    Writes data/eval/eval_YYYYMMDD_HHMMSS.json + symlink eval_latest.json
"""

from __future__ import annotations

import contextlib
import csv
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

import yaml

from shopq.returns.extractor import ReturnableReceiptExtractor

# ---------------------------------------------------------------------------
# Scoring thresholds (constants)
# ---------------------------------------------------------------------------
RECALL_TARGET = 0.80
PRECISION_TARGET = 0.80
DATE_ACCURACY_TARGET = 0.80  # orders with known delivery dates
DATE_PRODUCED_TARGET = 0.70  # TBD orders that still get a date
ITEM_QUALITY_TARGET = 0.75  # good + acceptable

# ---------------------------------------------------------------------------
# Vendor → merchant domain mapping (for expected date computation)
# ---------------------------------------------------------------------------
VENDOR_TO_DOMAIN: dict[str, str] = {
    "amazon": "amazon.com",
    "bestbuy": "bestbuy.com",
    "best buy": "bestbuy.com",
    "banana republic": "bananarepublic.com",
    "madewell": "madewell.com",
    "walmart": "walmart.com",
    "percival": "_default",
    "harry's": "_default",
    "ilia beauty": "_default",
    "calvin klein": "_default",
    "west elm": "_default",
    "bombas": "_default",
}

# ---------------------------------------------------------------------------
# Generic phrases (reused from extractor.py:399-433) for item quality check
# ---------------------------------------------------------------------------
_GENERIC_PHRASES = frozenset(
    {
        "thanks for your order",
        "thank you for your order",
        "your order has been placed",
        "order confirmation",
        "your order",
        "package has been delivered",
        "your package has been delivered",
        "your package was delivered",
        "your delivery is complete",
        "delivery notification",
        "delivered",
        "your order has shipped",
        "your order has been shipped",
        "your package is on the way",
        "out for delivery",
        "shipped",
        "in transit",
        "on the way",
        "order received",
        "has shipped",
        "has been shipped",
        "has been delivered",
        "was delivered",
        "has been placed",
        "is on the way",
        "confirmation",
    }
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
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
            with contextlib.suppress(ValueError, TypeError):
                received_at = datetime.fromisoformat(e["received_at"])

        body = e.get("body_text", "")
        body_html = e.get("body_html", "")

        if not body:
            empty_body_count += 1

        emails.append(
            {
                "id": e["message_id"],
                "from": e.get("from_address", ""),
                "subject": e.get("subject", ""),
                "body": body,
                "body_html": body_html,
                "received_at": received_at,
            }
        )

    print(f"  Emails with empty body_text: {empty_body_count}/{len(emails)}")
    if html_fallback_count:
        print(f"  HTML fallback applied: {html_fallback_count}")
    return emails


def _parse_golden_date(date_str: str) -> tuple[datetime | None, bool]:
    """Parse golden dataset date column.

    Returns (parsed_date, is_tbd).
    Handles MM-DD-YYYY format and TBD variants.
    """
    s = date_str.strip()
    if not s:
        return None, False
    if s.upper().startswith("TBD"):
        return None, True
    # Try MM-DD-YYYY
    for fmt in ["%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt), False
        except ValueError:
            continue
    return None, False


def load_golden_csv(path: Path) -> list[dict]:
    """Load the golden dataset CSV with parsed dates and deduplication.

    Deduplicates split shipments: orders that appear twice with different
    delivery dates are grouped by order number, keeping the latest delivery date.
    """
    raw_orders: list[dict] = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            delivery_str = row.get(
                "Date delivered (relevant for computing return window)", ""
            ).strip()
            delivery_date, is_tbd = _parse_golden_date(delivery_str)

            raw_orders.append(
                {
                    "vendor": row.get("Vendor", "").strip(),
                    "order_name": row.get("Order Name", "").strip(),
                    "order_number": row.get("Order Number", "").strip(),
                    "delivery_date_str": delivery_str,
                    "delivery_date": delivery_date,
                    "is_tbd": is_tbd,
                    "has_delivery_date": delivery_date is not None,
                    "return_window": row.get("Return Window", "").strip(),
                    "notes": row.get("Notes", "").strip(),
                }
            )

    # Deduplicate split shipments: group by order number, keep latest delivery date
    groups: dict[str, list[dict]] = {}
    for order in raw_orders:
        key = order["order_number"]
        if not key or key == "Unknown":
            # No order number — keep as-is (no grouping possible)
            groups.setdefault(f"_nonum_{id(order)}", []).append(order)
        else:
            groups.setdefault(key, []).append(order)

    deduped: list[dict] = []
    for _key, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            # Pick the entry with the latest delivery date
            with_dates = [o for o in group if o["delivery_date"] is not None]
            if with_dates:
                best = max(with_dates, key=lambda o: o["delivery_date"])
                # Merge order names for context
                all_names = [o["order_name"] for o in group if o["order_name"]]
                best["order_name"] = " | ".join(all_names)
                deduped.append(best)
            else:
                # No dates at all — just take first
                deduped.append(group[0])

    return deduped


# ---------------------------------------------------------------------------
# Merchant rules for expected date computation
# ---------------------------------------------------------------------------
def load_merchant_rules(path: Path) -> dict:
    """Load merchant_rules.yaml."""
    with open(path) as f:
        return yaml.safe_load(f)


def compute_expected_return_by(order: dict, merchant_rules: dict) -> datetime | None:
    """Compute expected return-by date from golden delivery date + merchant rule."""
    if not order["has_delivery_date"]:
        return None

    vendor_lower = order["vendor"].lower()
    domain = VENDOR_TO_DOMAIN.get(vendor_lower, "_default")
    merchants = merchant_rules.get("merchants", {})
    rule = merchants.get(domain) or merchants.get("_default", {})
    days = rule.get("days", 30)

    return order["delivery_date"] + timedelta(days=days)


# ---------------------------------------------------------------------------
# Matching helpers (unchanged logic)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Item quality evaluation
# ---------------------------------------------------------------------------
def _assess_item_quality(
    item_summary: str | None, golden_order_name: str, email_subject: str = ""
) -> tuple[str, list[str]]:
    """Assess quality of a pipeline item summary.

    Returns (quality, flags) where quality is "good", "acceptable", or "poor"
    and flags explain issues.
    """
    flags: list[str] = []

    if not item_summary or not item_summary.strip():
        return "poor", ["empty_summary"]

    text = item_summary.strip().rstrip(".!").lower()

    # Check for generic phrases
    if text in _GENERIC_PHRASES:
        flags.append("generic_phrase")

    # Check if it looks like an email subject echo (starts with same words)
    if email_subject:
        subj_lower = email_subject.lower().strip()
        # If the summary is very similar to the subject, flag it
        if text == subj_lower or text.startswith(subj_lower[:30]):
            flags.append("subject_echo")

    # Check for product overlap with golden order name
    if golden_order_name and golden_order_name.strip():
        golden_words = {
            w.lower()
            for w in re.split(r"[\s,;/|&()\-]+", golden_order_name)
            if len(w) >= 3
            and w.lower()
            not in {"the", "and", "for", "with", "your", "order", "from", "that", "this"}
        }
        summary_words = {
            w.lower() for w in re.split(r"[\s,;/|&()\-]+", item_summary) if len(w) >= 3
        }
        if golden_words and summary_words and not (golden_words & summary_words):
            flags.append("no_product_overlap")

    # Score
    if not flags:
        return "good", flags
    if "generic_phrase" in flags or ("no_product_overlap" in flags and "subject_echo" in flags):
        return "poor", flags
    return "acceptable", flags


# ---------------------------------------------------------------------------
# Structured JSON output
# ---------------------------------------------------------------------------
def write_eval_json(
    eval_dir: Path,
    golden_orders: list[dict],
    recall_matches: dict,
    precision_matches: dict,
    card_list: list,
    date_results: list[dict],
    item_results: list[dict],
    scores: dict,
    email_count: int,
) -> Path:
    """Write structured eval JSON and symlink eval_latest.json."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = eval_dir / f"eval_{timestamp}.json"

    # Build per-order details
    order_details = []
    for gi, order in enumerate(golden_orders):
        matched_card = recall_matches.get(gi)
        detail: dict = {
            "vendor": order["vendor"],
            "order_number": order["order_number"],
            "golden_order_name": order["order_name"],
            "delivery_date": (
                order["delivery_date"].strftime("%Y-%m-%d") if order["delivery_date"] else None
            ),
            "is_tbd": order["is_tbd"],
            "matched": matched_card is not None,
        }

        if matched_card:
            detail["pipeline_merchant"] = matched_card.merchant
            detail["pipeline_order_number"] = matched_card.order_number
            detail["pipeline_return_by"] = (
                str(matched_card.return_by_date)[:10] if matched_card.return_by_date else None
            )
            detail["pipeline_item_summary"] = matched_card.item_summary
            conf = matched_card.confidence
            detail["pipeline_confidence"] = conf.value if hasattr(conf, "value") else str(conf)

        # Merge date evaluation results
        date_entry = next(
            (d for d in date_results if d["order_number"] == order["order_number"]),
            None,
        )
        if date_entry:
            detail["expected_return_by"] = date_entry.get("expected_return_by")
            detail["date_delta_days"] = date_entry.get("date_delta_days")
            detail["date_pass"] = date_entry.get("date_pass")

        # Merge item quality results
        item_entry = next(
            (q for q in item_results if q["order_number"] == order["order_number"]),
            None,
        )
        if item_entry:
            detail["item_quality"] = item_entry.get("item_quality")
            detail["item_flags"] = item_entry.get("item_flags", [])

        order_details.append(detail)

    # Unmatched pipeline cards (false positives)
    fp_details = []
    for ci, c in enumerate(card_list):
        if ci not in precision_matches:
            fp_details.append(
                {
                    "pipeline_merchant": c.merchant,
                    "pipeline_order_number": c.order_number,
                    "pipeline_return_by": (
                        str(c.return_by_date)[:10] if c.return_by_date else None
                    ),
                    "pipeline_item_summary": c.item_summary,
                }
            )

    output = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "email_count": email_count,
            "golden_order_count": len(golden_orders),
            "pipeline_card_count": len(card_list),
        },
        "scores": scores,
        "orders": order_details,
        "false_positives": fp_details,
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    # Create/update symlink (copy fallback for Windows)
    latest_link = eval_dir / "eval_latest.json"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    try:
        latest_link.symlink_to(out_path.name)
    except OSError:
        import shutil

        shutil.copy2(out_path, latest_link)

    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    emails_path = project_root / "data" / "labeling" / "emails_full.json"
    golden_path = (
        project_root / "data" / "labeling" / "60-days-gds-11-30-2025--1-31-2026 - Sheet1.csv"
    )
    merchant_rules_path = project_root / "config" / "merchant_rules.yaml"
    eval_dir = project_root / "data" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("PIPELINE EVALUATION")
    print("=" * 80)

    # Load data
    emails = load_emails(emails_path)
    golden_orders = load_golden_csv(golden_path)
    merchant_rules = load_merchant_rules(merchant_rules_path)
    print(f"Loaded {len(emails)} emails, {len(golden_orders)} golden orders (after dedup)")
    print()

    # Warn about unmapped vendors
    unmapped = {o["vendor"] for o in golden_orders if o["vendor"].lower() not in VENDOR_TO_DOMAIN}
    if unmapped:
        print(f"Warning: {len(unmapped)} vendors not in VENDOR_TO_DOMAIN (using _default):")
        for v in sorted(unmapped):
            print(f"  - {v}")
        print()

    # Compute expected return-by dates for golden orders
    for order in golden_orders:
        order["expected_return_by"] = compute_expected_return_by(order, merchant_rules)

    # Disable budget limits for eval runs by patching check_budget everywhere
    import shopq.infrastructure.llm_budget as budget_mod
    import shopq.returns.extractor as extractor_mod

    _orig_check = budget_mod.check_budget

    def _unlocked(user_id, **_kw):
        return _orig_check(user_id, user_limit=100000, global_limit=100000)

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
    errors = [
        r for r in results if not r.success and r.stage_reached not in ("filter", "classifier")
    ]

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
        conf = c.confidence.value if hasattr(c.confidence, "value") else str(c.confidence)
        print(
            f"  {c.merchant:<25} | order#: {(c.order_number or 'none'):<25} | "
            f"return_by: {str(c.return_by_date)[:10] if c.return_by_date else 'none':<12} | "
            f"conf: {conf}"
        )
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

    # ======================================================================
    # RECALL
    # ======================================================================
    print("RECALL: Did the pipeline find each golden order?")
    print("-" * 80)
    recall_matches = match_golden_to_cards(golden_orders, card_list)
    found = 0
    for gi, order in enumerate(golden_orders):
        matched_card = recall_matches.get(gi)
        if matched_card:
            found += 1
            marker = "HIT"
            match_type = (
                "order#"
                if _order_num_matches(order["order_number"], matched_card.order_number or "")
                else "vendor"
            )
            rbd = str(matched_card.return_by_date)[:10] if matched_card.return_by_date else "none"
            detail = f"-> {matched_card.merchant} [{match_type}], return_by: {rbd}"
        else:
            marker = "MISS"
            detail = ""

        print(f"  [{marker:4}] {order['vendor']:<18} {order['order_number']:<25} {detail}")

    print()
    recall_pct = found / len(golden_orders) if golden_orders else 0
    print(f"Recall: {found}/{len(golden_orders)} golden orders found ({recall_pct:.0%})")
    print()

    # ======================================================================
    # PRECISION
    # ======================================================================
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
            match_type = (
                "order#"
                if _order_num_matches(matched_order["order_number"], card_order_num)
                else "vendor"
            )
            marker = f"TP:{match_type}"
        else:
            false_pos += 1
            marker = "FP"

        items = (c.item_summary or "")[:40]
        print(f"  [{marker:<10}] {(c.merchant or '?'):<25} order#: {card_order_num:<25} {items}")

    print()
    total_cards = true_pos + false_pos
    precision_pct = true_pos / total_cards if total_cards > 0 else 0
    if total_cards > 0:
        print(
            f"Precision: {true_pos}/{total_cards} cards are real golden orders "
            f"({precision_pct:.0%})"
        )
    print()

    # ======================================================================
    # DATE ACCURACY
    # ======================================================================
    print("=" * 80)
    print("DATE ACCURACY (orders with known delivery dates)")
    print("-" * 80)

    date_results: list[dict] = []
    known_date_pass = 0
    known_date_total = 0
    tbd_produced = 0
    tbd_total = 0

    for gi, order in enumerate(golden_orders):
        matched_card = recall_matches.get(gi)
        if not matched_card:
            # Not matched — skip date evaluation
            date_results.append(
                {
                    "order_number": order["order_number"],
                    "vendor": order["vendor"],
                    "category": "unmatched",
                }
            )
            continue

        if order["has_delivery_date"]:
            # Known delivery date — compare pipeline return_by vs expected
            known_date_total += 1
            expected = order["expected_return_by"]
            pipeline_rbd = matched_card.return_by_date

            entry: dict = {
                "order_number": order["order_number"],
                "vendor": order["vendor"],
                "category": "known_date",
                "expected_return_by": (expected.strftime("%Y-%m-%d") if expected else None),
                "pipeline_return_by": (str(pipeline_rbd)[:10] if pipeline_rbd else None),
            }

            if expected and pipeline_rbd:
                # Normalize both to naive for comparison
                exp_naive = expected.replace(tzinfo=None) if expected.tzinfo else expected
                pipe_naive = (
                    pipeline_rbd.replace(tzinfo=None) if pipeline_rbd.tzinfo else pipeline_rbd
                )
                delta = (pipe_naive - exp_naive).days
                passed = abs(delta) <= 2
                if passed:
                    known_date_pass += 1
                entry["date_delta_days"] = delta
                entry["date_pass"] = passed
                sign = "+" if delta >= 0 else ""
                status = "PASS" if passed else "FAIL"
                print(
                    f"  [{status}]  {order['vendor']:<18} {order['order_number']:<25} "
                    f"expected: {expected.strftime('%Y-%m-%d')}  "
                    f"pipeline: {str(pipeline_rbd)[:10]}  "
                    f"delta: {sign}{delta}d"
                )
            elif expected and not pipeline_rbd:
                entry["date_delta_days"] = None
                entry["date_pass"] = False
                print(
                    f"  [FAIL]  {order['vendor']:<18} {order['order_number']:<25} "
                    f"expected: {expected.strftime('%Y-%m-%d')}  "
                    f"pipeline: none"
                )
            else:
                entry["date_delta_days"] = None
                entry["date_pass"] = None
                print(
                    f"  [????]  {order['vendor']:<18} {order['order_number']:<25} "
                    f"no expected date to compare"
                )

            date_results.append(entry)

        elif order["is_tbd"]:
            # TBD delivery — check pipeline produced *any* return_by_date
            tbd_total += 1
            pipeline_rbd = matched_card.return_by_date
            produced = pipeline_rbd is not None

            conf = matched_card.confidence
            conf_str = conf.value if hasattr(conf, "value") else str(conf)

            entry = {
                "order_number": order["order_number"],
                "vendor": order["vendor"],
                "category": "tbd",
                "pipeline_return_by": (str(pipeline_rbd)[:10] if pipeline_rbd else None),
                "date_pass": produced,
                "confidence": conf_str,
            }

            if produced:
                tbd_produced += 1
                conf_note = "" if conf_str == "estimated" else f"  [conf: {conf_str}]"
                print(
                    f"  [PASS]  {order['vendor']:<18} {order['order_number']:<25} "
                    f"TBD -> pipeline: {str(pipeline_rbd)[:10]}{conf_note}"
                )
            else:
                print(
                    f"  [FAIL]  {order['vendor']:<18} {order['order_number']:<25} "
                    f"TBD -> pipeline: none"
                )

            date_results.append(entry)
        else:
            # No delivery info at all
            date_results.append(
                {
                    "order_number": order["order_number"],
                    "vendor": order["vendor"],
                    "category": "no_date_info",
                }
            )

    print()
    if known_date_total > 0:
        kd_pct = known_date_pass / known_date_total
        print(
            f"Date accuracy: {known_date_pass}/{known_date_total} within +/-2 days ({kd_pct:.0%})"
        )
    if tbd_total > 0:
        tbd_pct = tbd_produced / tbd_total
        print(f"Date produced (TBD): {tbd_produced}/{tbd_total} ({tbd_pct:.0%})")
    print()

    # ======================================================================
    # ITEM SUMMARY QUALITY
    # ======================================================================
    print("=" * 80)
    print("ITEM SUMMARY QUALITY")
    print("-" * 80)

    item_results: list[dict] = []
    quality_counts = {"good": 0, "acceptable": 0, "poor": 0}

    for gi, order in enumerate(golden_orders):
        matched_card = recall_matches.get(gi)
        if not matched_card:
            continue

        quality, flags = _assess_item_quality(
            matched_card.item_summary,
            order["order_name"],
        )
        quality_counts[quality] += 1

        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        summary_preview = (matched_card.item_summary or "")[:60]
        label = quality.upper()
        print(
            f"  [{label:4}] {order['vendor']:<18} {order['order_number']:<25} "
            f'"{summary_preview}"{flag_str}'
        )

        item_results.append(
            {
                "order_number": order["order_number"],
                "vendor": order["vendor"],
                "item_quality": quality,
                "item_flags": flags,
                "pipeline_item_summary": matched_card.item_summary,
            }
        )

    print()
    total_assessed = sum(quality_counts.values())
    good_ok = quality_counts["good"] + quality_counts["acceptable"]
    print(
        f"Quality: {quality_counts['good']} good, "
        f"{quality_counts['acceptable']} acceptable, "
        f"{quality_counts['poor']} poor"
    )
    print()

    # ======================================================================
    # SCORECARD
    # ======================================================================
    print("=" * 80)
    print("SCORECARD")
    print("=" * 80)

    scores: dict = {}

    def _score_line(label: str, num: int, denom: int, target: float) -> None:
        pct = num / denom if denom > 0 else 0
        passed = pct >= target
        result = "PASS" if passed else "FAIL"
        scores[label] = {
            "numerator": num,
            "denominator": denom,
            "percentage": round(pct * 100, 1),
            "target_percentage": round(target * 100, 1),
            "passed": passed,
        }
        print(f"  {label:<25} {num:>3}/{denom:<3}  >= {target:.0%}     {result}")

    print(f"  {'':25} {'SCORE':>7}  {'TARGET':>10}  RESULT")
    _score_line("Recall", found, len(golden_orders), RECALL_TARGET)
    _score_line("Precision", true_pos, total_cards, PRECISION_TARGET)
    _score_line("Date accuracy (known)", known_date_pass, known_date_total, DATE_ACCURACY_TARGET)
    _score_line("Date produced (TBD)", tbd_produced, tbd_total, DATE_PRODUCED_TARGET)
    _score_line("Item quality (good+ok)", good_ok, total_assessed, ITEM_QUALITY_TARGET)
    print()

    all_passed = all(s["passed"] for s in scores.values())
    print(f"Overall: {'ALL PASS' if all_passed else 'SOME FAILURES'}")
    print()

    # ======================================================================
    # FILTER/CLASSIFIER REJECTIONS (sample)
    # ======================================================================
    print("=" * 80)
    print("FILTER/CLASSIFIER REJECTIONS (sample)")
    print("=" * 80)
    for r in rejected_filter[:10]:
        email_id = r.card.source_email_ids[0] if r.card else "?"
        orig = next((e for e in emails if e["id"] == email_id), None)
        if not orig:
            print(f"  [FILTER] {r.rejection_reason}")
        else:
            print(f"  [FILTER] {orig['from'][:40]:<40} | {orig['subject'][:40]}")

    print("  ...")
    print(f"  ({len(rejected_filter)} total filter rejections)")
    print()
    for r in rejected_classifier[:10]:
        print(f"  [CLASSF] {r.rejection_reason}")
    print(f"  ({len(rejected_classifier)} total classifier rejections)")
    print()

    # ======================================================================
    # Write structured JSON output
    # ======================================================================
    out_path = write_eval_json(
        eval_dir=eval_dir,
        golden_orders=golden_orders,
        recall_matches=recall_matches,
        precision_matches=precision_matches,
        card_list=card_list,
        date_results=date_results,
        item_results=item_results,
        scores=scores,
        email_count=len(emails),
    )
    print(f"Eval JSON written to: {out_path}")
    print(f"Symlink: {eval_dir / 'eval_latest.json'}")


if __name__ == "__main__":
    main()
