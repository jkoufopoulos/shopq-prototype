"""
Returns API endpoints for Return Watch feature.

Provides CRUD operations for return cards and status management.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from shopq.api.middleware.user_auth import AuthenticatedUser, get_current_user
from shopq.config import (
    API_BATCH_SIZE_MAX,
    API_EXPIRING_THRESHOLD_DAYS,
    API_LIST_LIMIT_DEFAULT,
    API_LIST_LIMIT_MAX,
)
from shopq.observability.logging import get_logger
from shopq.returns import (
    ExtractionStage,
    ReturnCard,
    ReturnCardCreate,
    ReturnCardRepository,
    ReturnCardUpdate,
    ReturnConfidence,
    ReturnStatus,
)
from shopq.utils.error_sanitizer import sanitize_error_message
from shopq.utils.validators import (
    validate_email_id,
    validate_merchant_domain,
    validate_order_number,
)

router = APIRouter(prefix="/api/returns", tags=["returns"])
logger = get_logger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================


class ReturnCardResponse(BaseModel):
    """API response for a single return card."""

    id: str
    user_id: str
    merchant: str
    merchant_domain: str
    item_summary: str
    status: str
    confidence: str
    source_email_ids: list[str]
    order_number: str | None
    amount: float | None
    currency: str
    order_date: str | None
    delivery_date: str | None
    return_by_date: str | None
    return_portal_link: str | None
    shipping_tracking_link: str | None
    evidence_snippet: str | None
    notes: str | None
    days_remaining: int | None
    created_at: str
    updated_at: str

    @classmethod
    def from_card(cls, card: ReturnCard) -> ReturnCardResponse:
        """Convert ReturnCard to API response."""
        return cls(
            id=card.id,
            user_id=card.user_id,
            merchant=card.merchant,
            merchant_domain=card.merchant_domain,
            item_summary=card.item_summary,
            status=card.status if isinstance(card.status, str) else card.status.value,
            confidence=card.confidence
            if isinstance(card.confidence, str)
            else card.confidence.value,
            source_email_ids=card.source_email_ids,
            order_number=card.order_number,
            amount=card.amount,
            currency=card.currency,
            order_date=card.order_date.isoformat() if card.order_date else None,
            delivery_date=card.delivery_date.isoformat() if card.delivery_date else None,
            return_by_date=card.return_by_date.isoformat() if card.return_by_date else None,
            return_portal_link=card.return_portal_link,
            shipping_tracking_link=card.shipping_tracking_link,
            evidence_snippet=card.evidence_snippet,
            notes=card.notes,
            days_remaining=card.days_until_expiry(),
            created_at=card.created_at.isoformat(),
            updated_at=card.updated_at.isoformat(),
        )


class ReturnCardListResponse(BaseModel):
    """API response for listing return cards."""

    cards: list[ReturnCardResponse]
    total: int
    expiring_soon_count: int


class CreateReturnCardRequest(BaseModel):
    """Request to create a new return card."""

    merchant: str
    merchant_domain: str = ""
    item_summary: str
    confidence: str = "unknown"
    source_email_ids: list[str] = Field(default_factory=list)
    order_number: str | None = None
    amount: float | None = None
    currency: str = "USD"
    order_date: str | None = None
    delivery_date: str | None = None
    return_by_date: str | None = None
    return_portal_link: str | None = None
    shipping_tracking_link: str | None = None
    evidence_snippet: str | None = None

    # SEC-012: Input validation
    @field_validator("merchant_domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if not v:
            return ""
        validated = validate_merchant_domain(v)
        return validated or ""

    @field_validator("order_number")
    @classmethod
    def validate_order(cls, v: str | None) -> str | None:
        return validate_order_number(v)

    @field_validator("source_email_ids")
    @classmethod
    def validate_email_ids(cls, v: list[str]) -> list[str]:
        return [validated for eid in v if (validated := validate_email_id(eid)) is not None]


class UpdateStatusRequest(BaseModel):
    """Request to update a card's status."""

    status: str  # returned | dismissed


class UpdateCardRequest(BaseModel):
    """Request to update card fields."""

    status: str | None = None
    notes: str | None = None
    return_by_date: str | None = None
    return_portal_link: str | None = None


