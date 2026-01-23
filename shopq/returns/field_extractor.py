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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shopq.infrastructure.settings import GEMINI_MODEL, GEMINI_LOCATION, GOOGLE_CLOUD_PROJECT
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event
from shopq.returns.models import ReturnConfidence

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
        r"order\s*#?\s*:?\s*([A-Z0-9-]{5,25})",
        r"confirmation\s*#?\s*:?\s*([A-Z0-9-]{5,25})",
        r"order\s+number\s*:?\s*([A-Z0-9-]{5,25})",
        r"#([0-9]{3}-[0-9]{7}-[0-9]{7})",  # Amazon format
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

Subject: {subject}
From: {from_address}
Body:
{body}

Extract these fields:
1. merchant_name: The retailer/store name (e.g., "Amazon", "Target", "Nike")
2. item_summary: Brief description of items (e.g., "Wireless headphones, Phone case")
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
  "order_date": "2024-01-15" or null,
  "delivery_date": "2024-01-20" or null,
  "explicit_return_by": "2024-02-20" or null,
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
        self._model = None

    def _get_model(self):
        """Lazy-load Gemini model."""
        if self._model is None:
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel

                if GOOGLE_CLOUD_PROJECT:
                    vertexai.init(project=GOOGLE_CLOUD_PROJECT, location=GEMINI_LOCATION)

                self._model = GenerativeModel(GEMINI_MODEL)
                logger.info("Initialized Gemini model %s for field extraction", GEMINI_MODEL)

            except Exception as e:
                logger.error("Failed to initialize Gemini model: %s", e)
                raise

        return self._model

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
            response = model.generate_content(
                prompt,
                request_options={"timeout": LLM_TIMEOUT_SECONDS},
            )
            return response.text
        except DeadlineExceeded as e:
            counter("returns.extractor.timeout")
            logger.warning("LLM call timed out after %ds", LLM_TIMEOUT_SECONDS)
            raise TimeoutError(f"LLM call timed out: {e}") from e
        except ServiceUnavailable as e:
            counter("returns.extractor.service_unavailable")
            logger.warning("LLM service unavailable, will retry: %s", e)
            raise ConnectionError(f"LLM service unavailable: {e}") from e

    def extract(
        self,
        from_address: str,
        subject: str,
        body: str,
        merchant_domain: str,
    ) -> ExtractedFields:
        """
        Extract all fields from a purchase email.

        Args:
            from_address: Email sender
            subject: Email subject
            body: Email body text
            merchant_domain: Sender domain (for merchant rule lookup)

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
                llm_fields = self._extract_with_llm(from_address, subject, body)
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
        )

        # Build evidence snippet - prefer return policy quote, fallback to body preview
        evidence = return_policy_quote if return_policy_quote else (body[:200] if body else None)

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
            order_number=rules_fields.get("order_number") or llm_fields.get("order_number"),
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
            match = re.search(pattern, text, re.IGNORECASE)
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

    def _extract_with_llm(self, from_address: str, subject: str, body: str) -> dict:
        """Extract fields using LLM."""
        # Truncate body for prompt - use 4000 chars to capture return policies at bottom
        body_truncated = body[:4000] if body else ""

        # LOG: What we're sending to LLM (for validation)
        logger.info(
            "LLM extraction input: subject=%s, body_length=%d, truncated_length=%d",
            subject[:50],
            len(body) if body else 0,
            len(body_truncated),
        )
        if body_truncated:
            logger.debug(
                "LLM input body tail (last 300 chars): %s",
                body_truncated[-300:] if len(body_truncated) > 300 else body_truncated,
            )

        prompt = self.EXTRACTION_PROMPT.format(
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
        if result.get("return_policy_quote"):
            logger.debug("LLM extracted quote: %s", result.get("return_policy_quote")[:200])

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

    def _compute_return_by_date(
        self,
        explicit_return_by: datetime | None,
        order_date: datetime | None,
        delivery_date: datetime | None,
        merchant_domain: str,
        return_window_days: int | None = None,
    ) -> tuple[datetime | None, ReturnConfidence]:
        """
        Compute return_by_date using PRD priority logic.

        Priority:
        1. EXACT: Explicit return-by date found in email
        2. ESTIMATED (email): Return window days from email + anchor date
        3. ESTIMATED (merchant): Merchant rule window + anchor date
        4. UNKNOWN: No date info
        """
        # P1: Explicit return-by date from email
        if explicit_return_by:
            return explicit_return_by, ReturnConfidence.EXACT

        # P2: Return window from email (with quote evidence)
        if return_window_days and return_window_days > 0:
            anchor = delivery_date or order_date
            if anchor:
                return_by = anchor + timedelta(days=return_window_days)
                return return_by, ReturnConfidence.ESTIMATED

        # P3: Use merchant rules as fallback
        merchants = self.merchant_rules.get("merchants", {})
        rule = merchants.get(merchant_domain) or merchants.get("_default")

        if rule:
            days = rule.get("days", 30)
            anchor_type = rule.get("anchor", "delivery")

            # Get anchor date
            anchor = delivery_date if anchor_type == "delivery" else order_date
            if anchor is None:
                anchor = order_date  # Fallback to order date

            if anchor:
                return_by = anchor + timedelta(days=days)
                return return_by, ReturnConfidence.ESTIMATED

        # P4: Unknown
        return None, ReturnConfidence.UNKNOWN

    def _guess_merchant(self, from_address: str, subject: str) -> str:
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
        """Sanitize input for LLM prompt."""
        if not text:
            return ""

        text = re.sub(r"(?i)(ignore|disregard).*(instruction|prompt)", "[REDACTED]", text)
        text = text.replace("{", "{{").replace("}", "}}")
        return text[:max_length]
