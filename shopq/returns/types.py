"""
Module: types
Purpose: Shared domain types for the returns pipeline.
Dependencies: shopq.returns.models (ReturnConfidence only)

Stable import boundary — these types are used across extractor, filters,
field_extractor, service, and routes. Keeping them in a leaf module with
minimal dependencies prevents circular imports when splitting other modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from shopq.returns.models import ReturnConfidence

if TYPE_CHECKING:
    from shopq.returns.models import ReturnCard
    from shopq.returns.returnability_classifier import ReturnabilityResult


# ---------------------------------------------------------------------------
# Stage 1 result (from filters.py)
# ---------------------------------------------------------------------------


@dataclass
class FilterResult:
    """Result of domain filter check."""

    is_candidate: bool
    reason: str
    domain: str
    match_type: str  # "allowlist" | "blocklist" | "heuristic" | "unknown"


# ---------------------------------------------------------------------------
# Stage 3 result (from field_extractor.py)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Pipeline stage enum (from extractor.py)
# ---------------------------------------------------------------------------


class ExtractionStage(str, Enum):
    """Pipeline stage reached during extraction.

    Extends str so JSON serialization produces raw strings (e.g. "filter"),
    preserving the existing API contract.
    """

    NONE = "none"
    FILTER = "filter"
    CLASSIFIER = "classifier"
    EXTRACTOR = "extractor"
    CANCELLATION_CHECK = "cancellation_check"
    COMPLETE = "complete"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Full pipeline result (from extractor.py)
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Result of the full extraction pipeline."""

    success: bool
    card: ReturnCard | None = None
    filter_result: FilterResult | None = None
    returnability_result: ReturnabilityResult | None = None
    extracted_fields: ExtractedFields | None = None
    rejection_reason: str | None = None
    stage_reached: ExtractionStage = ExtractionStage.NONE

    @classmethod
    def rejected_at_filter(cls, filter_result: FilterResult) -> ExtractionResult:
        return cls(
            success=False,
            filter_result=filter_result,
            rejection_reason=f"filter:{filter_result.reason}",
            stage_reached=ExtractionStage.FILTER,
        )

    @classmethod
    def rejected_budget_exceeded(cls, filter_result: FilterResult, reason: str) -> ExtractionResult:
        """SCALE-001: Rejection when LLM budget is exceeded."""
        return cls(
            success=False,
            filter_result=filter_result,
            rejection_reason=f"budget:{reason}",
            stage_reached=ExtractionStage.FILTER,
        )

    @classmethod
    def rejected_at_classifier(
        cls,
        filter_result: FilterResult,
        returnability: ReturnabilityResult,
    ) -> ExtractionResult:
        return cls(
            success=False,
            filter_result=filter_result,
            returnability_result=returnability,
            rejection_reason=f"classifier:{returnability.reason}",
            stage_reached=ExtractionStage.CLASSIFIER,
        )

    @classmethod
    def rejected_at_cancellation_check(
        cls, original_result: ExtractionResult, order_number: str
    ) -> ExtractionResult:
        """Rejection when a separate cancellation/refund email was found for the order."""
        return cls(
            success=False,
            filter_result=original_result.filter_result,
            returnability_result=original_result.returnability_result,
            extracted_fields=original_result.extracted_fields,
            rejection_reason=f"cancelled_order:{order_number}",
            stage_reached=ExtractionStage.CANCELLATION_CHECK,
        )

    @classmethod
    def completed(
        cls,
        card: ReturnCard,
        filter_result: FilterResult,
        returnability: ReturnabilityResult,
        fields: ExtractedFields,
    ) -> ExtractionResult:
        return cls(
            success=True,
            card=card,
            filter_result=filter_result,
            returnability_result=returnability,
            extracted_fields=fields,
            stage_reached=ExtractionStage.COMPLETE,
        )
