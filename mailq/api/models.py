"""Pydantic request/response models for MailQ API.

This module contains all shared Pydantic models used across API endpoints.
Centralizing models here prevents circular imports and provides a single
source of truth for API contracts.
"""

from __future__ import annotations

import html
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# VALIDATION HELPERS
# =============================================================================

# Dict validation constants to prevent DoS attacks
MAX_DICT_SIZE = 100  # Maximum number of keys in any dict
MAX_STRING_LENGTH = 10_000  # Maximum string length in dict values
MAX_DICT_DEPTH = 5  # Maximum nesting depth


def validate_dict_structure(
    data: dict[str, Any],
    max_keys: int = MAX_DICT_SIZE,
    max_str_len: int = MAX_STRING_LENGTH,
    max_depth: int = MAX_DICT_DEPTH,
    current_depth: int = 0,
) -> None:
    """
    Validate dict structure to prevent DoS attacks.

    Protects against:
    - Deeply nested dicts: {"a": {"b": {"c": ...}}}
    - Deeply nested lists: [[[[...]]]]
    - Mixed nesting: {"a": [{"b": [{"c": ...}]}]}
    - Large dicts/lists (DoS via memory)

    Args:
        data: Dict to validate
        max_keys: Maximum number of keys allowed
        max_str_len: Maximum string value length
        max_depth: Maximum nesting depth (dicts + lists combined)
        current_depth: Current recursion depth

    Raises:
        ValueError: If validation fails

    Side Effects:
        - None (pure function, raises on invalid input)
    """
    if current_depth > max_depth:
        raise ValueError(f"Dict nesting exceeds maximum depth of {max_depth}")

    if len(data) > max_keys:
        raise ValueError(f"Dict has too many keys: {len(data)} > {max_keys}")

    for key, value in data.items():
        # Validate key length
        if isinstance(key, str) and len(key) > 100:
            raise ValueError(f"Dict key too long: {len(key)} > 100")

        # Validate value based on type
        if isinstance(value, str):
            if len(value) > max_str_len:
                raise ValueError(f"String value too long: {len(value)} > {max_str_len}")
        elif isinstance(value, dict):
            validate_dict_structure(value, max_keys, max_str_len, max_depth, current_depth + 1)
        elif isinstance(value, list):
            _validate_list_structure(value, max_keys, max_str_len, max_depth, current_depth + 1)


def _validate_list_structure(
    data: list[Any],
    max_keys: int,
    max_str_len: int,
    max_depth: int,
    current_depth: int,
) -> None:
    """
    Validate list structure to prevent DoS attacks via nested lists.

    Args:
        data: List to validate
        max_keys: Maximum list length
        max_str_len: Maximum string value length
        max_depth: Maximum nesting depth
        current_depth: Current recursion depth

    Raises:
        ValueError: If validation fails

    Side Effects:
        - None (pure function, raises on invalid input)
    """
    if current_depth > max_depth:
        raise ValueError(f"List nesting exceeds maximum depth of {max_depth}")

    if len(data) > max_keys:
        raise ValueError(f"List too long: {len(data)} > {max_keys}")

    for item in data:
        if isinstance(item, dict):
            validate_dict_structure(item, max_keys, max_str_len, max_depth, current_depth + 1)
        elif isinstance(item, list):
            # Recursively validate nested lists with depth tracking
            _validate_list_structure(item, max_keys, max_str_len, max_depth, current_depth + 1)
        elif isinstance(item, str) and len(item) > max_str_len:
            raise ValueError(f"String value too long in list: {len(item)} > {max_str_len}")


# =============================================================================
# CLASSIFICATION MODELS
# =============================================================================


class EmailInput(BaseModel):
    """Single email input for classification."""

    subject: str = Field(..., min_length=1, max_length=1000, description="Email subject line")
    snippet: str = Field(default="", max_length=5000, description="Email snippet/preview")
    sender: str = Field(
        ..., alias="from", min_length=1, max_length=500, description="Sender email address"
    )

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        """Validate subject is not empty or whitespace-only.

        Side Effects:
            None (pure validator - validates and transforms input only)
        """
        if not v or not v.strip():
            raise ValueError("Invalid subject")
        return v.strip()

    @field_validator("sender")
    @classmethod
    def validate_sender(cls, v: str) -> str:
        """Validate sender is not empty.

        Side Effects:
            None (pure validator - validates and transforms input only)
        """
        if not v or not v.strip():
            raise ValueError("Invalid sender")
        return v.strip()

    class Config:
        populate_by_name = True


class EmailBatch(BaseModel):
    """Batch of emails for classification.

    Security: max_length=100 prevents cost DoS attacks. The Chrome extension
    typically sends 10-30 emails per batch. A limit of 100 provides headroom
    while preventing attackers from sending 1000+ emails per request.
    """

    emails: list[EmailInput] = Field(
        ..., min_length=1, max_length=100, description="Batch of emails to classify (max 100)"
    )
    user_prefs: dict[str, Any] | None = Field(default=None, description="Optional user preferences")

    @field_validator("emails")
    @classmethod
    def validate_emails(cls, v: list[EmailInput]) -> list[EmailInput]:
        """Validate email batch is not empty.

        Side Effects:
            None (pure validator - validates input only)
        """
        if not v:
            raise ValueError("Email batch cannot be empty")
        if len(v) > 100:
            raise ValueError("Email batch cannot exceed 100 emails")
        return v


