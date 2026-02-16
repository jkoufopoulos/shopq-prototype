"""
Field Extractor - Extract structured data from returnable purchase emails.

Stage 3 of the extraction pipeline. Uses hybrid LLM + rules approach:
- LLM extracts core fields (merchant, items, dates, amounts)
- Rules compute return_by_date from merchant_rules.yaml
- Regex patterns extract order numbers, tracking links

Cost: ~$0.0002 per email (Gemini Flash)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

from pydantic import BaseModel
from pydantic import Field as PydanticField

from reclaim.config import (
    PIPELINE_BODY_TRUNCATION,
    PIPELINE_DATE_WINDOW_DAYS,
    PIPELINE_DEFAULT_RETURN_DAYS,
    PIPELINE_ORDER_NUM_MAX_LEN,
    PIPELINE_ORDER_NUM_MIN_LEN,
)
from reclaim.observability.logging import get_logger
from reclaim.observability.telemetry import counter, log_event
from reclaim.returns.models import ReturnConfidence
from reclaim.returns.types import ExtractedFields
from reclaim.utils.redaction import redact_pii, redact_subject

logger = get_logger(__name__)


def _use_llm() -> bool:
    """Check LLM feature flag at call time (not import time).

    Reads env var fresh to avoid stale cache when dotenv loads after module import.
    """
    return os.getenv("RECLAIM_USE_LLM", os.getenv("SHOPQ_USE_LLM", "false")).lower() == "true"


class LLMExtractionSchema(BaseModel):
    """Schema for LLM extraction response."""

    merchant_name: str = PydanticField(description="Merchant/retailer name")
    item_summary: str = PydanticField(description="Brief description of items purchased")
    order_number: str | None = PydanticField(default=None, description="Order/confirmation number")
    amount: float | None = PydanticField(default=None, description="Total purchase amount")
    currency: str = PydanticField(default="USD", description="Currency code")
    order_date: str | None = PydanticField(default=None, description="Order date (YYYY-MM-DD)")
    delivery_date: str | None = PydanticField(
        default=None, description="Delivery/shipped date (YYYY-MM-DD)"
    )
    explicit_return_by: str | None = PydanticField(
        default=None, description="Explicit return-by date if mentioned (YYYY-MM-DD)"
    )
    return_window_days: int | None = PydanticField(
        default=None, description="Return window in days if mentioned (e.g., 30 for '30 days')"
    )
    return_policy_quote: str | None = PydanticField(
        default=None, description="Verbatim quote from email mentioning return policy/deadline"
    )


# Gemini structured output schema
EXTRACTOR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "merchant_name": {
            "type": "string",
            "nullable": True,
            "description": "Retailer or store name (e.g. Amazon, Target, Nike)",
        },
        "item_summary": {
            "type": "string",
            "nullable": True,
            "description": "Actual product names purchased, comma-separated. null if no specific product name found.",
        },
        "order_number": {
            "type": "string",
            "nullable": True,
            "description": "Order or confirmation number. null if not visible in the email.",
        },
        "amount": {
            "type": "number",
            "nullable": True,
            "description": "Total purchase amount as a number, no currency symbol. null if not stated.",
        },
        "currency": {
            "type": "string",
            "description": "ISO currency code, default USD",
        },
        "order_date": {
            "type": "string",
            "nullable": True,
            "description": "Date the order was placed in YYYY-MM-DD format. null if not stated.",
        },
        "delivery_date": {
            "type": "string",
            "nullable": True,
            "description": "Expected or actual delivery date in YYYY-MM-DD format. null if not stated.",
        },
        "explicit_return_by": {
            "type": "string",
            "nullable": True,
            "description": "Return deadline date in YYYY-MM-DD format. Only if the email states a specific date. null otherwise.",
        },
        "return_window_days": {
            "type": "integer",
            "nullable": True,
            "description": "Number of days for returns if mentioned (e.g. 30 for '30-day returns'). null if not stated.",
        },
        "return_policy_quote": {
            "type": "string",
            "nullable": True,
            "description": "Verbatim quote from the email about return policy. Copy exact text. null if no return info.",
        },
    },
    "required": ["merchant_name", "item_summary"],
    "propertyOrdering": [
        "merchant_name", "item_summary", "order_number", "amount", "currency",
        "order_date", "delivery_date", "explicit_return_by", "return_window_days",
        "return_policy_quote",
    ],
}


# System instruction — cached by Gemini, reduces per-call latency.
EXTRACTOR_SYSTEM_INSTRUCTION = """You extract structured purchase details from order/shipping emails.

