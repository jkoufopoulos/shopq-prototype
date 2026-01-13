"""
Digest Support Utilities

Consolidates utility functions for digest generation:
- Entity grouping and deduplication
- Text normalization
- Email payload normalization
- Data models (DTOs)
- Protocol adapters

Phase 2 Architecture Cleanup - Issue #59
Merged from: entity_grouping.py, normalize.py, dto.py, adapters.py
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from shopq.observability.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from shopq.contracts.entities import DigestEntity
    from shopq.contracts.synthesis import DigestTimeline

UTC = UTC


# =============================================================================
# Section 1: Entity Grouping (from entity_grouping.py)
# =============================================================================


def canonical_subject(subject: str) -> str:
    """
    Normalize subject for grouping/deduplication.

    Side Effects: None (pure function)

    Args:
        subject: Email subject line

    Returns:
        Canonicalized subject (lowercase, alphanumeric only)
    """
    normalized = subject or ""
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or "untitled"


def entity_key(sender_domain: str, canonical_subject: str, email_type: str) -> str:
    """
    Generate deduplication key for entity.

    Side Effects: None (pure function)

    Args:
        sender_domain: Email sender domain
        canonical_subject: Canonicalized subject
        email_type: Email type classification

    Returns:
        Unique key string for deduplication
    """
    domain = sender_domain or "unknown"
    return f"{domain}:{canonical_subject}:{email_type}"


def stable_sort_entities(entities: Iterable[dict]) -> list[dict]:
    """
    Sort entities by importance, domain, subject, type (stable sort).

    Side Effects: None (pure function - returns new list)

    Args:
        entities: Iterable of entity dictionaries

    Returns:
        Sorted list of entities
    """
    return sorted(
        entities,
        key=lambda entity: (
            entity.get("importance", ""),
            entity.get("sender_domain", ""),
            entity.get("canonical_subject", ""),
            entity.get("email_type", ""),
        ),
    )


# =============================================================================
# Section 2: Text Normalization (from normalize.py)
# =============================================================================


def _collapse_whitespace(text: str) -> str:
    """
    Collapse multiple whitespace characters into single space.

    Side Effects: None (pure function)
    """
    return " ".join(text.split())


def _strip_html(text: str) -> str:
    """
    Remove HTML tags from text.

    Side Effects: None (pure function)
    """
    # Remove script and style blocks
    text = re.sub(r"<(script|style).*?>.*?</\1>", " ", text, flags=re.DOTALL)
    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    return _collapse_whitespace(text)


def _decode_base64(text: str) -> str | None:
    """
    Attempt to decode base64-encoded text.

    Side Effects: None (pure function)

    Returns:
        Decoded text if valid base64, None otherwise
    """
    cleaned = text.strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    if not cleaned or len(cleaned) % 4 != 0:
        return None
    if re.fullmatch(r"[A-Za-z0-9+/=]+", cleaned) is None:
        return None
    try:
        decoded = base64.b64decode(cleaned, validate=True)
        return decoded.decode("utf-8", errors="ignore")
    except (ValueError, binascii.Error):
        # Invalid base64 encoding
        return None


def normalize_text(value: str, *, is_html: bool = True) -> str:
    """
    Normalize text: decode base64 if present, strip HTML, collapse whitespace.

    Side Effects: None (pure function)

    Args:
        value: Text to normalize
        is_html: Whether to strip HTML tags

    Returns:
        Normalized text string
    """
    if not value:
        return ""
    decoded = _decode_base64(value)
    source = decoded if decoded is not None else value
    text = html.unescape(source)
    if is_html:
        text = _strip_html(text)
    return _collapse_whitespace(text)


def extract_domain_address(value: str) -> str:
    """
    Extract domain from email address.

    Side Effects: None (pure function)

    Args:
        value: Email address string

    Returns:
        Domain portion (lowercase)
    """
    match = re.search(r"@([\w\.-]+)", value or "")
    if not match:
        return (value or "unknown").lower()
    return match.group(1).lower()


def extract_etld_plus_one(domain: str) -> str:
    """
    Extract eTLD+1 from domain (e.g., mail.google.com -> google.com).

    Side Effects: None (pure function)

    Args:
        domain: Full domain string

    Returns:
        eTLD+1 (last two parts of domain)
    """
    parts = domain.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain


def normalize_timestamp(value: Any) -> datetime:
    """
    Normalize various timestamp formats to datetime.

    Side Effects: None (pure function, but uses datetime.now() as fallback)

    Args:
        value: Timestamp (int/float in seconds or ms, ISO string, or other)

    Returns:
        UTC datetime object
    """
    if isinstance(value, int | float):
        # Assume milliseconds if large enough, otherwise seconds
        ts = value / 1000.0 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=UTC)
    if isinstance(value, str):
        try:
            numeric = float(value)
            return datetime.fromtimestamp(numeric / 1000.0 if numeric > 1e12 else numeric, tz=UTC)
        except ValueError:
            try:
                candidate = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if candidate.tzinfo is None:
                    candidate = candidate.replace(tzinfo=UTC)
                return candidate.astimezone(UTC)
            except ValueError:
                pass
    return datetime.now(UTC)


# =============================================================================
# Section 3: Email Normalization (from normalize.py)
# =============================================================================


@dataclass
class NormalizedEmail:
    """
    Normalized email payload with extracted fields.

    Contains all classification metadata and normalized text fields.
    Note: domains/domain_conf removed - not used in 4-label system.
    """

    message_id: str
    thread_id: str
    subject: str
    canonical_subject: str
    snippet: str
    normalized_snippet: str
    body: str
    normalized_body: str
    from_email: str
    from_name: str
    sender_domain: str
    sender_etld: str
    type: str
    attention: str
    relationship: str
    relationship_conf: float
    decider: str
    timestamp: datetime
    timezone: str | None
    type_conf: float
    attention_conf: float
    normalized_input_digest: str
    importance: str
    client_label: str

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary representation.

        Side Effects: None (pure function - returns new dict)
        """
        return {
            "id": self.message_id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "canonical_subject": self.canonical_subject,
            "snippet": self.snippet,
            "normalized_snippet": self.normalized_snippet,
            "body": self.body,
            "normalized_body": self.normalized_body,
            "from_email": self.from_email,
            "from_name": self.from_name,
            "from": self.from_email,
            "sender_domain": self.sender_domain,
            "sender_etld": self.sender_etld,
            "type": self.type,
            "attention": self.attention,
            "relationship": self.relationship,
            "relationship_conf": self.relationship_conf,
            "decider": self.decider,
            "type_conf": self.type_conf,
            "attention_conf": self.attention_conf,
            "date": self.timestamp.isoformat(),
            "timezone": self.timezone,
            "normalized_input_digest": self.normalized_input_digest,
            "importance": self.importance,
            "client_label": self.client_label,
        }


