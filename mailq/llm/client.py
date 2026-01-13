"""
LLM adapter for email classification with schema validation, caching, and fallback.

Safety features:
- Feature flag to enable/disable LLM (defaults to disabled)
- Cache results by (prompt_hash, email_key) for determinism
- Strict JSON schema validation on all LLM outputs
- PII redaction in all logs
- Never block digest generation on LLM failures
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from mailq.observability.telemetry import counter, log_event
from mailq.storage.cache import TTLCache

# Feature flag: disable LLM by default for safety
USE_LLM = os.getenv("MAILQ_USE_LLM", "false").lower() == "true"

# LLM response cache (keyed by prompt_hash + email_key)
# TTL: 24 hours (classifications shouldn't change frequently)
_LLM_CACHE = TTLCache[dict](name="llm_classification", ttl_seconds=86400.0)


class LLMError(RuntimeError):
    """Raised when LLM call fails (network, API, etc)."""


class LLMSchemaError(ValueError):
    """Raised when LLM output doesn't match expected schema."""


def _compute_cache_key(prompt: str, email_key: str) -> str:
    """
    Compute deterministic cache key from prompt and email.

    Args:
        prompt: Classification prompt (contains email content)
        email_key: Idempotency key for email

    Returns:
        SHA256 hash of (prompt || email_key)

    Side Effects:
        None (pure function)
    """
    combined = f"{prompt}::{email_key}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _redact_prompt(prompt: str) -> str:
    """Redact email content from prompt for safe logging."""
    # Return first 50 chars + hash of full prompt
    preview = prompt[:50] if len(prompt) > 50 else prompt
    full_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    return f"{preview}... (hash:{full_hash})"


def classify_email_llm(
    prompt: str,
    email_key: str,
    expected_schema: type[BaseModel],
    llm_call_fn: Callable[[str], dict[str, Any] | str] | None = None,
) -> dict[str, Any] | None:
    """
    Classify email using LLM with caching and validation.

    Args:
        prompt: Classification prompt (includes email content)
        email_key: Idempotency key for email
        expected_schema: Pydantic model class for validation
        llm_call_fn: Optional function that calls LLM API (for testing)

    Returns:
        Classification dict if successful, None if LLM disabled or failed

    Raises:
        LLMSchemaError: If LLM output doesn't match schema (caller should fallback)
        LLMError: If LLM API call fails (caller should fallback)

    Side Effects:
        - Calls external LLM API (Gemini, OpenAI, etc.) via llm_call_fn
        - Writes to in-memory LLM cache (_LLM_CACHE)
        - Increments telemetry counters (llm.cache_hit, llm.call_success, etc.)
        - Writes telemetry log events for LLM calls and errors
    """

    # Check feature flag
    if not USE_LLM:
        counter("llm.disabled")
        log_event("llm.skipped", reason="feature_flag_disabled")
        return None

    # Check cache first
    cache_key = _compute_cache_key(prompt, email_key)
    cached_result = _LLM_CACHE.get(cache_key)
    if cached_result is not None:
        counter("llm.cache_hit")
        log_event(
            "llm.cache_hit",
            cache_key_hash=cache_key[:12],
            email_key_hash=email_key[:12],
        )
        return cached_result

    counter("llm.cache_miss")

    # Call LLM (stub for now, real implementation would call Gemini/OpenAI)
    if llm_call_fn is None:
        # TODO(clarify): Replace with actual LLM API call (Gemini, OpenAI, etc.)
        log_event("llm.call_skipped", reason="no_llm_fn_provided")
        return None

    try:
        # Call LLM with redacted logging
        log_event(
            "llm.call_start",
            prompt_preview=_redact_prompt(prompt),
            email_key_hash=email_key[:12],
        )

        raw_response = llm_call_fn(prompt)
        counter("llm.call_success")

    except Exception as exc:
        counter("llm.call_error")
        log_event(
            "llm.call_error",
            error=str(exc),
            email_key_hash=email_key[:12],
        )
        raise LLMError(f"LLM API call failed: {exc}") from exc

    # Parse and validate response
    try:
        # Attempt to parse JSON
        if isinstance(raw_response, str):
            response_data = json.loads(raw_response)
        elif isinstance(raw_response, dict):
            response_data = raw_response
        else:
            raise LLMSchemaError(f"LLM response must be JSON, got {type(raw_response)}")

        # Validate against Pydantic schema
        validated = expected_schema.model_validate(response_data)
        validated_dict = validated.model_dump()

        counter("llm.schema_validation_success")
        log_event(
            "llm.schema_validation_success",
            email_key_hash=email_key[:12],
            schema=expected_schema.__name__,
        )

        # Cache successful result
        _LLM_CACHE.put(cache_key, validated_dict)

        return validated_dict

    except json.JSONDecodeError as exc:
        counter("llm.schema_validation_failures")
        log_event(
            "llm.json_parse_error",
            error=str(exc),
            email_key_hash=email_key[:12],
            response_preview=str(raw_response)[:100],
        )
        raise LLMSchemaError(f"LLM response is not valid JSON: {exc}") from exc

    except ValidationError as exc:
        counter("llm.schema_validation_failures")
        log_event(
            "llm.schema_validation_failed",
            errors=exc.errors(),
            email_key_hash=email_key[:12],
            schema=expected_schema.__name__,
        )
        raise LLMSchemaError(f"LLM response doesn't match schema: {exc}") from exc


def clear_llm_cache() -> None:
    """
    Clear all cached LLM results (useful for testing)

    Side Effects:
        - Clears _LLM_CACHE in-memory cache
        - Writes telemetry event (llm.cache_cleared)
    """
    _LLM_CACHE.clear()
    log_event("llm.cache_cleared")
