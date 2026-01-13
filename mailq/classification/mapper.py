"""

from __future__ import annotations

Gmail label mapper - converts semantic classification to 4 client labels.

The 4 Gmail labels (from TAXONOMY.md):
- MailQ-Receipts: Purchase confirmations, order updates
- MailQ-Messages: Personal/professional correspondence
- MailQ-Action-Required: Critical items needing immediate attention
- MailQ-Everything-Else: Newsletters, notifications, promotions, etc.

NOTE: Granular type/domain labels (MailQ-Notifications, MailQ-Finance, etc.)
were removed - extension only uses these 4 client labels.
"""

from typing import Any


def compute_client_label(email_type: str, attention: str) -> str:
    """Compute client_label from type and attention.

    This is the single source of truth for the 4 UI categories.
    Must match extension logic in mapper.js computeClientLabel().

    Args:
        email_type: Classification type (receipt, message, notification, etc.)
        attention: Attention level (action_required, none)

    Returns:
        One of: receipts, messages, action-required, everything-else
    """
    if email_type == "receipt":
        return "receipts"
    if email_type == "message":
        return "messages"
    if email_type == "otp":
        return "everything-else"  # OTPs are ephemeral, not action-required
    if attention == "action_required":
        return "action-required"
    return "everything-else"


# Map client_label to Gmail label name (hyphen format)
CLIENT_LABEL_TO_GMAIL = {
    "receipts": "MailQ-Receipts",
    "messages": "MailQ-Messages",
    "action-required": "MailQ-Action-Required",
    "everything-else": "MailQ-Everything-Else",
}


def map_to_gmail_labels(
    result: dict[str, Any],
    _user_prefs: dict[str, Any] | None = None,
    **_kwargs: Any,  # Ignore legacy gate parameters
) -> dict[str, Any]:
    """Map semantic classification to one of 4 Gmail client labels.

    Only returns ONE label per email (the client_label category).
    Granular type/domain labels are NOT used - extension ignores them.

    Side Effects:
        None (pure function - builds labels dict from classification result)
    """
    email_type = result.get("type", "uncategorized")
    attention = result.get("attention", "none")
    type_conf = result.get("type_conf", 0.5)

    # Compute which of the 4 buckets this email belongs to
    client_label = compute_client_label(email_type, attention)
    gmail_label = CLIENT_LABEL_TO_GMAIL.get(client_label, "MailQ-Everything-Else")

    return {
        "labels": [gmail_label],
        "labels_conf": {gmail_label: type_conf},
    }


def validate_classification_result(result: dict[str, Any]) -> bool:
    """Validate classification result matches schema.

    Required fields (4-label system):
    - type, type_conf: Email category
    - attention, attention_conf: Whether action is required
    - relationship, relationship_conf: Sender relationship
    - decider, reason: Classification source and explanation
    - propose_rule: Optional rule learning metadata

    Note: domains/domain_conf removed - no longer used in 4-label system.
    """
    required_fields = [
        "type",
        "type_conf",
        "attention",
        "attention_conf",
        "relationship",
        "relationship_conf",
        "decider",
        "reason",
        "propose_rule",
    ]

    # Check all required fields present
    for field in required_fields:
        if field not in result:
            return False

    # Validate enums - use canonical types from contracts
    from mailq.storage.classification import get_valid_email_types

    valid_types = get_valid_email_types()
    if result["type"] not in valid_types:
        return False

    valid_attention = ["action_required", "none"]
    if result["attention"] not in valid_attention:
        return False

    valid_relationship = ["from_contact", "from_unknown"]
    if result["relationship"] not in valid_relationship:
        return False

    valid_decider = ["rule", "gemini", "fallback", "type_mapper"]
    if result["decider"] not in valid_decider:
        return False

    # Validate confidence scores are 0-1
    conf_fields = ["type_conf", "attention_conf", "relationship_conf"]
    for field in conf_fields:
        if not (0 <= result[field] <= 1):
            return False

    # Validate propose_rule
    if not isinstance(result["propose_rule"], dict):
        return False
    rule_fields = ["should_propose", "pattern", "kind", "support_count"]
    return all(field in result["propose_rule"] for field in rule_fields)
