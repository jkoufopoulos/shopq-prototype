"""
Delivery Service - Business logic for return package pickups.

Orchestrates between:
- DeliveryRepository (persistence)
- UberDirectClient (delivery API)
- CarrierLocations (drop-off points)
"""

from __future__ import annotations

from reclaim.delivery.carrier_locations import get_location_by_id, get_nearby_locations
from reclaim.delivery.models import (
    Address,
    CarrierLocation,
    ConfirmRequest,
    Delivery,
    DeliveryResponse,
    DeliveryStatus,
    QuoteRequest,
    QuoteResponse,
)
from reclaim.delivery.repository import DeliveryRepository
from reclaim.delivery.uber_client import get_uber_client
from reclaim.observability.logging import get_logger

logger = get_logger(__name__)


class DeliveryServiceError(Exception):
    """Base exception for delivery service errors."""

    pass


class QuoteExpiredError(DeliveryServiceError):
    """Quote has expired."""

    pass


class DeliveryNotFoundError(DeliveryServiceError):
    """Delivery not found."""

    pass


class InvalidStateError(DeliveryServiceError):
    """Delivery is in invalid state for operation."""

    pass


class LocationNotFoundError(DeliveryServiceError):
    """Carrier location not found."""

    pass


class DeliveryService:
    """
    Service layer for delivery operations.

    Handles quote requests, confirmations, status updates, and cancellations.
    """

    def __init__(self):
        self.repository = DeliveryRepository
        self.uber_client = get_uber_client()

    async def get_quote(
        self,
        user_id: str,
        request: QuoteRequest,
    ) -> QuoteResponse:
        """
        Get a delivery quote for a return pickup.

        Args:
            user_id: User requesting the quote
            request: Quote request with addresses and location

        Returns:
            QuoteResponse with pricing and time estimates

        Raises:
            LocationNotFoundError: If dropoff location not found
        """
        # Get carrier location
        carrier_location = get_location_by_id(request.dropoff_location_id)
        if not carrier_location:
            raise LocationNotFoundError(f"Location not found: {request.dropoff_location_id}")

        # Create delivery record in quote_pending state
        delivery = self.repository.create(
            user_id=user_id,
            order_key=request.order_key,
            pickup_address=request.pickup_address,
            dropoff_address=carrier_location.address,
            dropoff_location_name=f"{carrier_location.name} - {carrier_location.address.city}",
        )

        # Get quote from Uber
        quote = await self.uber_client.get_quote(
            pickup=request.pickup_address,
            dropoff=carrier_location.address,
        )

        # Update delivery with quote
        updated_delivery = self.repository.update_with_quote(delivery.id, quote)
        if not updated_delivery:
            raise DeliveryServiceError(f"Failed to update delivery {delivery.id} with quote")

        # Format fee for display
        fee_display = f"${quote.fee_cents / 100:.2f}"

        logger.info(
            "Generated quote for user %s: delivery %s, fee %s",
            user_id,
            delivery.id,
            fee_display,
        )

        return QuoteResponse(
            delivery_id=delivery.id,
            quote_id=quote.quote_id,
            fee_cents=quote.fee_cents,
            fee_display=fee_display,
            estimated_pickup_time=quote.estimated_pickup_time,
            estimated_dropoff_time=quote.estimated_dropoff_time,
            expires_at=quote.expires_at,
            pickup_address=request.pickup_address,
            dropoff_address=carrier_location.address,
            dropoff_location_name=f"{carrier_location.name} - {carrier_location.address.city}",
        )

    async def confirm_delivery(
        self,
        user_id: str,
        request: ConfirmRequest,
    ) -> DeliveryResponse:
        """
        Confirm quote and dispatch driver.

        Args:
            user_id: User confirming the delivery
            request: Confirmation request with delivery ID

        Returns:
            DeliveryResponse with tracking info

        Raises:
            DeliveryNotFoundError: If delivery not found
            InvalidStateError: If delivery not in QUOTED state
            QuoteExpiredError: If quote has expired
        """
        # Get delivery
        delivery = self.repository.get_by_id(request.delivery_id)
        if not delivery:
            raise DeliveryNotFoundError(f"Delivery not found: {request.delivery_id}")

        # Verify ownership
        if delivery.user_id != user_id:
            raise DeliveryNotFoundError(f"Delivery not found: {request.delivery_id}")

        # Verify state
        if delivery.status != DeliveryStatus.QUOTED:
            raise InvalidStateError(
                f"Delivery {request.delivery_id} is in state {delivery.status}, expected QUOTED"
            )

        # Check quote expiry
        if delivery.quote and delivery.quote.is_expired():
            raise QuoteExpiredError(f"Quote for delivery {request.delivery_id} has expired")

        # Create delivery with Uber
        uber_result = await self.uber_client.create_delivery(
            quote_id=delivery.quote.quote_id if delivery.quote else "",
            pickup=delivery.pickup_address,
            dropoff=delivery.dropoff_address,
        )

        # Update our record
        updated_delivery = self.repository.confirm_delivery(
            delivery_id=request.delivery_id,
            uber_delivery_id=uber_result["uber_delivery_id"],
            fee_cents=uber_result["fee_cents"],
            tracking_url=uber_result.get("tracking_url"),
        )

        if not updated_delivery:
            raise DeliveryServiceError(f"Failed to confirm delivery {request.delivery_id}")

        logger.info(
            "Confirmed delivery %s for user %s, uber_id %s",
            request.delivery_id,
            user_id,
            uber_result["uber_delivery_id"],
        )

        return self._to_response(updated_delivery)

    async def get_delivery(
        self,
        user_id: str,
        delivery_id: str,
    ) -> DeliveryResponse:
        """
        Get delivery status.

        Args:
            user_id: User requesting status
            delivery_id: Delivery to get

        Returns:
            DeliveryResponse with current status

        Raises:
            DeliveryNotFoundError: If delivery not found or wrong user
        """
        delivery = self.repository.get_by_id(delivery_id)
        if not delivery or delivery.user_id != user_id:
            raise DeliveryNotFoundError(f"Delivery not found: {delivery_id}")

        # If delivery is active and has uber_delivery_id, fetch latest status
        if delivery.is_active() and delivery.uber_delivery_id:
            try:
                uber_status = await self.uber_client.get_delivery_status(delivery.uber_delivery_id)

                # Update local record if status changed
                new_status = DeliveryStatus(uber_status["status"])
                if new_status != delivery.status:
                    delivery = self.repository.update_status(
                        delivery_id=delivery.id,
                        new_status=new_status,
                        driver_name=uber_status.get("driver_name"),
                        driver_phone=uber_status.get("driver_phone"),
                        tracking_url=uber_status.get("tracking_url"),
                        pickup_eta=uber_status.get("pickup_eta"),
                        dropoff_eta=uber_status.get("dropoff_eta"),
                    )
            except Exception as e:
                logger.warning("Failed to fetch Uber status for %s: %s", delivery_id, e)

        return self._to_response(delivery)

    async def get_delivery_for_order(
        self,
        user_id: str,
        order_key: str,
    ) -> DeliveryResponse | None:
        """
        Get the most recent delivery for a return card.

        Args:
            user_id: User requesting status
            order_key: Return card ID

        Returns:
            DeliveryResponse if found, None otherwise
        """
        delivery = self.repository.get_by_order_key(order_key)
        if not delivery or delivery.user_id != user_id:
            return None

        return self._to_response(delivery)

    async def cancel_delivery(
        self,
        user_id: str,
        delivery_id: str,
    ) -> bool:
        """
        Cancel a pending delivery.

        Args:
            user_id: User requesting cancellation
            delivery_id: Delivery to cancel

        Returns:
            True if canceled

        Raises:
            DeliveryNotFoundError: If delivery not found or wrong user
            InvalidStateError: If delivery cannot be canceled
        """
        delivery = self.repository.get_by_id(delivery_id)
        if not delivery or delivery.user_id != user_id:
            raise DeliveryNotFoundError(f"Delivery not found: {delivery_id}")

        # Can only cancel active deliveries
        if delivery.is_terminal():
            raise InvalidStateError(
                f"Delivery {delivery_id} is in terminal state {delivery.status}"
            )

        # Cancel with Uber if confirmed
        if delivery.uber_delivery_id:
            try:
                await self.uber_client.cancel_delivery(delivery.uber_delivery_id)
            except Exception as e:
                logger.error("Failed to cancel with Uber: %s", e)
                # Continue to update our record anyway

        # Update our record
        result = self.repository.cancel(delivery_id)

        logger.info("Canceled delivery %s for user %s", delivery_id, user_id)

        return result is not None

    async def list_active_deliveries(
        self,
        user_id: str,
    ) -> list[DeliveryResponse]:
        """
        List all active deliveries for a user.

        Args:
            user_id: User to list deliveries for

        Returns:
            List of active DeliveryResponse objects
        """
        deliveries = self.repository.list_active_by_user(user_id)
        return [self._to_response(d) for d in deliveries]

    def get_nearby_locations(
        self,
        lat: float,
        lng: float,
        limit: int = 5,
        carrier: str | None = None,
    ) -> list[CarrierLocation]:
        """
        Get carrier locations near a point.

        Args:
            lat: Latitude
            lng: Longitude
            limit: Maximum locations to return
            carrier: Optional carrier filter ("UPS" or "FedEx")

        Returns:
            List of CarrierLocation sorted by distance
        """
        return get_nearby_locations(lat, lng, limit=limit, carrier=carrier)

    def _to_response(self, delivery: Delivery) -> DeliveryResponse:
        """Convert Delivery to DeliveryResponse."""
        fee_display = f"${delivery.fee_cents / 100:.2f}" if delivery.fee_cents else None

        return DeliveryResponse(
            id=delivery.id,
            order_key=delivery.order_key,
            status=delivery.status if isinstance(delivery.status, str) else delivery.status.value,
            fee_cents=delivery.fee_cents,
            fee_display=fee_display,
            driver_name=delivery.driver_name,
            driver_phone=delivery.driver_phone,
            tracking_url=delivery.tracking_url,
            pickup_address=delivery.pickup_address,
            dropoff_address=delivery.dropoff_address,
            dropoff_location_name=delivery.dropoff_location_name,
            pickup_eta=delivery.pickup_eta,
            dropoff_eta=delivery.dropoff_eta,
            created_at=delivery.created_at,
            updated_at=delivery.updated_at,
        )


# Singleton instance
_service: DeliveryService | None = None


def get_delivery_service() -> DeliveryService:
    """Get or create singleton DeliveryService instance."""
    global _service
    if _service is None:
        _service = DeliveryService()
    return _service
