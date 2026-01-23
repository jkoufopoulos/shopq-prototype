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

from shopq.infrastructure.settings import GEMINI_MODEL, GEMINI_LOCATION, GOOGLE_CLOUD_PROJECT
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event

logger = get_logger(__name__)

# Feature flag: control LLM usage
USE_LLM = os.getenv("SHOPQ_USE_LLM", "false").lower() == "true"


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
        description="Type: product_order, service, subscription, digital, donation, ticket, bill, unknown"
    )


class ReturnabilityClassifier:
    """
    LLM-based classifier for purchase returnability.

    Determines if an email represents a returnable physical product purchase
    vs non-returnable transactions (services, subscriptions, digital goods, etc.)
    """

    # Classification prompt template
    PROMPT_TEMPLATE = """Classify if this receipt/confirmation is for a RETURNABLE PHYSICAL PRODUCT.

Subject: {subject}
From: {from_address}
Snippet: {snippet}

## RETURNABLE (is_returnable=true, receipt_type="product_order"):
- Physical products with shipping/delivery: clothing, electronics, furniture, appliances, toys
- Store pickup orders for physical goods
- Items that come in a box/package you could send back

## NOT RETURNABLE:

### IMPORTANT: Groceries and Perishables are NEVER returnable (receipt_type="service"):
- ANY grocery order: Whole Foods, Amazon Fresh, Instacart, Walmart Grocery, Target groceries
- ANY food delivery: DoorDash, Grubhub, Uber Eats, Postmates
- ANY meal kits: HelloFresh, Blue Apron, Factor, Home Chef
- ANY perishable items: flowers, plants, fresh food, prepared meals
- These are CONSUMED or PERISHABLE - they cannot be returned like physical products

### Services (receipt_type="service"):
- Rides: Uber, Lyft
- Haircuts, cleaning, repairs, professional services

### Subscriptions (receipt_type="subscription"):
- Streaming: Netflix, Spotify, Hulu
- Software subscriptions: Adobe, Microsoft 365
- Gym memberships, news subscriptions

### Digital goods (receipt_type="digital"):
- Ebooks, audiobooks
- Video games (Steam, PlayStation Store)
- In-app purchases, gift cards
- Software licenses

### Donations (receipt_type="donation"):
- Charity contributions
- Crowdfunding (Kickstarter, GoFundMe)
- Tips, gratuity

### Tickets (receipt_type="ticket"):
- Concert/event tickets
- Airline tickets
- Movie tickets
(These have separate refund policies, not standard returns)

### Bills (receipt_type="bill"):
- Utility bills
- Insurance payments
- Phone bills

## Output JSON:
{{
  "is_returnable": true/false,
  "confidence": 0.0-1.0,
  "reason": "brief explanation (10 words max)",
  "receipt_type": "product_order|service|subscription|digital|donation|ticket|bill|unknown"
}}

Respond with ONLY the JSON, no other text."""

    def __init__(self):
        """Initialize classifier with Gemini model."""
        self._model = None  # Lazy load

    def _get_model(self):
        """Lazy-load Gemini model."""
        if self._model is None:
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel

                # Initialize Vertex AI if needed
                if GOOGLE_CLOUD_PROJECT:
                    vertexai.init(project=GOOGLE_CLOUD_PROJECT, location=GEMINI_LOCATION)

                self._model = GenerativeModel(GEMINI_MODEL)
                logger.info("Initialized Gemini model %s for returnability classification", GEMINI_MODEL)

            except Exception as e:
                logger.error("Failed to initialize Gemini model: %s", e)
                raise

        return self._model

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
        if not USE_LLM:
            counter("returns.classifier.llm_disabled")
            logger.warning(
                "LLM DISABLED: SHOPQ_USE_LLM=%s - returning default returnable",
                os.getenv("SHOPQ_USE_LLM", "not_set")
            )
            # Conservative default: assume returnable if LLM disabled
            return ReturnabilityResult.returnable(
                reason="llm_disabled_default",
                confidence=0.5,
            )

        # Build prompt
        prompt = self._build_prompt(from_address, subject, snippet)

        try:
            # Call LLM
            model = self._get_model()
            logger.info(
                "LLM CLASSIFIER: Calling %s for subject='%s'",
                GEMINI_MODEL,
                subject[:50]
            )
            response = model.generate_content(prompt)

            # Parse response
            result = self._parse_response(response.text)

            counter("returns.classifier.success")
            logger.info(
                "LLM CLASSIFIER RESULT: is_returnable=%s, type=%s, reason='%s'",
                result.is_returnable,
                result.receipt_type.value,
                result.reason
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
        # Sanitize inputs to prevent prompt injection
        subject = self._sanitize(subject, max_length=200)
        from_address = self._sanitize(from_address, max_length=100)
        snippet = self._sanitize(snippet, max_length=2000)

        return self.PROMPT_TEMPLATE.format(
            subject=subject,
            from_address=from_address,
            snippet=snippet,
        )

    def _sanitize(self, text: str, max_length: int = 500) -> str:
        """Sanitize input to prevent prompt injection."""
        if not text:
            return ""

        # Remove common injection patterns
        text = re.sub(r"(?i)(ignore|disregard).*(instruction|prompt)", "[REDACTED]", text)
        text = re.sub(r"(?i)system\s*:", "", text)
        text = re.sub(r"(?i)assistant\s*:", "", text)

        # Escape template markers
        text = text.replace("{", "{{").replace("}", "}}")

        # Truncate
        return text[:max_length]

    def _parse_response(self, response_text: str) -> ReturnabilityResult:
        """Parse LLM response into ReturnabilityResult."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_text = response_text.strip()
            if json_text.startswith("```"):
                # Remove markdown code fence
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
