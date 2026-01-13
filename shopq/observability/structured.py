"""
Structured Logging Kit for ShopQ

Provides one-line JSON event logging with:
- Correlation IDs (session_id + email_id)
- Event taxonomy (~12 event types across 5 handoffs)
- Sampling & rate limits (10% info, 100% error/critical)
- Privacy redaction (subjects, PII)
- Copy-paste ready for Claude Code debugging

Usage:
    from shopq.observability.structured import StructuredLogger, EventType

    logger = StructuredLogger(session_id="20251111_234512")

    logger.log_event(
        event_type=EventType.LLM_CALL_ERROR,
        email_id="18c2a4f8d",
        error="QuotaExceeded",
        fallback=True,
        cost_wasted=0.0001
    )

Output:
    {"ts":"2025-11-11T23:45:12.123Z","level":"ERROR","session":"20251111_234512","email":"18c2a4f8d","event":"llm_call_error","error":"QuotaExceeded","fallback":true,"cost":0.0001}
"""

import hmac
import json
import logging
import random
import re
import secrets
import threading
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any

# Configure base logger
logger = logging.getLogger("shopq.structured")

# HIGH FIX: Pre-compiled regex patterns for redaction (performance optimization)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")


class EventType(str, Enum):
    """Event taxonomy covering 5 critical handoffs"""

    # 1. LLM Classification
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_OK = "llm_call_ok"
    LLM_CALL_ERROR = "llm_call_error"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_FALLBACK_INVOKED = "llm_fallback_invoked"
    LLM_FALLBACK_OK = "llm_fallback_ok"
    LLM_FALLBACK_ERROR = "llm_fallback_error"

    # 2. Bridge Mapper
    MAP_START = "map_start"
    MAP_DECISION = "map_decision"
    MAP_MISSING_FIELD = "map_missing_field"
    MAP_GUARDRAIL_APPLIED = "map_guardrail_applied"
    MAP_DEFAULT_USED = "map_default_used"
    MAP_ERROR = "map_error"

    # 3. Temporal Enrichment
    TEMPORAL_PARSE_OK = "temporal_parse_ok"
    TEMPORAL_PARSE_ERROR = "temporal_parse_error"
    TEMPORAL_RESOLVE_DECISION = "temporal_resolve_decision"
    TEMPORAL_FILTER_APPLIED = "temporal_filter_applied"

    # 4. Entity Extraction
    EXTRACT_ENTITIES_OK = "extract_entities_ok"
    EXTRACT_ENTITIES_ERROR = "extract_entities_error"
    EXTRACT_INCONSISTENT = "extract_inconsistent"

    # 5. Digest Assembly
    DIGEST_BUILD_OK = "digest_build_ok"
    DIGEST_BUILD_ERROR = "digest_build_error"
    DIGEST_MISSED_DETECTED = "digest_missed_detected"
    DIGEST_FLAGGED_PENDING = "digest_flagged_pending"

    # 6. Extension/Label Application
    EXT_BATCH_START = "ext_batch_start"
    EXT_BATCH_DONE = "ext_batch_done"
    EXT_LABEL_APPLY_OK = "ext_label_apply_ok"
    EXT_LABEL_APPLY_ERROR = "ext_label_apply_error"
    EXT_ARCHIVE_ERROR = "ext_archive_error"
    EXT_MISMATCH = "ext_mismatch"

    # 7. Heartbeat/Checkpointing
    HEARTBEAT_RESUME_DETECTED = "heartbeat_resume_detected"
    HEARTBEAT_RESUME_OK = "heartbeat_resume_ok"
    HEARTBEAT_RESUME_ERROR = "heartbeat_resume_error"
    CHECKPOINT_SAVE = "checkpoint_save"
    CHECKPOINT_CLEAR = "checkpoint_clear"
    CHECKPOINT_LOAD = "checkpoint_load"