## Fields to extract

1. merchant_name: The retailer or store name (e.g., "Amazon", "Target", "Nike").
2. item_summary: The actual product names purchased, comma-separated. Extract specific product names from the email body. Do not use generic phrases like "your package" or "some of the items". Include all items if multiple are listed. null if no specific product name can be found.
3. order_number: Order or confirmation number. null if not visible in the email.
4. amount: Total purchase amount as a number (no currency symbol). null if not stated.
5. currency: Currency code. Default "USD" if not specified.
6. order_date: Date the order was placed, YYYY-MM-DD format. null if not stated.
7. delivery_date: Expected or actual delivery date, YYYY-MM-DD format. null if not stated.
8. explicit_return_by: Return deadline date, YYYY-MM-DD format. Only if the email states a specific return-by date. null otherwise.
9. return_window_days: Number of days for returns if mentioned (e.g., 30 for "30-day returns"). null if not stated.
10. return_policy_quote: Verbatim quote from the email mentioning return policy. Copy the exact text. null if no return info exists.

## Few-shot examples

Email:
Date this email was sent: 2025-01-10
Subject: Your Nike.com Order Confirmation
From: nikeonline@nike.com
Body:
Thanks for your order! Order #C02849371 placed on January 10, 2025.
Nike Air Max 90 - Men's Size 10 - White/Black — $130.00
Estimated delivery: January 16, 2025
Free returns within 30 days of delivery. Start a return at nike.com/returns.

Extraction:
{"merchant_name": "Nike", "item_summary": "Nike Air Max 90 - Men's Size 10 - White/Black", "order_number": "C02849371", "amount": 130.00, "currency": "USD", "order_date": "2025-01-10", "delivery_date": "2025-01-16", "explicit_return_by": null, "return_window_days": 30, "return_policy_quote": "Free returns within 30 days of delivery."}

Email:
Date this email was sent: 2025-02-05
Subject: Your package has been delivered
From: delivery-notification@amazon.com
Body:
Your package was delivered today at 2:15 PM. It was left at your front door.
Items in this shipment: 1 package

Extraction:
{"merchant_name": "Amazon", "item_summary": null, "order_number": null, "amount": null, "currency": "USD", "order_date": null, "delivery_date": "2025-02-05", "explicit_return_by": null, "return_window_days": null, "return_policy_quote": null}

## Output format
Extract all available fields. Use null for any field not found in the email."""


class ReturnFieldExtractor:
    """
    Extract structured fields from returnable purchase emails.

    Combines LLM extraction with rules-based computation for return_by_date.
    """

    # Regex patterns for common fields
    ORDER_NUMBER_PATTERNS = [
        # Amazon-specific format (most specific, check first)
        r"#([0-9]{3}-[0-9]{7}-[0-9]{7})",
        # "ORDER NUMBER [#51596895]" or "Order Number: ABC123"
        r"(?:order|confirmation)\s+number\s*:?\s*\[?#?\s*([A-Z0-9][-A-Z0-9]{3,24})",
        # "Order #ABC123" or "Order #: ABC123" (requires # delimiter)
        r"order\s*#\s*:?\s*([A-Z0-9][-A-Z0-9]{3,24})",
        # "Confirmation #ABC123" or "Confirmation: ABC123"
        r"confirmation\s*[#:]\s*([A-Z0-9][-A-Z0-9]{3,24})",
        # "Trans: 67082" or "Transaction #67082"
        r"trans(?:action)?\s*[#:]\s*([A-Z0-9][-A-Z0-9]{3,24})",
        # "Updated Shipping Address for 1P8QCX0" — order number after "for"
        r"(?:for|regarding|re:?)\s+#?\s*([A-Z0-9][-A-Z0-9]{4,24})\s*$",
    ]

    TRACKING_LINK_PATTERNS = [
        r"(https?://[^\s]*(?:track|tracking|shipment)[^\s]*)",
        r"(https?://[^\s]*(?:ups|fedex|usps|dhl)[^\s]*)",
    ]

    RETURN_PORTAL_PATTERNS = [
        r"(https?://[^\s]*(?:return|refund)[^\s]*)",
    ]

    # User message template — only per-email data
    EXTRACTION_PROMPT = """Date this email was sent: {today}