class StatusCountsResponse(BaseModel):
    """Response with card counts by status."""

    active: int = 0
    expiring_soon: int = 0
    expired: int = 0
    returned: int = 0
    dismissed: int = 0
    total: int = 0


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=ReturnCardListResponse)
async def list_returns(
    user: AuthenticatedUser = Depends(get_current_user),
    status: str | None = Query(
        None,
        description="Comma-separated statuses: active,expiring_soon,expired,returned,dismissed",
    ),
    limit: int = Query(API_LIST_LIMIT_DEFAULT, ge=1, le=API_LIST_LIMIT_MAX),
    offset: int = Query(0, ge=0),
) -> ReturnCardListResponse:
    """
    List return cards for the authenticated user.

    Filters by status if provided. Returns cards ordered by return_by_date (soonest first).
    """
    try:
        user_id = user.id
        # Refresh statuses first (update expired/expiring_soon based on current date)
        ReturnCardRepository.refresh_statuses(user_id)

        # Parse status filter
        status_filter: list[ReturnStatus] | None = None
        if status:
            status_filter = [ReturnStatus(s.strip()) for s in status.split(",")]

        cards = ReturnCardRepository.list_by_user(
            user_id=user_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )

        # CODE-006: Get true total count for pagination (not just len of current page)
        total_count = ReturnCardRepository.count_by_user(user_id, status_filter)

        # Get expiring soon count
        expiring = ReturnCardRepository.list_expiring_soon(user_id)

        return ReturnCardListResponse(
            cards=[ReturnCardResponse.from_card(c) for c in cards],
            total=total_count,
            expiring_soon_count=len(expiring),
        )

    except ValueError as e:
        # SEC-011: Sanitize error messages
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(e), 400)) from None
    except Exception as e:
        logger.error("Failed to list returns: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list returns") from None


@router.get("/expiring", response_model=list[ReturnCardResponse])
async def list_expiring_returns(
    user: AuthenticatedUser = Depends(get_current_user),
    threshold_days: int = Query(API_EXPIRING_THRESHOLD_DAYS, ge=1, le=30, description="Days to look ahead"),
) -> list[ReturnCardResponse]:
    """
    Get returns expiring within threshold days for the authenticated user.

    Returns cards with return_by_date within threshold, ordered by urgency.
    """
    try:
        user_id = user.id
        # Refresh statuses first
        ReturnCardRepository.refresh_statuses(user_id, threshold_days)

        cards = ReturnCardRepository.list_expiring_soon(user_id, threshold_days)
        return [ReturnCardResponse.from_card(c) for c in cards]

    except Exception as e:
        logger.error("Failed to list expiring returns: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list expiring returns") from None


@router.get("/counts", response_model=StatusCountsResponse)
async def get_status_counts(
    user: AuthenticatedUser = Depends(get_current_user),
) -> StatusCountsResponse:
    """
    Get count of cards by status for the authenticated user.

    Useful for dashboard summary and badge counts.
    """
    try:
        user_id = user.id
        # Refresh statuses first
        ReturnCardRepository.refresh_statuses(user_id)

        counts = ReturnCardRepository.count_by_status(user_id)

        return StatusCountsResponse(
            active=counts.get("active", 0),
            expiring_soon=counts.get("expiring_soon", 0),
            expired=counts.get("expired", 0),
            returned=counts.get("returned", 0),
            dismissed=counts.get("dismissed", 0),
            total=sum(counts.values()),
        )

    except Exception as e:
        logger.error("Failed to get status counts: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get status counts") from None


