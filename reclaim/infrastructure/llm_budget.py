"""
LLM Budget Tracking for Reclaim API (in-memory, stateless).

SCALE-001: Tracks LLM API usage per user and globally to prevent cost overruns.
Uses in-memory TTLCache — resets on instance restart (acceptable for abuse prevention).

Budget limits:
- Per user: 500 LLM calls per day
- Global: 10,000 LLM calls per day

Cost estimates (Gemini Flash):
- Classifier: ~$0.0001 per call
- Extractor: ~$0.0002 per call
- Daily per-user max: ~$0.15
- Daily global max: ~$3.00
"""

from __future__ import annotations

from typing import NamedTuple

from cachetools import TTLCache

from reclaim.config import LLM_GLOBAL_DAILY_LIMIT, LLM_USER_DAILY_LIMIT
from reclaim.observability.logging import get_logger
from reclaim.observability.telemetry import counter

logger = get_logger(__name__)

# Budget limits (from centralized config)
DEFAULT_USER_DAILY_LIMIT = LLM_USER_DAILY_LIMIT
DEFAULT_GLOBAL_DAILY_LIMIT = LLM_GLOBAL_DAILY_LIMIT

# Cost estimates per call type (for monitoring)
COST_ESTIMATES = {
    "classifier": 0.0001,
    "extractor": 0.0002,
}

# In-memory counters with 24-hour TTL (reset daily)
_DAY_SECONDS = 86400
_user_calls: TTLCache[str, int] = TTLCache(maxsize=10000, ttl=_DAY_SECONDS)
_global_counter: TTLCache[str, int] = TTLCache(maxsize=1, ttl=_DAY_SECONDS)
_GLOBAL_KEY = "__global__"


class BudgetStatus(NamedTuple):
    """Current budget status for a user."""

    user_calls_today: int
    user_limit: int
    global_calls_today: int
    global_limit: int
    is_allowed: bool
    reason: str | None


def check_budget(
    user_id: str,
    user_limit: int = DEFAULT_USER_DAILY_LIMIT,
    global_limit: int = DEFAULT_GLOBAL_DAILY_LIMIT,
) -> BudgetStatus:
    """
    Check if user is within budget for LLM calls.

    Args:
        user_id: User to check
        user_limit: Max calls per user per day
        global_limit: Max global calls per day

    Returns:
        BudgetStatus with current usage and whether call is allowed
    """
    user_calls = _user_calls.get(user_id, 0)
    global_calls = _global_counter.get(_GLOBAL_KEY, 0)

    if user_calls >= user_limit:
        return BudgetStatus(
            user_calls_today=user_calls,
            user_limit=user_limit,
            global_calls_today=global_calls,
            global_limit=global_limit,
            is_allowed=False,
            reason=f"User daily limit exceeded ({user_calls}/{user_limit})",
        )

    if global_calls >= global_limit:
        return BudgetStatus(
            user_calls_today=user_calls,
            user_limit=user_limit,
            global_calls_today=global_calls,
            global_limit=global_limit,
            is_allowed=False,
            reason=f"Global daily limit exceeded ({global_calls}/{global_limit})",
        )

    return BudgetStatus(
        user_calls_today=user_calls,
        user_limit=user_limit,
        global_calls_today=global_calls,
        global_limit=global_limit,
        is_allowed=True,
        reason=None,
    )


def record_llm_call(
    user_id: str,
    call_type: str = "classifier",
) -> None:
    """
    Record an LLM call for budget tracking.

    Args:
        user_id: User who made the call
        call_type: Type of call (classifier, extractor)
    """
    # Increment user counter
    _user_calls[user_id] = _user_calls.get(user_id, 0) + 1

    # Increment global counter
    _global_counter[_GLOBAL_KEY] = _global_counter.get(_GLOBAL_KEY, 0) + 1

    counter(f"llm.budget.call.{call_type}")
    logger.debug("Recorded LLM call: user=%s, type=%s", user_id, call_type)
