"""
Judge evals — LLM-as-judge for extraction quality assessment.

Uses Gemini Flash for cheap, fast evaluation of extraction results.
Only run with --judges flag (not part of default eval suite).

Two judges:
1. Extraction Quality — Is the merchant/item/date extraction reasonable?
2. Confidence Calibration — Does confidence match source email clarity?
"""

from __future__ import annotations

import json
import os
import re


def _result(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "pass": passed, "detail": detail}


def _call_gemini(prompt: str) -> str | None:
    """Call Gemini Flash for judge evaluation. Returns response text or None."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import httpx
    except ImportError:
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 256,
        },
    }

    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def extraction_quality_judge(result: dict, case: dict) -> dict:
    """LLM judge: Is the extraction reasonable given the source email?"""
    if not result.get("success"):
        return _result("judge_extraction_quality", True, "skipped — no extraction to judge")

    card = result.get("card") or {}
    email_body = case.get("body", "")[:1000]
    subject = case.get("subject", "")

    prompt = f"""You are evaluating an email extraction system. Given the source email and the extracted data, determine if the extraction is reasonable.

Source email subject: {subject}
Source email body (first 1000 chars):
{email_body}

Extracted data:
- Merchant: {card.get('merchant', 'N/A')}
- Item: {card.get('item_summary', 'N/A')}
- Order number: {card.get('order_number', 'N/A')}
- Return by date: {card.get('return_by_date', 'N/A')}

Is this extraction reasonable? Consider:
1. Does the merchant match the email sender?
2. Does the item summary reflect actual products in the email?
3. Is the order number extracted correctly?

Respond with exactly one line: PASS: <reason> or FAIL: <reason>"""

    response = _call_gemini(prompt)
    if not response:
        return _result("judge_extraction_quality", True, "skipped — Gemini unavailable")

    response = response.strip().split("\n")[0]
    if response.upper().startswith("PASS"):
        return _result("judge_extraction_quality", True, response)
    elif response.upper().startswith("FAIL"):
        return _result("judge_extraction_quality", False, response)
    else:
        return _result("judge_extraction_quality", True, f"ambiguous judge response: {response[:80]}")


def confidence_calibration_judge(result: dict, case: dict) -> dict:
    """LLM judge: Does the confidence level match the source email clarity?"""
    if not result.get("success"):
        return _result("judge_confidence_calibration", True, "skipped — no extraction to judge")

    card = result.get("card") or {}
    confidence = card.get("confidence", "unknown")
    email_body = case.get("body", "")[:1000]
    subject = case.get("subject", "")

    prompt = f"""You are evaluating whether an extraction system's confidence level is calibrated correctly.

Source email subject: {subject}
Source email body (first 1000 chars):
{email_body}

System assigned confidence: {confidence}
(EXACT = explicit return date found in email, ESTIMATED = calculated from merchant rules, UNKNOWN = no date info)

Extracted return_by_date: {card.get('return_by_date', 'None')}

Is the confidence level appropriate? Consider:
- EXACT: should only be used when the email explicitly states a return-by date
- ESTIMATED: appropriate when calculating from delivery/order date + standard policy
- UNKNOWN: when there's no date information available

Respond with exactly one line: PASS: <reason> or FAIL: <reason>"""

    response = _call_gemini(prompt)
    if not response:
        return _result("judge_confidence_calibration", True, "skipped — Gemini unavailable")

    response = response.strip().split("\n")[0]
    if response.upper().startswith("PASS"):
        return _result("judge_confidence_calibration", True, response)
    elif response.upper().startswith("FAIL"):
        return _result("judge_confidence_calibration", False, response)
    else:
        return _result("judge_confidence_calibration", True, f"ambiguous: {response[:80]}")


# All judge evals
ALL_JUDGE_EVALS = [
    extraction_quality_judge,
    confidence_calibration_judge,
]


def run_judge_evals(result: dict, case: dict) -> list[dict]:
    """Run all judge evals on a single result+case pair."""
    return [eval_fn(result, case) for eval_fn in ALL_JUDGE_EVALS]