Subject: {subject}
From: {from_address}
Body:
{body}"""

    def __init__(self, merchant_rules: dict | None = None):
        """
        Initialize extractor with merchant rules.

        Args:
            merchant_rules: Dict from merchant_rules.yaml with return windows
        """
        self.merchant_rules = merchant_rules or {}
        # CODE-011: Model is now obtained from shared singleton

    def _call_llm_with_retry(
        self,
        prompt: str,
        system_instruction: str | None = None,
        response_schema: dict | None = None,
    ) -> str:
        """Call LLM with retry logic and timeout.

        CODE-003: Delegates to shared call_llm() with extractor-specific counter prefix.
        """
        from reclaim.llm.retry import call_llm

        return call_llm(
            prompt,
            counter_prefix="extractor",
            system_instruction=system_instruction,
            response_schema=response_schema,
        )

    # Common garbage values the LLM or regex may extract as order numbers
    _GARBAGE_ORDER_WORDS = frozenset(
        {
            "confirmation",
            "tracking",
            "order",
            "number",
            "receipt",
            "invoice",
            "shipping",
            "delivery",
            "purchase",
            "unknown",
            "none",
            "n/a",
            "null",
        }
    )

    @staticmethod
    def _validate_order_number(order_num: str | None) -> str | None:
        """Validate and clean an extracted order number.

        Rejects:
        - None / empty
        - Common words (CONFIRMATION, TRACKING, etc.)
        - Strings with no digits
        - Too short (<3 chars) or too long (>40 chars)
        - Leading/trailing dashes
        """
        if not order_num:
            return None

        cleaned = order_num.strip().strip("-").strip()

        if not cleaned or len(cleaned) < PIPELINE_ORDER_NUM_MIN_LEN or len(cleaned) > PIPELINE_ORDER_NUM_MAX_LEN:
            return None

        # Reject if it's a common word
        if cleaned.lower() in ReturnFieldExtractor._GARBAGE_ORDER_WORDS:
            return None

        # Reject if no digits at all
        if not any(c.isdigit() for c in cleaned):
            return None

        return cleaned

    def extract(
        self,
        from_address: str,
        subject: str,
        body: str,
        merchant_domain: str,
        received_at: datetime | None = None,
    ) -> ExtractedFields:
        """
        Extract all fields from a purchase email.

        Args:
            from_address: Email sender
            subject: Email subject
            body: Email body text
            merchant_domain: Sender domain (for merchant rule lookup)
            received_at: When the email was received (fallback anchor date)

        Returns:
            ExtractedFields with all available data

        Side Effects:
            - Calls Gemini API if USE_LLM is true
            - Logs extraction events
        """
        # Start with rules-based extraction
        rules_fields = self._extract_with_rules(body, subject)

        # LLM extraction for complex fields
        if _use_llm():
            try:
                llm_fields = self._extract_with_llm(from_address, subject, body, received_at)
                counter("returns.extractor.llm_success")
            except Exception as e:
                logger.warning("LLM extraction failed, using rules only: %s", e)
                counter("returns.extractor.llm_error")
                llm_fields = {}
        else:
            llm_fields = {}
            counter("returns.extractor.llm_disabled")

        # Merge results (LLM takes precedence for text fields)
        merchant = llm_fields.get("merchant_name") or self._guess_merchant(from_address, subject)
        item_summary = llm_fields.get("item_summary") or self._extract_item_summary(subject, body)

        # Dates - prefer explicit, then LLM, then rules
        order_date = self._parse_date(llm_fields.get("order_date"))
        delivery_date = self._parse_date(llm_fields.get("delivery_date"))
        explicit_return_by = self._parse_date(llm_fields.get("explicit_return_by"))

        # Get return policy info from LLM
        return_window_days = llm_fields.get("return_window_days")
        return_policy_quote = llm_fields.get("return_policy_quote")

        # Compute return_by_date using priority logic
        return_by_date, return_confidence = self._compute_return_by_date(
            explicit_return_by=explicit_return_by,
            order_date=order_date,
            delivery_date=delivery_date,
            merchant_domain=merchant_domain,
            return_window_days=return_window_days,
            received_at=received_at,
        )

        # Build evidence snippet - only use actual return policy quote from LLM
        # CODE-008: Redact PII from evidence before storage
        raw_evidence = return_policy_quote
        evidence = redact_pii(raw_evidence, max_length=200) if raw_evidence else None

        # Build result
        result = ExtractedFields(
            merchant=merchant,
            merchant_domain=merchant_domain,
            item_summary=item_summary,
            order_date=order_date,
            delivery_date=delivery_date,
            explicit_return_by=explicit_return_by,
            return_by_date=return_by_date,
            return_confidence=return_confidence,
            order_number=(
                self._validate_order_number(rules_fields.get("order_number"))
                or self._validate_order_number(llm_fields.get("order_number"))
            ),
            amount=llm_fields.get("amount"),
            currency=llm_fields.get("currency", "USD"),
            return_portal_link=rules_fields.get("return_portal_link"),
            tracking_link=rules_fields.get("tracking_link"),
            evidence_snippet=evidence,
            extraction_method="hybrid" if llm_fields else "rules",
        )

        log_event(
            "returns.extractor.complete",
            merchant=merchant,
            has_return_by=return_by_date is not None,
            confidence=return_confidence.value,
            method=result.extraction_method,
        )

        return result

    def _extract_with_rules(self, body: str, subject: str) -> dict:
        """Extract fields using regex patterns."""
        text = f"{subject}\n{body}".lower()
        result = {}

        # Order number
        for pattern in self.ORDER_NUMBER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                result["order_number"] = match.group(1).upper()
                break

        # Tracking link
        for pattern in self.TRACKING_LINK_PATTERNS:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                result["tracking_link"] = match.group(1)
                break

        # Return portal link
        for pattern in self.RETURN_PORTAL_PATTERNS:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                result["return_portal_link"] = match.group(1)
                break

        return result

    def _extract_with_llm(
        self,
        from_address: str,
        subject: str,
        body: str,
        received_at: datetime | None = None,
    ) -> dict:
        """Extract fields using LLM."""
        body_truncated = body[:PIPELINE_BODY_TRUNCATION] if body else ""

        # LOG: What we're sending to LLM (for validation)
        # SEC-016: Redact PII from logging
        logger.info(
            "LLM extraction input: subject=%s, body_length=%d, truncated_length=%d",
            redact_subject(subject),
            len(body) if body else 0,
            len(body_truncated),
        )
        # NOTE: Body content not logged to prevent PII exposure

        # Privacy: Redact PII from body before sending to Gemini
        body_redacted = redact_pii(body_truncated, max_length=PIPELINE_BODY_TRUNCATION)

        # Use the email's received date as "today" so the LLM correctly interprets
        # relative dates like "Delivered today" or "Arriving tomorrow"
        context_date = received_at or datetime.now()
        prompt = self.EXTRACTION_PROMPT.format(
            today=context_date.strftime("%Y-%m-%d"),
            subject=self._sanitize(subject, 200),
            from_address=self._sanitize(from_address, 100),
            body=self._sanitize(body_redacted, PIPELINE_BODY_TRUNCATION),
        )

        # Call LLM with retry, system instruction, and structured output
        response_text = self._call_llm_with_retry(
            prompt,
            system_instruction=EXTRACTOR_SYSTEM_INSTRUCTION,
            response_schema=EXTRACTOR_RESPONSE_SCHEMA,
        )

        # Parse JSON response
        result = self._parse_llm_response(response_text)

        # LOG: What LLM returned (for validation)
        logger.info(
            "LLM extraction output: return_window_days=%s, has_quote=%s, explicit_return_by=%s",
            result.get("return_window_days"),
            bool(result.get("return_policy_quote")),
            result.get("explicit_return_by"),
        )
        quote = result.get("return_policy_quote")
        if quote:
            logger.debug("LLM extracted quote: %s", quote[:200])

        return result

    def _parse_llm_response(self, response_text: str) -> dict:
        """Parse LLM JSON response."""
        try:
            # Handle markdown code blocks
            json_text = response_text.strip()
            if json_text.startswith("```"):
                # Should not trigger with response_schema
                counter("returns.extractor.code_fence_fallback")
                logger.warning("Extractor response contained code fences (unexpected with schema)")
                json_text = re.sub(r"^```(?:json)?\n?", "", json_text)
                json_text = re.sub(r"\n?```$", "", json_text)

            data = json.loads(json_text)

            # Validate with schema
            validated = LLMExtractionSchema.model_validate(data)
            return validated.model_dump()

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse LLM extraction response: %s", e)
            return {}

    @staticmethod
    def _validate_date_against_email(
        date: datetime | None, received_at: datetime | None
    ) -> datetime | None:
        """Reject LLM-extracted dates that are implausibly far from the email date."""
        if date is None or received_at is None:
            return date
        # Normalize both to naive for comparison (avoid tz-aware vs tz-naive error)
        d = date.replace(tzinfo=None) if date.tzinfo else date
        r = received_at.replace(tzinfo=None) if received_at.tzinfo else received_at
        delta_days = abs((d - r).days)
        if delta_days > PIPELINE_DATE_WINDOW_DAYS:
            logger.warning(
                "Rejecting extracted date %s: %d days from email received %s",
                date.isoformat(),
                delta_days,
                received_at.isoformat(),
            )
            return None
        return date

    def _compute_return_by_date(
        self,
        explicit_return_by: datetime | None,
        order_date: datetime | None,
        delivery_date: datetime | None,
        merchant_domain: str,
        return_window_days: int | None = None,
        received_at: datetime | None = None,
    ) -> tuple[datetime | None, ReturnConfidence]:
        """
        Compute return_by_date using PRD priority logic.

        Priority:
        1. EXACT: Explicit return-by date found in email
        2. ESTIMATED (email): Return window days from email + anchor date
        3. ESTIMATED (merchant): Merchant rule window + anchor date
        4. UNKNOWN: No date info

        ``received_at`` is used as a last-resort anchor when both
        ``order_date`` and ``delivery_date`` are None.
        """
        # Normalize received_at to naive to avoid tz-aware vs tz-naive mismatches
        # (LLM-parsed dates are typically naive; received_at from Gmail is tz-aware)
        if received_at and received_at.tzinfo is not None:
            received_at = received_at.replace(tzinfo=None)

        # Validate LLM-extracted dates against email received date
        order_date = self._validate_date_against_email(order_date, received_at)
        delivery_date = self._validate_date_against_email(delivery_date, received_at)
        explicit_return_by = self._validate_date_against_email(explicit_return_by, received_at)

        # P1: Explicit return-by date from email
        if explicit_return_by:
            return explicit_return_by, ReturnConfidence.EXACT

        # P2: Return window from email (with quote evidence)
        if return_window_days and return_window_days > 0:
            anchor = delivery_date or order_date or received_at
            if anchor:
                return_by = anchor + timedelta(days=return_window_days)
                return return_by, ReturnConfidence.ESTIMATED

        # P3: Use merchant rules as fallback
        merchants = self.merchant_rules.get("merchants", {})
        rule = merchants.get(merchant_domain) or merchants.get("_default")

        if rule:
            days = rule.get("days", PIPELINE_DEFAULT_RETURN_DAYS)
            anchor_type = rule.get("anchor", "delivery")

            # Get anchor date, falling back to received_at
            anchor = delivery_date if anchor_type == "delivery" else order_date
            if anchor is None:
                anchor = order_date or received_at

            if anchor:
                return_by = anchor + timedelta(days=days)
                return return_by, ReturnConfidence.ESTIMATED

        # P4: Unknown
        return None, ReturnConfidence.UNKNOWN

    def _guess_merchant(self, from_address: str, subject: str) -> str:  # noqa: ARG002
        """Guess merchant name from email metadata."""
        # Extract from "Name <email>" format
        match = re.search(r"^([^<]+)", from_address)
        if match:
            name = match.group(1).strip()
            # Clean up common suffixes
            name = re.sub(
                r"\s*(Customer Service|Support|Orders?|Shipping).*$", "", name, flags=re.IGNORECASE
            )
            if name and len(name) > 2:
                return name

        # Extract from domain
        domain_match = re.search(r"@([^.]+)", from_address)
        if domain_match:
            return domain_match.group(1).title()

        return "Unknown Merchant"

    def _extract_item_summary(self, subject: str, body: str) -> str:
        """Extract item summary from subject/body when LLM unavailable."""
        # Try subject first
        # Remove common prefixes
        summary = re.sub(
            r"^(Your |Order |Shipping |Delivery |RE: |FW: )+",
            "",
            subject,
            flags=re.IGNORECASE,
        )

        if len(summary) > 10:
            return summary[:100]

        # Fallback to first line of body
        if body:
            first_line = body.split("\n")[0][:100]
            return first_line or "Purchase"

        return "Purchase"

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse date string to datetime."""
        if not date_str:
            return None

        try:
            # Try ISO format first
            return datetime.fromisoformat(date_str)
        except ValueError:
            pass

        # Try common formats
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _sanitize(self, text: str, max_length: int) -> str:
        """Sanitize input for LLM prompt.

        CODE-007: Delegates to shared sanitize_llm_input().
        """
        from reclaim.utils.redaction import sanitize_llm_input

        return sanitize_llm_input(text, max_length=max_length, counter_prefix="extractor")
