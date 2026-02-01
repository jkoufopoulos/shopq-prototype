"""
Returnable Receipt Extractor - Main orchestrator for the 3-stage pipeline.

Coordinates:
1. MerchantDomainFilter (Stage 1) - Fast rule-based pre-filter
2. ReturnabilityClassifier (Stage 2) - LLM-based returnability check
3. ReturnFieldExtractor (Stage 3) - Hybrid LLM + rules field extraction

Entry point: ReturnableReceiptExtractor.extract_from_email()
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from shopq.infrastructure.llm_budget import check_budget, record_llm_call
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event
from shopq.returns.field_extractor import ExtractedFields, ReturnFieldExtractor
from shopq.returns.filters import FilterResult, MerchantDomainFilter
from shopq.returns.models import ReturnCard, ReturnConfidence
from shopq.returns.returnability_classifier import (
    ReturnabilityClassifier,
    ReturnabilityResult,
)
from shopq.utils.html import html_to_text
from shopq.utils.redaction import redact_subject

logger = get_logger(__name__)

# Minimum useful characters in body_text before preferring HTML conversion.
# Some merchants (e.g., Best Buy) send body_text that is just "View as a Web page"
# links with no actual content — all real content is in the HTML.
_MIN_USEFUL_BODY_CHARS = 100


def _is_body_boilerplate(body: str) -> bool:
    """Check if body text is empty or just boilerplate (URLs, separators)."""
    if not body:
        return True
    stripped = re.sub(r"https?://\S+", "", body)
    stripped = re.sub(r"[=\-]{3,}", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return len(stripped) < _MIN_USEFUL_BODY_CHARS


# Common words to ignore when comparing item summaries for overlap
_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "of",
        "in",
        "to",
        "with",
        "by",
        "on",
        "at",
        "from",
        "is",
        "it",
        "its",
        "your",
        "my",
        "this",
        "that",
        "x",
        "oz",
        "ct",
        "pk",
        "pack",
        "count",
        "size",
        "color",
        "qty",
    }
)

# Minimum word length to consider meaningful
_MIN_WORD_LEN = 3


def _items_overlap(summary_a: str | None, summary_b: str | None) -> bool:
    """Check if two item summaries share meaningful product-name words.

    Tokenizes both summaries, strips stop words and short tokens, and checks
    whether they share at least one significant word. Returns True if either
    summary is empty/None (conservative: don't block merge when we can't tell).
    """
    if not summary_a or not summary_b:
        return True  # can't tell — allow merge

    tokens_a = {
        w
        for w in re.split(r"[\s,;/|&()\-]+", summary_a.lower())
        if len(w) >= _MIN_WORD_LEN and w not in _STOP_WORDS
    }
    tokens_b = {
        w
        for w in re.split(r"[\s,;/|&()\-]+", summary_b.lower())
        if len(w) >= _MIN_WORD_LEN and w not in _STOP_WORDS
    }

    if not tokens_a or not tokens_b:
        return True  # can't tell — allow merge

    return bool(tokens_a & tokens_b)


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
            stage_reached="cancellation_check",
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
    4. Cross-email cancellation check → Suppress orders cancelled in other emails (free)

    Total cost per email: ~$0.00005 (accounting for filter rejection rate)
    """

    # Amazon order number pattern: 3-7-7 digits
    _AMAZON_ORDER_RE = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")

    # Cancellation/refund signals in subject lines (case-insensitive matching)
    _CANCELLATION_SUBJECT_KEYWORDS = [
        "cancelled",
        "cancellation",
        "advance refund issued",
        "refund issued",
    ]

    # Cancellation/refund signals in email body (case-insensitive matching)
    _CANCELLATION_BODY_KEYWORDS = [
        "your order was cancelled",
        "has been cancelled",
        "item cancelled successfully",
        "being returned to us by the carrier",
        "we've issued your refund",
        "we have issued your refund",
    ]

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
        body_html: str | None = None,
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
            body_html: Raw HTML body (used as fallback when body is empty)

        Returns:
            ExtractionResult with success=True and card if returnable,
            success=False with rejection_reason otherwise.

        Side Effects:
            - Calls Gemini API (2 calls for returnable emails)
            - Logs extraction events
            - Increments telemetry counters
        """
        # Convert HTML body to text when plain-text body is empty or boilerplate
        if body_html and _is_body_boilerplate(body):
            body = html_to_text(body_html)
            logger.info("Converted HTML body to text (%d chars)", len(body))

        counter("returns.extraction.started")
        # SEC-016: Redact PII from logging
        logger.info(
            "EXTRACTION START: subject='%s' from='%s'", redact_subject(subject), from_address
        )

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
                "STAGE 1 REJECTED: domain=%s reason=%s", filter_result.domain, filter_result.reason
            )
            log_event(
                "returns.extraction.rejected",
                stage="filter",
                reason=filter_result.reason,
                domain=filter_result.domain,
            )
            return ExtractionResult.rejected_at_filter(filter_result)

        counter("returns.extraction.passed_filter")
        logger.info(
            "STAGE 1 PASSED: domain=%s -> proceeding to LLM classifier", filter_result.domain
        )

        # =========================================================
        # SCALE-001: Budget Check before LLM calls
        # =========================================================
        budget_status = check_budget(user_id)
        if not budget_status.is_allowed:
            counter("returns.extraction.rejected_budget")
            logger.warning("BUDGET EXCEEDED: user=%s reason=%s", user_id, budget_status.reason)
            log_event(
                "returns.extraction.rejected",
                stage="budget",
                reason=budget_status.reason,
                user_calls=budget_status.user_calls_today,
                global_calls=budget_status.global_calls_today,
            )
            return ExtractionResult.rejected_budget_exceeded(
                filter_result, budget_status.reason or ""
            )

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
                returnability.reason,
            )
            log_event(
                "returns.extraction.rejected",
                stage="classifier",
                reason=returnability.reason,
                receipt_type=returnability.receipt_type.value,
            )
            return ExtractionResult.rejected_at_classifier(filter_result, returnability)

        counter("returns.extraction.passed_classifier")
        logger.info(
            "STAGE 2 PASSED BY LLM: type=%s -> proceeding to extraction",
            returnability.receipt_type.value,
        )

        # =========================================================
        # Stage 3: Field Extraction (~$0.0002)
        # =========================================================
        fields = self.field_extractor.extract(
            from_address=from_address,
            subject=subject,
            body=body,
            merchant_domain=filter_result.domain,
            received_at=received_at,
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

        # Reject cards with no identifiable content (no item and no order number,
        # or item_summary is just a generic email phrase echoing the subject line)
        _generic = frozenset(
            {
                # Order confirmation phrases
                "thanks for your order",
                "thank you for your order",
                "your order has been placed",
                "order confirmation",
                "your order",
                # Delivery notification phrases
                "package has been delivered",
                "your package has been delivered",
                "your package was delivered",
                "your delivery is complete",
                "delivery notification",
                "delivered",
                # Shipping notification phrases
                "your order has shipped",
                "your order has been shipped",
                "your package is on the way",
                "out for delivery",
                "shipped",
                # Additional delivery/shipping variants
                "in transit",
                "on the way",
                "order received",
                # Post-prefix-stripped variants (fallback extractor strips
                # "Your ", "Order ", "Shipping ", "Delivery " prefixes)
                "has shipped",
                "has been shipped",
                "has been delivered",
                "was delivered",
                "has been placed",
                "is on the way",
                "confirmation",
            }
        )
        item_text = (card.item_summary or "").strip().rstrip(".!").lower()
        if not card.order_number and (not card.item_summary or item_text in _generic):
            counter("returns.extraction.rejected_empty_card")
            logger.info(
                "EMPTY CARD REJECTED: merchant=%s - no item_summary or order_number",
                card.merchant,
            )
            return ExtractionResult(
                success=False,
                filter_result=filter_result,
                returnability_result=returnability,
                extracted_fields=fields,
                rejection_reason="empty_card:no_item_or_order",
                stage_reached="extractor",
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
        received_at: datetime | None,  # noqa: ARG002
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

    def _detect_cancelled_orders(self, emails: list[dict[str, Any]]) -> set[str]:
        """Scan emails for cancellation/refund signals and extract cancelled order numbers.

        This is a free, deterministic post-processing step that checks all emails
        in a batch for cancellation keywords and extracts order numbers from matches.

        Returns:
            Set of order number strings found in cancellation emails.
        """
        cancelled: set[str] = set()

        for email in emails:
            subject = (email.get("subject") or "").lower()
            body = (email.get("body") or "").lower()

            is_cancellation = False

            # Check subject for cancellation signals
            for keyword in self._CANCELLATION_SUBJECT_KEYWORDS:
                if keyword in subject:
                    is_cancellation = True
                    break

            # Check body for cancellation signals (only if subject didn't match)
            if not is_cancellation:
                for keyword in self._CANCELLATION_BODY_KEYWORDS:
                    if keyword in body:
                        is_cancellation = True
                        break

            if not is_cancellation:
                continue

            # Extract order numbers from the cancellation email (use original case)
            raw_subject = email.get("subject") or ""
            raw_body = email.get("body") or ""
            order_numbers = self._AMAZON_ORDER_RE.findall(raw_subject + " " + raw_body)

            if order_numbers:
                cancelled.update(order_numbers)
                logger.info(
                    "Cancellation detected: email_id=%s orders=%s",
                    email.get("id", "unknown"),
                    order_numbers,
                )

        return cancelled

    def _suppress_cancelled_cards(
        self,
        results: list[ExtractionResult],
        cancelled_orders: set[str],
    ) -> list[ExtractionResult]:
        """Suppress ReturnCards whose orders were cancelled in other emails.

        Converts successful results with matching order numbers into rejections.

        Args:
            results: List of extraction results (post-dedup).
            cancelled_orders: Set of order numbers found in cancellation emails.

        Returns:
            Modified results list with cancelled orders converted to rejections.
        """
        suppressed = []
        for result in results:
            if (
                result.success
                and result.card
                and result.card.order_number
                and result.card.order_number in cancelled_orders
            ):
                order_num = result.card.order_number
                logger.info(
                    "Suppressing card for cancelled order: order=%s merchant=%s",
                    order_num,
                    result.card.merchant,
                )
                counter("returns.extraction.suppressed_cancelled")
                suppressed.append(
                    ExtractionResult.rejected_at_cancellation_check(result, order_num)
                )
            else:
                suppressed.append(result)
        return suppressed

    def process_email_batch(
        self,
        user_id: str,
        emails: list[dict[str, Any]],
    ) -> list[ExtractionResult]:
        """
        Process a batch of emails and deduplicate results.

        Args:
            user_id: User who owns these emails
            emails: List of email dicts with keys:
                    - id: Gmail message ID
                    - from: Sender address
                    - subject: Subject line
                    - body: Body text
                    - body_html: Optional HTML body (fallback when body is empty)
                    - received_at: Optional datetime

        Returns:
            List of ExtractionResult for each email (deduplicated)
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
                    body_html=email.get("body_html"),
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

        # Deduplicate successful results
        results = self._deduplicate_results(results)

        # Cross-email cancellation suppression (free, deterministic)
        cancelled_orders = self._detect_cancelled_orders(emails)
        if cancelled_orders:
            results = self._suppress_cancelled_cards(results, cancelled_orders)

        # Log batch summary
        successful = sum(1 for r in results if r.success)
        log_event(
            "returns.extraction.batch_complete",
            total=len(emails),
            successful=successful,
            user_id=user_id,
        )

        return results

    @staticmethod
    def _card_richness(card: ReturnCard) -> int:
        """Score how many useful fields a card has (higher = richer)."""
        score = 0
        if card.order_number:
            score += 2
        if card.return_by_date:
            score += 3
        if card.amount:
            score += 1
        if card.order_date:
            score += 1
        if card.delivery_date:
            score += 1
        if card.item_summary and len(card.item_summary) > 10:
            score += 1
        if card.evidence_snippet:
            score += 1
        return score

    def _deduplicate_results(self, results: list[ExtractionResult]) -> list[ExtractionResult]:
        """Deduplicate extraction results in three passes.

        Pass 1: Group by (merchant_domain, order_number) — same merchant, same order.
        Pass 2: Merge cross-domain groups that share the same order_number —
                handles cases like ILIA emails from shopifyemail.com vs iliabeauty.com.
        Pass 3: Merge cards without order numbers into their merchant's group
                when there's exactly one group for that merchant (unambiguous).

        For each group, keeps the richest card and merges source_email_ids
        and missing dates from siblings.
        """
        successful = [r for r in results if r.success and r.card]
        non_successful = [r for r in results if not r.success or not r.card]

        if not successful:
            return results

        # Pass 1: Group by (merchant_domain, order_number)
        groups: dict[tuple[str, str], list[ExtractionResult]] = {}
        ungrouped: list[ExtractionResult] = []

        for r in successful:
            card = r.card
            assert card is not None  # guaranteed by filter above
            key_domain = (card.merchant_domain or "").lower()
            key_order = (card.order_number or "").strip()

            if not key_order:
                ungrouped.append(r)
                continue

            key = (key_domain, key_order)
            groups.setdefault(key, []).append(r)

        # Pass 2: Merge cross-domain groups sharing the same order_number
        by_order: dict[str, list[tuple[str, str]]] = {}
        for key_domain, key_order in groups:
            by_order.setdefault(key_order, []).append((key_domain, key_order))

        for order_num, keys in by_order.items():
            if len(keys) <= 1:
                continue
            # Merge all groups for this order_number into the first group
            primary_key = keys[0]
            for secondary_key in keys[1:]:
                groups[primary_key].extend(groups.pop(secondary_key))
            logger.info(
                "Dedup: merged %d domain variants for order %s",
                len(keys),
                order_num,
            )

        # Pass 3: Merge ungrouped (no order#) into unambiguous merchant groups
        # Build domain -> group keys mapping
        domain_to_keys: dict[str, list[tuple[str, str]]] = {}
        for key in groups:
            domain_to_keys.setdefault(key[0], []).append(key)

        # Collect merge candidates per group key first, then only merge
        # when exactly one ungrouped card targets a group. This prevents
        # cards from different orders (same merchant, missing order#)
        # from being incorrectly merged into one group.
        merge_candidates: dict[tuple[str, str], list[ExtractionResult]] = {}
        still_ungrouped: list[ExtractionResult] = []
        for r in ungrouped:
            assert r.card is not None  # guaranteed by filter above
            card_domain = (r.card.merchant_domain or "").lower()
            matching_keys = domain_to_keys.get(card_domain, [])
            if len(matching_keys) == 1:
                # Only merge if items share meaningful words with any card
                # in the group — prevents cards from unrelated orders being
                # merged just because the merchant has one order with an order#.
                group_items = groups[matching_keys[0]]
                if any(
                    _items_overlap(r.card.item_summary, gr.card.item_summary)
                    for gr in group_items
                    if gr.card is not None
                ):
                    merge_candidates.setdefault(matching_keys[0], []).append(r)
                else:
                    still_ungrouped.append(r)
            else:
                still_ungrouped.append(r)

        for target_key, candidates in merge_candidates.items():
            if len(candidates) == 1:
                # Unambiguous: exactly one no-order# card for this merchant group
                groups[target_key].append(candidates[0])
                logger.info(
                    "Dedup: merged no-order# card into %s/%s",
                    target_key[0],
                    target_key[1],
                )
            else:
                # Multiple no-order# cards for the same merchant.
                # If all candidates share the same product (items overlap pairwise),
                # they're likely the same order (e.g. shipped + out-for-delivery +
                # delivered emails). Merge them into the group.
                all_same_product = all(
                    _items_overlap(
                        candidates[0].card.item_summary,  # type: ignore[union-attr]
                        c.card.item_summary,  # type: ignore[union-attr]
                    )
                    for c in candidates[1:]
                )
                if all_same_product:
                    groups[target_key].extend(candidates)
                    logger.info(
                        "Dedup: merged %d same-product no-order# cards into %s/%s",
                        len(candidates),
                        target_key[0],
                        target_key[1],
                    )
                else:
                    # Truly ambiguous: different products, keep separate
                    logger.info(
                        "Dedup: skipped merging %d ambiguous no-order# cards for %s",
                        len(candidates),
                        target_key[0],
                    )
                    still_ungrouped.extend(candidates)

        # Merge each group into a single result
        deduped: list[ExtractionResult] = []

        for key, group in groups.items():
            if len(group) == 1:
                deduped.append(group[0])
                continue

            # Pick the richest card (r.card is guaranteed non-None by filter above)
            group.sort(
                key=lambda r: self._card_richness(r.card),  # type: ignore[arg-type]
                reverse=True,
            )
            winner = group[0]
            card = winner.card
            assert card is not None  # guaranteed by filter above

            # Merge source_email_ids from all siblings
            all_email_ids: list[str] = []
            seen: set[str] = set()
            for r in group:
                assert r.card is not None  # guaranteed by filter above
                for eid in r.card.source_email_ids:
                    if eid not in seen:
                        all_email_ids.append(eid)
                        seen.add(eid)
            card.source_email_ids = all_email_ids

            # Fill missing dates from siblings
            had_delivery_date = card.delivery_date is not None
            for r in group[1:]:
                assert r.card is not None  # guaranteed by filter above
                sibling = r.card
                if not card.order_date and sibling.order_date:
                    card.order_date = sibling.order_date
                if not card.delivery_date and sibling.delivery_date:
                    card.delivery_date = sibling.delivery_date
                if not card.return_by_date and sibling.return_by_date:
                    card.return_by_date = sibling.return_by_date
                    card.confidence = sibling.confidence

            # If we gained a delivery_date from a sibling that the winner
            # didn't have, recompute return_by_date using merchant rules
            # so the date is anchored on actual delivery, not received_at.
            if not had_delivery_date and card.delivery_date:
                merchants = self.merchant_rules.get("merchants", {})
                domain = (card.merchant_domain or "").lower()
                rule = merchants.get(domain) or merchants.get("_default")
                if rule:
                    days = rule.get("days", 30)
                    card.return_by_date = card.delivery_date + timedelta(days=days)
                    card.confidence = ReturnConfidence.ESTIMATED
                    logger.info(
                        "Dedup: recomputed return_by from sibling delivery_date for %s/%s",
                        key[0],
                        key[1],
                    )

            logger.info(
                "Dedup: merged %d cards for %s/%s",
                len(group),
                key[0],
                key[1],
            )
            deduped.append(winner)

        return non_successful + deduped + still_ungrouped


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
