"""

from __future__ import annotations

Observability Module - Comprehensive logging and validation

Provides:
1. Entity link validation in narrative
2. Count validation (digest vs classified)
3. Weather API usage tracking
4. Import classification reasoning
"""

import os
import re
from typing import Any

from mailq.observability.logging import get_logger

logger = get_logger(__name__)

# Precompile regex patterns for performance and ReDoS prevention
# Using re.ASCII flag to prevent catastrophic backtracking on unicode
SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?]+", re.ASCII)
FLIGHT_NUMBER_PATTERN = re.compile(r"[A-Z]{2,3}\s*\d{1,4}", re.ASCII)
TIME_PATTERN = re.compile(r"\d{1,2}:\d{2}", re.ASCII)

# Maximum text length to process (prevent DoS via massive emails)
MAX_TEXT_LENGTH = 10000


def _safe_regex_search(
    pattern: re.Pattern[str], text: str, max_len: int = MAX_TEXT_LENGTH
) -> re.Match[str] | None:
    """
    Safe regex search with length limit to prevent ReDoS attacks.

    Args:
        pattern: Compiled regex pattern
        text: Text to search
        max_len: Maximum text length to process

    Returns:
        Match object or None

    Side Effects:
        - Logs warning if text exceeds max_len (truncates without failing)
    """
    if len(text) > max_len:
        logger.warning(
            "Text exceeds max length for regex search: %d > %d (truncating)", len(text), max_len
        )
        text = text[:max_len]

    return pattern.search(text)


