"""
Delivery Repository - CRUD operations for deliveries table.

Follows the established database patterns in reclaim/infrastructure/database.py.
"""

from __future__ import annotations

import uuid

from reclaim.delivery.models import (
    Address,
    Delivery,
    DeliveryQuote,
    DeliveryStatus,
    utc_now,
)
from reclaim.infrastructure.database import db_transaction, get_db_connection, retry_on_db_lock
from reclaim.observability.logging import get_logger

logger = get_logger(__name__)


class DeliveryRepository:
    """
    Repository for Delivery CRUD operations.

    All methods use connection pooling and proper transaction handling.
    """

    @staticmethod
    @retry_on_db_lock()
    def create(
        user_id: str,
        order_key: str,
        pickup_address: Address,
        dropoff_address: Address,
        dropoff_location_name: str = "",
    ) -> Delivery:
        """
        Create a new delivery record in quote_pending state.

        Args:
            user_id: User requesting the delivery
            order_key: Return card ID this delivery is for
            pickup_address: User's pickup address
            dropoff_address: Carrier location address
            dropoff_location_name: Name of the carrier location

        Returns:
            Created Delivery with generated id

        Side Effects:
            - Inserts row into deliveries table
            - Commits transaction
        """
        delivery_id = str(uuid.uuid4())
        now = utc_now()

        delivery = Delivery(
            id=delivery_id,
            user_id=user_id,
            order_key=order_key,
            status=DeliveryStatus.QUOTE_PENDING,
            pickup_address=pickup_address,
            dropoff_address=dropoff_address,
            dropoff_location_name=dropoff_location_name,
            created_at=now,
            updated_at=now,
        )

        db_dict = delivery.to_db_dict()

        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO deliveries (
                    id, user_id, order_key, uber_delivery_id, status,
                    pickup_address, dropoff_address, dropoff_location_name,
                    quote_json, fee_cents, driver_name, driver_phone, tracking_url,
                    created_at, updated_at, pickup_eta, dropoff_eta, completed_at
                ) VALUES (
                    :id, :user_id, :order_key, :uber_delivery_id, :status,
                    :pickup_address, :dropoff_address, :dropoff_location_name,
                    :quote_json, :fee_cents, :driver_name, :driver_phone, :tracking_url,
                    :created_at, :updated_at, :pickup_eta, :dropoff_eta, :completed_at
                )
                """,
                db_dict,
            )

        logger.info("Created delivery %s for order %s", delivery_id, order_key)
        return delivery

    @staticmethod
    def get_by_id(delivery_id: str) -> Delivery | None:
        """
        Get a delivery by ID.

        Args:
            delivery_id: The delivery's unique identifier

        Returns:
            Delivery if found, None otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM deliveries WHERE id = ?",
                (delivery_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return Delivery.from_db_row(dict(row))

    @staticmethod
    def get_by_uber_id(uber_delivery_id: str) -> Delivery | None:
        """
        Get a delivery by Uber's delivery ID.

        Used for webhook processing.

        Args:
            uber_delivery_id: Uber's delivery identifier

        Returns:
            Delivery if found, None otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM deliveries WHERE uber_delivery_id = ?",
                (uber_delivery_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return Delivery.from_db_row(dict(row))

    @staticmethod
    def get_by_order_key(order_key: str) -> Delivery | None:
        """
        Get the most recent delivery for a return card.

        Args:
            order_key: Return card ID

        Returns:
            Most recent Delivery if found, None otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM deliveries
                WHERE order_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (order_key,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return Delivery.from_db_row(dict(row))

    @staticmethod
    def list_active_by_user(user_id: str) -> list[Delivery]:
        """
        List all active deliveries for a user.

        Active = quoted, pending, pickup, pickup_complete, dropoff

        Args:
            user_id: User's identifier

        Returns:
            List of active Delivery objects
        """
        active_statuses = [
            DeliveryStatus.QUOTED.value,
            DeliveryStatus.PENDING.value,
            DeliveryStatus.PICKUP.value,
            DeliveryStatus.PICKUP_COMPLETE.value,
            DeliveryStatus.DROPOFF.value,
        ]
        placeholders = ",".join("?" * len(active_statuses))

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT * FROM deliveries
                WHERE user_id = ? AND status IN ({placeholders})
                ORDER BY created_at DESC
                """,
                (user_id, *active_statuses),
            )
            rows = cursor.fetchall()

        return [Delivery.from_db_row(dict(row)) for row in rows]

    @staticmethod
    def list_by_user(
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Delivery]:
        """
        List all deliveries for a user.

        Args:
            user_id: User's identifier
            limit: Maximum number of deliveries to return
            offset: Number of deliveries to skip

        Returns:
            List of Delivery objects, ordered by created_at DESC
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM deliveries
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            )
            rows = cursor.fetchall()

        return [Delivery.from_db_row(dict(row)) for row in rows]

    @staticmethod
    @retry_on_db_lock()
    def update_with_quote(
        delivery_id: str,
        quote: DeliveryQuote,
    ) -> Delivery | None:
        """
        Update delivery with quote from Uber.

        Args:
            delivery_id: Delivery to update
            quote: Quote received from Uber

        Returns:
            Updated Delivery, or None if not found

        Side Effects:
            - Updates quote_json, status, pickup_eta, dropoff_eta in deliveries table
            - Commits transaction
        """
        import json

        now = utc_now().isoformat()
        quote_json = json.dumps(quote.to_dict())

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE deliveries
                SET quote_json = ?,
                    status = ?,
                    pickup_eta = ?,
                    dropoff_eta = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    quote_json,
                    DeliveryStatus.QUOTED.value,
                    quote.estimated_pickup_time.isoformat(),
                    quote.estimated_dropoff_time.isoformat(),
                    now,
                    delivery_id,
                ),
            )

            if cursor.rowcount == 0:
                return None

        logger.info("Updated delivery %s with quote %s", delivery_id, quote.quote_id)
        return DeliveryRepository.get_by_id(delivery_id)

    @staticmethod
    @retry_on_db_lock()
    def confirm_delivery(
        delivery_id: str,
        uber_delivery_id: str,
        fee_cents: int,
        tracking_url: str | None = None,
    ) -> Delivery | None:
        """
        Confirm a delivery after user accepts quote.

        Args:
            delivery_id: Delivery to confirm
            uber_delivery_id: Uber's delivery ID
            fee_cents: Final fee charged
            tracking_url: Optional tracking URL

        Returns:
            Updated Delivery, or None if not found

        Side Effects:
            - Updates uber_delivery_id, status, fee_cents, tracking_url in deliveries table
            - Commits transaction
        """
        now = utc_now().isoformat()

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE deliveries
                SET uber_delivery_id = ?,
                    status = ?,
                    fee_cents = ?,
                    tracking_url = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    uber_delivery_id,
                    DeliveryStatus.PENDING.value,
                    fee_cents,
                    tracking_url,
                    now,
                    delivery_id,
                ),
            )

            if cursor.rowcount == 0:
                return None

        logger.info(
            "Confirmed delivery %s -> uber_id %s, fee %d cents",
            delivery_id,
            uber_delivery_id,
            fee_cents,
        )
        return DeliveryRepository.get_by_id(delivery_id)

    @staticmethod
    @retry_on_db_lock()
    def update_status(
        delivery_id: str,
        new_status: DeliveryStatus,
        driver_name: str | None = None,
        driver_phone: str | None = None,
        tracking_url: str | None = None,
        pickup_eta: str | None = None,
        dropoff_eta: str | None = None,
    ) -> Delivery | None:
        """
        Update delivery status and optional driver info.

        Args:
            delivery_id: Delivery to update
            new_status: New status value
            driver_name: Driver name (optional)
            driver_phone: Driver phone (optional)
            tracking_url: Updated tracking URL (optional)
            pickup_eta: Updated pickup ETA (optional)
            dropoff_eta: Updated dropoff ETA (optional)

        Returns:
            Updated Delivery, or None if not found

        Side Effects:
            - Updates status and related fields in deliveries table
            - Sets completed_at for terminal states
            - Commits transaction
        """
        now = utc_now()
        now_str = now.isoformat()

        updates = {
            "status": new_status.value,
            "updated_at": now_str,
        }

        if driver_name is not None:
            updates["driver_name"] = driver_name
        if driver_phone is not None:
            updates["driver_phone"] = driver_phone
        if tracking_url is not None:
            updates["tracking_url"] = tracking_url
        if pickup_eta is not None:
            updates["pickup_eta"] = pickup_eta
        if dropoff_eta is not None:
            updates["dropoff_eta"] = dropoff_eta

        # Set completed_at for terminal states
        if new_status in (
            DeliveryStatus.DELIVERED,
            DeliveryStatus.CANCELED,
            DeliveryStatus.FAILED,
        ):
            updates["completed_at"] = now_str

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [delivery_id]

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE deliveries SET {set_clause} WHERE id = ?",
                values,
            )

            if cursor.rowcount == 0:
                return None

        logger.info("Updated delivery %s status to %s", delivery_id, new_status.value)
        return DeliveryRepository.get_by_id(delivery_id)

    @staticmethod
    @retry_on_db_lock()
    def cancel(delivery_id: str) -> Delivery | None:
        """
        Cancel a delivery.

        Args:
            delivery_id: Delivery to cancel

        Returns:
            Updated Delivery, or None if not found

        Side Effects:
            - Updates status to canceled, sets completed_at
            - Commits transaction
        """
        return DeliveryRepository.update_status(delivery_id, DeliveryStatus.CANCELED)

    @staticmethod
    @retry_on_db_lock()
    def delete(delivery_id: str) -> bool:
        """
        Delete a delivery record.

        Args:
            delivery_id: Delivery to delete

        Returns:
            True if deleted, False if not found

        Side Effects:
            - Removes row from deliveries table
            - Commits transaction
        """
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM deliveries WHERE id = ?",
                (delivery_id,),
            )

            deleted = cursor.rowcount > 0

        if deleted:
            logger.info("Deleted delivery %s", delivery_id)

        return deleted
