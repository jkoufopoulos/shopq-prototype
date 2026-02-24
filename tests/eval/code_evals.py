"""
Code evals — deterministic checks on extraction results.

Pure checks on the API response, no LLM calls needed. Each eval returns
a dict with {"name": str, "pass": bool, "detail": str}.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# PII patterns to detect in item summaries
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+\w+\s+(Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Blvd|Boulevard|Way|Court|Ct)\b",
    re.IGNORECASE,
)
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$")

# Valid confidence values from the API
_VALID_CONFIDENCES = {"exact", "estimated", "unknown"}

# Valid stage_reached values
_VALID_STAGES = {"none", "filter", "classifier", "extractor", "cancellation_check", "complete", "error"}


def _result(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "pass": passed, "detail": detail}


def valid_merchant(result: dict) -> dict:
    """Check that merchant_domain is non-empty and looks like a domain."""
    if not result.get("success"):
        return _result("valid_merchant", True, "skipped — not a successful extraction")

    card = result.get("card") or {}
    domain = card.get("merchant_domain", "")
    merchant = card.get("merchant", "")

    if not merchant:
        return _result("valid_merchant", False, "merchant name is empty")
    if not domain:
        return _result("valid_merchant", False, "merchant_domain is empty")
    if not _DOMAIN_RE.match(domain):
        return _result("valid_merchant", False, f"merchant_domain '{domain}' doesn't look like a domain")

    return _result("valid_merchant", True, f"merchant='{merchant}' domain='{domain}'")


def valid_return_date(result: dict) -> dict:
    """Check return_by_date is reasonable: after order_date, within a plausible range."""
    if not result.get("success"):
        return _result("valid_return_date", True, "skipped — not a successful extraction")

    card = result.get("card") or {}
    return_by = card.get("return_by_date")

    if not return_by:
        return _result("valid_return_date", True, "no return_by_date set — acceptable")

    try:
        rbd = datetime.fromisoformat(return_by) if isinstance(return_by, str) else return_by
    except (ValueError, TypeError):
        return _result("valid_return_date", False, f"cannot parse return_by_date: {return_by}")

    order_date_str = card.get("order_date")
    if order_date_str:
        try:
            od = datetime.fromisoformat(order_date_str) if isinstance(order_date_str, str) else order_date_str
            if rbd < od:
                return _result("valid_return_date", False,
                               f"return_by_date {rbd} is before order_date {od}")
        except (ValueError, TypeError):
            pass  # order_date unparseable, skip this check

    return _result("valid_return_date", True, f"return_by_date={return_by}")


def valid_confidence(result: dict) -> dict:
    """Check confidence is one of the valid enum values."""
    if not result.get("success"):
        return _result("valid_confidence", True, "skipped — not a successful extraction")

    card = result.get("card") or {}
    conf = card.get("confidence", "")

    if conf.lower() not in _VALID_CONFIDENCES:
        return _result("valid_confidence", False, f"unexpected confidence: '{conf}'")

    return _result("valid_confidence", True, f"confidence='{conf}'")


def order_number_format(result: dict) -> dict:
    """If order_number is present, check it's not garbage."""
    if not result.get("success"):
        return _result("order_number_format", True, "skipped — not a successful extraction")

    card = result.get("card") or {}
    order_num = card.get("order_number")

    if not order_num:
        return _result("order_number_format", True, "no order_number present")

    # Should be at least 3 chars
    if len(order_num.strip()) < 3:
        return _result("order_number_format", False, f"order_number too short: '{order_num}'")

    # Should not be a full sentence
    if len(order_num) > 50:
        return _result("order_number_format", False, f"order_number too long ({len(order_num)} chars)")

    # Should not contain newlines
    if "\n" in order_num:
        return _result("order_number_format", False, "order_number contains newlines")

    return _result("order_number_format", True, f"order_number='{order_num}'")


