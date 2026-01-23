"""
Return Card Repository - CRUD operations for return_cards table.

Follows the established database patterns in shopq/infrastructure/database.py.
"""

from __future__ import annotations

import uuid
from typing import Any

from shopq.infrastructure.database import db_transaction, get_db_connection, retry_on_db_lock
from shopq.observability.logging import get_logger
from shopq.returns.models import (
    ReturnCard,
    ReturnCardCreate,
    ReturnCardUpdate,
    ReturnStatus,
    utc_now,
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
        now = utc_now()

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
        now = utc_now().isoformat()
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
            update_data["status"] = (
                updates.status.value if isinstance(updates.status, ReturnStatus) else updates.status
            )
        if updates.notes is not None:
            update_data["notes"] = updates.notes
        if updates.return_by_date is not None:
            update_data["return_by_date"] = updates.return_by_date.isoformat()
        if updates.return_portal_link is not None:
            update_data["return_portal_link"] = updates.return_portal_link

        if not update_data:
            return ReturnCardRepository.get_by_id(card_id)

        update_data["updated_at"] = utc_now().isoformat()
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
        now = utc_now().isoformat()

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
    def find_by_order_key(
        user_id: str,
        merchant_domain: str,
        order_number: str | None = None,
        tracking_number: str | None = None,
    ) -> ReturnCard | None:
        """
        Find a card by order identity key (for deduplication).

        Per L2_order_deduplication_v1, order identity is:
        - merchant_domain + order_number
        - merchant_domain + tracking_number

        Args:
            user_id: User's identifier
            merchant_domain: Merchant domain (e.g., "amazon.com")
            order_number: Order ID/number
            tracking_number: Shipping tracking number

        Returns:
            ReturnCard if found, None otherwise
        """
        if not order_number and not tracking_number:
            return None

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Try order_number first (stronger match)
            if order_number:
                cursor.execute(
                    """
                    SELECT * FROM return_cards
                    WHERE user_id = ?
                      AND merchant_domain = ?
                      AND order_number = ?
                      AND status NOT IN ('dismissed')
                    LIMIT 1
                    """,
                    (user_id, merchant_domain, order_number),
                )
                row = cursor.fetchone()
                if row:
                    return ReturnCard.from_db_row(dict(row))

            # Try tracking_number as fallback
            if tracking_number:
                cursor.execute(
                    """
                    SELECT * FROM return_cards
                    WHERE user_id = ?
                      AND merchant_domain = ?
                      AND shipping_tracking_link LIKE ?
                      AND status NOT IN ('dismissed')
                    LIMIT 1
                    """,
                    (user_id, merchant_domain, f"%{tracking_number}%"),
                )
                row = cursor.fetchone()
                if row:
                    return ReturnCard.from_db_row(dict(row))

        return None

    @staticmethod
    @retry_on_db_lock()
    def merge_email_into_card(
        card_id: str,
        email_id: str,
        new_data: dict | None = None,
    ) -> ReturnCard | None:
        """
        Merge a new email into an existing card, updating with new data.

        This implements the entity-based approach where multiple emails about
        the same order are merged into ONE card, with status derived from
        the latest/best information.

        Update logic:
        - delivery_date: Use new value if existing is None
        - return_by_date: Recalculate if delivery_date updated
        - item_summary: Use new value if more detailed (longer)
        - evidence_snippet: Use new value if it contains return policy info

        Args:
            card_id: Card to update
            email_id: Email ID to add
            new_data: Optional dict with fields to potentially update:
                - delivery_date, order_date, return_by_date
                - item_summary, evidence_snippet
                - return_portal_link, shipping_tracking_link

        Returns:
            Updated ReturnCard, or None if not found
        """
        import json
        from datetime import datetime

        now = utc_now()
        now_str = now.isoformat()

        with db_transaction() as conn:
            cursor = conn.cursor()
            # Get current card data
            cursor.execute(
                "SELECT * FROM return_cards WHERE id = ?",
                (card_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            row_dict = dict(row)
            updates = {"updated_at": now_str}

            # Add email ID to source list
            current_ids = json.loads(row_dict["source_email_ids"]) if row_dict["source_email_ids"] else []
            if email_id not in current_ids:
                current_ids.append(email_id)
                updates["source_email_ids"] = json.dumps(current_ids)

            # Merge new data if provided
            if new_data:
                # Delivery date: Use new if existing is None (order → shipped → delivered progression)
                if new_data.get("delivery_date") and not row_dict.get("delivery_date"):
                    new_delivery = new_data["delivery_date"]
                    if isinstance(new_delivery, datetime):
                        updates["delivery_date"] = new_delivery.isoformat()
                    else:
                        updates["delivery_date"] = new_delivery
                    logger.info("Card %s: Updated delivery_date from new email", card_id)

                # Return-by date: Use new if existing is None or if we just got delivery_date
                if new_data.get("return_by_date") and (
                    not row_dict.get("return_by_date") or "delivery_date" in updates
                ):
                    new_return_by = new_data["return_by_date"]
                    if isinstance(new_return_by, datetime):
                        updates["return_by_date"] = new_return_by.isoformat()
                    else:
                        updates["return_by_date"] = new_return_by
                    logger.info("Card %s: Updated return_by_date from new email", card_id)

                # Item summary: Use new if longer (more detailed)
                if new_data.get("item_summary"):
                    existing_summary = row_dict.get("item_summary") or ""
                    new_summary = new_data["item_summary"]
                    if len(new_summary) > len(existing_summary):
                        updates["item_summary"] = new_summary

                # Evidence snippet: Prefer one with return policy keywords
                if new_data.get("evidence_snippet"):
                    new_evidence = new_data["evidence_snippet"].lower()
                    if any(kw in new_evidence for kw in ["return", "refund", "days", "policy"]):
                        updates["evidence_snippet"] = new_data["evidence_snippet"]

                # Links: Fill in if missing
                if new_data.get("return_portal_link") and not row_dict.get("return_portal_link"):
                    updates["return_portal_link"] = new_data["return_portal_link"]
                if new_data.get("shipping_tracking_link") and not row_dict.get("shipping_tracking_link"):
                    updates["shipping_tracking_link"] = new_data["shipping_tracking_link"]

            # Perform update
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [card_id]
                cursor.execute(
                    f"UPDATE return_cards SET {set_clause} WHERE id = ?",
                    values,
                )

        logger.info("Merged email %s into card %s (updated %d fields)", email_id, card_id, len(updates))
        return ReturnCardRepository.get_by_id(card_id)

    @staticmethod
    def find_by_item_summary(
        user_id: str,
        merchant_domain: str,
        item_summary: str,
    ) -> ReturnCard | None:
        """
        Find a card by merchant and item summary (fuzzy match for deduplication).

        Used when order_number isn't available (e.g., shipping/delivery emails).
        Matches if the first 30 chars of item_summary are the same.

        Args:
            user_id: User's identifier
            merchant_domain: Merchant domain (e.g., "amazon.com")
            item_summary: Item description to match

        Returns:
            ReturnCard if found, None otherwise
        """
        if not item_summary or len(item_summary) < 10:
            return None

        # Use first 30 chars for matching (handles slight variations)
        item_prefix = item_summary[:30]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM return_cards
                WHERE user_id = ?
                  AND merchant_domain = ?
                  AND item_summary LIKE ?
                  AND status NOT IN ('dismissed', 'returned')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, merchant_domain, f"{item_prefix}%"),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return ReturnCard.from_db_row(dict(row))

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
        now = utc_now().isoformat()
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
