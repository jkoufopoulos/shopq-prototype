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
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel
from pydantic import Field as PydanticField
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shopq.llm.gemini import get_gemini_model
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event
from shopq.returns.models import ReturnConfidence
from shopq.utils.redaction import redact_pii, redact_subject

logger = get_logger(__name__)

# Feature flag
USE_LLM = os.getenv("SHOPQ_USE_LLM", "false").lower() == "true"

# CODE-003/CODE-004: LLM call configuration
LLM_TIMEOUT_SECONDS = 30  # Maximum time to wait for LLM response
LLM_MAX_RETRIES = 3  # Number of retry attempts for transient failures


@dataclass
class ExtractedFields:
    """Fields extracted from a purchase email."""

    # Core fields (from LLM)
    merchant: str
    merchant_domain: str
    item_summary: str

    # Dates
    order_date: datetime | None = None
    delivery_date: datetime | None = None
    explicit_return_by: datetime | None = None  # If found in email

    # Computed return-by
    return_by_date: datetime | None = None
    return_confidence: ReturnConfidence = ReturnConfidence.UNKNOWN

    # Optional fields
    order_number: str | None = None
    amount: float | None = None
    currency: str = "USD"
    return_portal_link: str | None = None
    tracking_link: str | None = None
    evidence_snippet: str | None = None

    # Metadata
    extraction_method: str = "unknown"  # "llm" | "rules" | "hybrid"


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

    # LLM prompt for field extraction
    EXTRACTION_PROMPT = """Extract purchase details from this email.

Date this email was sent: {today}

Subject: {subject}
From: {from_address}
Body:
{body}

Extract these fields:
1. merchant_name: The retailer/store name (e.g., "Amazon", "Target", "Nike")
2. item_summary: The ACTUAL PRODUCT NAMES purchased, comma-separated.
   Example: "Wireless headphones, Phone case"
   RULES: Extract specific product names from the email body.
   Do NOT use generic phrases like "your package", "some of the items",
   or "package has been delivered". Include ALL items if multiple are listed.
   If no specific product name can be found, use null.
3. order_number: Order/confirmation number if present
4. amount: Total purchase amount (number only, no currency symbol)
5. currency: Currency code (default USD)
6. order_date: When order was placed (YYYY-MM-DD format)
7. delivery_date: Expected or actual delivery date (YYYY-MM-DD format)
8. explicit_return_by: ONLY if email explicitly states a return deadline date (YYYY-MM-DD format)
9. return_window_days: Number of days for returns if mentioned (e.g., 30 for "30-day returns")
10. return_policy_quote: VERBATIM quote from email mentioning return policy (copy exact text)

IMPORTANT for return fields:
- If the email mentions a return policy, copy the EXACT text into return_policy_quote
- Only fill explicit_return_by if a specific date appears in the quote
- Only fill return_window_days if a specific number of days appears in the quote
- Do NOT guess. If no return info exists, leave these fields null.

Output JSON:
{{
  "merchant_name": "...",
  "item_summary": "...",
  "order_number": "..." or null,
  "amount": 123.45 or null,
  "currency": "USD",
  "order_date": "YYYY-MM-DD" or null,
  "delivery_date": "YYYY-MM-DD" or null,
  "explicit_return_by": "YYYY-MM-DD" or null,
  "return_window_days": 30 or null,
  "return_policy_quote": "exact text from email about returns" or null
}}

Respond with ONLY the JSON."""

    def __init__(self, merchant_rules: dict | None = None):
        """
        Initialize extractor with merchant rules.

        Args:
            merchant_rules: Dict from merchant_rules.yaml with return windows
        """
        self.merchant_rules = merchant_rules or {}
        # CODE-011: Model is now obtained from shared singleton

    def _get_model(self):
        """Get shared Gemini model instance.

        CODE-011: Uses shared singleton instead of per-instance model.
        """
        return get_gemini_model()

    @retry(
        stop=stop_after_attempt(LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
        reraise=True,
    )
    def _call_llm_with_retry(self, prompt: str) -> str:
        """Call LLM with retry logic and timeout.

        CODE-003: Retries up to 3 times with exponential backoff for transient failures.
        CODE-004: 30-second timeout to prevent hanging requests.
        """
        from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable

        model = self._get_model()

        try:
            response = model.generate_content(prompt)
            return response.text
        except DeadlineExceeded as e:
            counter("returns.extractor.timeout")
            logger.warning("LLM call timed out after %ds", LLM_TIMEOUT_SECONDS)
            raise TimeoutError(f"LLM call timed out: {e}") from e
        except ServiceUnavailable as e:
            counter("returns.extractor.service_unavailable")
            logger.warning("LLM service unavailable, will retry: %s", e)
            raise ConnectionError(f"LLM service unavailable: {e}") from e

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

        if not cleaned or len(cleaned) < 3 or len(cleaned) > 40:
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
        if USE_LLM:
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

        # Build evidence snippet - prefer return policy quote, fallback to body preview
        # CODE-008: Redact PII from evidence before storage
        raw_evidence = (
            return_policy_quote if return_policy_quote else (body[:200] if body else None)
        )
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
        # Truncate body for prompt - use 4000 chars to capture return policies at bottom
        body_truncated = body[:4000] if body else ""

        # LOG: What we're sending to LLM (for validation)
        # SEC-016: Redact PII from logging
        logger.info(
            "LLM extraction input: subject=%s, body_length=%d, truncated_length=%d",
            redact_subject(subject),
            len(body) if body else 0,
            len(body_truncated),
        )
        # NOTE: Body content not logged to prevent PII exposure

        # Use the email's received date as "today" so the LLM correctly interprets
        # relative dates like "Delivered today" or "Arriving tomorrow"
        context_date = received_at or datetime.now()
        prompt = self.EXTRACTION_PROMPT.format(
            today=context_date.strftime("%Y-%m-%d"),
            subject=self._sanitize(subject, 200),
            from_address=self._sanitize(from_address, 100),
            body=self._sanitize(body_truncated, 4000),
        )

        # Call LLM with retry and timeout (CODE-003, CODE-004)
        response_text = self._call_llm_with_retry(prompt)

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
        if delta_days > 180:
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
            days = rule.get("days", 30)
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

        CODE-007: Enhanced sanitization with expanded patterns for role impersonation
        and control character removal.
        """
        if not text:
            return ""

        # Remove control characters (except newlines and tabs)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

        # Remove common injection patterns - instruction override attempts
        text = re.sub(
            r"(?i)(ignore|disregard|forget|skip|override).*(instruction|prompt|above|previous|rule)",
            "[REDACTED]",
            text,
        )
        text = re.sub(r"(?i)do\s+not\s+follow.*", "[REDACTED]", text)
        text = re.sub(r"(?i)instead\s+(of|do|output).*", "[REDACTED]", text)

        # Remove role impersonation attempts
        text = re.sub(r"(?i)(system|assistant|user|human|ai|claude|gpt)\s*:", "", text)
        text = re.sub(r"(?i)<\s*(system|assistant|user|human)\s*>", "", text)
        text = re.sub(r"(?i)\[\s*(system|assistant|user|human)\s*\]", "", text)
        text = re.sub(r"(?i)you\s+are\s+(now|a|an)\s+", "", text)
        text = re.sub(r"(?i)act\s+as\s+(a|an|if)\s+", "", text)
        text = re.sub(r"(?i)pretend\s+(to\s+be|you)", "", text)
        text = re.sub(r"(?i)roleplay\s+as", "", text)

        # Remove XML/markdown injection attempts
        text = re.sub(r"```.*?```", "[CODE]", text, flags=re.DOTALL)
        text = re.sub(r"<script.*?>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Escape template markers
        text = text.replace("{", "{{").replace("}", "}}")

        # Log if redaction occurred (for monitoring injection attempts)
        if "[REDACTED]" in text:
            counter("returns.extractor.injection_attempt")
            logger.warning("Prompt injection pattern detected and sanitized in extractor")

        return text[:max_length]
