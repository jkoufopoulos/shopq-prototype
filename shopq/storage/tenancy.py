"""
Tenancy enforcement utilities for multi-tenant database operations.

This module provides decorators and guards to ensure all database queries
are properly scoped to a user_id, preventing cross-tenant data leakage.
"""

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any


class TenancyViolationError(Exception):
    """Raised when a database operation violates tenancy constraints."""

    pass


def enforce_tenancy(func: Callable) -> Callable:
    """
    Decorator to ensure all database query functions receive a user_id parameter.

    This decorator validates that:
    1. The function has a user_id parameter
    2. The user_id value is provided (not None)
    3. The user_id is a non-empty string

    Args:
        func: Function to wrap (must have user_id parameter)

    Returns:
        Wrapped function that validates user_id before execution

    Raises:
        TenancyViolationError: If user_id is missing, None, or invalid

    Example:
        @enforce_tenancy
        def get_email_threads(user_id: str, session_id: str):
            return db.query("SELECT * FROM email_threads WHERE user_id = ? AND session_id = ?",
                          (user_id, session_id))
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        # Get function signature
        sig = inspect.signature(func)

        # Bind arguments to get user_id value
        try:
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
        except TypeError as e:
            # If binding fails, check if it's because user_id is missing
            if "user_id" not in sig.parameters:
                raise TenancyViolationError(
                    f"{func.__name__} must have a 'user_id' parameter for tenancy enforcement"
                ) from e
            raise

        # Check if user_id parameter exists
        if "user_id" not in bound_args.arguments:
            raise TenancyViolationError(f"{func.__name__} requires 'user_id' parameter")

        # Get user_id value
        user_id = bound_args.arguments["user_id"]

        # Validate user_id is not None
        if user_id is None:
            raise TenancyViolationError(
                f"{func.__name__} received None for user_id - all queries must be scoped to a user"
            )

        # Validate user_id is a non-empty string
        if not isinstance(user_id, str) or not user_id.strip():
            raise TenancyViolationError(
                f"{func.__name__} received invalid user_id: {user_id!r} - must be non-empty string"
            )

        # Call original function
        return func(*args, **kwargs)

    return wrapper


def require_user_scope(query: str, user_id: str) -> None:  # noqa: ARG001
    """
    Validate that a SQL query includes user_id filtering.

    This is a secondary safety check for raw SQL queries to ensure
    they include WHERE user_id = ? clauses.

    Args:
        query: SQL query string to validate
        user_id: User ID that should be used in the query

    Raises:
        TenancyViolationError: If query doesn't appear to filter by user_id

    Example:
        query = "SELECT * FROM email_threads WHERE user_id = ? AND session_id = ?"
        require_user_scope(query, user_id)
        result = db.execute(query, (user_id, session_id))
    """
    query_lower = query.lower()

    # Check if query mentions user_id
    if "user_id" not in query_lower:
        raise TenancyViolationError(
            f"Query must include user_id filtering for tenancy safety: {query[:100]}..."
        )

    # Check if it's in a WHERE clause (basic heuristic)
    if "where" in query_lower or "join" in query_lower:
        # Query has filtering, assume it's correct if user_id is mentioned
        return

    # For INSERT/UPDATE statements, user_id should be in column list
    if any(keyword in query_lower for keyword in ["insert", "update"]):
        return

    # If it's a SELECT without WHERE, that's suspicious
    if "select" in query_lower and "where" not in query_lower:
        raise TenancyViolationError(
            f"SELECT query must include WHERE clause with user_id filtering: {query[:100]}..."
        )
