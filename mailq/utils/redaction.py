"""
Shared logging utilities for redacting sensitive information before telemetry.

Provides:
- redact(): Hash sensitive strings for correlation without exposure
- redact_subject(): Partially redact email subjects for debugging
- sanitize_for_prompt(): Remove potential prompt injection patterns
"""

from __future__ import annotations

import re
from hashlib import sha256

# Patterns that could be used for prompt injection
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+instructions?",
    r"disregard\s+(previous|above|all)\s+instructions?",
    r"forget\s+(previous|above|all)\s+instructions?",
    r"new\s+instructions?:",
    r"system\s*:",
    r"assistant\s*:",
    r"user\s*:",
    r"\[INST\]",
    r"\[/INST\]",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
]
INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def redact(value: str | None) -> str:
    """
    Return a stable hash representation of a sensitive string.
    """
    if not value:
        return "hash:missing"
    digest = sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"hash:{digest}"


def redact_subject(subject: str | None, max_length: int = 30) -> str:
    """
    Partially redact email subject for logging while preserving debuggability.

    Shows first N characters + hash suffix for correlation.

    Args:
        subject: Email subject line
        max_length: Maximum visible characters (default 30)

    Returns:
        Redacted subject like "Your order has been..." (hash:abc123)

    Example:
        "Your Amazon order #123-456 has shipped" ->
        "Your Amazon order #123-456 h..." (hash:7a8b9c)
    """
    if not subject:
        return "(no subject)"

    # Keep first N chars, add ellipsis if truncated
    visible = subject[:max_length] + "..." if len(subject) > max_length else subject

    # Add hash for correlation
    digest = sha256(subject.encode("utf-8")).hexdigest()[:6]
    return f"{visible} (h:{digest})"


def sanitize_for_prompt(text: str, max_length: int = 500) -> str:
    """
    Sanitize user-provided text before including in LLM prompts.

    Mitigates prompt injection by:
    1. Removing known injection patterns
    2. Truncating to reasonable length
    3. Escaping special characters

    Args:
        text: User-provided text (email subject, snippet, etc.)
        max_length: Maximum allowed length

    Returns:
        Sanitized text safe for prompt inclusion

    Note:
        This is defense-in-depth. The primary defense is proper prompt
        engineering (clear system instructions, output validation).
    """
    if not text:
        return ""

    # Truncate first to limit processing
    text = text[:max_length]

    # Remove potential injection patterns
    text = INJECTION_REGEX.sub("[REDACTED]", text)

    # Escape characters that might confuse prompt parsing
    # Keep alphanumeric, spaces, and common punctuation
    # This is conservative - adjust based on your prompt format
    text = re.sub(r"[<>{}|\\]", "", text)

    return text.strip()
