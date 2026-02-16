"""
Returnability Classifier - LLM-based classification for returnable purchases.

Stage 2 of the extraction pipeline. Uses Gemini to determine if an email
represents a returnable physical product purchase vs services/digital/subscriptions.

Cost: ~$0.0001 per email (Gemini Flash, small prompt)
Expected rejection rate: 60-70% of candidates
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

from reclaim.infrastructure.settings import GEMINI_MODEL
from reclaim.observability.logging import get_logger
from reclaim.observability.telemetry import counter, log_event
from reclaim.utils.redaction import redact_subject

logger = get_logger(__name__)


def _use_llm() -> bool:
    """Check LLM feature flag at call time (not import time).

    Reads env var fresh to avoid stale cache when dotenv loads after module import.
    """
    return os.getenv("RECLAIM_USE_LLM", os.getenv("SHOPQ_USE_LLM", "false")).lower() == "true"


class ReceiptType(str, Enum):
    """Type of receipt/transaction."""

    PRODUCT_ORDER = "product_order"  # Physical goods (returnable)
    SERVICE = "service"  # Rides, food delivery, haircuts
    SUBSCRIPTION = "subscription"  # Netflix, Spotify, memberships
    DIGITAL = "digital"  # Games, ebooks, software licenses
    DONATION = "donation"  # Charity, tips, crowdfunding
    TICKET = "ticket"  # Events, flights (different refund rules)
    BILL = "bill"  # Utilities, insurance
    UNKNOWN = "unknown"  # Can't determine


@dataclass
class ReturnabilityResult:
    """Result of returnability classification."""

    is_returnable: bool
    confidence: float  # 0.0-1.0
    reason: str  # Brief explanation
    receipt_type: ReceiptType

    @classmethod
    def not_returnable(cls, reason: str, receipt_type: ReceiptType) -> ReturnabilityResult:
        """Factory for non-returnable result."""
        return cls(
            is_returnable=False,
            confidence=0.9,
            reason=reason,
            receipt_type=receipt_type,
        )

    @classmethod
    def returnable(cls, reason: str, confidence: float = 0.85) -> ReturnabilityResult:
        """Factory for returnable result."""
        return cls(
            is_returnable=True,
            confidence=confidence,
            reason=reason,
            receipt_type=ReceiptType.PRODUCT_ORDER,
        )


class ReturnabilitySchema(BaseModel):
    """Schema for LLM response validation."""

    is_returnable: bool = Field(description="True if physical product that can be returned")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in classification")
    reason: str = Field(description="Brief explanation of classification")
    receipt_type: str = Field(
        description=(
            "Type: product_order, service, subscription, digital, donation, ticket, bill, unknown"
        )
    )


# Gemini structured output schema — reason comes first to encourage
# chain-of-thought reasoning before the classification decision.
CLASSIFIER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {
            "type": "string",
            "description": "Brief explanation of classification (10 words max). Write this first.",
        },
        "is_returnable": {
            "type": "boolean",
            "description": "true if this is a returnable physical product, false otherwise",
        },
        "confidence": {
            "type": "number",
            "description": "Classification confidence from 0.0 (uncertain) to 1.0 (certain)",
        },
        "receipt_type": {
            "type": "string",
            "description": "Category of transaction",
            "enum": [
                "product_order",
                "service",
                "subscription",
                "digital",
                "donation",
                "ticket",
                "bill",
                "unknown",
            ],
        },
    },
    "required": ["reason", "is_returnable", "confidence", "receipt_type"],
    "propertyOrdering": ["reason", "is_returnable", "confidence", "receipt_type"],
}


# System instruction — cached by Gemini, reduces per-call latency.
CLASSIFIER_SYSTEM_INSTRUCTION = """You classify email receipts and confirmations.

Your task: determine whether an email represents a RETURNABLE PHYSICAL PRODUCT purchase.

## RETURNABLE (is_returnable=true, receipt_type="product_order")
Physical products with shipping or delivery: clothing, electronics, furniture, appliances, toys, accessories. Store pickup orders for physical goods. Items that come in a box or package you could send back.

## NOT RETURNABLE

Groceries and perishables (receipt_type="service"):
- Grocery orders from any retailer: Whole Foods, Amazon Fresh, Instacart, Walmart Grocery, Target groceries
- Food delivery: DoorDash, Grubhub, Uber Eats, Postmates
- Meal kits: HelloFresh, Blue Apron, Factor, Home Chef
- Perishable items: flowers, plants, fresh food, prepared meals
- Consumable health/nutrition products: protein shakes, protein bars, supplements, vitamins — these are perishable even when shipped by retailers like Amazon

