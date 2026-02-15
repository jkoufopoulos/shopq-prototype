"""Stateless extraction endpoint for Reclaim API.

Runs emails through the 3-stage pipeline (filter -> classifier -> extractor)
and returns structured JSON. No database writes, no user data stored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from reclaim.api.middleware.user_auth import AuthenticatedUser, get_current_user
from reclaim.config import API_BATCH_SIZE_MAX
from reclaim.observability.logging import get_logger
from reclaim.returns.types import ExtractionStage
from reclaim.utils.validators import validate_email_id

router = APIRouter(prefix="/api", tags=["extract"])
logger = get_logger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================


class ExtractEmail(BaseModel):
    """A single email in an extraction request."""

    email_id: str
    from_address: str
    subject: str
    body: str
    body_html: str | None = None
    received_at: str | None = None  # ISO format

    @field_validator("email_id")
    @classmethod
    def validate_email(cls, v: str) -> str:
        validated = validate_email_id(v)
        if not validated:
            raise ValueError("Invalid email_id")
        return validated


class ExtractRequest(BaseModel):
    """Request to extract return info from emails (stateless)."""

    emails: list[ExtractEmail] = Field(..., max_length=API_BATCH_SIZE_MAX)


class ExtractedCard(BaseModel):
    """A single extracted return card (no persistence)."""

    id: str
    merchant: str
    merchant_domain: str
    item_summary: str
    status: str
    confidence: str
    source_email_ids: list[str]
    order_number: str | None = None
    amount: float | None = None
    currency: str = "USD"
    order_date: str | None = None
    delivery_date: str | None = None
    return_by_date: str | None = None
    return_portal_link: str | None = None
    shipping_tracking_link: str | None = None
    evidence_snippet: str | None = None
    days_remaining: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ExtractResultItem(BaseModel):
    """Result for a single email in the batch."""

    email_id: str
    success: bool
    card: ExtractedCard | None = None
    rejection_reason: str | None = None
    stage_reached: str | None = None


class ExtractStats(BaseModel):
    """Statistics from batch extraction."""

    total: int
    rejected_filter: int
    rejected_classifier: int
    rejected_empty: int
    cards_extracted: int


class ExtractResponse(BaseModel):
    """Response from stateless batch extraction."""

    results: list[ExtractResultItem]
    stats: ExtractStats


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/extract", response_model=ExtractResponse)
async def extract_emails(
    request: ExtractRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ExtractResponse:
    """
    Extract return card data from a batch of emails (stateless).

    Runs all emails through the 3-stage pipeline (filter -> classifier -> extractor),
    deduplicates across the batch, and returns structured JSON. No data is persisted.
    Email content is processed and immediately discarded.

    Max 500 emails per batch.
    """
    from reclaim.returns import ReturnableReceiptExtractor

    try:
        user_id = user.id

        # Convert request emails to the dict format process_email_batch() expects
        emails = [
            {
                "id": email.email_id,
                "from": email.from_address,
                "subject": email.subject,
                "body": email.body,
                "body_html": email.body_html,
                "received_at": datetime.fromisoformat(email.received_at)
                if email.received_at
                else None,
            }
            for email in request.emails
        ]

        logger.info("Extracting batch of %d emails for user %s", len(emails), user_id)

        extractor = ReturnableReceiptExtractor()
        results = extractor.process_email_batch(user_id, emails)

        # Build response
        stats = ExtractStats(
            total=len(request.emails),
            rejected_filter=0,
            rejected_classifier=0,
            rejected_empty=0,
            cards_extracted=0,
        )

        result_items: list[ExtractResultItem] = []

        # Map results back to email IDs
        email_id_list = [e.email_id for e in request.emails]

        for result_idx, result in enumerate(results):
            if not result.success or not result.card:
                # Count rejection reasons
                if result.stage_reached == ExtractionStage.FILTER:
                    stats.rejected_filter += 1
                elif result.stage_reached == ExtractionStage.CLASSIFIER:
                    stats.rejected_classifier += 1
                else:
                    stats.rejected_empty += 1

                # Find the email_id for this result
                email_id = ""
                if result.card and result.card.source_email_ids:
                    email_id = result.card.source_email_ids[0]
                elif result_idx < len(email_id_list):
                    email_id = email_id_list[result_idx]

                result_items.append(
                    ExtractResultItem(
                        email_id=email_id,
                        success=False,
                        rejection_reason=result.rejection_reason,
                        stage_reached=result.stage_reached.value if result.stage_reached else None,
                    )
                )
            else:
                card = result.card
                card.user_id = user_id
                stats.cards_extracted += 1

                result_items.append(
                    ExtractResultItem(
                        email_id=card.source_email_ids[0] if card.source_email_ids else "",
                        success=True,
                        card=ExtractedCard(
                            id=card.id,
                            merchant=card.merchant,
                            merchant_domain=card.merchant_domain,
                            item_summary=card.item_summary,
                            status=card.status
                            if isinstance(card.status, str)
                            else card.status.value,
                            confidence=card.confidence
                            if isinstance(card.confidence, str)
                            else card.confidence.value,
                            source_email_ids=card.source_email_ids,
                            order_number=card.order_number,
                            amount=card.amount,
                            currency=card.currency,
                            order_date=card.order_date.isoformat() if card.order_date else None,
                            delivery_date=card.delivery_date.isoformat()
                            if card.delivery_date
                            else None,
                            return_by_date=card.return_by_date.isoformat()
                            if card.return_by_date
                            else None,
                            return_portal_link=card.return_portal_link,
                            shipping_tracking_link=card.shipping_tracking_link,
                            evidence_snippet=card.evidence_snippet,
                            days_remaining=card.days_until_expiry(),
                            created_at=card.created_at.isoformat() if card.created_at else None,
                            updated_at=card.updated_at.isoformat() if card.updated_at else None,
                        ),
                        stage_reached="extractor",
                    )
                )

        logger.info(
            "Extraction complete: %d emails -> %d cards extracted",
            len(request.emails),
            stats.cards_extracted,
        )

        return ExtractResponse(results=result_items, stats=stats)

    except Exception as e:
        logger.error("Failed to extract email batch: %s", e)
        raise HTTPException(status_code=500, detail="Failed to extract email batch") from None


# ============================================================================
# Policy Extraction (On-demand)
# ============================================================================


class ExtractPolicyRequest(BaseModel):
    """Request for on-demand return policy extraction."""

    context: str = Field(..., max_length=2000)
    merchant: str = Field(..., max_length=200)


class ExtractPolicyResponse(BaseModel):
    """Response from policy extraction."""

    return_by_date: str | None = None
    return_window_days: int | None = None
    evidence_quote: str | None = None
    confidence: str = "low"


@router.post("/extract-policy", response_model=ExtractPolicyResponse)
async def extract_policy(
    request: ExtractPolicyRequest,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: ARG001
) -> ExtractPolicyResponse:
    """
    Extract return policy from email context (stateless).

    Used for on-demand enrichment when user views order details.
    """
    from reclaim.llm.retry import call_llm
    from reclaim.utils.redaction import redact_pii, sanitize_llm_input

    try:
        # Sanitize input
        context = sanitize_llm_input(request.context, max_length=2000, counter_prefix="policy")
        # Redact PII before sending to LLM
        context = redact_pii(context, max_length=2000)
        merchant = sanitize_llm_input(request.merchant, max_length=200, counter_prefix="policy")

        prompt = f"""Extract the return policy from this email excerpt for {merchant}.

