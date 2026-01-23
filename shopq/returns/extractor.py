"""
Returnable Receipt Extractor - Main orchestrator for the 3-stage pipeline.

Coordinates:
1. MerchantDomainFilter (Stage 1) - Fast rule-based pre-filter
2. ReturnabilityClassifier (Stage 2) - LLM-based returnability check
3. ReturnFieldExtractor (Stage 3) - Hybrid LLM + rules field extraction

Entry point: ReturnableReceiptExtractor.extract_from_email()
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from shopq.infrastructure.llm_budget import check_budget, record_llm_call
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event
from shopq.returns.field_extractor import ExtractedFields, ReturnFieldExtractor
from shopq.returns.filters import FilterResult, MerchantDomainFilter
from shopq.returns.models import ReturnCard
from shopq.returns.returnability_classifier import (
    ReturnabilityClassifier,
    ReturnabilityResult,
)

logger = get_logger(__name__)


@dataclass
class ExtractionResult:
    """Result of the full extraction pipeline."""

    success: bool
    card: ReturnCard | None = None
    filter_result: FilterResult | None = None
    returnability_result: ReturnabilityResult | None = None
    extracted_fields: ExtractedFields | None = None
    rejection_reason: str | None = None
    stage_reached: str = "none"  # "filter" | "classifier" | "extractor" | "complete"

    @classmethod
    def rejected_at_filter(cls, filter_result: FilterResult) -> ExtractionResult:
        return cls(
            success=False,
            filter_result=filter_result,
            rejection_reason=f"filter:{filter_result.reason}",
            stage_reached="filter",
        )

    @classmethod
    def rejected_budget_exceeded(cls, filter_result: FilterResult, reason: str) -> ExtractionResult:
        """SCALE-001: Rejection when LLM budget is exceeded."""
        return cls(
            success=False,
            filter_result=filter_result,
            rejection_reason=f"budget:{reason}",
            stage_reached="filter",
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
            stage_reached="classifier",
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
            stage_reached="complete",
        )


class ReturnableReceiptExtractor:
    """
    Main orchestrator for returnable purchase extraction.

    Pipeline:
    1. MerchantDomainFilter → Quick domain-based pre-filter (free)
    2. ReturnabilityClassifier → LLM decides if returnable (~$0.0001)
    3. ReturnFieldExtractor → Hybrid LLM + rules extraction (~$0.0002)

    Total cost per email: ~$0.00005 (accounting for filter rejection rate)
    """

    def __init__(self, merchant_rules_path: Path | None = None):
        """
        Initialize extractor with merchant rules.

        Args:
            merchant_rules_path: Path to merchant_rules.yaml
        """
        if merchant_rules_path is None:
            merchant_rules_path = (
                Path(__file__).parent.parent.parent / "config" / "merchant_rules.yaml"
            )

        self.merchant_rules = self._load_merchant_rules(merchant_rules_path)

        # Initialize pipeline stages
        self.domain_filter = MerchantDomainFilter(merchant_rules_path)
        self.returnability_classifier = ReturnabilityClassifier()
        self.field_extractor = ReturnFieldExtractor(self.merchant_rules)

        logger.info(
            "ReturnableReceiptExtractor initialized with %d merchant rules",
            len(self.merchant_rules.get("merchants", {})),
        )

    def _load_merchant_rules(self, path: Path) -> dict:
        """Load merchant rules from YAML."""
        if not path.exists():
            logger.warning("Merchant rules not found at %s", path)
            return {"merchants": {}}

        with open(path) as f:
            return yaml.safe_load(f)

    def extract_from_email(
        self,
        user_id: str,
        email_id: str,
        from_address: str,
        subject: str,
        body: str,
        received_at: datetime | None = None,
    ) -> ExtractionResult:
        """
        Extract return card from email if it's a returnable purchase.

        This is the main entry point for the extraction pipeline.

        Args:
            user_id: User who owns this email
            email_id: Gmail message ID
            from_address: Email sender
            subject: Email subject
            body: Email body text
            received_at: When email was received

        Returns:
            ExtractionResult with success=True and card if returnable,
            success=False with rejection_reason otherwise.

        Side Effects:
            - Calls Gemini API (2 calls for returnable emails)
            - Logs extraction events
            - Increments telemetry counters
        """
        counter("returns.extraction.started")
        logger.info("EXTRACTION START: subject='%s' from='%s'", subject[:60], from_address)

        # =========================================================
        # Stage 1: Domain Filter (FREE)
        # =========================================================
        filter_result = self.domain_filter.filter(
            from_address=from_address,
            subject=subject,
            snippet=body[:2000] if body else "",
        )

        if not filter_result.is_candidate:
            counter("returns.extraction.rejected_filter")
            logger.info(
                "STAGE 1 REJECTED: domain=%s reason=%s",
                filter_result.domain,
                filter_result.reason
            )
            log_event(
                "returns.extraction.rejected",
                stage="filter",
                reason=filter_result.reason,
                domain=filter_result.domain,
            )
            return ExtractionResult.rejected_at_filter(filter_result)

        counter("returns.extraction.passed_filter")
        logger.info("STAGE 1 PASSED: domain=%s -> proceeding to LLM classifier", filter_result.domain)

        # =========================================================
        # SCALE-001: Budget Check before LLM calls
        # =========================================================
        budget_status = check_budget(user_id)
        if not budget_status.is_allowed:
            counter("returns.extraction.rejected_budget")
            logger.warning(
                "BUDGET EXCEEDED: user=%s reason=%s",
                user_id,
                budget_status.reason
            )
            log_event(
                "returns.extraction.rejected",
                stage="budget",
                reason=budget_status.reason,
                user_calls=budget_status.user_calls_today,
                global_calls=budget_status.global_calls_today,
            )
            return ExtractionResult.rejected_budget_exceeded(filter_result, budget_status.reason)

        # =========================================================
        # Stage 2: Returnability Classifier (~$0.0001)
        # =========================================================
        returnability = self.returnability_classifier.classify(
            from_address=from_address,
            subject=subject,
            snippet=body[:2000] if body else "",
        )

        # SCALE-001: Record classifier LLM call
        record_llm_call(user_id, "classifier")

        if not returnability.is_returnable:
            counter("returns.extraction.rejected_classifier")
            logger.info(
                "STAGE 2 REJECTED BY LLM: type=%s reason=%s",
                returnability.receipt_type.value,
                returnability.reason
            )
            log_event(
                "returns.extraction.rejected",
                stage="classifier",
                reason=returnability.reason,
                receipt_type=returnability.receipt_type.value,
            )
            return ExtractionResult.rejected_at_classifier(filter_result, returnability)

        counter("returns.extraction.passed_classifier")
        logger.info("STAGE 2 PASSED BY LLM: type=%s -> proceeding to extraction", returnability.receipt_type.value)

        # =========================================================
        # Stage 3: Field Extraction (~$0.0002)
        # =========================================================
        fields = self.field_extractor.extract(
            from_address=from_address,
            subject=subject,
            body=body,
            merchant_domain=filter_result.domain,
        )

        # SCALE-001: Record extractor LLM call
        record_llm_call(user_id, "extractor")

        counter("returns.extraction.passed_extractor")

        # =========================================================
        # Build ReturnCard
        # =========================================================
        card = self._build_return_card(
            user_id=user_id,
            email_id=email_id,
            fields=fields,
            received_at=received_at,
        )

        counter("returns.extraction.completed")
        log_event(
            "returns.extraction.completed",
            merchant=fields.merchant,
            confidence=fields.return_confidence.value,
            has_return_by=fields.return_by_date is not None,
        )

        return ExtractionResult.completed(
            card=card,
            filter_result=filter_result,
            returnability=returnability,
            fields=fields,
        )

    def _build_return_card(
        self,
        user_id: str,
        email_id: str,
        fields: ExtractedFields,
        received_at: datetime | None,
    ) -> ReturnCard:
        """Build ReturnCard from extracted fields."""
        now = datetime.now(UTC)

        return ReturnCard(
            id=str(uuid.uuid4()),
            user_id=user_id,
            merchant=fields.merchant,
            merchant_domain=fields.merchant_domain,
            item_summary=fields.item_summary,
            confidence=fields.return_confidence,
            source_email_ids=[email_id],
            order_number=fields.order_number,
            amount=fields.amount,
            currency=fields.currency,
            order_date=fields.order_date,
            delivery_date=fields.delivery_date,
            return_by_date=fields.return_by_date,
            return_portal_link=fields.return_portal_link,
            shipping_tracking_link=fields.tracking_link,
            evidence_snippet=fields.evidence_snippet,
            created_at=now,
            updated_at=now,
        )

    def process_email_batch(
        self,
        user_id: str,
        emails: list[dict[str, Any]],
    ) -> list[ExtractionResult]:
        """
        Process a batch of emails.

        Args:
            user_id: User who owns these emails
            emails: List of email dicts with keys:
                    - id: Gmail message ID
                    - from: Sender address
                    - subject: Subject line
                    - body: Body text
                    - received_at: Optional datetime

        Returns:
            List of ExtractionResult for each email
        """
        results = []

        for email in emails:
            try:
                result = self.extract_from_email(
                    user_id=user_id,
                    email_id=email["id"],
                    from_address=email.get("from", ""),
                    subject=email.get("subject", ""),
                    body=email.get("body", ""),
                    received_at=email.get("received_at"),
                )
                results.append(result)

            except Exception as e:
                logger.error("Failed to process email %s: %s", email.get("id"), e)
                counter("returns.extraction.error")
                # Create error result
                results.append(
                    ExtractionResult(
                        success=False,
                        rejection_reason=f"error:{str(e)[:100]}",
                        stage_reached="error",
                    )
                )

        # Log batch summary
        successful = sum(1 for r in results if r.success)
        log_event(
            "returns.extraction.batch_complete",
            total=len(emails),
            successful=successful,
            user_id=user_id,
        )

        return results


# Convenience function for single email extraction
def extract_return_card(
    user_id: str,
    email_id: str,
    from_address: str,
    subject: str,
    body: str,
) -> ReturnCard | None:
    """
    Extract return card from a single email.

    Convenience wrapper that creates extractor and returns just the card.

    Returns:
        ReturnCard if email is returnable purchase, None otherwise.
    """
    extractor = ReturnableReceiptExtractor()
    result = extractor.extract_from_email(
        user_id=user_id,
        email_id=email_id,
        from_address=from_address,
        subject=subject,
        body=body,
    )
    return result.card if result.success else None