Cancelled or refunded orders (receipt_type="service"):
- Emails containing "cancelled", "cancellation", or "item cancelled" — nothing to return
- Pre-orders cancelled before shipping
- Refund confirmations for cancelled items

Return processing emails (receipt_type="service"):
- "Your return is approved", "return has been processed"
- Emails from return services: Happy Returns, Returnly, Loop
- Refund confirmations — outgoing, not incoming products

Warranty and protection plans (receipt_type="service"):
- Extended warranties: Asurion, Allstate, SquareTrade
- Protection plans, care plans, insurance add-ons — service contracts, not physical products

Services (receipt_type="service"):
- Rides: Uber, Lyft
- Haircuts, cleaning, repairs, professional services

Subscriptions (receipt_type="subscription"):
- Streaming: Netflix, Spotify, Hulu
- Software subscriptions: Adobe, Microsoft 365
- Gym memberships, news subscriptions

Digital goods (receipt_type="digital"):
- Ebooks, audiobooks, video games (Steam, PlayStation Store)
- In-app purchases, gift cards, software licenses

Donations (receipt_type="donation"):
- Charity contributions, crowdfunding (Kickstarter, GoFundMe), tips

Tickets (receipt_type="ticket"):
- Concert/event tickets, airline tickets, movie tickets (separate refund policies)

Bills (receipt_type="bill"):
- Utility bills, insurance payments, phone bills

## Few-shot examples

Email:
Subject: Your Amazon.com order of Bose QuietComfort 45 Headphones
From: auto-confirm@amazon.com
Snippet: Your order has been placed. Estimated delivery: Jan 15. Order #112-3456789-0123456.

Classification:
{"reason": "Physical electronics product with shipping", "is_returnable": true, "confidence": 0.95, "receipt_type": "product_order"}

Email:
Subject: Your Amazon Fresh order has been delivered
From: no-reply@amazon.com
Snippet: Your grocery delivery is at your door. Bananas, milk, chicken breast, and 5 other items.

Classification:
{"reason": "Grocery delivery is perishable", "is_returnable": false, "confidence": 0.95, "receipt_type": "service"}

Email:
Subject: Your Spotify Premium receipt
From: no-reply@spotify.com
Snippet: Thanks for your payment. Your monthly Spotify Premium subscription renewed for $10.99.

Classification:
{"reason": "Streaming music subscription renewal", "is_returnable": false, "confidence": 0.95, "receipt_type": "subscription"}

Email:
Subject: Your order has been cancelled
From: auto-confirm@amazon.com
Snippet: We've cancelled your order #112-9862455-9195428 as requested. A refund of $45.99 will be issued.

Classification:
{"reason": "Cancelled order, nothing to return", "is_returnable": false, "confidence": 0.95, "receipt_type": "service"}

Email:
Subject: Your Allstate Protection Plan
From: noreply@squaretrade.com
Snippet: Thank you for purchasing the 3-Year Protection Plan for your laptop. Your plan ID is SQ-88291.

Classification:
{"reason": "Protection plan is a service contract", "is_returnable": false, "confidence": 0.95, "receipt_type": "service"}

## Output format
Write the reason field first — explain your reasoning before giving the classification."""


class ReturnabilityClassifier:
    """
    LLM-based classifier for purchase returnability.

    Determines if an email represents a returnable physical product purchase
    vs non-returnable transactions (services, subscriptions, digital goods, etc.)
    """

    # User message template — only the per-email data
    PROMPT_TEMPLATE = """Subject: {subject}
