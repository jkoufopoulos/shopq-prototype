"""

from __future__ import annotations

Entity dataclasses for Context Digest

These represent structured information extracted from emails:
- Flight: airline, flight number, departure/arrival info
- Event: title, time, location
- Deadline: what's due, when, amount
- Reminder: from whom, action needed
- Promo: merchant, offer, expiry

Each entity has:
- type: entity type
- confidence: extraction confidence (0.0-1.0)
- source_email_id: reference to original email
- importance: critical | time_sensitive | routine
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Entity:
    """Base entity class"""

    confidence: float
    source_email_id: str
    source_subject: str
    source_snippet: str
    timestamp: datetime
    type: str = "unknown"
    importance: str = "routine"  # Stage 1: critical | time_sensitive | routine
    source_thread_id: str = ""  # Gmail thread ID for linking to full conversation

    # Phase 4 temporal decay fields (set during enrichment, optional)
    stored_importance: str | None = None  # Stage 1 output (preserved for audit)
    resolved_importance: str | None = None  # Stage 2 output (after temporal decay)
    decay_reason: str | None = None  # Why importance was modified
    was_modified: bool = False  # Flag indicating temporal modulation occurred
    digest_section: str | None = None  # NOW / COMING_UP / WORTH_KNOWING
    hide_in_digest: bool = False  # True for expired events

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization

        Side Effects:
            None (pure function - builds local dict only)
        """
        return {
            "type": self.type,
            "confidence": self.confidence,
            "source_email_id": self.source_email_id,
            "source_subject": self.source_subject,
            "source_snippet": self.source_snippet,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
        }


@dataclass
class Location:
    """Location information"""

    city: str | None = None
    state: str | None = None
    airport_code: str | None = None
    full_address: str | None = None

    def __str__(self):
        if self.full_address:
            return self.full_address
        if self.airport_code:
            return f"{self.city} ({self.airport_code})"
        if self.city and self.state:
            return f"{self.city}, {self.state}"
        if self.city:
            return self.city
        return "Unknown"


@dataclass
class FlightEntity(Entity):
    """Flight information extracted from email"""

    airline: str | None = None
    flight_number: str | None = None
    departure: Location | None = None
    arrival: Location | None = None
    departure_time: str | None = None  # "tomorrow at 5 PM", "Tue Oct 28, 5:00 PM"
    confirmation_code: str | None = None
    weather_context: str | None = None  # "it'll be 95° in Houston"

    def __post_init__(self) -> None:
        """Initialize entity type field.

        Side Effects: None (only sets instance attributes during construction)
        """
        self.type = "flight"

    def to_dict(self) -> dict[str, Any]:
        """Convert flight entity to dictionary

        Side Effects:
            None (pure function - builds local dict only)
        """
        base = super().to_dict()
        base.update(
            {
                "airline": self.airline,
                "flight_number": self.flight_number,
                "departure": str(self.departure) if self.departure else None,
                "arrival": str(self.arrival) if self.arrival else None,
                "departure_time": self.departure_time,
                "confirmation_code": self.confirmation_code,
                "weather_context": self.weather_context,
            }
        )
        return base


@dataclass
class EventEntity(Entity):
    """Event information (classes, appointments, reservations)"""

    title: str | None = None
    event_time: str | None = None  # "tomorrow at 7 PM", "Wed Oct 29, 2:00 PM"
    event_end_time: str | None = None  # End time for temporal decay (ISO 8601 or natural language)
    location: Location | None = None
    organizer: str | None = None
    weather_context: str | None = None

    def __post_init__(self) -> None:
        """Initialize entity type field.

        Side Effects: None (only sets instance attributes during construction)
        """
        self.type = "event"

    def to_dict(self) -> dict[str, Any]:
        """Convert event entity to dictionary

        Side Effects:
            None (pure function - builds local dict only)
        """
        base = super().to_dict()
        base.update(
            {
                "title": self.title,
                "event_time": self.event_time,
                "event_end_time": self.event_end_time,
                "location": str(self.location) if self.location else None,
                "organizer": self.organizer,
            }
        )
        return base