def normalize_email_payload(payload: dict[str, Any]) -> NormalizedEmail:
    """
    Normalize email payload from API to structured format.

    Side Effects: None (pure function - builds and returns NormalizedEmail)

    Args:
        payload: Raw email payload dictionary

    Returns:
        NormalizedEmail with extracted and normalized fields
    """
    import os

    classification = payload.get("classification", {})

    # Debug logging (gated behind environment variable)
    if os.getenv("SHOPQ_DEBUG_CLASSIFICATION", "").lower() in ("true", "1", "yes"):
        has_email_timestamp = "emailTimestamp" in payload
        data_path = "logger" if has_email_timestamp else "cache"

        # Log first email from EACH path (cache vs logger) - once per path
        debug_key = f"_debug_logged_{data_path}"
        if not hasattr(normalize_email_payload, debug_key):
            setattr(normalize_email_payload, debug_key, True)
            logger.debug(
                f"[DEBUG] normalize_email_payload ({data_path} path): "
                f"classification={classification}, "
                f"payload.type={payload.get('type')}, "
                f"payload_keys={list(payload.keys())[:10]}"
            )
    subject = payload.get("subject", "") or ""
    snippet = payload.get("snippet", "") or ""
    body = payload.get("body", "") or ""
    from_email = payload.get("from") or payload.get("from_email", "")
    from_name = payload.get("from_name") or from_email.split("@")[0]
    sender_domain = extract_domain_address(from_email)
    message_id = payload.get("messageId") or payload.get("id") or payload.get("threadId", "")
    thread_id = payload.get("threadId") or message_id
    normalized_snippet = normalize_text(snippet, is_html=True)
    normalized_body = normalize_text(body, is_html=True)
    timestamp = normalize_timestamp(payload.get("emailTimestamp") or payload.get("timestamp"))
    timezone_str = payload.get("timezone")
    digest_source = f"{subject.strip()}.{snippet.strip()}"
    input_digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return NormalizedEmail(
        message_id=message_id,
        thread_id=thread_id,
        subject=subject.strip(),
        canonical_subject=canonical_subject(subject),
        snippet=snippet.strip(),
        normalized_snippet=normalized_snippet,
        body=body.strip(),
        normalized_body=normalized_body,
        from_email=from_email,
        from_name=from_name,
        sender_domain=sender_domain,
        sender_etld=extract_etld_plus_one(sender_domain),
        type=classification.get("type") or payload.get("type") or "notification",
        attention=classification.get("attention", payload.get("attention", "none")),
        relationship=classification.get(
            "relationship", payload.get("relationship", "from_unknown")
        ),
        relationship_conf=classification.get(
            "relationship_conf", payload.get("relationship_conf", 0.5)
        ),
        decider=classification.get("decider", payload.get("decider", "unknown")),
        type_conf=classification.get("type_conf", payload.get("type_conf", 0.0)),
        attention_conf=classification.get("attention_conf", payload.get("attention_conf", 0.0)),
        normalized_input_digest=input_digest,
        timestamp=timestamp,
        timezone=timezone_str,
        importance=classification.get("importance") or payload.get("importance") or "routine",
        client_label=classification.get(
            "client_label", payload.get("client_label", "everything-else")
        ),
    )


