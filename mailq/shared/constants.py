"""Shared constants used across the MailQ codebase.

This file contains constants that are used in multiple modules to avoid duplication.
"""

from __future__ import annotations

# Friendly names for email types in digest summaries
# Maps EmailType values to human-readable plural names for the "everything else" section
TYPE_FRIENDLY_NAMES: dict[str, str] = {
    "newsletter": "newsletters",
    "notification": "notifications",
    "promotion": "promotions",
    "receipt": "receipts",
    "event": "events",
    "message": "messages",
    "otp": "verification codes",
    "uncategorized": "other",
}


def get_friendly_type_name(email_type: str) -> str:
    """Get the friendly plural name for an email type.

    Args:
        email_type: EmailType value (e.g., 'newsletter', 'receipt')

    Returns:
        Human-readable plural name (e.g., 'newsletters', 'receipts')
    """
    return TYPE_FRIENDLY_NAMES.get(email_type, email_type)
