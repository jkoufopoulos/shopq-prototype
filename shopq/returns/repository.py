"""
Return Card Repository - CRUD operations for return_cards table.

Follows the established database patterns in shopq/infrastructure/database.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shopq.infrastructure.database import db_transaction, get_db_connection, retry_on_db_lock
from shopq.observability.logging import get_logger
from shopq.returns.models import (
    ReturnCard,
    ReturnCardCreate,
    ReturnCardUpdate,
    ReturnConfidence,
    ReturnStatus,
)

logger = get_logger(__name__)


class ReturnCardRepository:
    """
    Repository for ReturnCard CRUD operations.

    All methods use connection pooling and proper transaction handling.
    """

    @staticmethod
    @retry_on_db_lock()
    def create(card: ReturnCardCreate) -> ReturnCard:
        """
        Create a new return card.

        Args:
            card: ReturnCardCreate with required fields

        Returns:
            Created ReturnCard with generated id and timestamps

        Side Effects:
            - Inserts row into return_cards table
            - Commits transaction
        """
        card_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Compute initial status based on return_by_date
        initial_status = ReturnStatus.ACTIVE
        if card.return_by_date:
            days_remaining = (card.return_by_date - now).days
            if days_remaining <= 0:
                initial_status = ReturnStatus.EXPIRED
            elif days_remaining <= 7:
                initial_status = ReturnStatus.EXPIRING_SOON

        return_card = ReturnCard(
            id=card_id,
            user_id=card.user_id,
            merchant=card.merchant,
            merchant_domain=card.merchant_domain,
            item_summary=card.item_summary,
            status=initial_status,
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
            created_at=now,
            updated_at=now,
        )

        db_dict = return_card.to_db_dict()

        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO return_cards (
                    id, user_id, version, merchant, merchant_domain, item_summary,
                    status, confidence, source_email_ids, order_number, amount,
                    currency, order_date, delivery_date, return_by_date,
                    return_portal_link, shipping_tracking_link, evidence_snippet,
                    notes, created_at, updated_at, alerted_at
                ) VALUES (
                    :id, :user_id, :version, :merchant, :merchant_domain, :item_summary,
                    :status, :confidence, :source_email_ids, :order_number, :amount,
                    :currency, :order_date, :delivery_date, :return_by_date,
                    :return_portal_link, :shipping_tracking_link, :evidence_snippet,
                    :notes, :created_at, :updated_at, :alerted_at
                )
                """,
                db_dict,
            )

        logger.info("Created return card %s for user %s", card_id, card.user_id)
        return return_card

    @staticmethod
    def get_by_id(card_id: str) -> ReturnCard | None:
        """
        Get a return card by ID.

        Args:
            card_id: The card's unique identifier

        Returns:
            ReturnCard if found, None otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM return_cards WHERE id = ?",
                (card_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return ReturnCard.from_db_row(dict(row))

    @staticmethod
    def list_by_user(
        user_id: str,
        status: list[ReturnStatus] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReturnCard]:
        """
        List return cards for a user, optionally filtered by status.

        Args:
            user_id: User's identifier
            status: Optional list of statuses to filter by
            limit: Maximum number of cards to return
            offset: Number of cards to skip

        Returns:
            List of ReturnCard objects, ordered by return_by_date ASC (soonest first)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if status:
                status_values = [s.value if isinstance(s, ReturnStatus) else s for s in status]
                placeholders = ",".join("?" * len(status_values))
                cursor.execute(
                    f"""
                    SELECT * FROM return_cards
                    WHERE user_id = ? AND status IN ({placeholders})
                    ORDER BY
                        CASE WHEN return_by_date IS NULL THEN 1 ELSE 0 END,
                        return_by_date ASC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, *status_values, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM return_cards
                    WHERE user_id = ?
                    ORDER BY
                        CASE WHEN return_by_date IS NULL THEN 1 ELSE 0 END,
                        return_by_date ASC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, limit, offset),
                )

            rows = cursor.fetchall()

        return [ReturnCard.from_db_row(dict(row)) for row in rows]

    @staticmethod
    def list_expiring_soon(user_id: str, threshold_days: int = 7) -> list[ReturnCard]:
        """
        Get cards expiring within threshold days.

        Args:
            user_id: User's identifier
            threshold_days: Number of days to look ahead

        Returns:
            List of cards with return_by_date within threshold
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM return_cards
                WHERE user_id = ?
                  AND status IN ('active', 'expiring_soon')
                  AND return_by_date IS NOT NULL
                  AND date(return_by_date) <= date('now', '+' || ? || ' days')
                  AND date(return_by_date) >= date('now')
                ORDER BY return_by_date ASC
                """,
                (user_id, threshold_days),
            )
            rows = cursor.fetchall()

        return [ReturnCard.from_db_row(dict(row)) for row in rows]

    @staticmethod
    @retry_on_db_lock()
    def update_status(card_id: str, new_status: ReturnStatus) -> ReturnCard | None:
        """
        Update a card's status (mark returned, dismissed, etc.)

        Args:
            card_id: Card to update
            new_status: New status value

        Returns:
            Updated ReturnCard, or None if not found

        Side Effects:
            - Updates status and updated_at in return_cards table
            - Commits transaction
        """
        now = datetime.utcnow().isoformat()
        status_value = new_status.value if isinstance(new_status, ReturnStatus) else new_status

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE return_cards
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status_value, now, card_id),
            )

            if cursor.rowcount == 0:
                return None

        logger.info("Updated card %s status to %s", card_id, status_value)
        return ReturnCardRepository.get_by_id(card_id)

    @staticmethod
    @retry_on_db_lock()
    def update(card_id: str, updates: ReturnCardUpdate) -> ReturnCard | None:
        """
        Update a card with partial data.

        Args:
            card_id: Card to update
            updates: ReturnCardUpdate with fields to change

        Returns:
            Updated ReturnCard, or None if not found

        Side Effects:
            - Updates specified fields in return_cards table
            - Commits transaction
        """
        # Build SET clause from non-None fields
        update_data: dict[str, Any] = {}
        if updates.status is not None:
            update_data["status"] = updates.status.value if isinstance(updates.status, ReturnStatus) else updates.status
        if updates.notes is not None:
            update_data["notes"] = updates.notes
        if updates.return_by_date is not None:
            update_data["return_by_date"] = updates.return_by_date.isoformat()
        if updates.return_portal_link is not None:
            update_data["return_portal_link"] = updates.return_portal_link

        if not update_data:
            return ReturnCardRepository.get_by_id(card_id)

        update_data["updated_at"] = datetime.utcnow().isoformat()
        update_data["id"] = card_id

        set_clause = ", ".join(f"{k} = :{k}" for k in update_data if k != "id")

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE return_cards SET {set_clause} WHERE id = :id",
                update_data,
            )

            if cursor.rowcount == 0:
                return None

        logger.info("Updated card %s with fields: %s", card_id, list(update_data.keys()))
        return ReturnCardRepository.get_by_id(card_id)

    @staticmethod
    @retry_on_db_lock()
    def mark_alerted(card_id: str) -> bool:
        """
        Mark a card as having been alerted.

        Args:
            card_id: Card that was alerted

        Returns:
            True if updated, False if not found

        Side Effects:
            - Sets alerted_at timestamp in return_cards table
            - Commits transaction
        """
        now = datetime.utcnow().isoformat()

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE return_cards
                SET alerted_at = ?, updated_at = ?
                WHERE id = ? AND alerted_at IS NULL
                """,
                (now, now, card_id),
            )

            return cursor.rowcount > 0

    @staticmethod
    @retry_on_db_lock()
    def delete(card_id: str) -> bool:
        """
        Delete a return card.

        Args:
            card_id: Card to delete

        Returns:
            True if deleted, False if not found

        Side Effects:
            - Removes row from return_cards table
            - Commits transaction
        """
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM return_cards WHERE id = ?",
                (card_id,),
            )

            deleted = cursor.rowcount > 0

        if deleted:
            logger.info("Deleted return card %s", card_id)

        return deleted

    @staticmethod
    def find_by_email_id(user_id: str, email_id: str) -> ReturnCard | None:
        """
        Find a card that contains a specific email ID in its sources.

        Useful for deduplication - checking if we already have a card for this email.

        Args:
            user_id: User's identifier
            email_id: Gmail message ID to search for

        Returns:
            ReturnCard if found, None otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # JSON contains search (SQLite JSON1 extension)
            cursor.execute(
                """
                SELECT * FROM return_cards
                WHERE user_id = ?
                  AND json_valid(source_email_ids)
                  AND EXISTS (
                      SELECT 1 FROM json_each(source_email_ids)
                      WHERE json_each.value = ?
                  )
                LIMIT 1
                """,
                (user_id, email_id),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return ReturnCard.from_db_row(dict(row))

    @staticmethod
    @retry_on_db_lock()
    def refresh_statuses(user_id: str, threshold_days: int = 7) -> int:
        """
        Refresh status for all active cards based on current date.

        Updates cards from ACTIVE → EXPIRING_SOON → EXPIRED as time passes.

        Args:
            user_id: User whose cards to refresh
            threshold_days: Days before expiry to mark as expiring_soon

        Returns:
            Number of cards updated

        Side Effects:
            - Updates status for cards where return_by_date has passed thresholds
            - Commits transaction
        """
        now = datetime.utcnow().isoformat()
        updated_count = 0

        with db_transaction() as conn:
            cursor = conn.cursor()

            # Mark expired (past return_by_date)
            cursor.execute(
                """
                UPDATE return_cards
                SET status = 'expired', updated_at = ?
                WHERE user_id = ?
                  AND status IN ('active', 'expiring_soon')
                  AND return_by_date IS NOT NULL
                  AND date(return_by_date) < date('now')
                """,
                (now, user_id),
            )
            updated_count += cursor.rowcount

            # Mark expiring_soon (within threshold)
            cursor.execute(
                """
                UPDATE return_cards
                SET status = 'expiring_soon', updated_at = ?
                WHERE user_id = ?
                  AND status = 'active'
                  AND return_by_date IS NOT NULL
                  AND date(return_by_date) <= date('now', '+' || ? || ' days')
                  AND date(return_by_date) >= date('now')
                """,
                (now, user_id, threshold_days),
            )
            updated_count += cursor.rowcount

        if updated_count > 0:
            logger.info("Refreshed %d card statuses for user %s", updated_count, user_id)

        return updated_count

    @staticmethod
    def count_by_status(user_id: str) -> dict[str, int]:
        """
        Get count of cards by status for a user.

        Returns:
            Dict mapping status → count
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM return_cards
                WHERE user_id = ?
                GROUP BY status
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

        return {row["status"]: row["count"] for row in rows}