@dataclass
class DeadlineEntity(Entity):
    """Deadline information (bills, payments, tasks due)"""

    title: str | None = None
    due_date: str | None = None  # "Friday", "Oct 31", "tomorrow"
    amount: str | None = None  # "$145.00"
    from_whom: str | None = None  # "PG&E", "Landlord"

    def __post_init__(self) -> None:
        """Initialize entity type field.

        Side Effects: None (only sets instance attributes during construction)
        """
        self.type = "deadline"

    def to_dict(self) -> dict[str, Any]:
        """Convert deadline entity to dictionary

        Side Effects:
            None (pure function - builds local dict only)
        """
        base = super().to_dict()
        base.update(
            {
                "title": self.title,
                "due_date": self.due_date,
                "amount": self.amount,
                "from_whom": self.from_whom,
            }
        )
        return base


@dataclass
class ReminderEntity(Entity):
    """Reminder information (schedule appointment, renew, etc.)"""

    from_sender: str | None = None
    action: str | None = None  # "schedule a cleaning", "renew license"
    deadline: str | None = None  # Optional deadline if mentioned

    def __post_init__(self) -> None:
        """Initialize entity type field.

        Side Effects: None (only sets instance attributes during construction)
        """
        self.type = "reminder"

    def to_dict(self) -> dict[str, Any]:
        """Convert reminder entity to dictionary

        Side Effects:
            None (pure function - builds local dict only)
        """
        base = super().to_dict()
        base.update(
            {
                "from_sender": self.from_sender,
                "action": self.action,
                "deadline": self.deadline,
            }
        )
        return base


@dataclass
class PromoEntity(Entity):
    """Promotional offer information"""

    merchant: str | None = None
    offer: str | None = None  # "25% off", "$20 off $50"
    expiry: str | None = None  # "ends tonight", "expires Friday"
    product_category: str | None = None  # "home decor", "electronics"

    def __post_init__(self) -> None:
        """Initialize entity type field.

        Side Effects: None (only sets instance attributes during construction)
        """
        self.type = "promo"

    def to_dict(self) -> dict[str, Any]:
        """Convert promo entity to dictionary

        Side Effects:
            None (pure function - builds local dict only)
        """
        base = super().to_dict()
        base.update(
            {
                "merchant": self.merchant,
                "offer": self.offer,
                "expiry": self.expiry,
                "product_category": self.product_category,
            }
        )
        return base


@dataclass
class NotificationEntity(Entity):
    """Generic notification (for things that don't fit other categories)"""

    category: str | None = None  # "package_delivery", "fraud_alert", "bill"
    message: str | None = None
    action_required: bool = False

    # OTP fields (for temporal decay)
    otp_expires_at: datetime | None = None  # When OTP code expires

    # Shipping fields (for temporal decay)
    ship_status: str | None = None  # "processing", "in_transit", "out_for_delivery", "delivered"
    delivered_at: datetime | None = None  # When package was delivered
    tracking_number: str | None = None  # Optional tracking number

    def __post_init__(self) -> None:
        """Initialize entity type field.

        Side Effects: None (only sets instance attributes during construction)
        """
        self.type = "notification"

    def to_dict(self) -> dict[str, Any]:
        """Convert notification entity to dictionary

        Side Effects:
            None (pure function - builds local dict only)
        """
        base = super().to_dict()
        base.update(
            {
                "category": self.category,
                "message": self.message,
                "action_required": self.action_required,
                "otp_expires_at": self.otp_expires_at.isoformat() if self.otp_expires_at else None,
                "ship_status": self.ship_status,
                "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
                "tracking_number": self.tracking_number,
            }
        )
        return base


def create_entity(entity_type: str, **kwargs) -> Entity:
    """Factory function to create entities by type.

    Side Effects: None (pure factory function, no database or API calls)
    """
    entity_map = {
        "flight": FlightEntity,
        "event": EventEntity,
        "deadline": DeadlineEntity,
        "reminder": ReminderEntity,
        "promo": PromoEntity,
        "notification": NotificationEntity,
    }

    entity_class = entity_map.get(entity_type)
    if not entity_class:
        raise ValueError(f"Unknown entity type: {entity_type}")

    return entity_class(**kwargs)
