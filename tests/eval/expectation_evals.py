"""
Expectation evals — compare extraction results against synthetic case expected values.

Each eval takes a result dict (from the API) and a case dict (from synthetic-emails.json)
and checks whether the extraction matched expectations.
"""

from __future__ import annotations


def _result(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "pass": passed, "detail": detail}


def expected_extraction(result: dict, case: dict) -> dict:
    """Did it extract (success=True) when expected, reject when not?"""
    expected = case["expected"]
    should_extract = expected["should_extract"]
    did_extract = result.get("success", False)

    if should_extract and not did_extract:
        reason = result.get("rejection_reason", "unknown")
        return _result("expected_extraction", False,
                        f"expected extraction but was rejected: {reason}")

    if not should_extract and did_extract:
        card = result.get("card") or {}
        return _result("expected_extraction", False,
                        f"expected rejection but extracted: merchant={card.get('merchant', '?')}")

    action = "extracted" if did_extract else "rejected"
    return _result("expected_extraction", True, f"correctly {action}")


def expected_merchant(result: dict, case: dict) -> dict:
    """Does merchant_domain match expected?"""
    expected = case["expected"]
    if not expected["should_extract"]:
        return _result("expected_merchant", True, "skipped — expected rejection")

    if not result.get("success"):
        return _result("expected_merchant", True, "skipped — extraction failed (covered by expected_extraction)")

    card = result.get("card") or {}
    actual_domain = (card.get("merchant_domain") or "").lower()
    expected_domain = (expected.get("merchant_domain") or "").lower()

    if not expected_domain:
        return _result("expected_merchant", True, "no expected merchant_domain specified")

    if actual_domain == expected_domain:
        return _result("expected_merchant", True, f"domain='{actual_domain}'")

    # Allow subdomain matches (e.g., "email.nike.com" matching "nike.com")
    if actual_domain.endswith("." + expected_domain) or expected_domain.endswith("." + actual_domain):
        return _result("expected_merchant", True,
                        f"domain subdomain match: actual='{actual_domain}' expected='{expected_domain}'")

    return _result("expected_merchant", False,
                    f"expected domain '{expected_domain}', got '{actual_domain}'")


def expected_order_number(result: dict, case: dict) -> dict:
    """If expected, was order_number extracted correctly?"""
    expected = case["expected"]
    if not expected["should_extract"] or not expected.get("has_order_number"):
        return _result("expected_order_number", True, "skipped — no order number expected")

    if not result.get("success"):
        return _result("expected_order_number", True, "skipped — extraction failed")

    card = result.get("card") or {}
    actual = card.get("order_number")
    expected_num = expected.get("order_number")

    if not expected_num:
        # Just check that some order number was extracted
        if actual:
            return _result("expected_order_number", True, f"order_number present: '{actual}'")
        return _result("expected_order_number", False, "expected an order number but got none")

    if not actual:
        return _result("expected_order_number", False,
                        f"expected order_number '{expected_num}' but got none")

    # Normalize for comparison (strip whitespace)
    if actual.strip() == expected_num.strip():
        return _result("expected_order_number", True, f"order_number='{actual}'")

    # Check if expected is contained in actual (sometimes extra context is included)
    if expected_num.strip() in actual.strip():
        return _result("expected_order_number", True,
                        f"order_number contains expected: actual='{actual}' expected='{expected_num}'")

    return _result("expected_order_number", False,
                    f"expected order_number '{expected_num}', got '{actual}'")


def expected_confidence(result: dict, case: dict) -> dict:
    """Does confidence level match expected?"""
    expected = case["expected"]
    if not expected["should_extract"]:
        return _result("expected_confidence", True, "skipped — expected rejection")

    if not result.get("success"):
        return _result("expected_confidence", True, "skipped — extraction failed")

    expected_conf = expected.get("confidence")
    if not expected_conf:
        return _result("expected_confidence", True, "no expected confidence specified")

    card = result.get("card") or {}
    actual_conf = (card.get("confidence") or "").lower()

    if actual_conf == expected_conf.lower():
        return _result("expected_confidence", True, f"confidence='{actual_conf}'")

    return _result("expected_confidence", False,
                    f"expected confidence '{expected_conf}', got '{actual_conf}'")


def expected_rejection_stage(result: dict, case: dict) -> dict:
    """If expected to reject, was it at a reasonable stage?"""
    expected = case["expected"]
    if expected["should_extract"]:
        return _result("expected_rejection_stage", True, "skipped — expected extraction")

    if result.get("success"):
        return _result("expected_rejection_stage", True,
                        "skipped — extraction succeeded (covered by expected_extraction)")

    stage = result.get("stage_reached", "unknown")
    reason = result.get("rejection_reason", "")

    # For non-purchase emails, rejection at filter or classifier is correct
    tags = case.get("tags", [])
    if "should_reject" in tags:
        if stage in ("filter", "classifier", "extractor"):
            return _result("expected_rejection_stage", True,
                            f"correctly rejected at stage='{stage}': {reason}")

    return _result("expected_rejection_stage", True, f"rejected at stage='{stage}'")


def must_not_contain(result: dict, case: dict) -> dict:
    """Check must_not list against card fields."""
    expected = case["expected"]
    must_not = expected.get("must_not", [])

    if not must_not:
        return _result("must_not_contain", True, "no must_not constraints")

    if not result.get("success"):
        return _result("must_not_contain", True, "skipped — extraction failed")

    card = result.get("card") or {}
    # Concatenate all text fields for checking
    text_fields = " ".join(str(v) for v in [
        card.get("merchant", ""),
        card.get("item_summary", ""),
        card.get("evidence_snippet", ""),
        card.get("order_number", ""),
    ] if v)

    for forbidden in must_not:
        if forbidden.lower() in text_fields.lower():
            return _result("must_not_contain", False,
                            f"found forbidden string '{forbidden}' in card fields")

    return _result("must_not_contain", True, f"checked {len(must_not)} constraints")


# All expectation evals in execution order
ALL_EXPECTATION_EVALS = [
    expected_extraction,
    expected_merchant,
    expected_order_number,
    expected_confidence,
    expected_rejection_stage,
    must_not_contain,
]


def run_expectation_evals(result: dict, case: dict) -> list[dict]:
    """Run all expectation evals on a single result+case pair."""
    return [eval_fn(result, case) for eval_fn in ALL_EXPECTATION_EVALS]
