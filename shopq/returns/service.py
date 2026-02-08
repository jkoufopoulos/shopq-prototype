"""Returns service layer — facade between API routes and repository.

Centralizes ownership checks, dedup/merge logic, and business rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopq.observability.logging import get_logger
from shopq.returns.models import (
    ReturnCard,
    ReturnCardCreate,
    ReturnCardUpdate,
    ReturnStatus,
)
from shopq.returns.repository import ReturnCardRepository

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
    def dedup_and_persist(user_id: str, card: ReturnCard) -> DedupResult:
        """Deduplicate a card against the DB and persist (create or merge).

        Dedup strategy (order matters — never reorder):
        1. Match by merchant_domain + order_number
        2. Match by merchant_domain + item_summary (fuzzy, with order# conflict guard)
        3. Match by email_id (any in card.source_email_ids)

        If a match is found, merges the new card's data into the existing card.
        Otherwise, creates a new card.

        Returns:
            DedupResult with the saved card and whether it was merged.
        """
        raise NotImplementedError("Implemented in Step 1.7b")
