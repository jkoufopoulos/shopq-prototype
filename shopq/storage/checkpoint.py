"""Storage adapter stubs for digest checkpointing."""

from __future__ import annotations

from shopq.infrastructure.retry import CircuitBreaker, RetryPolicy
from shopq.observability.telemetry import log_event
from shopq.storage.models import Digest

_LAST_DIGEST: Digest | None = None

_STORAGE_POLICY = RetryPolicy(
    stage="storage.write", max_attempts=3, base_delay=0.2, timeout_seconds=5.0
)
_STORAGE_CIRCUIT = CircuitBreaker(stage="storage.write", fail_max=3, reset_timeout=30.0)


def checkpoint_digest(digest: Digest) -> None:
    """Persist digest metadata to durable storage.

    Side Effects:
        - Writes to global _LAST_DIGEST variable
        - Logs telemetry events via log_event()
        - Updates circuit breaker state
    """
    # TODO(clarify): persist digest metadata to durable storage.
    if not _STORAGE_CIRCUIT.allow_request():
        raise RuntimeError("storage circuit open")

    def _write() -> None:
        """_write implementation.

        Side Effects:
            None (pure function)
        """

        global _LAST_DIGEST
        _LAST_DIGEST = digest

    try:
        _STORAGE_POLICY.execute(_write)
    except Exception as exc:
        _STORAGE_CIRCUIT.record_failure()
        log_event("storage.write.error", error=str(exc))
        raise
    else:
        _STORAGE_CIRCUIT.record_success()
        log_event("storage.digest_checkpointed", key=digest.idempotency_key)


def load_seen_keys() -> set[str]:
    # TODO(clarify): fetch seen idempotency keys from storage with retry.
    return set()
