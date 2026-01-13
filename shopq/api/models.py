"""Pydantic request/response models for ShopQ Return Watch API.

This module contains shared Pydantic models and validation helpers
used across API endpoints.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

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
    """
    if current_depth > max_depth:
        raise ValueError(f"List nesting exceeds maximum depth of {max_depth}")

    if len(data) > max_keys:
        raise ValueError(f"List too long: {len(data)} > {max_keys}")

    for item in data:
        if isinstance(item, dict):
            validate_dict_structure(item, max_keys, max_str_len, max_depth, current_depth + 1)
        elif isinstance(item, list):
            _validate_list_structure(item, max_keys, max_str_len, max_depth, current_depth + 1)
        elif isinstance(item, str) and len(item) > max_str_len:
            raise ValueError(f"String value too long in list: {len(item)} > {max_str_len}")


# =============================================================================
# SHARED MODELS
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    error_count: int = 1
    invalid_fields: list[str] = []
