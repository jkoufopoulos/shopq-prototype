"""Returns service layer — facade between API routes and repository.

Centralizes ownership checks, dedup/merge logic, and business rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reclaim.observability.logging import get_logger
from reclaim.returns.models import (
    ReturnCard,
    ReturnCardCreate,
    ReturnCardUpdate,
    ReturnStatus,
)
from reclaim.returns.repository import ReturnCardRepository

logger = get_logger(__name__)


@dataclass
class DedupResult:
    """Result of dedup-and-persist operation."""

    card: ReturnCard
    was_merged: bool


class ReturnsService:
    """Service layer for return card operations.

    All methods that accept card_id + user_id enforce ownership.
    Returns None (or False for delete) when card is not found or not owned.
    """

    @staticmethod
    def get_card(card_id: str, user_id: str) -> ReturnCard | None:
        """Get a card if owned by user. Returns None if not found or not owned."""
        card = ReturnCardRepository.get_by_id(card_id)
        if not card or card.user_id != user_id:
            return None
        return card

    @staticmethod
    def list_returns(
        user_id: str,
        status: list[ReturnStatus] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ReturnCard], int, int]:
        """List returns with auto-refresh.

        Returns:
            (cards, total_count, expiring_soon_count)
        """
        ReturnCardRepository.refresh_statuses(user_id)
        cards = ReturnCardRepository.list_by_user(
            user_id=user_id, status=status, limit=limit, offset=offset
        )
        total_count = ReturnCardRepository.count_by_user(user_id, status)
        expiring = ReturnCardRepository.list_expiring_soon(user_id)
        return cards, total_count, len(expiring)

    @staticmethod
    def list_expiring(user_id: str, threshold_days: int = 7) -> list[ReturnCard]:
        """List expiring returns with auto-refresh."""
        ReturnCardRepository.refresh_statuses(user_id, threshold_days)
        return ReturnCardRepository.list_expiring_soon(user_id, threshold_days)

    @staticmethod
    def get_counts(user_id: str) -> dict[str, int]:
        """Get card counts by status with auto-refresh."""
        ReturnCardRepository.refresh_statuses(user_id)
        return ReturnCardRepository.count_by_status(user_id)

    @staticmethod
    def create(card_create: ReturnCardCreate) -> ReturnCard:
        """Create a new return card."""
        return ReturnCardRepository.create(card_create)

    @staticmethod
    def update_status(
        card_id: str, user_id: str, new_status: ReturnStatus
    ) -> ReturnCard | None:
        """Update card status if owned by user."""
        card = ReturnCardRepository.get_by_id(card_id)
        if not card or card.user_id != user_id:
            return None
        return ReturnCardRepository.update_status(card_id, new_status)

    @staticmethod
    def update(
        card_id: str, user_id: str, updates: ReturnCardUpdate
    ) -> ReturnCard | None:
        """Update card fields if owned by user."""
        card = ReturnCardRepository.get_by_id(card_id)
        if not card or card.user_id != user_id:
            return None
        return ReturnCardRepository.update(card_id, updates)

    @staticmethod
    def delete(card_id: str, user_id: str) -> bool:
        """Delete card if owned by user. Returns False if not found or not owned."""
        card = ReturnCardRepository.get_by_id(card_id)
        if not card or card.user_id != user_id:
            return False
        return ReturnCardRepository.delete(card_id)

    @staticmethod
    def refresh_statuses(user_id: str, threshold_days: int = 7) -> int:
        """Refresh card statuses based on current date."""
        return ReturnCardRepository.refresh_statuses(user_id, threshold_days)

    @staticmethod
    def _compute_merge_updates(existing: ReturnCard, new_card: ReturnCard) -> dict[str, Any]:
        """Determine which fields to update based on merge precedence rules.

        Rules (invariant — do not reorder or change semantics):
        - delivery_date: fill if empty
        - return_by_date: fill if empty, or replace if delivery_date was just filled
        - item_summary: longer wins
        - evidence_snippet: keyword-gated (must contain return/refund/days/policy)
        - return_portal_link: fill if empty
        - shipping_tracking_link: fill if empty
        """
        updates: dict[str, Any] = {}

        # delivery_date: use new if existing is None
        if new_card.delivery_date and not existing.delivery_date:
            updates["delivery_date"] = new_card.delivery_date

        # return_by_date: use new if existing is None or delivery_date was just set
        if new_card.return_by_date and (
            not existing.return_by_date or "delivery_date" in updates
        ):
            updates["return_by_date"] = new_card.return_by_date

        # item_summary: longer wins
        new_summary = new_card.item_summary or ""
        existing_summary = existing.item_summary or ""
        if len(new_summary) > len(existing_summary):
            updates["item_summary"] = new_summary

        # evidence_snippet: keyword-gated
        if new_card.evidence_snippet:
            lower = new_card.evidence_snippet.lower()
            if any(kw in lower for kw in ["return", "refund", "days", "policy"]):
                updates["evidence_snippet"] = new_card.evidence_snippet

        # Links: fill if missing
        if new_card.return_portal_link and not existing.return_portal_link:
            updates["return_portal_link"] = new_card.return_portal_link
        if new_card.shipping_tracking_link and not existing.shipping_tracking_link:
            updates["shipping_tracking_link"] = new_card.shipping_tracking_link

        return updates

    @staticmethod
    def dedup_and_persist(user_id: str, card: ReturnCard) -> DedupResult:
        """Deduplicate a card against the DB and persist (create or merge).

        Dedup strategy (order matters — never reorder):
        1. Match by merchant_domain + order_number
        2. Match by merchant_domain + item_summary (fuzzy, with order# conflict guard)
        3. Match by email_id (any in card.source_email_ids)

        If a match is found, computes merge updates and persists atomically.
        Otherwise, creates a new card.

        Returns:
            DedupResult with the saved card and whether it was merged.
        """
        normalized_domain = (card.merchant_domain or "").lower()

        logger.info(
            "DEDUP CHECK: merchant=%s, order_number=%s, item_summary=%s",
            card.merchant_domain,
            card.order_number,
            card.item_summary[:50] if card.item_summary else None,
        )

        # Strategy 1: Match by merchant_domain + order_number
        existing_card = None
        if card.order_number:
            existing_card = ReturnCardRepository.find_by_order_key(
                user_id=user_id,
                merchant_domain=normalized_domain,
                order_number=card.order_number,
                tracking_number=None,
            )
            if existing_card:
                logger.info("DEDUP MATCH: Found by order_number %s", card.order_number)

        # Strategy 2: Match by merchant_domain + item_summary
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
                else:
                    logger.info("DEDUP MATCH: Found by item_summary similarity")
            existing_card = candidate

        # Strategy 3: Match by email_id
        if not existing_card:
            for eid in card.source_email_ids:
                existing_card = ReturnCardRepository.find_by_email_id(user_id, eid)
                if existing_card:
                    logger.info("DEDUP MATCH: Found by email_id")
                    break

        if existing_card:
            # Compute merge updates using policy rules, then persist atomically
            merge_updates = ReturnsService._compute_merge_updates(existing_card, card)
            email_id = card.source_email_ids[0] if card.source_email_ids else ""
            saved = ReturnCardRepository.add_email_and_update(
                existing_card.id, email_id, merge_updates
            )
            if saved:
                logger.info(
                    "DEDUP MERGED: email -> existing card %s for %s",
                    saved.id,
                    saved.merchant,
                )
                return DedupResult(card=saved, was_merged=True)

        # No match — create new card
        logger.info(
            "DEDUP NO MATCH: Creating new card for %s - %s",
            card.merchant_domain,
            card.item_summary[:40] if card.item_summary else "unknown",
        )
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
        return DedupResult(card=saved, was_merged=False)