# Event severity mapping
EVENT_SEVERITY = {
    # LLM - errors are ERROR, success is INFO
    EventType.LLM_CALL_START: logging.DEBUG,
    EventType.LLM_CALL_OK: logging.INFO,
    EventType.LLM_CALL_ERROR: logging.ERROR,
    EventType.LLM_RATE_LIMITED: logging.ERROR,
    EventType.LLM_FALLBACK_INVOKED: logging.WARNING,
    EventType.LLM_FALLBACK_OK: logging.INFO,
    EventType.LLM_FALLBACK_ERROR: logging.ERROR,
    # Bridge Mapper
    EventType.MAP_START: logging.DEBUG,
    EventType.MAP_DECISION: logging.INFO,
    EventType.MAP_MISSING_FIELD: logging.WARNING,
    EventType.MAP_GUARDRAIL_APPLIED: logging.INFO,
    EventType.MAP_DEFAULT_USED: logging.WARNING,
    EventType.MAP_ERROR: logging.ERROR,
    # Temporal
    EventType.TEMPORAL_PARSE_OK: logging.DEBUG,
    EventType.TEMPORAL_PARSE_ERROR: logging.ERROR,
    EventType.TEMPORAL_RESOLVE_DECISION: logging.INFO,
    EventType.TEMPORAL_FILTER_APPLIED: logging.INFO,
    # Entity Extraction
    EventType.EXTRACT_ENTITIES_OK: logging.INFO,
    EventType.EXTRACT_ENTITIES_ERROR: logging.ERROR,
    EventType.EXTRACT_INCONSISTENT: logging.WARNING,
    # Digest
    EventType.DIGEST_BUILD_OK: logging.INFO,
    EventType.DIGEST_BUILD_ERROR: logging.ERROR,
    EventType.DIGEST_MISSED_DETECTED: logging.WARNING,
    EventType.DIGEST_FLAGGED_PENDING: logging.INFO,
    # Extension
    EventType.EXT_BATCH_START: logging.INFO,
    EventType.EXT_BATCH_DONE: logging.INFO,
    EventType.EXT_LABEL_APPLY_OK: logging.DEBUG,
    EventType.EXT_LABEL_APPLY_ERROR: logging.ERROR,
    EventType.EXT_ARCHIVE_ERROR: logging.ERROR,
    EventType.EXT_MISMATCH: logging.WARNING,
    # Heartbeat
    EventType.HEARTBEAT_RESUME_DETECTED: logging.INFO,
    EventType.HEARTBEAT_RESUME_OK: logging.INFO,
    EventType.HEARTBEAT_RESUME_ERROR: logging.ERROR,
    EventType.CHECKPOINT_SAVE: logging.DEBUG,
    EventType.CHECKPOINT_CLEAR: logging.DEBUG,
    EventType.CHECKPOINT_LOAD: logging.INFO,
}


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles common non-serializable types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dict__"):
            return str(obj)  # Fallback for custom objects
        return super().default(obj)


