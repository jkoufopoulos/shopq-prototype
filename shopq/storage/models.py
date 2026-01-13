"""
Domain models (Pydantic v2) for the ShopQ pipeline.

Contracts are versioned (v1) and enforce validation at ingress/egress. Sensitive
fields (subjects, addresses, bodies) are redacted in repr/model_dump previews.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


def _hash_value(value: str) -> str:
    digest = sha256(value.encode("utf-8")).hexdigest()
    return f"hash:{digest[:12]}"


class RedactedModel(BaseModel):
    """Base model that redacts sensitive fields in repr/dumps."""

    model_config = ConfigDict(frozen=True)
    _redact_fields = {"body", "body_text", "body_html", "from_address", "to_address", "subject"}

    def _redacted_dump(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        for field in self._redact_fields:
            if field in data and isinstance(data[field], str) and data[field]:
                data[field] = _hash_value(data[field])
        return data

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._redacted_dump()})"

    def redacted(self) -> dict[str, Any]:
        """Public helper for telemetry-safe dumps."""
        return self._redacted_dump()


class RawEmail(RedactedModel):
    version: str = Field(default="v1")
    message_id: str
    thread_id: str
    received_ts: str
    subject: str = ""
    from_address: str
    to_address: str
    body: str

    @model_validator(mode="after")
    def _check_fields(cls, values: RawEmail) -> RawEmail:
        if values.version != "v1":
            raise ValueError("RawEmail version must be 'v1'")
        required = {
            "message_id": values.message_id,
            "thread_id": values.thread_id,
            "received_ts": values.received_ts,
            "from_address": values.from_address,
            "to_address": values.to_address,
        }
        missing = [name for name, val in required.items() if not val]
        if missing:
            raise ValueError(f"RawEmail missing fields: {', '.join(missing)}")
        return values


class ParsedEmail(RedactedModel):
    version: str = Field(default="v1")
    base: RawEmail
    body_text: str = ""
    body_html: str | None = None

    @model_validator(mode="after")
    def _check_version(cls, values: ParsedEmail) -> ParsedEmail:
        if values.version != "v1":
            raise ValueError("ParsedEmail version must be 'v1'")
        # Note: body_text/body_html can be empty - classification uses subject + snippet
        return values


class ClassifiedEmail(RedactedModel):
    version: str = Field(default="v1")
    parsed: ParsedEmail
    category: str
    attention: str
    confidence: float = 0.0  # Overall classification confidence

    # Importance from LLM (preferred) - if not set, computed from attention/category
    # This allows LLM to directly classify importance per taxonomy rules
    llm_importance: str | None = Field(default=None)

    # Per-dimension confidence scores (for API compatibility)
    # These auto-populate from `confidence` if not explicitly set
    type_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    attention_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    importance_confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # LLM's importance_conf

    # Relationship dimension (from LLM or fallback)
    # Indicates whether sender is a known contact or unknown
    # Values: "from_contact", "from_known_person", "from_unknown"
    relationship: str = Field(default="from_unknown")
    relationship_confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    # Classification metadata
    decider: str = Field(default="unknown")  # type_mapper, rule, gemini, fallback
    reason: str = Field(default="")  # Explanation for classification

    @field_validator("category")
    @classmethod
    def _category_allowed(cls, value: str) -> str:
        # All types from taxonomy
        allowed = {
            "notification",
            "receipt",
            "event",
            "promotion",
            "message",
            "newsletter",
            "otp",
            "other",
            "uncategorized",
        }
        if value not in allowed:
            raise ValueError(f"unsupported category '{value}'")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="before")
    @classmethod
    def _populate_confidence(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Auto-populate dimension-specific confidence from base confidence if not set"""
        # Get base confidence
        base_conf = data.get("confidence", 0.7)

        # Populate type_confidence if not provided
        if "type_confidence" not in data or data["type_confidence"] == 0.0:
            data["type_confidence"] = base_conf

        # Populate attention_confidence if not provided
        if "attention_confidence" not in data or data["attention_confidence"] == 0.0:
            # Slightly lower confidence for action_required (more uncertain)
            attention = data.get("attention", "none")
            data["attention_confidence"] = (
                base_conf * 0.95 if attention == "action_required" else base_conf
            )

        # Populate importance_confidence if not provided
        if "importance_confidence" not in data or data["importance_confidence"] == 0.0:
            data["importance_confidence"] = base_conf

        return data

    @model_validator(mode="after")
    def _check_version(cls, values: ClassifiedEmail) -> ClassifiedEmail:
        if values.version != "v1":
            raise ValueError("ClassifiedEmail version must be 'v1'")
        return values

    @property
    def importance(self) -> str:
        """
        Return importance, preferring LLM classification over computed fallback.

        Priority:
        1. llm_importance (if set) - LLM directly classified per taxonomy
        2. Computed fallback - based on type and attention

        Computed fallback rules (only used if llm_importance is None):
        - action_required → time_sensitive
        - event → time_sensitive (events are inherently time-bound)
        - else → routine

        NOTE: receipts are NOT automatically time_sensitive. Most receipts
        (shipped, delivered) are routine. Only specific stages like
        out_for_delivery are time_sensitive, determined by LLM.

        Returns:
            "critical" | "time_sensitive" | "routine"
        """
        # Prefer LLM importance if available
        if self.llm_importance is not None:
            return self.llm_importance

        # Fallback: compute from attention + type
        if self.attention == "action_required":
            return "time_sensitive"

        # Events are inherently time-sensitive (have dates/times)
        # This ensures they appear in "Coming Up" section of digest
        if self.category == "event":
            return "time_sensitive"

        # Default to routine
        return "routine"

    def _to_mapping_dict(self) -> dict[str, Any]:
        """Convert to dict format expected by map_to_gmail_labels.

        This helper enables the gmail_labels computed property.
        """
        return {
            "type": self.category,
            "type_conf": self.type_confidence,
            "importance": self.importance,
            "attention": self.attention,
            "attention_conf": self.attention_confidence,
        }

    @property
    def gmail_labels(self) -> list[str]:
        """Compute Gmail labels from classification.

        Labels are computed based on type and importance dimensions.
        """
        from shopq.classification.mapper import map_to_gmail_labels

        mapping = map_to_gmail_labels(self._to_mapping_dict())
        return mapping["labels"]

    @property
    def gmail_labels_conf(self) -> dict[str, float]:
        """Confidence for each Gmail label."""
        from shopq.classification.mapper import map_to_gmail_labels

        mapping = map_to_gmail_labels(self._to_mapping_dict())
        return mapping["labels_conf"]