def no_empty_card(result: dict) -> dict:
    """If success=True, card should have merchant + item_summary at minimum."""
    if not result.get("success"):
        return _result("no_empty_card", True, "skipped — not a successful extraction")

    card = result.get("card") or {}
    merchant = card.get("merchant", "")
    item = card.get("item_summary", "")

    if not merchant:
        return _result("no_empty_card", False, "card missing merchant")
    if not item:
        return _result("no_empty_card", False, "card missing item_summary")

    return _result("no_empty_card", True, f"merchant='{merchant}' item='{item[:40]}'")


def return_window_reasonable(result: dict) -> dict:
    """Check return window is 7-365 days (no nonsense values)."""
    if not result.get("success"):
        return _result("return_window_reasonable", True, "skipped — not a successful extraction")

    card = result.get("card") or {}
    return_by = card.get("return_by_date")
    order_date = card.get("order_date")
    delivery_date = card.get("delivery_date")

    if not return_by:
        return _result("return_window_reasonable", True, "no return_by_date — skipped")

    anchor = delivery_date or order_date
    if not anchor:
        return _result("return_window_reasonable", True, "no anchor date for window calculation — skipped")

    try:
        rbd = datetime.fromisoformat(return_by) if isinstance(return_by, str) else return_by
        anc = datetime.fromisoformat(anchor) if isinstance(anchor, str) else anchor
        window_days = (rbd - anc).days
    except (ValueError, TypeError):
        return _result("return_window_reasonable", True, "date parse error — skipped")

    if window_days < 7:
        return _result("return_window_reasonable", False,
                        f"return window too short: {window_days} days")
    if window_days > 365:
        return _result("return_window_reasonable", False,
                        f"return window too long: {window_days} days")

    return _result("return_window_reasonable", True, f"window={window_days} days")


def stage_consistency(result: dict) -> dict:
    """Check stage_reached matches success/failure status."""
    success = result.get("success", False)
    stage = result.get("stage_reached")

    if not stage:
        return _result("stage_consistency", True, "no stage_reached in response — skipped")

    # The API returns "extractor" for successful extractions (route-level convention)
    # and "complete" from the internal pipeline. Both are valid for success=True.
    if success and stage not in ("complete", "extractor"):
        return _result("stage_consistency", False,
                        f"success=True but stage_reached='{stage}' (expected 'complete' or 'extractor')")

    if not success and stage in ("complete", "extractor"):
        return _result("stage_consistency", False,
                        f"success=False but stage_reached='{stage}'")

    if stage not in _VALID_STAGES:
        return _result("stage_consistency", False, f"unknown stage: '{stage}'")

    return _result("stage_consistency", True, f"stage='{stage}' success={success}")


def no_pii_in_item(result: dict) -> dict:
    """Check item_summary doesn't contain emails, phone numbers, or addresses."""
    if not result.get("success"):
        return _result("no_pii_in_item", True, "skipped — not a successful extraction")

    card = result.get("card") or {}
    item = card.get("item_summary", "")

    if not item:
        return _result("no_pii_in_item", True, "no item_summary")

    if _EMAIL_RE.search(item):
        return _result("no_pii_in_item", False, f"email address found in item_summary: '{item[:60]}'")

    if _PHONE_RE.search(item):
        return _result("no_pii_in_item", False, f"phone number found in item_summary: '{item[:60]}'")

    if _ADDRESS_RE.search(item):
        return _result("no_pii_in_item", False, f"physical address found in item_summary: '{item[:60]}'")

    return _result("no_pii_in_item", True, "clean")


# All code evals in execution order
ALL_CODE_EVALS = [
    valid_merchant,
    valid_return_date,
    valid_confidence,
    order_number_format,
    no_empty_card,
    return_window_reasonable,
    stage_consistency,
    no_pii_in_item,
]


def run_code_evals(result: dict) -> list[dict]:
    """Run all code evals on a single extraction result."""
    return [eval_fn(result) for eval_fn in ALL_CODE_EVALS]
