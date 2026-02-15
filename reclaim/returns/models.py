"""
Return Card domain models for Reclaim Return Watch.

These models represent tracked returns with their status, confidence levels,
and associated metadata extracted from emails.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

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

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dict for database storage."""
        import json

        return {
            "id": self.id,
            "user_id": self.user_id,
            "version": self.version,
            "merchant": self.merchant,
            "merchant_domain": self.merchant_domain,
            "item_summary": self.item_summary,
            "status": self.status if isinstance(self.status, str) else self.status.value,
            "confidence": self.confidence
            if isinstance(self.confidence, str)
            else self.confidence.value,
            "source_email_ids": json.dumps(self.source_email_ids),
            "order_number": self.order_number,
            "tracking_number": self.tracking_number,
            "amount": self.amount,
            "currency": self.currency,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "delivery_date": self.delivery_date.isoformat() if self.delivery_date else None,
            "return_by_date": self.return_by_date.isoformat() if self.return_by_date else None,
            "return_portal_link": self.return_portal_link,
            "shipping_tracking_link": self.shipping_tracking_link,
            "evidence_snippet": self.evidence_snippet,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "alerted_at": self.alerted_at.isoformat() if self.alerted_at else None,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> ReturnCard:
        """Create ReturnCard from database row."""
        import json

        def parse_dt(val: str | None) -> datetime | None:
            if val is None:
                return None
            return datetime.fromisoformat(val)

        return cls(
            id=row["id"],
            user_id=row["user_id"],
            version=row.get("version", "v1"),
            merchant=row["merchant"],
            merchant_domain=row.get("merchant_domain", ""),
            item_summary=row["item_summary"],
            status=ReturnStatus(row["status"]),
            confidence=ReturnConfidence(row["confidence"]),
            source_email_ids=json.loads(row["source_email_ids"]) if row["source_email_ids"] else [],
            order_number=row.get("order_number"),
            tracking_number=row.get("tracking_number"),
            amount=row.get("amount"),
            currency=row.get("currency", "USD"),
            order_date=parse_dt(row.get("order_date")),
            delivery_date=parse_dt(row.get("delivery_date")),
            return_by_date=parse_dt(row.get("return_by_date")),
            return_portal_link=row.get("return_portal_link"),
            shipping_tracking_link=row.get("shipping_tracking_link"),
            evidence_snippet=row.get("evidence_snippet"),
            notes=row.get("notes"),
            created_at=parse_dt(row.get("created_at")) or utc_now(),
            updated_at=parse_dt(row.get("updated_at")) or utc_now(),
            alerted_at=parse_dt(row.get("alerted_at")),
        )


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