From: {from_address}
Snippet: {snippet}"""

    def __init__(self):
        """Initialize classifier with Gemini model."""
        # CODE-011: Model is now obtained from shared singleton
        pass

    def _call_llm_with_retry(
        self,
        prompt: str,
        system_instruction: str | None = None,
        response_schema: dict | None = None,
    ) -> str:
        """Call LLM with retry logic and timeout.

        CODE-003: Delegates to shared call_llm() with classifier-specific counter prefix.
        """
        from reclaim.llm.retry import call_llm

        return call_llm(
            prompt,
            counter_prefix="classifier",
            system_instruction=system_instruction,
            response_schema=response_schema,
        )

    def classify(
        self,
        from_address: str,
        subject: str,
        snippet: str,
    ) -> ReturnabilityResult:
        """
        Classify if email represents a returnable purchase.

        Args:
            from_address: Email sender
            subject: Email subject line
            snippet: Email body preview (first ~2000 chars)

        Returns:
            ReturnabilityResult with is_returnable and receipt_type

        Side Effects:
            - Calls Gemini API (~$0.0001 per call)
            - Logs classification events
            - Increments telemetry counters
        """
        # Check feature flag
        if not _use_llm():
            counter("returns.classifier.llm_disabled")
            logger.warning(
                "LLM DISABLED: RECLAIM_USE_LLM=%s - returning default returnable",
                os.getenv("RECLAIM_USE_LLM", os.getenv("SHOPQ_USE_LLM", "not_set")),
            )
            # Conservative default: assume returnable if LLM disabled
            return ReturnabilityResult.returnable(
                reason="llm_disabled_default",
                confidence=0.5,
            )

        # Build prompt
        prompt = self._build_prompt(from_address, subject, snippet)

        try:
            # Call LLM with retry and timeout (CODE-003, CODE-004)
            # SEC-016: Redact PII from logging
            logger.info(
                "LLM CLASSIFIER: Calling %s for subject='%s'", GEMINI_MODEL, redact_subject(subject)
            )
            response_text = self._call_llm_with_retry(
                prompt,
                system_instruction=CLASSIFIER_SYSTEM_INSTRUCTION,
                response_schema=CLASSIFIER_RESPONSE_SCHEMA,
            )

            # Parse response
            result = self._parse_response(response_text)

            counter("returns.classifier.success")
            logger.info(
                "LLM CLASSIFIER RESULT: is_returnable=%s, type=%s, reason='%s'",
                result.is_returnable,
                result.receipt_type.value,
                result.reason,
            )
            log_event(
                "returns.classifier.result",
                is_returnable=result.is_returnable,
                receipt_type=result.receipt_type.value,
                confidence=result.confidence,
                model=GEMINI_MODEL,
            )

            return result

        except Exception as e:
            counter("returns.classifier.error")
            logger.error("LLM CLASSIFIER ERROR: %s (model=%s)", e, GEMINI_MODEL)
            log_event("returns.classifier.error", error=str(e), model=GEMINI_MODEL)

            # REJECT on LLM failure - don't let unclassified emails through
            # This prevents garbage from polluting the list when LLM is broken
            return ReturnabilityResult.not_returnable(
                reason=f"llm_error_reject: {str(e)[:50]}",
                receipt_type=ReceiptType.UNKNOWN,
            )

    def _build_prompt(self, from_address: str, subject: str, snippet: str) -> str:
        """Build classification prompt with sanitized inputs."""
        from reclaim.utils.redaction import redact_pii

        # Sanitize inputs to prevent prompt injection
        subject = self._sanitize(subject, max_length=200)
        from_address = self._sanitize(from_address, max_length=100)
        snippet = self._sanitize(snippet, max_length=2000)

        # Privacy: Redact PII from snippet before sending to Gemini
        snippet = redact_pii(snippet, max_length=2000)

        return self.PROMPT_TEMPLATE.format(
            subject=subject,
            from_address=from_address,
            snippet=snippet,
        )

    def _sanitize(self, text: str, max_length: int = 500) -> str:
        """Sanitize input to prevent prompt injection.

        CODE-007: Delegates to shared sanitize_llm_input().
        """
        from reclaim.utils.redaction import sanitize_llm_input

        return sanitize_llm_input(text, max_length=max_length, counter_prefix="classifier")

    def _parse_response(self, response_text: str) -> ReturnabilityResult:
        """Parse LLM response into ReturnabilityResult."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_text = response_text.strip()
            if json_text.startswith("```"):
                # Remove markdown code fence — should not trigger with response_schema
                counter("returns.classifier.code_fence_fallback")
                logger.warning("Classifier response contained code fences (unexpected with schema)")
                json_text = re.sub(r"^```(?:json)?\n?", "", json_text)
                json_text = re.sub(r"\n?```$", "", json_text)

            data = json.loads(json_text)

            # Validate with Pydantic
            validated = ReturnabilitySchema.model_validate(data)

            # Convert to result
            receipt_type = ReceiptType(validated.receipt_type)

            return ReturnabilityResult(
                is_returnable=validated.is_returnable,
                confidence=validated.confidence,
                reason=validated.reason,
                receipt_type=receipt_type,
            )

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse returnability response: %s", e)
            counter("returns.classifier.parse_error")

            # Fallback: try to extract boolean from text
            text_lower = response_text.lower()
            if "not returnable" in text_lower or 'is_returnable": false' in text_lower:
                return ReturnabilityResult.not_returnable(
                    reason="parsed_from_text",
                    receipt_type=ReceiptType.UNKNOWN,
                )

            # Conservative default
            return ReturnabilityResult.returnable(
                reason="parse_error_fallback",
                confidence=0.3,
            )


def classify_returnability_sync(
    from_address: str,
    subject: str,
    snippet: str,
) -> ReturnabilityResult:
    """
    Convenience function for synchronous classification.

    Creates a new classifier instance per call. For batch processing,
    prefer creating a single ReturnabilityClassifier instance.
    """
    classifier = ReturnabilityClassifier()
    return classifier.classify(from_address, subject, snippet)
