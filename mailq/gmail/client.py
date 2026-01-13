"""
Gmail adapter facade returning RawEmail objects.

Real HTTP fetching is intentionally omitted; callers supply raw message payloads
retrieved elsewhere. This module handles transformation plus validation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from mailq.gmail.parser import parse_message_strict
from mailq.infrastructure.retry import AdapterError, CircuitBreaker, RetryPolicy
from mailq.observability.telemetry import counter, log_event, time_block
from mailq.storage.models import ParsedEmail

_FETCH_POLICY = RetryPolicy(stage="gmail.fetch")
_CIRCUIT = CircuitBreaker(stage="gmail.fetch", fail_max=3, reset_timeout=30.0)

# Batch size for Gmail API calls (list/get operations)
BATCH_SIZE = 50


def fetch_messages_with_retry(fetcher: Callable[[], Iterable[dict]]) -> Iterable[dict]:
    """
    Fetch Gmail messages with retry/circuit protection.

    Uses batching to reduce roundtrips when fetcher supports it.
    """
    if not _CIRCUIT.allow_request():
        raise RuntimeError("gmail circuit open")

    try:
        with time_block("gmail.fetch.latency"):
            result = _FETCH_POLICY.execute(fetcher)
    except AdapterError as exc:
        _CIRCUIT.record_failure()
        log_event("gmail.fetch.error", status=exc.status_code)
        raise
    except Exception as exc:
        _CIRCUIT.record_failure()
        log_event("gmail.fetch.error", error=str(exc))
        raise
    else:
        _CIRCUIT.record_success()
        return result


def fetch_messages_batched(
    list_ids: Callable[[], list[str]],
    get_message: Callable[[str], dict],
    batch_size: int = BATCH_SIZE,
) -> list[dict]:
    """
    Fetch messages in batches to reduce Gmail API roundtrips.

    Args:
        list_ids: Function that returns list of message IDs
        get_message: Function that fetches a single message by ID
        batch_size: Number of messages to fetch per batch

    Returns:
        List of raw message payloads

    Note: In production, this would use Gmail's batchGet API.
    For now, we batch locally to demonstrate the pattern.
    """
    with time_block("gmail.batch_fetch.latency"):
        message_ids = list_ids()
        counter("gmail.messages.listed", len(message_ids))

        messages: list[dict] = []
        for i in range(0, len(message_ids), batch_size):
            batch_ids = message_ids[i : i + batch_size]
            with time_block("gmail.batch_get.latency"):
                # TODO(clarify): Replace with actual Gmail batchGet API call
                batch_messages = [get_message(msg_id) for msg_id in batch_ids]
                messages.extend(batch_messages)
                counter("gmail.batch.count")
                log_event("gmail.batch_fetched", batch_size=len(batch_ids), total=len(messages))

        return messages


def parse_messages(messages: Iterable[dict]) -> list[ParsedEmail]:
    """
    Parse raw Gmail API message payloads into ParsedEmail objects.
    """
    with time_block("gmail.parse.latency"):
        parsed_emails: list[ParsedEmail] = []
        for message in messages:
            parsed = parse_message_strict(message)
            parsed_emails.append(parsed)
        log_event("gmail.batch_parsed", count=len(parsed_emails))
        counter("gmail.batch_parsed.count", len(parsed_emails))
        return parsed_emails
