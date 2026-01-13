"""Pipeline coordinator orchestrating MailQ stages."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable, Iterable

from mailq.gmail.client import fetch_messages_with_retry, parse_messages
from mailq.gmail.parser import parse_message_strict
from mailq.infrastructure.idempotency import email_key, is_duplicate, reset_seen
from mailq.observability.telemetry import counter, log_event, time_block
from mailq.storage.checkpoint import checkpoint_digest
from mailq.storage.models import ClassifiedEmail, Digest, ParsedEmail

ClassifierFn = Callable[[Iterable[ParsedEmail]], list[ClassifiedEmail]]
AssemblerFn = Callable[[Iterable[ClassifiedEmail]], Digest]

# Parallelization config
MAX_WORKERS = 4  # Limit concurrency to avoid overwhelming LLM APIs


def run_pipeline(
    fetcher: Callable[[], Iterable[dict]],
    classify: ClassifierFn,
    assemble: AssemblerFn,
    parallel: bool = False,
) -> Digest:
    """
    Coordinate fetch → parse → classify → persist → assemble → render flow.

    Args:
        fetcher: Function to fetch raw Gmail messages
        classify: Function to classify parsed emails
        assemble: Function to assemble classified emails into digest
        parallel: Enable parallel processing of parse/classify stages
        (default False for determinism)

    Note: When parallel=True, parsing and classification happen concurrently,
    but final assembly maintains stable sort order to preserve digest determinism.
    """

    with time_block("pipeline.total"):
        raw_messages = fetch_messages_with_retry(fetcher)

        reset_seen()  # TODO(clarify): seed from durable store once available.

        if parallel:
            # Parallel path: parse and deduplicate concurrently
            unique = _parse_and_dedupe_parallel(raw_messages)
        else:
            # Sequential path: maintains original order deterministically
            with time_block("pipeline.parse"):
                parsed_emails = parse_messages(raw_messages)
            unique = _deduplicate(parsed_emails)

        if not unique:
            counter("pipeline.no_new_messages")
            log_event("pipeline.no_new_messages")
            raise ValueError("no new emails to process")

        with time_block("pipeline.classify"):
            classified = classify(unique)

        with time_block("pipeline.assemble"):
            digest = assemble(classified)

        checkpoint_digest(digest)
        log_event("pipeline.completed", items=len(digest.items), parallel=parallel)
        return digest


def _deduplicate(parsed_emails: list[ParsedEmail]) -> list[ParsedEmail]:
    """Remove duplicate emails based on idempotency key."""
    unique: list[ParsedEmail] = []
    for parsed in parsed_emails:
        key = email_key(parsed.base.message_id, parsed.base.received_ts, parsed.base.body)
        if is_duplicate(key):
            continue
        unique.append(parsed)
    return unique


def _parse_and_dedupe_parallel(raw_messages: Iterable[dict]) -> list[ParsedEmail]:
    """
    Parse messages in parallel, then deduplicate while preserving original order.

    Returns emails in same order as input (deterministic despite parallelism).
    """
    with time_block("pipeline.parse.parallel"):
        # Convert to list and preserve indices for stable sorting
        messages_list = list(raw_messages)

        # Parse in parallel
        parsed_with_idx: list[tuple[int, ParsedEmail]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all parsing tasks
            future_to_idx = {
                executor.submit(parse_message_strict, msg): idx
                for idx, msg in enumerate(messages_list)
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    parsed = future.result()
                    parsed_with_idx.append((idx, parsed))
                except Exception as exc:
                    log_event("pipeline.parse.parallel.error", index=idx, error=str(exc))
                    counter("pipeline.parse.parallel.errors")
                    # Skip failed parses (already logged by parse_message_strict)

        # Restore original order (critical for determinism)
        parsed_with_idx.sort(key=lambda x: x[0])
        parsed_emails = [email for _, email in parsed_with_idx]

        counter("pipeline.parse.parallel.count", len(parsed_emails))

    # Deduplicate while maintaining order
    return _deduplicate(parsed_emails)
