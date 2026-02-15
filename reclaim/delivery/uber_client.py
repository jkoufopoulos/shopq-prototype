"""
Uber Direct API client for delivery requests.

MVP: Mock implementation that simulates Uber responses with realistic delays.
Production: Set UBER_DIRECT_MOCK=false and implement real OAuth + API calls.
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import timedelta
from uuid import uuid4

from reclaim.delivery.models import Address, DeliveryQuote, DeliveryStatus, utc_now
from reclaim.observability.logging import get_logger

logger = get_logger(__name__)


class UberDirectClient:
    """
    Uber Direct API client for delivery quotes and dispatching.

    In mock mode (default), returns simulated responses with realistic pricing.
    When UBER_DIRECT_MOCK=false, makes real API calls to Uber Direct.
    """

    def __init__(self):
        self.mock_mode = os.getenv("UBER_DIRECT_MOCK", "true").lower() == "true"
        self._mock_deliveries: dict[str, dict] = {}  # Track mock delivery states

        if self.mock_mode:
            logger.info("UberDirectClient initialized in MOCK mode")
        else:
            logger.info("UberDirectClient initialized for REAL API")
            # TODO: Initialize OAuth token manager when ready
            # self.client_id = os.environ["UBER_DIRECT_CLIENT_ID"]
            # self.client_secret = os.environ["UBER_DIRECT_CLIENT_SECRET"]
            # self.customer_id = os.environ["UBER_DIRECT_CUSTOMER_ID"]

    async def get_quote(
        self,
        pickup: Address,
        dropoff: Address,
    ) -> DeliveryQuote:
        """
        Request delivery quote from Uber.

        Args:
            pickup: Pickup address
            dropoff: Dropoff address

        Returns:
            DeliveryQuote with fee and time estimates

        Mock: Returns $12-18 estimate based on simulated distance.
        Real: POST /v1/customers/{id}/delivery_quotes
        """
        if self.mock_mode:
            return await self._mock_get_quote(pickup, dropoff)

        # TODO: Implement real Uber API call
        raise NotImplementedError("Real Uber API not yet implemented")

    async def create_delivery(
        self,
        quote_id: str,
        pickup: Address,
        dropoff: Address,
    ) -> dict:
        """
        Confirm quote and dispatch driver.

        Args:
            quote_id: Quote ID to confirm
            pickup: Pickup address (for API call)
            dropoff: Dropoff address (for API call)

        Returns:
            Dict with uber_delivery_id, tracking_url, fee_cents

        Mock: Returns pending delivery, simulates status progression.
        Real: POST /v1/customers/{id}/deliveries
        """
        if self.mock_mode:
            return await self._mock_create_delivery(quote_id)

        # TODO: Implement real Uber API call
        raise NotImplementedError("Real Uber API not yet implemented")

    async def get_delivery_status(self, uber_delivery_id: str) -> dict:
        """
        Get current delivery status from Uber.

        Args:
            uber_delivery_id: Uber's delivery ID

        Returns:
            Dict with status, driver_name, driver_phone, tracking_url, ETAs

        Mock: Returns simulated status progression.
        Real: GET /v1/customers/{id}/deliveries/{delivery_id}
        """
        if self.mock_mode:
            return await self._mock_get_status(uber_delivery_id)

        # TODO: Implement real Uber API call
        raise NotImplementedError("Real Uber API not yet implemented")

    async def cancel_delivery(self, uber_delivery_id: str) -> bool:
        """
        Cancel a pending delivery.

        Args:
            uber_delivery_id: Uber's delivery ID to cancel

        Returns:
            True if canceled successfully

        Mock: Always returns True for non-terminal deliveries.
        Real: POST /v1/customers/{id}/deliveries/{delivery_id}/cancel
        """
        if self.mock_mode:
            return await self._mock_cancel_delivery(uber_delivery_id)

        # TODO: Implement real Uber API call
        raise NotImplementedError("Real Uber API not yet implemented")

    # -------------------------------------------------------------------------
    # Mock implementations
    # -------------------------------------------------------------------------

    async def _mock_get_quote(
        self,
        pickup: Address,
        dropoff: Address,
    ) -> DeliveryQuote:
        """Generate realistic mock quote."""
        # Simulate API latency
        await asyncio.sleep(random.uniform(0.3, 0.8))

        # Base fee + variance (simulating distance-based pricing)
        base_fee = 1200  # $12.00
        variance = random.randint(0, 600)  # Up to $6.00 variance
        fee = base_fee + variance

        # If we have lat/lng, add distance-based fee
        if pickup.lat and pickup.lng and dropoff.lat and dropoff.lng:
            # Simple distance approximation (not real haversine)
            lat_diff = abs(pickup.lat - dropoff.lat)
            lng_diff = abs(pickup.lng - dropoff.lng)
            approx_miles = (lat_diff + lng_diff) * 69  # Rough conversion
            fee += int(approx_miles * 50)  # $0.50 per mile

        now = utc_now()
        quote = DeliveryQuote(
            quote_id=f"mock_quote_{uuid4().hex[:12]}",
            fee_cents=fee,
            estimated_pickup_time=now + timedelta(minutes=random.randint(10, 25)),
            estimated_dropoff_time=now + timedelta(minutes=random.randint(35, 55)),
            expires_at=now + timedelta(minutes=5),
        )

        logger.info("Generated mock quote: %s for $%.2f", quote.quote_id, fee / 100)
        return quote

    async def _mock_create_delivery(self, quote_id: str) -> dict:
        """Create mock delivery and start status simulation."""
        # Simulate API latency
        await asyncio.sleep(random.uniform(0.2, 0.5))

        uber_delivery_id = f"mock_delivery_{uuid4().hex[:12]}"
        now = utc_now()

        # Extract fee from quote_id if available, otherwise use default
        fee_cents = 1450  # Default $14.50

        # Store mock delivery state for status queries
        self._mock_deliveries[uber_delivery_id] = {
            "status": DeliveryStatus.PENDING.value,
            "created_at": now.isoformat(),
            "driver_name": None,
            "driver_phone": None,
            "fee_cents": fee_cents,
            # Simulate driver assignment in 1-3 minutes
            "driver_assign_time": (now + timedelta(minutes=random.randint(1, 3))).isoformat(),
            # Simulate pickup in 10-20 minutes
            "pickup_time": (now + timedelta(minutes=random.randint(10, 20))).isoformat(),
            # Simulate dropoff in 30-45 minutes
            "dropoff_time": (now + timedelta(minutes=random.randint(30, 45))).isoformat(),
        }

        tracking_url = f"https://track.uber.com/mock/{uber_delivery_id}"

        logger.info("Created mock delivery: %s", uber_delivery_id)

        return {
            "uber_delivery_id": uber_delivery_id,
            "tracking_url": tracking_url,
            "fee_cents": fee_cents,
            "status": DeliveryStatus.PENDING.value,
        }

    async def _mock_get_status(self, uber_delivery_id: str) -> dict:
        """Get mock delivery status with simulated progression."""
        # Simulate API latency
        await asyncio.sleep(random.uniform(0.1, 0.3))

        if uber_delivery_id not in self._mock_deliveries:
            # If not in cache, return a plausible state
            return {
                "status": DeliveryStatus.PENDING.value,
                "driver_name": None,
                "driver_phone": None,
                "tracking_url": f"https://track.uber.com/mock/{uber_delivery_id}",
                "pickup_eta": None,
                "dropoff_eta": None,
            }

        delivery = self._mock_deliveries[uber_delivery_id]
        now = utc_now()

        # Simulate status progression based on time
        from datetime import datetime

        driver_assign_time = datetime.fromisoformat(delivery["driver_assign_time"])
        pickup_time = datetime.fromisoformat(delivery["pickup_time"])
        dropoff_time = datetime.fromisoformat(delivery["dropoff_time"])

        if now >= dropoff_time:
            status = DeliveryStatus.DELIVERED.value
            driver_name = "Alex M."
            driver_phone = "+1-555-0123"
        elif now >= pickup_time:
            status = DeliveryStatus.DROPOFF.value
            driver_name = "Alex M."
            driver_phone = "+1-555-0123"
        elif now >= driver_assign_time:
            status = DeliveryStatus.PICKUP.value
            driver_name = "Alex M."
            driver_phone = "+1-555-0123"
        else:
            status = DeliveryStatus.PENDING.value
            driver_name = None
            driver_phone = None

        return {
            "status": status,
            "driver_name": driver_name,
            "driver_phone": driver_phone,
            "tracking_url": f"https://track.uber.com/mock/{uber_delivery_id}",
            "pickup_eta": pickup_time.isoformat() if status == DeliveryStatus.PICKUP.value else None,
            "dropoff_eta": dropoff_time.isoformat()
            if status in (DeliveryStatus.PICKUP.value, DeliveryStatus.DROPOFF.value)
            else None,
        }

    async def _mock_cancel_delivery(self, uber_delivery_id: str) -> bool:
        """Cancel mock delivery."""
        # Simulate API latency
        await asyncio.sleep(random.uniform(0.1, 0.3))

        if uber_delivery_id in self._mock_deliveries:
            delivery = self._mock_deliveries[uber_delivery_id]
            # Can't cancel if already delivered or canceled
            if delivery["status"] in (
                DeliveryStatus.DELIVERED.value,
                DeliveryStatus.CANCELED.value,
            ):
                logger.warning("Cannot cancel mock delivery %s: already %s", uber_delivery_id, delivery["status"])
                return False

            delivery["status"] = DeliveryStatus.CANCELED.value
            logger.info("Canceled mock delivery: %s", uber_delivery_id)

        return True


# Singleton instance
_client: UberDirectClient | None = None


def get_uber_client() -> UberDirectClient:
    """Get or create singleton UberDirectClient instance."""
    global _client
    if _client is None:
        _client = UberDirectClient()
    return _client
