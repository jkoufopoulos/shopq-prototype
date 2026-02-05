"""
Delivery domain models for Uber Direct integration.

These models represent delivery entities including quotes, addresses,
and delivery status tracking.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


class DeliveryStatus(str, Enum):
    """Status of a delivery in the pickup lifecycle."""

    QUOTE_PENDING = "quote_pending"  # Getting price quote from Uber
    QUOTED = "quoted"  # Quote ready, awaiting user confirmation
    PENDING = "pending"  # Confirmed, waiting for driver assignment
    PICKUP = "pickup"  # Driver en route to pickup location
    PICKUP_COMPLETE = "pickup_complete"  # Package picked up by driver
    DROPOFF = "dropoff"  # Driver en route to dropoff location
    DELIVERED = "delivered"  # Package delivered to carrier location
    CANCELED = "canceled"  # Delivery canceled by user or system
    FAILED = "failed"  # Delivery failed (driver issue, etc.)


class Address(BaseModel):
    """Physical address for pickup or dropoff."""

    model_config = ConfigDict(frozen=False)

    street: str = Field(..., description="Street address line")
    city: str = Field(..., description="City name")
    state: str = Field(..., description="State/province code (e.g., 'CA')")
    zip_code: str = Field(..., description="Postal/ZIP code")
    country: str = Field(default="US", description="Country code")
    lat: float | None = Field(default=None, description="Latitude coordinate")
    lng: float | None = Field(default=None, description="Longitude coordinate")

    def to_display_string(self) -> str:
        """Format address for display."""
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


class DeliveryQuote(BaseModel):
    """Price quote from Uber Direct for a delivery."""

    model_config = ConfigDict(frozen=False)

    quote_id: str = Field(..., description="Unique quote identifier")
    fee_cents: int = Field(..., description="Delivery fee in cents (e.g., 1200 = $12.00)")
    estimated_pickup_time: datetime = Field(..., description="Estimated driver arrival for pickup")
    estimated_dropoff_time: datetime = Field(..., description="Estimated delivery completion time")
    expires_at: datetime = Field(..., description="Quote expiry time (typically 5 minutes)")

    def is_expired(self) -> bool:
        """Check if quote has expired."""
        return utc_now() > self.expires_at

    def fee_dollars(self) -> float:
        """Get fee in dollars."""
        return self.fee_cents / 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON storage."""
        return {
            "quote_id": self.quote_id,
            "fee_cents": self.fee_cents,
            "estimated_pickup_time": self.estimated_pickup_time.isoformat(),
            "estimated_dropoff_time": self.estimated_dropoff_time.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeliveryQuote:
        """Create from dict (JSON storage)."""
        return cls(
            quote_id=data["quote_id"],
            fee_cents=data["fee_cents"],
            estimated_pickup_time=datetime.fromisoformat(data["estimated_pickup_time"]),
            estimated_dropoff_time=datetime.fromisoformat(data["estimated_dropoff_time"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )


class Delivery(BaseModel):
    """
    A delivery request for return package pickup.

    Tracks the full lifecycle from quote request through delivery completion.
    """

    model_config = ConfigDict(frozen=False, use_enum_values=True)

    # Identity
    id: str = Field(..., description="Internal delivery ID (UUID)")
    user_id: str = Field(..., description="User who requested the delivery")
    order_key: str = Field(..., description="Links to return card ID")

    # Uber integration
    uber_delivery_id: str | None = Field(
        default=None, description="Uber's delivery ID (after confirmation)"
    )
    status: DeliveryStatus = Field(default=DeliveryStatus.QUOTE_PENDING)

    # Addresses
    pickup_address: Address = Field(..., description="User's pickup address")
    dropoff_address: Address = Field(..., description="Carrier location address")
    dropoff_location_name: str = Field(
        default="", description="Carrier location name (e.g., 'UPS Store #1234')"
    )

    # Quote and payment
    quote: DeliveryQuote | None = Field(default=None, description="Price quote from Uber")
    fee_cents: int | None = Field(default=None, description="Final delivery fee in cents")

    # Driver information (populated after driver assignment)
    driver_name: str | None = Field(default=None)
    driver_phone: str | None = Field(default=None)
    tracking_url: str | None = Field(default=None, description="Live tracking URL")

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    pickup_eta: datetime | None = Field(default=None, description="Estimated pickup time")
    dropoff_eta: datetime | None = Field(default=None, description="Estimated dropoff time")
    completed_at: datetime | None = Field(default=None, description="When delivery completed")

    def is_active(self) -> bool:
        """Check if delivery is still in progress."""
        return self.status in (
            DeliveryStatus.QUOTED,
            DeliveryStatus.PENDING,
            DeliveryStatus.PICKUP,
            DeliveryStatus.PICKUP_COMPLETE,
            DeliveryStatus.DROPOFF,
        )

    def is_terminal(self) -> bool:
        """Check if delivery has reached a terminal state."""
        return self.status in (
            DeliveryStatus.DELIVERED,
            DeliveryStatus.CANCELED,
            DeliveryStatus.FAILED,
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dict for database storage."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "order_key": self.order_key,
            "uber_delivery_id": self.uber_delivery_id,
            "status": self.status if isinstance(self.status, str) else self.status.value,
            "pickup_address": json.dumps(self.pickup_address.model_dump()),
            "dropoff_address": json.dumps(self.dropoff_address.model_dump()),
            "dropoff_location_name": self.dropoff_location_name,
            "quote_json": json.dumps(self.quote.to_dict()) if self.quote else None,
            "fee_cents": self.fee_cents,
            "driver_name": self.driver_name,
            "driver_phone": self.driver_phone,
            "tracking_url": self.tracking_url,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "pickup_eta": self.pickup_eta.isoformat() if self.pickup_eta else None,
            "dropoff_eta": self.dropoff_eta.isoformat() if self.dropoff_eta else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> Delivery:
        """Create Delivery from database row."""

        def parse_dt(val: str | None) -> datetime | None:
            if val is None:
                return None
            return datetime.fromisoformat(val)

        # Parse JSON fields
        pickup_address = Address(**json.loads(row["pickup_address"]))
        dropoff_address = Address(**json.loads(row["dropoff_address"]))
        quote = (
            DeliveryQuote.from_dict(json.loads(row["quote_json"]))
            if row.get("quote_json")
            else None
        )

        return cls(
            id=row["id"],
            user_id=row["user_id"],
            order_key=row["order_key"],
            uber_delivery_id=row.get("uber_delivery_id"),
            status=DeliveryStatus(row["status"]),
            pickup_address=pickup_address,
            dropoff_address=dropoff_address,
            dropoff_location_name=row.get("dropoff_location_name", ""),
            quote=quote,
            fee_cents=row.get("fee_cents"),
            driver_name=row.get("driver_name"),
            driver_phone=row.get("driver_phone"),
            tracking_url=row.get("tracking_url"),
            created_at=parse_dt(row.get("created_at")) or utc_now(),
            updated_at=parse_dt(row.get("updated_at")) or utc_now(),
            pickup_eta=parse_dt(row.get("pickup_eta")),
            dropoff_eta=parse_dt(row.get("dropoff_eta")),
            completed_at=parse_dt(row.get("completed_at")),
        )


# Request/Response models for API
class QuoteRequest(BaseModel):
    """Request to get a delivery quote."""

    order_key: str = Field(..., description="Return card ID to schedule delivery for")
    pickup_address: Address = Field(..., description="User's pickup address")
    dropoff_location_id: str = Field(..., description="Carrier location ID from locations list")


class QuoteResponse(BaseModel):
    """Response with delivery quote details."""

    delivery_id: str = Field(..., description="Internal delivery ID")
    quote_id: str = Field(..., description="Quote ID to confirm")
    fee_cents: int = Field(..., description="Delivery fee in cents")
    fee_display: str = Field(..., description="Formatted fee (e.g., '$14.50')")
    estimated_pickup_time: datetime
    estimated_dropoff_time: datetime
    expires_at: datetime
    pickup_address: Address
    dropoff_address: Address
    dropoff_location_name: str


class ConfirmRequest(BaseModel):
    """Request to confirm a quote and dispatch driver."""

    delivery_id: str = Field(..., description="Delivery ID from quote response")


class DeliveryResponse(BaseModel):
    """Response with delivery status details."""

    id: str
    order_key: str
    status: str
    fee_cents: int | None = None
    fee_display: str | None = None
    driver_name: str | None = None
    driver_phone: str | None = None
    tracking_url: str | None = None
    pickup_address: Address
    dropoff_address: Address
    dropoff_location_name: str
    pickup_eta: datetime | None = None
    dropoff_eta: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CarrierLocation(BaseModel):
    """A carrier drop-off location (UPS Store, FedEx Office, etc.)."""

    id: str = Field(..., description="Unique location identifier")
    name: str = Field(..., description="Location name (e.g., 'The UPS Store')")
    carrier: str = Field(..., description="Carrier name (UPS, FedEx)")
    address: Address
    hours: str = Field(default="", description="Operating hours")
    distance_miles: float | None = Field(default=None, description="Distance from user (computed)")