class ClassificationResult(BaseModel):
    """Multi-dimensional classification result for 4-label system.

    Fields:
    - labels/labels_conf: Gmail labels (one of the 4 client labels)
    - type/type_conf: Email category (receipt, message, notification, etc.)
    - attention/attention_conf: Whether action is required
    - relationship/relationship_conf: Sender relationship
    - decider/reason: Classification source and explanation
    - client_label: UI category (receipts, messages, action-required, everything-else)

    Note: domains/domain_conf removed - not used in 4-label system.
    """

    labels: list[str]
    labels_conf: dict[str, float]
    type: str
    type_conf: float
    attention: str
    attention_conf: float
    relationship: str
    relationship_conf: float
    decider: str
    reason: str
    client_label: str | None = None

    class Config:
        extra = "allow"


class OrganizeResponse(BaseModel):
    """Response from /api/organize endpoint."""

    results: list[ClassificationResult]
    model_version: str


# =============================================================================
# CATEGORY MODELS
# =============================================================================


class CategoryCreate(BaseModel):
    """Request model for creating a category."""

    name: str
    description: str | None = ""
    color: str | None = "#3b82f6"


# =============================================================================
# VERIFIER MODELS
# =============================================================================


class VerifyRequest(BaseModel):
    """Request for verifying a classification."""

    email: dict[str, Any] = Field(..., description="Email dict with subject, snippet, from fields")
    first_result: dict[str, Any] = Field(..., description="First-pass classification result")
    features: dict[str, Any] = Field(
        ..., description="Extracted features (has_order_id, has_otp, etc.)"
    )
    contradictions: list[str] = Field(default_factory=list, description="Detected contradictions")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate email has required fields and safe structure.

        Side Effects:
            None (pure validator - validates input only)
        """
        required_fields = ["subject", "snippet", "from"]
        for field in required_fields:
            if field not in v:
                raise ValueError(f"Email missing required field: {field}")

        # Validate dict structure to prevent DoS
        validate_dict_structure(v, max_keys=50, max_str_len=5000)

        return v

    @field_validator("first_result")
    @classmethod
    def validate_first_result(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate first_result has classification fields and safe structure.

        Side Effects:
            None (pure validator - validates input only)
        """
        if "type" not in v:
            raise ValueError("first_result missing required 'type' field")

        # Validate dict structure
        validate_dict_structure(v, max_keys=30, max_str_len=1000)

        return v

    @field_validator("features")
    @classmethod
    def validate_features(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate features dict structure.

        Side Effects:
            None (pure validator - validates input only)
        """
        validate_dict_structure(v, max_keys=50, max_str_len=1000)
        return v


class VerifyResponse(BaseModel):
    """Verifier response."""

    verdict: str  # "confirm" or "correct"
    correction: dict[str, Any] | None = None  # Full classification if verdict=correct
    rubric_violations: list[str] = []
    confidence_delta: float = 0.0
    why_bad: str = ""


# =============================================================================
# DIGEST/SUMMARY MODELS
# =============================================================================


class SummaryRequest(BaseModel):
    """Request for generating inbox summary."""

    current_data: list[dict[str, Any]] = Field(
        ..., min_length=1, max_length=1000, description="Current classifications from logger"
    )
    previous_data: list[dict[str, Any]] | None = Field(
        default=None, description="Previous classifications for delta"
    )
    session_start: str | None = Field(default=None, description="ISO timestamp of session start")
    timezone: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z_]+/[A-Za-z_]+$",
        description="IANA timezone (e.g., America/New_York)",
    )
    client_now: str | None = Field(
        default=None, description="Client-side ISO timestamp at request time"
    )
    timezone_offset_minutes: int | None = Field(
        default=None, ge=-720, le=840, description="Client UTC offset in minutes (-12h to +14h)"
    )
    city: str | None = Field(
        default=None, max_length=100, description="Client city hint for weather"
    )
    region: str | None = Field(
        default=None,
        max_length=100,
        description="Client region/state for weather disambiguation (e.g., 'New York')",
    )
    user_name: str | None = Field(
        default=None, max_length=50, description="User's first name for personalized greeting"
    )
    raw_digest: bool = Field(
        default=False,
        description="Use raw LLM digest (bypass classification/section logic for A/B testing)",
    )

    @field_validator("current_data")
    @classmethod
    def validate_current_data(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate current_data structure.

        Side Effects:
            None (pure validator - validates input only)
        """
        if not v:
            raise ValueError("current_data cannot be empty")

        # Validate that each email has required fields and safe structure
        for i, email in enumerate(v):
            if not isinstance(email, dict):
                raise ValueError(f"Email at index {i} must be a dict")
            if "id" not in email:
                raise ValueError(f"Email at index {i} missing required 'id' field")
            if "subject" not in email:
                raise ValueError(f"Email at index {i} missing required 'subject' field")

            # Validate dict structure to prevent DoS
            validate_dict_structure(email, max_keys=50, max_str_len=5000)

        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Validate timezone format if provided.

        Side Effects:
            None (pure validator - validates input only)
        """
        if v is None:
            return v
        # Basic IANA timezone format validation
        if "/" not in v:
            raise ValueError(f"Invalid timezone format: {v}. Expected format: 'Region/City'")
        return v

    @field_validator("timezone_offset_minutes")
    @classmethod
    def validate_timezone_offset(cls, v: int | None) -> int | None:
        """
        Validate timezone offset and monitor for unusual values.

        Most timezones fall within UTC-12 to UTC+14 range.
        Values outside the common range (-660 to +720, i.e., UTC-11 to UTC+12)
        are logged for monitoring purposes.

        Side Effects:
            - Logs unusual timezone offsets (outside UTC-11 to UTC+12) to telemetry
            - Logs warning to application logger for monitoring
        """
        if v is None:
            return v

        # Log unusual timezone offsets (outside UTC-11 to UTC+12)
        # Common range covers 99% of world population
        if v < -660 or v > 720:
            from mailq.observability.logging import get_logger
            from mailq.observability.telemetry import log_event

            logger = get_logger(__name__)
            log_event(
                "api.unusual_timezone_offset",
                offset_minutes=v,
                offset_hours=round(v / 60, 1),
                severity="warning",
            )
            logger.warning(
                "Unusual timezone offset received: %d minutes (UTC%+.1f hours)", v, v / 60
            )

        return v

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str | None) -> str | None:
        """
        Validate and sanitize city name.

        Removes potentially dangerous characters while allowing:
        - Letters (including Unicode for international city names)
        - Spaces, hyphens, apostrophes (for names like "New York", "O'Brien")

        Side Effects:
            None (pure validator - sanitizes input only)
        """
        if v is None:
            return v
        # Strip leading/trailing whitespace
        v = v.strip()
        if not v:
            return None
        # Remove HTML/script injection attempts
        v = html.escape(v)
        # Only allow alphanumeric (unicode), spaces, hyphens, apostrophes, commas, periods
        if not re.match(r"^[\w\s\-',.\u00C0-\u017F]+$", v, re.UNICODE):
            raise ValueError(f"Invalid city name format: {v}")
        return v

    @field_validator("user_name")
    @classmethod
    def validate_user_name(cls, v: str | None) -> str | None:
        """
        Validate and sanitize user name.

        Side Effects:
            None (pure validator - sanitizes input only)
        """
        if v is None:
            return v
        # Strip leading/trailing whitespace
        v = v.strip()
        if not v:
            return None
        # Remove HTML/script injection attempts
        v = html.escape(v)
        # Only allow alphanumeric (unicode), spaces, hyphens, apostrophes
        if not re.match(r"^[\w\s\-'\u00C0-\u017F]+$", v, re.UNICODE):
            raise ValueError(f"Invalid user name format: {v}")
        return v


class SummaryResponse(BaseModel):
    """Summary email response."""

    html: str  # HTML formatted email body
    subject: str  # Email subject line


# =============================================================================
# RULES MODELS
# =============================================================================


class RuleCreate(BaseModel):
    """Request model for creating a rule."""

    pattern_type: str = Field(..., description="Type: 'from', 'subject', 'keyword'")
    pattern: str = Field(..., min_length=1, max_length=500, description="Pattern to match")
    category: str = Field(..., min_length=1, max_length=100, description="Category to assign")
    confidence: int = Field(85, ge=0, le=100, description="Confidence score")

    @field_validator("pattern_type")
    @classmethod
    def validate_pattern_type(cls, v: str) -> str:
        """Validate pattern_type is one of the allowed types.

        Side Effects:
            None (pure validator - validates input only)
        """
        allowed_types = ["from", "subject", "keyword"]
        if v not in allowed_types:
            raise ValueError(f"pattern_type must be one of {allowed_types}, got: {v}")
        return v

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate pattern is not empty or whitespace-only.

        Side Effects:
            None (pure validator - validates and transforms input only)
        """
        if not v or not v.strip():
            raise ValueError("Pattern cannot be empty or whitespace-only")
        return v.strip()


class RuleUpdate(BaseModel):
    """Request model for updating a rule."""

    pattern: str | None = Field(None, min_length=1, max_length=500, description="Pattern to match")
    category: str | None = Field(
        None, min_length=1, max_length=100, description="Category to assign"
    )
    confidence: int | None = Field(None, ge=0, le=100, description="Confidence score")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str | None) -> str | None:
        """Validate pattern is not empty or whitespace-only if provided.

        Side Effects:
            None (pure validator - validates and transforms input only)
        """
        if v is not None and (not v or not v.strip()):
            raise ValueError("Pattern cannot be empty or whitespace-only")
        return v.strip() if v else None
