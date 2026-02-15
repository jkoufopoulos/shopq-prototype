"""
Provides idempotency detection for email processing pipelines.

Generates deterministic keys (message_id:received_ts:body_hash) to detect duplicate
emails and prevent reprocessing. Tracks seen keys in memory with telemetry logging.

Key: email_key() creates unique identifier, is_duplicate() checks for reprocessing.
"""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

from reclaim.observability.telemetry import counter, log_event

_SEEN_KEYS: set[str] = set()


def email_key(message_id: str, received_ts: str, body_normalized: str) -> str:
    """
    Compute deterministic idempotency key. Raises ValueError if required inputs are missing.
    """
    missing = [
        name for name, val in (("message_id", message_id), ("received_ts", received_ts)) if not val
    ]
    if missing:
        counter("idempotency_drops")
        log_event("idempotency.drop", missing_fields=missing)
        raise ValueError(f"idempotency key requires: {', '.join(missing)}")

    digest = sha256((body_normalized or "").encode("utf-8")).hexdigest()
    return f"{message_id}:{received_ts}:{digest}"


def is_duplicate(key: str) -> bool:
    """Check if key has been seen before and mark it as seen.

    Side Effects:
        Adds key to global _SEEN_KEYS set if not already present.
        Logs telemetry event and increments counter if duplicate detected.
    """
    if key in _SEEN_KEYS:
        counter("idempotency_drops")
        log_event("idempotency.duplicate", key_hash=sha256(key.encode()).hexdigest()[:12])
        return True
    _SEEN_KEYS.add(key)
    return False


def reset_seen() -> None:
    """Clear all seen keys from memory.

    Side Effects:
        Clears the global _SEEN_KEYS set.
    """
    _SEEN_KEYS.clear()


def seed_seen(keys: Iterable[str]) -> None:
    """Preload a set of keys as already seen (e.g., for initialization).

    Side Effects:
        Adds all provided keys to the global _SEEN_KEYS set.
    """
    _SEEN_KEYS.update(keys)
