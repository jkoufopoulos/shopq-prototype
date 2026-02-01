"""
Error message sanitization utility.

SEC-011: Prevents information leakage by sanitizing error messages
before returning them to clients.
"""

from __future__ import annotations

import re

from shopq.observability.logging import get_logger

logger = get_logger(__name__)

# Patterns that might leak sensitive information
SENSITIVE_PATTERNS = [
    # File paths
    r"/[^\s]+\.py",
    r"[A-Za-z]:\\[^\s]+",
    # Stack trace indicators
    r"Traceback \(most recent call last\)",
    r"File \".*\"",
    r"line \d+",
    # Database errors
    r"sqlite3?\.",
    r"UNIQUE constraint",
    r"FOREIGN KEY constraint",
    r"no such table",
    r"no such column",
    # API keys / secrets patterns
    r"[A-Za-z0-9_-]{20,}",  # Long alphanumeric strings that might be keys
    r"Bearer [A-Za-z0-9._-]+",
    # Internal module names
    r"shopq\.[a-z_.]+",
]

# Generic error messages for different error types
GENERIC_MESSAGES = {
    400: "Invalid request. Please check your input and try again.",
    401: "Authentication required.",
    403: "Access denied.",
    404: "Resource not found.",
    422: "Invalid data format.",
    429: "Too many requests. Please try again later.",
    500: "An internal error occurred. Please try again later.",
    503: "Service temporarily unavailable.",
}


def sanitize_error_message(
    message: str,
    status_code: int = 500,
    allow_field_names: bool = True,
) -> str:
    """
    Sanitize an error message to prevent information leakage.

    Args:
        message: The original error message
        status_code: HTTP status code (used to select generic fallback)
        allow_field_names: Whether to allow simple field name references

    Returns:
        Sanitized error message safe for client consumption
    """
    if not message:
        return GENERIC_MESSAGES.get(status_code, "An error occurred.")

    # Check for sensitive patterns
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            logger.warning("Sanitized sensitive error pattern: %s", pattern)
            return GENERIC_MESSAGES.get(status_code, "An error occurred.")

    # For 400 errors, allow simple validation messages (not detailed internal errors)
    if (
        status_code == 400
        and allow_field_names
        and len(message) < 100
        and not any(c in message for c in ["{", "}", "[", "]", "\n"])
    ):
        return message

    # For other errors, use generic message
    return GENERIC_MESSAGES.get(status_code, "An error occurred.")


def get_safe_error_detail(
    error: Exception,
    status_code: int = 500,
    context: str | None = None,
) -> str:
    """
    Get a safe error detail string for HTTP responses.

    Args:
        error: The exception that occurred
        status_code: HTTP status code
        context: Optional context to include (e.g., "Failed to create return")

    Returns:
        Safe error message for client
    """
    # Log the full error for debugging
    logger.error("Error (status=%d): %s - %s", status_code, type(error).__name__, str(error))

    # Return sanitized message
    if context:
        # Use context as the base message for 500 errors
        if status_code >= 500:
            return context
        # For client errors, try to sanitize the actual message
        return sanitize_error_message(str(error), status_code)

    return sanitize_error_message(str(error), status_code)