class DigestItem(RedactedModel):
    version: str = Field(default="v1")
    source: ClassifiedEmail
    priority: float
    title: str
    snippet: str
    gmail_thread_link: str

    @field_validator("priority")
    @classmethod
    def _priority_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("priority must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def _post_checks(cls, values: DigestItem) -> DigestItem:
        """_post_checks implementation.

        Side Effects:
            None (validation only, no state modification)
        """

        if values.version != "v1":
            raise ValueError("DigestItem version must be 'v1'")
        if not values.title:
            raise ValueError("DigestItem.title is required")
        if not values.gmail_thread_link.startswith("https://mail.google.com"):
            raise ValueError("DigestItem.gmail_thread_link must be a Gmail URL")
        return values


class Digest(RedactedModel):
    version: str = Field(default="v1")
    items: list[DigestItem]
    generated_ts: str
    idempotency_key: str

    @model_validator(mode="after")
    def _validate(cls, values: Digest) -> Digest:
        if values.version != "v1":
            raise ValueError("Digest version must be 'v1'")
        if not values.items:
            raise ValueError("Digest must contain at least one item")
        if not values.generated_ts:
            raise ValueError("Digest.generated_ts is required")
        if not values.idempotency_key:
            raise ValueError("Digest.idempotency_key is required")
        return values


def validate_or_raise(model_cls: type[BaseModel], data: dict[str, Any]) -> BaseModel:
    """
    Helper for safe validation. Returns validated instance, raising ValidationError.
    """
    try:
        return model_cls.model_validate(data)
    except ValidationError:
        raise