Email excerpt:
{context}

Output JSON:
{{
  "return_by_date": "YYYY-MM-DD or null (only if explicit date mentioned)",
  "return_window_days": "number or null (e.g., 30 for '30-day returns')",
  "evidence_quote": "exact text from email about return policy or null",
  "confidence": "high/medium/low"
}}

Respond with ONLY the JSON."""

        import json
        import os
        import re

        if os.getenv("RECLAIM_USE_LLM", os.getenv("SHOPQ_USE_LLM", "false")).lower() != "true":
            return ExtractPolicyResponse()

        response_text = call_llm(prompt, counter_prefix="policy")

        # Parse JSON response
        json_text = response_text.strip()
        if json_text.startswith("```"):
            json_text = re.sub(r"^```(?:json)?\n?", "", json_text)
            json_text = re.sub(r"\n?```$", "", json_text)

        data = json.loads(json_text)

        return ExtractPolicyResponse(
            return_by_date=data.get("return_by_date"),
            return_window_days=data.get("return_window_days"),
            evidence_quote=redact_pii(data.get("evidence_quote"), max_length=200)
            if data.get("evidence_quote")
            else None,
            confidence=data.get("confidence", "low"),
        )

    except Exception as e:
        logger.error("Failed to extract policy: %s", e)
        return ExtractPolicyResponse()


# ============================================================================
# Merchant Rules (Static JSON)
# ============================================================================


@router.get("/config/merchant-rules")
async def get_merchant_rules() -> dict[str, Any]:
    """
    Serve merchant return rules as JSON.

    Cacheable, no auth required. Extension polls on startup
    and falls back to bundled defaults.
    """
    from pathlib import Path

    import yaml

    rules_path = Path(__file__).parent.parent.parent.parent / "config" / "merchant_rules.yaml"

    if not rules_path.exists():
        return {"merchants": {}, "version": "1.0"}

    with open(rules_path) as f:
        return yaml.safe_load(f)