class StructuredLogger:
    """
    Structured event logger with sampling and privacy redaction

    Features:
    - Correlation via session_id (organize run) + email_id (short hash)
    - Sampling: 10% for INFO, 100% for ERROR/CRITICAL
    - Privacy: auto-redacts subjects and PII
    - One-line JSON output for easy parsing
    """

    def __init__(
        self,
        session_id: str | None = None,
        sample_rate_info: float = 0.1,
        sample_rate_error: float = 1.0,
    ):
        """
        Args:
            session_id: Unique ID for this session (e.g., "20251111_234512")
            sample_rate_info: % of INFO logs to emit (0.0-1.0)
            sample_rate_error: % of ERROR logs to emit (0.0-1.0)
        """
        self.session_id = session_id or self._generate_session_id()
        self.sample_rate_info = sample_rate_info
        self.sample_rate_error = sample_rate_error
        self._rate_limiter: dict[str, datetime] = {}  # event_key -> last_log_time
        self._rate_limiter_lock = threading.Lock()  # CRITICAL FIX: Thread safety
        self._last_cleanup = datetime.now(UTC)  # CRITICAL FIX: Memory cleanup
        self._salt = secrets.token_bytes(32)  # HIGH FIX: HMAC salt for privacy

    @staticmethod
    def _generate_session_id() -> str:
        """Generate session ID: YYYYMMDD_HHMMSS"""
        return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    def hash_email_id(self, email_id: str) -> str:
        """Hash email ID with HMAC for privacy (HIGH FIX: cryptographic hash with salt)

        Side Effects:
            None (pure function - computes HMAC hash only)
        """
        if not email_id:
            return "unknown"
        # HMAC-SHA256 with per-instance salt (64-bit output = 16 hex chars)
        h = hmac.new(self._salt, email_id.encode("utf-8"), "sha256")
        return h.hexdigest()[:16]

    @staticmethod
    def redact_subject(subject: str, max_len: int = 50) -> str:
        """Redact subject line for privacy (keep first 50 chars, hash rest)
        HIGH FIX: Use pre-compiled regex patterns for performance

        Side Effects:
            None (pure function - redacts PII from string only)
        """
        if not subject:
            return ""

        # Truncate to max_len
        truncated = subject[:max_len]

        # Replace email addresses (use pre-compiled pattern)
        truncated = _EMAIL_PATTERN.sub("[EMAIL]", truncated)

        # Replace phone numbers (use pre-compiled pattern)
        truncated = _PHONE_PATTERN.sub("[PHONE]", truncated)

        return truncated + ("..." if len(subject) > max_len else "")

    def _should_log(self, event_type: EventType) -> bool:
        """Determine if event should be logged based on sampling rate"""
        severity = EVENT_SEVERITY.get(event_type, logging.INFO)

        # Always log ERROR and CRITICAL
        if severity >= logging.ERROR:
            return random.random() < self.sample_rate_error

        # Sample INFO/DEBUG
        return random.random() < self.sample_rate_info

    def _rate_limit(self, event_key: str, min_interval_sec: float = 60.0) -> bool:
        """
        Rate limit events by key (e.g., "llm_call_error:18c2a4f8d")
        CRITICAL FIX: Thread-safe with periodic cleanup to prevent memory leak

        Returns:
            True if event should be logged, False if rate limited
        """
        now = datetime.now(UTC)

        with self._rate_limiter_lock:
            # Periodic cleanup: remove entries older than 1 hour (every 5 minutes)
            if (now - self._last_cleanup).total_seconds() > 300:  # 5 minutes
                cutoff = now - timedelta(hours=1)
                self._rate_limiter = {k: v for k, v in self._rate_limiter.items() if v > cutoff}
                self._last_cleanup = now

            # Check rate limit window
            last_log = self._rate_limiter.get(event_key)

            if last_log and (now - last_log).total_seconds() < min_interval_sec:
                return False  # Rate limited

            self._rate_limiter[event_key] = now
            return True

    def log_event(
        self,
        event_type: EventType,
        email_id: str | None = None,
        rate_limit_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Log a structured event

        Args:
            event_type: Event type from EventType enum
            email_id: Email ID (will be hashed to 12 chars)
            rate_limit_key: Optional key for rate limiting (default: event_type)
            **kwargs: Additional fields for the event

        Example:
            logger.log_event(
                EventType.LLM_CALL_ERROR,
                email_id="18c2a4f8d3e2f1a0b9c8d7e6f5a4b3c2",
                error="QuotaExceeded",
                fallback=True,
                cost_wasted=0.0001
            )

        Side Effects:
            - Writes structured JSON log entry to logging system
            - Updates rate limiter dictionary (thread-safe)
            - May modify _rate_limiter dict during periodic cleanup
        """
        # Check sampling
        if not self._should_log(event_type):
            return

        # Check rate limiting
        rl_key = rate_limit_key or f"{event_type}:{self.hash_email_id(email_id or 'none')}"
        severity = EVENT_SEVERITY.get(event_type, logging.INFO)

        # Only rate limit INFO/DEBUG (not errors)
        if severity < logging.ERROR and not self._rate_limit(rl_key):
            return

        # Build event payload
        event = {
            "ts": datetime.now(UTC).isoformat(),
            "level": logging.getLevelName(severity),
            "session": self.session_id,
            "event": event_type.value,
        }

        # Add email_id if provided
        if email_id:
            event["email"] = self.hash_email_id(email_id)

        # Add custom fields
        for key, value in kwargs.items():
            # Redact subject if present
            if key == "subject" and isinstance(value, str):
                event[key] = self.redact_subject(value)
            # Truncate long strings
            elif isinstance(value, str) and len(value) > 200:
                event[key] = value[:200] + "..."
            else:
                event[key] = value

        # Log as one-line JSON (HIGH FIX: SafeJSONEncoder handles datetime/Enum/objects)
        try:
            json_line = json.dumps(event, separators=(",", ":"), cls=SafeJSONEncoder)
            logger.log(severity, json_line)
        except Exception as e:
            # Fallback: log error without crashing pipeline
            logger.error(
                f"structured_log_error: failed to serialize event type={event_type} error={e}"
            )

    # Convenience methods for common events

    def llm_call_error(
        self, email_id: str, error: str, fallback: bool = False, cost: float = 0.0
    ) -> None:
        """Log LLM classification error

        Side Effects:
            - Logs event to application logger via log_event()
        """
        self.log_event(
            EventType.LLM_CALL_ERROR,
            email_id=email_id,
            error=error,
            fallback=fallback,
            cost=cost,
        )

    def llm_rate_limited(self, email_id: str, retry_after: int | None = None) -> None:
        """Log LLM rate limit hit

        Side Effects:
            - Logs event to application logger via log_event()
        """
        self.log_event(
            EventType.LLM_RATE_LIMITED,
            email_id=email_id,
            retry_after=retry_after,
        )

    def map_decision(
        self,
        email_id: str,
        importance: str,
        source: str,
        rule_name: str | None = None,
    ) -> None:
        """Log bridge mapper decision

        Side Effects:
            - Logs event to application logger via log_event()
        """
        self.log_event(
            EventType.MAP_DECISION,
            email_id=email_id,
            importance=importance,
            source=source,
            rule=rule_name,
        )

    def map_guardrail_applied(self, email_id: str, rule_name: str, importance: str) -> None:
        """Log guardrail override

        Side Effects:
            - Logs event to application logger via log_event()
        """
        self.log_event(
            EventType.MAP_GUARDRAIL_APPLIED,
            email_id=email_id,
            rule=rule_name,
            importance=importance,
        )

    def temporal_resolve(
        self,
        email_id: str,
        decision: str,
        reason: str,
        hours_until: float | None = None,
    ) -> None:
        """Log temporal enrichment decision

        Side Effects:
            - Logs event to application logger via log_event()
        """
        self.log_event(
            EventType.TEMPORAL_RESOLVE_DECISION,
            email_id=email_id,
            decision=decision,  # escalated/downgraded/expired
            reason=reason,
            hours=hours_until,
        )

    def extract_entities_ok(self, count_by_type: dict[str, int], avg_conf: float) -> None:
        """Log successful entity extraction

        Side Effects:
            - Logs event to application logger via log_event()
        """
        self.log_event(
            EventType.EXTRACT_ENTITIES_OK,
            counts=count_by_type,
            avg_conf=round(avg_conf, 2),
        )

    def digest_build_ok(self, featured: int, time_sensitive: int, routine: int, total: int) -> None:
        """Log successful digest build

        Side Effects:
            - Logs event to application logger via log_event()
        """
        self.log_event(
            EventType.DIGEST_BUILD_OK,
            featured=featured,
            time_sensitive=time_sensitive,
            routine=routine,
            total=total,
        )


# Global logger instance (can be overridden)
_global_logger: StructuredLogger | None = None


def get_logger(session_id: str | None = None) -> StructuredLogger:
    """
    Get or create global structured logger

    Args:
        session_id: Optional session ID (creates new logger if provided)

    Returns:
        StructuredLogger instance

    Side Effects:
        - May modify global _global_logger variable if creating new logger
    """
    global _global_logger

    if session_id or _global_logger is None:
        _global_logger = StructuredLogger(session_id=session_id)

    return _global_logger
