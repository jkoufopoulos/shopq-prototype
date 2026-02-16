"""
Return Card domain models for Reclaim Return Watch.

These models represent tracked returns with their status, confidence levels,
and associated metadata extracted from emails.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


class ReturnStatus(str, Enum):
    """Status of a return card in the tracking lifecycle."""

    ACTIVE = "active"  # Return window open, not expiring soon
    EXPIRING_SOON = "expiring_soon"  # Within threshold (default 7 days)
    EXPIRED = "expired"  # Past return-by date
    RETURNED = "returned"  # User marked as returned
    DISMISSED = "dismissed"  # User dismissed (doesn't want to track)


class ReturnConfidence(str, Enum):
    """Confidence level for return-by date."""

    EXACT = "exact"  # Explicit return-by date found in email
    ESTIMATED = "estimated"  # Calculated from merchant rules + anchor date
    UNKNOWN = "unknown"  # No date info available


class ReturnCard(BaseModel):
    """
    A tracked return with all relevant information.

    This is the core domain model for Return Watch. Each card represents
    a potential return extracted from order/delivery emails.
    """

    model_config = ConfigDict(frozen=False, use_enum_values=True)

    # Identity
    id: str = Field(..., description="Unique identifier (UUID)")
    user_id: str = Field(..., description="User who owns this card")
    version: str = Field(default="v1", description="Schema version")

    # Required fields (from PRD)
    merchant: str = Field(..., description="Merchant name (e.g., 'Amazon', 'Target')")
    merchant_domain: str = Field(default="", description="Merchant email domain for rule matching")
    item_summary: str = Field(..., description="Brief description of item(s)")
    status: ReturnStatus = Field(default=ReturnStatus.ACTIVE)
    confidence: ReturnConfidence = Field(default=ReturnConfidence.UNKNOWN)
    source_email_ids: list[str] = Field(default_factory=list, description="Gmail message IDs")

    # Optional fields
    order_number: str | None = Field(default=None)
    tracking_number: str | None = Field(default=None, description="Shipping tracking number")
    amount: float | None = Field(default=None, description="Purchase amount")
    currency: str = Field(default="USD")
    order_date: datetime | None = Field(default=None)
    delivery_date: datetime | None = Field(default=None)
    return_by_date: datetime | None = Field(default=None)
    return_portal_link: str | None = Field(
        default=None, description="URL to merchant return portal"
    )
    shipping_tracking_link: str | None = Field(default=None)
    evidence_snippet: str | None = Field(
        default=None, description="Key text from email (for provenance)"
    )
    notes: str | None = Field(default=None, description="User notes")

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Alert tracking
    alerted_at: datetime | None = Field(default=None, description="When user was first alerted")

    @field_validator("merchant")
    @classmethod
    def merchant_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("merchant cannot be empty")
        return v.strip()

    @field_validator("item_summary")
    @classmethod
    def item_summary_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("item_summary cannot be empty")
        return v.strip()

    @model_validator(mode="after")
    def validate_version(self) -> ReturnCard:
        if self.version != "v1":
            raise ValueError("ReturnCard version must be 'v1'")
        return self

    def is_alertable(self) -> bool:
        """
        Check if this card should trigger an alert.

        Per PRD: Only alert for exact/estimated confidence, never unknown.
        Only alert for active/expiring_soon status.
        """
        if self.confidence == ReturnConfidence.UNKNOWN:
            return False
        if self.status not in (ReturnStatus.ACTIVE, ReturnStatus.EXPIRING_SOON):
            return False
        return self.alerted_at is None

    def days_until_expiry(self) -> int | None:
        """Calculate days remaining until return window closes."""
        if self.return_by_date is None:
            return None
        # Ensure comparison is timezone-aware
        return_date = self.return_by_date
        if return_date.tzinfo is None:
            return_date = return_date.replace(tzinfo=UTC)
        delta = return_date - utc_now()
        return max(0, delta.days)

    def compute_status(self, threshold_days: int = 7) -> ReturnStatus:
        """
        Compute status based on return_by_date and threshold.

        Does NOT update self.status - returns computed value for comparison.

        Args:
            threshold_days: Days before expiry to mark as expiring_soon

        Returns:
            Computed ReturnStatus
        """
        # Terminal states don't change
        if self.status in (ReturnStatus.RETURNED, ReturnStatus.DISMISSED):
            return self.status

        # No date = stay active (unknown confidence)
        if self.return_by_date is None:
            return ReturnStatus.ACTIVE

        days = self.days_until_expiry()
        if days is None:
            return ReturnStatus.ACTIVE

        if days <= 0:
            return ReturnStatus.EXPIRED
        if days <= threshold_days:
            return ReturnStatus.EXPIRING_SOON
        return ReturnStatus.ACTIVE



class ReturnCardCreate(BaseModel):
    """Input model for creating a new ReturnCard (without id/timestamps)."""

    model_config = ConfigDict(use_enum_values=True)

    user_id: str
    merchant: str
    merchant_domain: str = ""
    item_summary: str
    confidence: ReturnConfidence = ReturnConfidence.UNKNOWN
    source_email_ids: list[str] = Field(default_factory=list)

    # Optional
    order_number: str | None = None
    tracking_number: str | None = None
    amount: float | None = None
    currency: str = "USD"
    order_date: datetime | None = None
    delivery_date: datetime | None = None
    return_by_date: datetime | None = None
    return_portal_link: str | None = None
    shipping_tracking_link: str | None = None
    evidence_snippet: str | None = None


class ReturnCardUpdate(BaseModel):
    """Input model for updating a ReturnCard (all fields optional)."""

    model_config = ConfigDict(use_enum_values=True)

    status: ReturnStatus | None = None
    notes: str | None = None
    return_by_date: datetime | None = None
    return_portal_link: str | None = None