# =============================================================================
# Section 4: Data Transfer Objects (from dto.py)
# =============================================================================


class ValidatedDigestEntry(BaseModel):
    """
    Validated digest entry for deterministic rendering.

    This Pydantic model ensures all digest entries have clean, validated data
    before being passed to templates or LLM prose formatters.

    Note: This is distinct from shopq.contracts.entities.DigestEntity (Protocol)
    which defines the interface for entity objects from the classification layer.
    Note: domains field removed - not used in 4-label system.
    """

    message_id: str = Field(..., min_length=1, max_length=200, description="Gmail message ID")
    sender_or_topic: str = Field(
        ..., min_length=1, max_length=200, description="Sender name or topic"
    )
    one_line_summary: str = Field(
        ..., min_length=5, max_length=300, description="One-line summary of the email"
    )
    why_it_matters: str = Field(
        ..., min_length=3, max_length=500, description="Why this email matters"
    )
    action_label: str = Field(
        ..., max_length=100, description="Action label (e.g., 'Reply', 'Review')"
    )
    is_actionable: bool = Field(..., description="Whether this email requires action")
    time_ago: str = Field(
        ..., min_length=1, max_length=50, description="Time ago string (e.g., '2 hours ago')"
    )
    email_type: Literal[
        "otp",
        "notification",
        "receipt",
        "event",
        "promotion",
        "newsletter",
        "message",
        "uncategorized",
    ] = Field(..., description="Email type from classification")
    importance: Literal["critical", "time_sensitive", "routine"] = Field(
        ..., description="Importance level"
    )


class DigestDTOv3(BaseModel):
    """
    Versioned digest DTO for deterministic rendering.

    This is the single source of truth for digest rendering.
    All digest HTML must be generated from this validated DTO.
    """

    period_label: str = Field(
        ..., min_length=1, max_length=100, description="Time period label (e.g., 'Last 24 hours')"
    )
    calm_tagline: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Calm tagline (e.g., '12 emails, 3 need attention')",
    )
    top_topic_sentence: str = Field(default="", max_length=300, description="Top topic sentence")
    skip_confidence_sentence: str = Field(
        default="", max_length=300, description="Skip confidence sentence"
    )
    what_mattered: list[ValidatedDigestEntry] = Field(
        default_factory=list, description="Critical/time-sensitive emails"
    )
    actions_now: list[ValidatedDigestEntry] = Field(
        default_factory=list, description="Actionable emails"
    )
    fyi_stream: list[ValidatedDigestEntry] = Field(
        default_factory=list, description="FYI/routine emails"
    )
    hidden_value: dict[str, list[ValidatedDigestEntry]] = Field(
        default_factory=dict, description="Hidden/noise emails by category"
    )
    last_sync_line: str = Field(
        default="Updated recently", max_length=100, description="Last sync timestamp"
    )


