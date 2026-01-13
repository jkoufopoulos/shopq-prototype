"""
Entity Protocols for Digest Layer

These protocols define the interface contract between classification/ and digest/.
Classification entities implement these protocols; digest code depends only on protocols.

Design Principles (P1-P4):
- P1: All entity contracts in ONE file
- P3: Type-safe - mypy/pyright can verify compliance
- P4: Explicit contract - no hidden dependencies
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DigestEntity(Protocol):
    """Base entity protocol for digest rendering.

    All classification entities must implement this interface to be
    compatible with digest rendering.
    """

    # Core identification
    type: str
    confidence: float

    # Source tracking
    source_email_id: str
    source_subject: str
    source_snippet: str
    source_thread_id: str
    timestamp: datetime

    # Importance classification (Stage 1)
    importance: str  # critical | time_sensitive | routine

    # Temporal enrichment (Stage 3.5 - Phase 4)
    stored_importance: str | None  # Original importance before decay
    resolved_importance: str | None  # After temporal decay
    decay_reason: str | None
    was_modified: bool
    digest_section: str | None  # NOW / COMING_UP / WORTH_KNOWING
    hide_in_digest: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        ...


@runtime_checkable
class DigestLocation(Protocol):
    """Location information protocol."""

    city: str | None
    state: str | None
    airport_code: str | None
    full_address: str | None

    def __str__(self) -> str:
        """Formatted location string."""
        ...


@runtime_checkable
class DigestFlightEntity(DigestEntity, Protocol):
    """Flight entity protocol for digest rendering."""

    airline: str | None
    flight_number: str | None
    departure: DigestLocation | None
    arrival: DigestLocation | None
    departure_time: str | None
    confirmation_code: str | None
    weather_context: str | None


@runtime_checkable
class DigestEventEntity(DigestEntity, Protocol):
    """Event entity protocol (appointments, classes, reservations)."""

    title: str | None
    event_time: str | None
    event_end_time: str | None
    location: DigestLocation | None
    organizer: str | None
    weather_context: str | None


@runtime_checkable
class DigestDeadlineEntity(DigestEntity, Protocol):
    """Deadline entity protocol (bills, payments, tasks)."""

    title: str | None
    due_date: str | None
    amount: str | None
    from_whom: str | None


@runtime_checkable
class DigestReminderEntity(DigestEntity, Protocol):
    """Reminder entity protocol."""

    from_sender: str | None
    action: str | None
    deadline: str | None


@runtime_checkable
class DigestPromoEntity(DigestEntity, Protocol):
    """Promotional offer entity protocol."""

    merchant: str | None
    offer: str | None
    expiry: str | None
    product_category: str | None


@runtime_checkable
class DigestNotificationEntity(DigestEntity, Protocol):
    """Generic notification entity protocol."""

    category: str | None
    message: str | None
    action_required: bool

    # OTP fields
    otp_expires_at: datetime | None

    # Shipping fields
    ship_status: str | None
    delivered_at: datetime | None
    tracking_number: str | None
