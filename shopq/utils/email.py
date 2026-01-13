"""
Utility functions for ShopQ email processing.
"""

from __future__ import annotations

import re


def extract_email_address(email_address: str) -> str:
    """
    Extract and normalize email address from various formats.

    Args:
        email_address: Email address string (e.g., "user@example.com" or "Name <user@example.com>")

    Returns:
        Lowercase full email address (e.g., "user@example.com")
        If no valid email found, returns original string lowercased

    Examples:
        >>> extract_email_address("user@example.com")
        'user@example.com'

        >>> extract_email_address("John Doe <john@company.com>")
        'john@company.com'

        >>> extract_email_address("calendar-notification@google.com")
        'calendar-notification@google.com'

        >>> extract_email_address("invalid")
        'invalid'
    """
    if not email_address:
        return ""

    email_lower = email_address.lower().strip()

    # Handle "Name <email@domain.com>" format
    # Extract email from angle brackets if present
    angle_match = re.search(r"<([^>]+)>", email_lower)
    if angle_match:
        email_lower = angle_match.group(1).strip()

    # Validate basic email format (has @ symbol)
    if "@" in email_lower:
        # Return full email address (including local part)
        # This preserves specificity for type mapper rules
        # e.g., "calendar-notification@google.com" != "user@google.com"
        return email_lower

    # Not a valid email, return as-is (lowercased)
    return email_lower


def extract_domain_only(email_address: str) -> str:
    """
    Extract only the domain portion (after @) from email address.

    Args:
        email_address: Email address string

    Returns:
        Domain portion only (e.g., "google.com")

    Examples:
        >>> extract_domain_only("user@example.com")
        'example.com'

        >>> extract_domain_only("calendar-notification@google.com")
        'google.com'
    """
    full_email = extract_email_address(email_address)

    if "@" in full_email:
        return full_email.split("@")[1]

    return full_email