# =============================================================================
# Section 5: Protocol Adapters (from adapters.py)
# =============================================================================


def adapt_entity_for_digest(entity: Any) -> DigestEntity:
    """Adapt a classification entity to digest protocol.

    Args:
        entity: Entity from classification layer (any type implementing DigestEntity)

    Returns:
        Protocol-compatible entity for digest rendering

    Side Effects:
        None - returns same entity (protocols are structural, not nominal)

    Note:
        This is a type assertion function. Classification entities already
        implement the protocol structurally. This adapter exists for:
        1. Type narrowing (Any → DigestEntity)
        2. Future compatibility if we need transformations
        3. Explicit boundary between classification and digest layers
    """
    # Runtime check (optional, can be disabled in production)
    from shopq.contracts.entities import DigestEntity as DigestEntityProtocol

    if not isinstance(entity, DigestEntityProtocol):
        raise TypeError(
            f"Entity {entity} does not implement DigestEntity protocol. "
            f"Missing attributes: {_get_missing_protocol_attrs(entity, DigestEntityProtocol)}"
        )

    return entity


def adapt_entities_for_digest(entities: list[Any]) -> list[DigestEntity]:
    """Adapt a list of classification entities to digest protocols.

    Args:
        entities: List of entities from classification layer

    Returns:
        List of protocol-compatible entities

    Side Effects:
        None - pure function
    """
    return [adapt_entity_for_digest(e) for e in entities]


def adapt_timeline_for_digest(timeline: Any) -> DigestTimeline:
    """Adapt a classification timeline to digest timeline.

    Args:
        timeline: Timeline from classification synthesizer

    Returns:
        DigestTimeline dataclass

    Side Effects:
        None - pure function

    Note:
        Currently, classification.synthesizer.Timeline and DigestTimeline
        have the same structure. This adapter ensures digest layer doesn't
        depend on classification imports.
    """
    from shopq.contracts.synthesis import DigestTimeline

    # If timeline is already a DigestTimeline, return as-is
    if isinstance(timeline, DigestTimeline):
        return timeline

    # Otherwise, convert from classification Timeline
    return DigestTimeline(
        featured=adapt_entities_for_digest(timeline.featured),
        noise_breakdown=timeline.noise_breakdown,
        orphaned_time_sensitive=timeline.orphaned_time_sensitive,
        total_emails=timeline.total_emails,
        critical_count=timeline.critical_count,
        time_sensitive_count=timeline.time_sensitive_count,
        routine_count=timeline.routine_count,
    )


def _get_missing_protocol_attrs(obj: Any, protocol: type) -> list[str]:
    """Helper to identify missing protocol attributes for debugging.

    Args:
        obj: Object to check
        protocol: Protocol class to check against

    Returns:
        List of missing attribute names

    Side Effects:
        None - pure function
    """
    import inspect

    protocol_attrs = {name for name, _ in inspect.getmembers(protocol) if not name.startswith("_")}

    obj_attrs = {name for name in dir(obj) if not name.startswith("_")}

    return list(protocol_attrs - obj_attrs)


# Convenience type guards for downstream code
def is_flight_entity(entity: DigestEntity) -> bool:
    """Check if entity is a flight.

    Side Effects: None (pure function)
    """
    return entity.type == "flight"


def is_event_entity(entity: DigestEntity) -> bool:
    """Check if entity is an event.

    Side Effects: None (pure function)
    """
    return entity.type == "event"


def is_deadline_entity(entity: DigestEntity) -> bool:
    """Check if entity is a deadline.

    Side Effects: None (pure function)
    """
    return entity.type == "deadline"


def is_notification_entity(entity: DigestEntity) -> bool:
    """Check if entity is a notification.

    Side Effects: None (pure function)
    """
    return entity.type == "notification"


def is_promo_entity(entity: DigestEntity) -> bool:
    """Check if entity is a promotional offer.

    Side Effects: None (pure function)
    """
    return entity.type == "promo"


def is_reminder_entity(entity: DigestEntity) -> bool:
    """Check if entity is a reminder.

    Side Effects: None (pure function)
    """
    return entity.type == "reminder"
