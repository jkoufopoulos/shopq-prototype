from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# CANONICAL TYPE DEFINITIONS (Single Source of Truth)
# =============================================================================
# These are the authoritative definitions for email classification types.
# Import these from this module - do NOT duplicate in other files.

EmailType = Literal[
    "otp",
    "newsletter",
    "notification",
    "receipt",
    "event",
    "promotion",
    "message",
    "uncategorized",
]
"""
Valid email types for classification.

- otp: One-time passcodes, verification codes, 2FA codes
- newsletter: Editorial, informational, or educational content
- notification: Operational updates (shipping, account, security)
- receipt: Documentation of completed financial transactions
- event: Emails tied to attending something at a specific date/time
- promotion: Commercial emails intended to sell products/services
- message: Direct human-to-human or small-group communication
- uncategorized: Doesn't fit any other category
"""

ImportanceLevel = Literal["critical", "time_sensitive", "routine"]
"""
Valid importance levels for classification.

- critical: Real-world risk if ignored (fraud, security, OTPs)
- time_sensitive: Matters soon (0-48 hours) but not existentially risky
- routine: Low-consequence, informational, or archival content
"""

AttentionType = Literal["action_required", "none"]
"""Binary attention flag for user action."""

RelationshipType = Literal["from_contact", "from_unknown"]
"""Whether sender is in user's contacts."""

DomainType = Literal["finance", "shopping", "professional", "personal", "unknown"]
"""Valid domain categories."""

ClientLabelType = Literal["receipts", "action-required", "messages", "everything-else"]
"""
Valid client labels for email categorization (per TAXONOMY.md).

- receipts: All purchase-related emails (orders, shipping, payments)
- action-required: User must act to avoid negative consequence
- messages: Personal/conversational threads with real humans
- everything-else: Newsletters, promotions, events, notifications
"""


def get_valid_email_types() -> list[str]:
    """Return list of valid email types (for validation without importing Literal)."""
    return list(get_args(EmailType))


def get_valid_importance_levels() -> list[str]:
    """Return list of valid importance levels."""
    return list(get_args(ImportanceLevel))


def compute_client_label(
    email_type: EmailType,
    attention: AttentionType,
) -> ClientLabelType:
    """
    Compute the client-facing label from type and attention.

    This is the SINGLE SOURCE OF TRUTH for type+attention → client_label mapping.
    Rules are defined in docs/TAXONOMY.md.

    Mapping Rules (in priority order):
    1. type=receipt → "receipts" (all purchase/billing lifecycle)
    2. type=message → "messages" (human conversations)
    3. type=otp → "everything-else" (despite being critical, OTPs are ephemeral)
    4. attention=action_required → "action-required" (actionable security alerts, deadlines)
    5. Everything else → "everything-else" (newsletters, promotions, events, notifications)

    Args:
        email_type: The classified email type (otp, receipt, message, etc.)
        attention: The attention level (action_required, none)

    Returns:
        ClientLabelType: One of "receipts", "action-required", "messages", "everything-else"

    Examples:
        >>> compute_client_label("receipt", "none")
        "receipts"
        >>> compute_client_label("message", "none")
        "messages"
        >>> compute_client_label("otp", "none")
        "everything-else"  # OTPs are ephemeral, not action-required
        >>> compute_client_label("notification", "action_required")
        "action-required"  # Actionable security alerts
        >>> compute_client_label("notification", "none")
        "everything-else"  # Informational security notices
        >>> compute_client_label("newsletter", "none")
        "everything-else"
    """
    # Rule 1: Receipts (all purchase/billing lifecycle)
    if email_type == "receipt":
        return "receipts"

    # Rule 2: Messages (human conversations)
    if email_type == "message":
        return "messages"

    # Rule 3: OTPs → everything-else (despite being critical)
    # OTPs are ephemeral and don't require user action in the digest context
    if email_type == "otp":
        return "everything-else"

    # Rule 4: Action required → action-required
    # (actionable security alerts, deadlines requiring response)
    if attention == "action_required":
        return "action-required"

    # Rule 5: Everything else → everything-else
    # (newsletters, promotions, events, notifications, uncategorized)
    return "everything-else"


class ClassificationContract(BaseModel):
    """
    Strict schema for classifier output. All fields are validated and
    normalized to ensure reproducible downstream behavior.
    """

    model_config = ConfigDict(
        extra="allow",
        frozen=True,
        arbitrary_types_allowed=True,
        protected_namespaces=(),
    )

    message_id: str = Field(..., description="Gmail message ID")
    type: EmailType
    importance: ImportanceLevel
    importance_conf: float = Field(..., ge=0, le=1, description="Confidence score for importance")
    confidence: float = Field(..., ge=0, le=1)
    type_conf: float = Field(..., ge=0, le=1)
    attention: AttentionType
    attention_conf: float = Field(..., ge=0, le=1)
    client_label: ClientLabelType | None = Field(
        default=None,
        description="Client label for UI (4-bucket categorization)",
    )
    relationship: RelationshipType
    relationship_conf: float = Field(..., ge=0, le=1)
    decider: str
    reason: str = Field(..., min_length=3, max_length=500)
    propose_rule: dict[str, str] | None = Field(
        default_factory=lambda: {
            "should_propose": "false",
            "pattern": "",
            "kind": "",
            "support_count": "0",
        },
        description="Optional rule suggestion metadata",
    )
    model_name: str = Field(..., description="LLM model name")
    model_version: str = Field(..., description="LLM model version")
    prompt_version: str = Field(..., description="Prompt version used for classification")
    normalized_input_digest: str | None = Field(
        default=None,
        description="digest of normalized input (subject+snippet)",
    )
    temporal: dict[str, str] | None = Field(
        default=None,
        description="Optional temporal metadata (start_iso, end_iso)",
    )

    @property
    def normalized_dict(self) -> dict[str, Any]:
        """
        Return canonical dict for downstream mappers.
        """
        payload = self.model_dump()
        payload.setdefault("attention_confidence", payload.get("attention_conf"))
        return payload