class ObservabilityLogger:
    """Centralized logging for observability"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.logs: dict[str, Any] = {
            "importance": [],
            "entities": [],
            "weather": {},
            "validation": [],
        }

        # Check if verbose logging is enabled via DEBUG env var
        self.verbose = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

    def log_importance(
        self,
        thread_id: str,
        subject: str,
        importance: str,
        reason: str,
        email_type: str | None = None,
        attention: str | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Log importance classification decision

        Shows WHY each email was prioritized (or not)

        Side Effects:
            - Appends to internal logs["importance"] list
            - Writes to logger if verbose mode enabled
        """
        self.logs["importance"].append(
            {
                "thread_id": thread_id,
                "subject": subject[:60],
                "importance": importance,
                "reason": reason,
                "email_type": email_type,
                "attention": attention,
                "source": source,
                "metadata": metadata or {},
            }
        )

        # Only log importance classifications if DEBUG mode is enabled
        # Otherwise this creates 100+ log entries for large digests
        if self.verbose:
            logger.info(
                "[Importance] %s: %s - %s",
                importance.upper(),
                subject[:50],
                reason,
            )

    def log_entity(
        self,
        thread_id: str,
        subject: str,
        entity_extracted: bool,
        entity_type: str | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Log entity extraction result

        Shows which emails got entities and why (or why not)

        Side Effects:
            - Appends to internal logs["entities"] list
            - Writes to logger if verbose mode enabled
        """
        self.logs["entities"].append(
            {
                "thread_id": thread_id,
                "subject": subject[:60],
                "extracted": entity_extracted,
                "entity_type": entity_type,
                "reason": reason,
            }
        )

        # Only log entity extraction if DEBUG mode is enabled
        if self.verbose:
            if entity_extracted:
                logger.info("[Entity] ✅ %s: %s", entity_type, subject[:50])
            else:
                logger.warning(
                    "[Entity] ❌ No entity: %s - %s",
                    subject[:50],
                    reason or "no patterns matched",
                )

    def log_weather_api(
        self,
        called: bool,
        success: bool,
        data: dict[str, Any] | None = None,
        used_in_narrative: bool = False,
        reason: str | None = None,
    ) -> None:
        """
        Log weather API usage

        Shows if API was called, succeeded, and if data was used

        Side Effects:
            - Updates internal logs["weather"] dict
            - Writes to logger (info/error/warning based on status)
        """
        self.logs["weather"] = {
            "called": called,
            "success": success,
            "data": data,
            "used_in_narrative": used_in_narrative,
            "reason": reason,
        }

        if not called:
            logger.info("[Weather] Not called - %s", reason)
        elif not success:
            logger.error("[Weather] ❌ API failed - %s", reason)
        elif not used_in_narrative:
            logger.warning("[Weather] ⚠️ Data received but not used - %s", reason)
        else:
            temp = data.get("temperature", "?") if data else "?"
            logger.info("[Weather] ✅ Used in narrative (%s°)", temp)

    def log_validation_error(self, error: str) -> None:
        """
        Log validation error

        Side Effects:
            - Appends to internal logs["validation"] list
            - Writes error to logger
        """
        self.logs["validation"].append({"type": "error", "message": error})
        logger.error("[Validation] ❌ %s", error)

    def log_validation_warning(self, warning: str) -> None:
        """
        Log validation warning

        Side Effects:
            - Appends to internal logs["validation"] list
            - Writes warning to logger
        """
        self.logs["validation"].append({"type": "warning", "message": warning})
        logger.warning("[Validation] ⚠️  %s", warning)

    def print_summary(self) -> None:
        """
        Print observability summary (only in DEBUG mode)

        Side Effects:
            - Writes multiple log entries to logger if verbose mode enabled
        """
        if not self.verbose:
            return  # Skip summary in production mode

        logger.info("\n%s", "=" * 80)
        logger.info("📊 OBSERVABILITY SUMMARY - Session: %s", self.session_id)
        logger.info("%s", "=" * 80)

        logger.info("\n💡 IMPORTANCE DECISIONS")
        importance_counts: dict[str, int] = {}
        for log in self.logs["importance"]:
            imp = log["importance"]
            importance_counts[imp] = importance_counts.get(imp, 0) + 1

        for imp, count in sorted(importance_counts.items()):
            logger.info("  %s: %s", imp, count)

        logger.info("\n🎯 ENTITY EXTRACTION")
        extracted = sum(1 for e in self.logs["entities"] if e["extracted"])
        total = len(self.logs["entities"])
        logger.info(
            "  Success rate: %s/%s (%.1f%%)",
            extracted,
            total,
            extracted / total * 100 if total else 0,
        )

        if total - extracted > 0:
            logger.info("  Failed extractions:")
            for log in self.logs["entities"]:
                if not log["extracted"]:
                    logger.info("    - %s", log["subject"])

        logger.info("\n🌤️  WEATHER API")
        weather = self.logs["weather"]
        if weather:
            logger.info("  Called: %s", weather.get("called", False))
            logger.info("  Success: %s", weather.get("success", False))
            logger.info("  Used: %s", weather.get("used_in_narrative", False))
            if weather.get("reason"):
                logger.info("  Reason: %s", weather["reason"])

        logger.info("\n✅ VALIDATION")
        errors = [v for v in self.logs["validation"] if v["type"] == "error"]
        warnings = [v for v in self.logs["validation"] if v["type"] == "warning"]

        logger.info("  Errors: %s", len(errors))
        logger.info("  Warnings: %s", len(warnings))

        logger.info("\n%s\n", "=" * 80)


def validate_narrative_links(
    narrative: str, entities: list[Any], logger: ObservabilityLogger
) -> bool:
    """
    Validate that all narrative sentences have entity links

    Returns True if valid, logs errors for invalid

    Side Effects:
        - Calls logger.log_validation_error() for each unlinked sentence
        - Logs warning if narrative exceeds max length (truncates)
    """
    if not narrative or not entities:
        return True

    # Enforce length limit to prevent ReDoS
    if len(narrative) > MAX_TEXT_LENGTH:
        logger.log_validation_warning(
            f"Narrative exceeds max length ({len(narrative)} > {MAX_TEXT_LENGTH}), truncating"
        )
        narrative = narrative[:MAX_TEXT_LENGTH]

    # Extract entity names for matching
    entity_names = set()
    for entity in entities:
        # Extract names from different entity types
        if hasattr(entity, "airline") and entity.airline:
            entity_names.add(entity.airline.lower())
        if hasattr(entity, "title") and entity.title:
            entity_names.add(entity.title.lower())
        if hasattr(entity, "merchant") and entity.merchant:
            entity_names.add(entity.merchant.lower())
        if hasattr(entity, "from_sender") and entity.from_sender:
            entity_names.add(entity.from_sender.lower())
        if hasattr(entity, "category") and entity.category:
            entity_names.add(entity.category.lower())

    # Split narrative into sentences using precompiled pattern
    sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(narrative) if s.strip()]

    # Skip greeting/closing sentences
    skip_patterns = [
        "good morning",
        "have a great",
        "here's what",
        "your day",
        "have a productive",
        "enjoy your",
        "nothing urgent",
        "you have",
        "routine emails",
    ]

    unlinked_sentences = []

    for sentence in sentences:
        sentence_lower = sentence.lower()

        # Skip greeting/closing
        if any(pattern in sentence_lower for pattern in skip_patterns):
            continue

        # Check if mentions any entity
        has_entity_mention = any(name in sentence_lower for name in entity_names)

        # Special cases that don't need entity links
        is_weather = "weather" in sentence_lower or "°" in sentence
        is_summary_statement = any(
            word in sentence_lower
            for word in ["total", "including", "overall", "summary", "everything else"]
        )

        if not has_entity_mention and not is_weather and not is_summary_statement:
            unlinked_sentences.append(sentence)

    # Log errors
    is_valid = len(unlinked_sentences) == 0

    if not is_valid:
        logger.log_validation_error(
            f"Found {len(unlinked_sentences)} sentences without entity links"
        )
        for sentence in unlinked_sentences:
            logger.log_validation_error(f'  Unlinked: "{sentence[:80]}..."')

    return is_valid


def validate_digest_counts(
    featured_count: int,
    orphaned_count: int,
    noise_breakdown: dict[str, int],
    total_threads: int,
    logger: ObservabilityLogger,
) -> bool:
    """
    Validate that digest counts match classified totals

    Returns True if valid, logs errors for mismatches

    Side Effects:
        - Calls logger.log_validation_error() for count mismatches
        - Calls logger.log_validation_warning() if validation passes
    """
    noise_total = sum(noise_breakdown.values())
    digest_total = featured_count + orphaned_count + noise_total

    is_valid = True

    if digest_total != total_threads:
        is_valid = False
        logger.log_validation_error(
            f"Count mismatch: {digest_total} in digest != {total_threads} classified"
        )
        logger.log_validation_error(
            f"  Featured: {featured_count}, Orphaned: {orphaned_count}, Noise: {noise_total}"
        )

    # Validate individual categories
    for category, count in noise_breakdown.items():
        if count < 0:
            is_valid = False
            logger.log_validation_error(f"  Negative count for '{category}': {count}")

        if count > total_threads:
            is_valid = False
            logger.log_validation_error(
                f"  Category '{category}' count ({count}) exceeds total ({total_threads})"
            )

    if is_valid:
        logger.log_validation_warning(
            f"✅ Count validation passed: {digest_total} total = {featured_count} featured + "
            f"{orphaned_count} orphaned + {noise_total} noise"
        )

    return is_valid


def get_entity_failure_reason(email: dict[str, Any], entity_type: str) -> str:
    """
    Get specific reason why entity extraction failed

    Args:
        email: Email dict containing subject, snippet fields
        entity_type: Type of entity that failed (flight, event, deadline, etc.)

    Returns:
        Human-readable string explaining why extraction failed
    """
    # Limit subject and snippet length to prevent ReDoS
    subject = email.get("subject", "")[:500]
    snippet = email.get("snippet", "")[:500]
    text = f"{subject} {snippet}".lower()

    reasons = {
        "flight": [
            (
                "no flight number",
                lambda: "flight" not in text or not _safe_regex_search(FLIGHT_NUMBER_PATTERN, text),
            ),
            (
                "missing airline",
                lambda: not any(
                    airline in text for airline in ["united", "delta", "american", "southwest"]
                ),
            ),
        ],
        "event": [
            (
                "no event indicators",
                lambda: not any(
                    word in text for word in ["starts", "begins", "event", "meeting", "class"]
                ),
            ),
            ("missing time", lambda: not _safe_regex_search(TIME_PATTERN, text)),
        ],
        "deadline": [
            ("no due date", lambda: "due" not in text),
            (
                "missing bill keywords",
                lambda: not any(word in text for word in ["bill", "payment", "invoice"]),
            ),
        ],
    }

    if entity_type in reasons:
        for reason_text, check_func in reasons[entity_type]:
            try:
                if check_func():  # type: ignore[no-untyped-call]
                    return reason_text
            except (TypeError, AttributeError, KeyError):
                # Lambda may fail if entity fields are missing or wrong type
                pass

    return "no patterns matched"
