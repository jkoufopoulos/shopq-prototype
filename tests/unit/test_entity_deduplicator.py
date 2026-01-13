"""Tests for the entity deduplication helpers."""

from __future__ import annotations

from datetime import datetime

from shopq.classification.deduplicator import EntityDeduplicator
from shopq.classification.models import Entity, FlightEntity


def _make_flight_entity(departure_time: datetime, confidence: float = 0.5) -> FlightEntity:
    departure_time_str = departure_time.isoformat()
    return FlightEntity(
        confidence=confidence,
        source_email_id="email-id",
        source_subject="Flight update",
        source_snippet="Boarding soon",
        timestamp=departure_time,
        airline="United",
        flight_number="UA123",
        departure_time=departure_time_str,
    )


def test_deduplicate_handles_non_string_signature_parts():
    """Departure time datetimes should not cause signature generation failures."""

    deduplicator = EntityDeduplicator()
    departure_time = datetime(2024, 1, 1, 12, 30)

    flight_primary = _make_flight_entity(departure_time, confidence=0.9)
    flight_duplicate = _make_flight_entity(departure_time, confidence=0.5)

    # Would raise a TypeError prior to normalization of signature parts
    deduped = deduplicator.deduplicate([flight_primary, flight_duplicate])

    assert len(deduped) == 1
    assert deduped[0].confidence == flight_primary.confidence


def test_deduplicate_handles_missing_subject():
    """Entities without a source subject should be gracefully deduplicated."""

    deduplicator = EntityDeduplicator()
    timestamp = datetime(2024, 1, 2, 8, 0)

    notification = Entity(
        confidence=0.6,
        source_email_id="notif-1",
        source_subject=None,  # Previously caused an AttributeError
        source_snippet="Reminder",
        timestamp=timestamp,
        type="notification",
    )

    deduped = deduplicator.deduplicate([notification])

    assert deduped == [notification]