@router.get("/{card_id}", response_model=ReturnCardResponse)
async def get_return(
    card_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReturnCardResponse:
    """
    Get a single return card by ID.

    Only returns cards owned by the authenticated user.
    """
    card = ReturnCardRepository.get_by_id(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Return card not found")

    # Verify ownership
    if card.user_id != user.id:
        raise HTTPException(status_code=404, detail="Return card not found")

    return ReturnCardResponse.from_card(card)


@router.post("", response_model=ReturnCardResponse, status_code=201)
async def create_return(
    request: CreateReturnCardRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReturnCardResponse:
    """
    Create a new return card for the authenticated user.

    Called by the extractor when processing emails.
    """
    try:
        # Parse dates if provided
        order_date = datetime.fromisoformat(request.order_date) if request.order_date else None
        delivery_date = (
            datetime.fromisoformat(request.delivery_date) if request.delivery_date else None
        )
        return_by_date = (
            datetime.fromisoformat(request.return_by_date) if request.return_by_date else None
        )

        card_create = ReturnCardCreate(
            user_id=user.id,
            merchant=request.merchant,
            merchant_domain=request.merchant_domain,
            item_summary=request.item_summary,
            confidence=ReturnConfidence(request.confidence),
            source_email_ids=request.source_email_ids,
            order_number=request.order_number,
            amount=request.amount,
            currency=request.currency,
            order_date=order_date,
            delivery_date=delivery_date,
            return_by_date=return_by_date,
            return_portal_link=request.return_portal_link,
            shipping_tracking_link=request.shipping_tracking_link,
            evidence_snippet=request.evidence_snippet,
        )

        card = ReturnCardRepository.create(card_create)
        logger.info("Created return card %s for merchant %s", card.id, card.merchant)

        return ReturnCardResponse.from_card(card)

    except ValueError as e:
        # SEC-011: Sanitize error messages
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(e), 400)) from None
    except Exception as e:
        logger.error("Failed to create return card: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create return card") from None


@router.put("/{card_id}/status", response_model=ReturnCardResponse)
async def update_return_status(
    card_id: str,
    request: UpdateStatusRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReturnCardResponse:
    """
    Update a card's status (mark returned or dismissed).

    This is the primary user action - marking items as returned or dismissing them.
    Only the card owner can update status.
    """
    try:
        # Verify ownership first
        existing_card = ReturnCardRepository.get_by_id(card_id)
        if not existing_card or existing_card.user_id != user.id:
            raise HTTPException(status_code=404, detail="Return card not found")

        new_status = ReturnStatus(request.status)

        # Only allow user-initiated status changes
        if new_status not in (ReturnStatus.RETURNED, ReturnStatus.DISMISSED):
            raise HTTPException(
                status_code=400,
                detail="Status must be 'returned' or 'dismissed'",
            )

        card = ReturnCardRepository.update_status(card_id, new_status)
        if not card:
            raise HTTPException(status_code=404, detail="Return card not found")

        logger.info("Updated card %s status to %s", card_id, new_status.value)
        return ReturnCardResponse.from_card(card)

    except ValueError as e:
        # SEC-011: Sanitize error messages
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(e), 400)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update return status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update status") from None


@router.patch("/{card_id}", response_model=ReturnCardResponse)
async def update_return(
    card_id: str,
    request: UpdateCardRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReturnCardResponse:
    """
    Update a card's fields (notes, return_by_date, etc.)

    Only the card owner can update fields.
    """
    try:
        # Verify ownership first
        existing_card = ReturnCardRepository.get_by_id(card_id)
        if not existing_card or existing_card.user_id != user.id:
            raise HTTPException(status_code=404, detail="Return card not found")

        updates = ReturnCardUpdate(
            status=ReturnStatus(request.status) if request.status else None,
            notes=request.notes,
            return_by_date=datetime.fromisoformat(request.return_by_date)
            if request.return_by_date
            else None,
            return_portal_link=request.return_portal_link,
        )

        card = ReturnCardRepository.update(card_id, updates)
        if not card:
            raise HTTPException(status_code=404, detail="Return card not found")

        return ReturnCardResponse.from_card(card)

    except ValueError as e:
        # SEC-011: Sanitize error messages
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(e), 400)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update return card: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update card") from None


@router.delete("/{card_id}")
async def delete_return(
    card_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    """
    Delete a return card.

    Use sparingly - prefer marking as dismissed instead.
    Only the card owner can delete.
    """
    # Verify ownership first
    existing_card = ReturnCardRepository.get_by_id(card_id)
    if not existing_card or existing_card.user_id != user.id:
        raise HTTPException(status_code=404, detail="Return card not found")

    deleted = ReturnCardRepository.delete(card_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Return card not found")
    return Response(status_code=204)


@router.post("/refresh-statuses")
async def refresh_statuses(
    user: AuthenticatedUser = Depends(get_current_user),
    threshold_days: int = Query(API_EXPIRING_THRESHOLD_DAYS, ge=1, le=30, description="Days threshold for expiring_soon"),
) -> dict[str, Any]:
    """
    Refresh return card statuses based on current date for the authenticated user.

    Updates:
    - active -> expiring_soon if within threshold_days
    - active/expiring_soon -> expired if past return_by_date
    """
    try:
        user_id = user.id
        updated_count = ReturnCardRepository.refresh_statuses(user_id, threshold_days)
        return {
            "updated_count": updated_count,
            "message": f"Refreshed statuses for user {user_id}",
        }
    except Exception as e:
        logger.error("Failed to refresh statuses: %s", e)
        raise HTTPException(status_code=500, detail="Failed to refresh statuses") from None


class ProcessEmailRequest(BaseModel):
    """Request to process an email through the extraction pipeline."""

    email_id: str
    from_address: str
    subject: str
    body: str

    # SEC-012: Input validation
    @field_validator("email_id")
    @classmethod
    def validate_email(cls, v: str) -> str:
        validated = validate_email_id(v)
        if not validated:
            raise ValueError("Invalid email_id")
        return validated


class ProcessEmailResponse(BaseModel):
    """Response from email processing."""

    success: bool
    stage_reached: str
    rejection_reason: str | None = None
    card: ReturnCardResponse | None = None


# ============================================================================
# Batch Processing Models
# ============================================================================


class ProcessBatchEmail(BaseModel):
    """A single email in a batch processing request."""

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


class ProcessBatchRequest(BaseModel):
    """Request to process a batch of emails through the extraction pipeline."""

    emails: list[ProcessBatchEmail] = Field(..., max_length=API_BATCH_SIZE_MAX)


class ProcessBatchStats(BaseModel):
    """Statistics from batch processing."""

    total: int
    rejected_filter: int
    rejected_classifier: int
    rejected_empty: int
    cards_created: int
    cards_merged: int


class ProcessBatchResponse(BaseModel):
    """Response from batch email processing."""

    success: bool
    cards: list[ReturnCardResponse]
    stats: ProcessBatchStats


@router.post("/process", response_model=ProcessEmailResponse)
async def process_email(
    request: ProcessEmailRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessEmailResponse:
    """
    Process an email through the 3-stage extraction pipeline for the authenticated user.

    Stages:
    1. Domain Filter - Fast rule-based pre-filter (FREE)
    2. Returnability Classifier - LLM determines if returnable (~$0.0001)
    3. Field Extractor - LLM + rules extract fields (~$0.0002)

    Returns the created ReturnCard if email is a returnable purchase.
    """
    from shopq.returns import ReturnableReceiptExtractor

    try:
        user_id = user.id
        extractor = ReturnableReceiptExtractor()
        result = extractor.extract_from_email(
            user_id=user_id,
            email_id=request.email_id,
            from_address=request.from_address,
            subject=request.subject,
            body=request.body,
        )

        if result.success and result.card:
            # Log extraction result for debugging dedup issues
            logger.info(
                "DEDUP CHECK: merchant=%s, order_number=%s, item_summary=%s",
                result.card.merchant_domain,
                result.card.order_number,
                result.card.item_summary[:50] if result.card.item_summary else None,
            )

            # Check for existing card (deduplication)
            # Normalize domain for consistent matching
            normalized_domain = (result.card.merchant_domain or "").lower()

            # Strategy 1: Match by merchant_domain + order_number
            existing_card = None
            if result.card.order_number:
                existing_card = ReturnCardRepository.find_by_order_key(
                    user_id=user_id,
                    merchant_domain=normalized_domain,
                    order_number=result.card.order_number,
                    tracking_number=None,
                )
                if existing_card:
                    logger.info("DEDUP MATCH: Found by order_number %s", result.card.order_number)

            # Strategy 2: Match by merchant_domain + item_summary (for when order_number missing)
            if not existing_card and result.card.item_summary:
                candidate = ReturnCardRepository.find_by_item_summary(
                    user_id=user_id,
                    merchant_domain=normalized_domain,
                    item_summary=result.card.item_summary,
                )
                if candidate:
                    # Don't merge if order numbers conflict
                    new_order = result.card.order_number
                    existing_order = candidate.order_number
                    if new_order and existing_order and new_order != existing_order:
                        logger.info(
                            "DEDUP SKIP: order# conflict %s vs %s", new_order, existing_order
                        )
                        candidate = None
                    else:
                        logger.info("DEDUP MATCH: Found by item_summary similarity")
                existing_card = candidate

            # Strategy 3: Check if this email was already processed
            if not existing_card:
                existing_card = ReturnCardRepository.find_by_email_id(user_id, request.email_id)
                if existing_card:
                    logger.info("DEDUP MATCH: Found by email_id")

            if not existing_card:
                logger.info(
                    "DEDUP NO MATCH: Creating new card for %s - %s",
                    result.card.merchant_domain,
                    result.card.item_summary[:40] if result.card.item_summary else "unknown",
                )

            if existing_card:
                # Merge email into existing card with new data
                # This updates the card if the new email has better info
                # (e.g., delivery date from shipping email, return policy from confirmation)
                new_data = {
                    "delivery_date": result.card.delivery_date,
                    "return_by_date": result.card.return_by_date,
                    "item_summary": result.card.item_summary,
                    "evidence_snippet": result.card.evidence_snippet,
                    "return_portal_link": result.card.return_portal_link,
                    "shipping_tracking_link": result.card.shipping_tracking_link,
                }
                saved_card = ReturnCardRepository.merge_email_into_card(
                    existing_card.id, request.email_id, new_data
                )
                if saved_card:
                    logger.info(
                        "Processed email %s -> merged into existing card %s for %s",
                        request.email_id,
                        saved_card.id,
                        saved_card.merchant,
                    )
            else:
                # Create new card
                from shopq.returns import ReturnCardCreate

                card_create = ReturnCardCreate(
                    user_id=result.card.user_id,
                    merchant=result.card.merchant,
                    merchant_domain=normalized_domain,
                    item_summary=result.card.item_summary,
                    confidence=result.card.confidence,
                    source_email_ids=result.card.source_email_ids,
                    order_number=result.card.order_number,
                    amount=result.card.amount,
                    currency=result.card.currency,
                    order_date=result.card.order_date,
                    delivery_date=result.card.delivery_date,
                    return_by_date=result.card.return_by_date,
                    return_portal_link=result.card.return_portal_link,
                    shipping_tracking_link=result.card.shipping_tracking_link,
                    evidence_snippet=result.card.evidence_snippet,
                )

                saved_card = ReturnCardRepository.create(card_create)
                logger.info(
                    "Processed email %s -> created new card %s for %s",
                    request.email_id,
                    saved_card.id,
                    saved_card.merchant,
                )

            if saved_card:
                return ProcessEmailResponse(
                    success=True,
                    stage_reached=result.stage_reached,
                    card=ReturnCardResponse.from_card(saved_card),
                )

        return ProcessEmailResponse(
            success=False,
            stage_reached=result.stage_reached,
            rejection_reason=result.rejection_reason,
        )

    except Exception as e:
        # SEC-011: Don't expose raw error messages - log full error, return generic message
        logger.error("Failed to process email %s: %s", request.email_id, e)
        raise HTTPException(status_code=500, detail="Failed to process email") from None


@router.post("/process-batch", response_model=ProcessBatchResponse)
async def process_email_batch(
    request: ProcessBatchRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    skip_persistence: bool = Query(
        False, description="Skip DB save/dedup — return pipeline results directly (for testing)"
    ),
) -> ProcessBatchResponse:
    """
    Process a batch of emails through the 3-stage extraction pipeline.

    Runs all emails through filter → classifier → extractor, then deduplicates
    across the batch and suppresses cancelled orders. This is the preferred
    endpoint for scanning — it produces better results than processing emails
    one at a time because cross-email dedup and cancellation detection require
    seeing the full batch.

    Max 500 emails per batch.

    When skip_persistence=true, the pipeline runs normally but results are not
    saved to the database and not deduplicated against existing DB cards. This
    ensures reproducible results independent of database state.
    """
    from shopq.returns import ReturnableReceiptExtractor

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

        logger.info("Processing batch of %d emails for user %s", len(emails), user_id)

        extractor = ReturnableReceiptExtractor()
        results = extractor.process_email_batch(user_id, emails)

        # Upsert each successful result into DB (same dedup logic as single endpoint)
        stats = ProcessBatchStats(
            total=len(request.emails),
            rejected_filter=0,
            rejected_classifier=0,
            rejected_empty=0,
            cards_created=0,
            cards_merged=0,
        )

        saved_cards: list[ReturnCard] = []

        for result in results:
            if not result.success or not result.card:
                # Count rejection reasons
                reason = result.rejection_reason or ""
                if result.stage_reached == ExtractionStage.FILTER:
                    stats.rejected_filter += 1
                elif result.stage_reached == ExtractionStage.CLASSIFIER:
                    stats.rejected_classifier += 1
                elif reason.startswith("error:") or result.stage_reached == ExtractionStage.ERROR:
                    stats.rejected_empty += 1
                else:
                    stats.rejected_empty += 1
                continue

            card = result.card

            if skip_persistence:
                # Return pipeline results directly — no DB interaction
                card.user_id = user_id
                saved_cards.append(card)
                stats.cards_created += 1
                continue

            # Dedup against DB: check for existing card
            normalized_domain = (card.merchant_domain or "").lower()

            existing_card = None
            if card.order_number:
                existing_card = ReturnCardRepository.find_by_order_key(
                    user_id=user_id,
                    merchant_domain=normalized_domain,
                    order_number=card.order_number,
                    tracking_number=None,
                )

            if not existing_card and card.item_summary:
                candidate = ReturnCardRepository.find_by_item_summary(
                    user_id=user_id,
                    merchant_domain=normalized_domain,
                    item_summary=card.item_summary,
                )
                if candidate:
                    # Don't merge if order numbers conflict
                    new_order = card.order_number
                    existing_order = candidate.order_number
                    if new_order and existing_order and new_order != existing_order:
                        logger.info(
                            "DEDUP SKIP: order# conflict %s vs %s", new_order, existing_order
                        )
                        candidate = None
                    existing_card = candidate

            if not existing_card and card.source_email_ids:
                for eid in card.source_email_ids:
                    existing_card = ReturnCardRepository.find_by_email_id(user_id, eid)
                    if existing_card:
                        break

            if existing_card:
                new_data = {
                    "delivery_date": card.delivery_date,
                    "return_by_date": card.return_by_date,
                    "item_summary": card.item_summary,
                    "evidence_snippet": card.evidence_snippet,
                    "return_portal_link": card.return_portal_link,
                    "shipping_tracking_link": card.shipping_tracking_link,
                }
                email_id = card.source_email_ids[0] if card.source_email_ids else ""
                saved = ReturnCardRepository.merge_email_into_card(
                    existing_card.id, email_id, new_data
                )
                if saved:
                    saved_cards.append(saved)
                    stats.cards_merged += 1
            else:
                from shopq.returns import ReturnCardCreate

                card_create = ReturnCardCreate(
                    user_id=user_id,
                    merchant=card.merchant,
                    merchant_domain=normalized_domain,
                    item_summary=card.item_summary,
                    confidence=card.confidence,
                    source_email_ids=card.source_email_ids,
                    order_number=card.order_number,
                    amount=card.amount,
                    currency=card.currency,
                    order_date=card.order_date,
                    delivery_date=card.delivery_date,
                    return_by_date=card.return_by_date,
                    return_portal_link=card.return_portal_link,
                    shipping_tracking_link=card.shipping_tracking_link,
                    evidence_snippet=card.evidence_snippet,
                )
                saved = ReturnCardRepository.create(card_create)
                saved_cards.append(saved)
                stats.cards_created += 1

        logger.info(
            "Batch complete: %d emails -> %d cards (%d created, %d merged)",
            len(request.emails),
            len(saved_cards),
            stats.cards_created,
            stats.cards_merged,
        )

        return ProcessBatchResponse(
            success=True,
            cards=[ReturnCardResponse.from_card(c) for c in saved_cards],
            stats=stats,
        )

    except Exception as e:
        logger.error("Failed to process email batch: %s", e)
        raise HTTPException(status_code=500, detail="Failed to process email batch") from None
