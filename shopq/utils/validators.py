"""
Input validation utilities.

SEC-012: Validates user input to prevent injection attacks and ensure data integrity.
"""

from __future__ import annotations

import re

# Valid merchant domain pattern: lowercase letters, numbers, dots, hyphens
# Must start and end with alphanumeric, no consecutive dots
MERCHANT_DOMAIN_PATTERN = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$"
)

# Maximum length for merchant domain
MAX_MERCHANT_DOMAIN_LENGTH = 253  # DNS limit

# Valid order number pattern: alphanumeric, hyphens, underscores
ORDER_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9\-_#]+$")
MAX_ORDER_NUMBER_LENGTH = 100


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def validate_merchant_domain(domain: str | None) -> str | None:
    """
    Validate a merchant domain string.

    SEC-012: Prevents injection attacks and ensures valid domain format.

    Args:
        domain: The domain string to validate

    Returns:
        The validated domain (lowercase) or None if input was None

    Raises:
        ValidationError: If domain is invalid
    """
    if domain is None:
        return None

    # Normalize to lowercase
    domain = domain.lower().strip()

    if not domain:
        return None

    # Check length
    if len(domain) > MAX_MERCHANT_DOMAIN_LENGTH:
        raise ValidationError(
            f"Merchant domain exceeds maximum length of {MAX_MERCHANT_DOMAIN_LENGTH}"
        )

    # Check pattern
    if not MERCHANT_DOMAIN_PATTERN.match(domain):
        raise ValidationError(
            "Invalid merchant domain format. Must contain only lowercase letters, "
            "numbers, dots, and hyphens."
        )

    # Additional security checks
    if ".." in domain:
        raise ValidationError("Invalid merchant domain: consecutive dots not allowed")

    if domain.startswith("-") or domain.endswith("-"):
        raise ValidationError("Invalid merchant domain: cannot start or end with hyphen")

    return domain


def validate_order_number(order_number: str | None) -> str | None:
    """
    Validate an order number string.

    Args:
        order_number: The order number to validate

    Returns:
        The validated order number or None if input was None

    Raises:
        ValidationError: If order number is invalid
    """
    if order_number is None:
        return None

    order_number = order_number.strip()

    if not order_number:
        return None

    # Check length
    if len(order_number) > MAX_ORDER_NUMBER_LENGTH:
        raise ValidationError(
            f"Order number exceeds maximum length of {MAX_ORDER_NUMBER_LENGTH}"
        )

    # Check pattern
    if not ORDER_NUMBER_PATTERN.match(order_number):
        raise ValidationError(
            "Invalid order number format. Must contain only letters, numbers, "
            "hyphens, underscores, and #."
        )

    return order_number


def validate_email_id(email_id: str | None) -> str | None:
    """
    Validate a Gmail message ID.

    Args:
        email_id: The email ID to validate

    Returns:
        The validated email ID or None if input was None

    Raises:
        ValidationError: If email ID is invalid
    """
    if email_id is None:
        return None

    email_id = email_id.strip()

    if not email_id:
        return None

    # Gmail message IDs are typically 16 hex characters
    # But we'll be lenient and allow alphanumeric up to reasonable length
    if len(email_id) > 100:
        raise ValidationError("Email ID exceeds maximum length")

    if not re.match(r"^[A-Za-z0-9_-]+$", email_id):
        raise ValidationError("Invalid email ID format")

    return email_id
