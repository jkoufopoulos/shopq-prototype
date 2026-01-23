"""
LLM Budget Tracking for ShopQ API.

SCALE-001: Tracks LLM API usage per user and globally to prevent cost overruns.

Budget limits:
- Per user: 100 LLM calls per day
- Global: 10,000 LLM calls per day

Cost estimates (Gemini Flash):
- Classifier: ~$0.0001 per call
- Extractor: ~$0.0002 per call
- Daily per-user max: ~$0.03
- Daily global max: ~$3.00
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import NamedTuple

from shopq.infrastructure.database import get_db_connection, retry_on_db_lock
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter

logger = get_logger(__name__)

# Budget limits
DEFAULT_USER_DAILY_LIMIT = 100  # LLM calls per user per day
DEFAULT_GLOBAL_DAILY_LIMIT = 10000  # Total LLM calls per day

# Cost estimates per call type (for monitoring)
COST_ESTIMATES = {
    "classifier": 0.0001,
    "extractor": 0.0002,
}


class BudgetStatus(NamedTuple):
    """Current budget status for a user."""

    user_calls_today: int
    user_limit: int
    global_calls_today: int
    global_limit: int
    is_allowed: bool
    reason: str | None


def _ensure_budget_table() -> None:
    """Create llm_usage table if it doesn't exist."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                call_type TEXT NOT NULL,
                call_date DATE NOT NULL,
                call_count INTEGER DEFAULT 1,
                estimated_cost REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, call_type, call_date)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_date ON llm_usage(call_date)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_user_date ON llm_usage(user_id, call_date)
        """)
        conn.commit()


# Ensure table exists on module load
try:
    _ensure_budget_table()
except Exception as e:
    logger.warning("Could not create llm_usage table: %s", e)


@retry_on_db_lock()
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
    today = date.today().isoformat()

    with get_db_connection() as conn:
        # Get user's usage today
        cursor = conn.execute(
            """
            SELECT COALESCE(SUM(call_count), 0) as total
            FROM llm_usage
            WHERE user_id = ? AND call_date = ?
            """,
            (user_id, today),
        )
        user_calls = cursor.fetchone()[0]

        # Get global usage today
        cursor = conn.execute(
            """
            SELECT COALESCE(SUM(call_count), 0) as total
            FROM llm_usage
            WHERE call_date = ?
            """,
            (today,),
        )
        global_calls = cursor.fetchone()[0]

    # Check limits
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


@retry_on_db_lock()
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
    today = date.today().isoformat()
    estimated_cost = COST_ESTIMATES.get(call_type, 0.0001)

    with get_db_connection() as conn:
        # Upsert: increment if exists, insert if not
        conn.execute(
            """
            INSERT INTO llm_usage (user_id, call_type, call_date, call_count, estimated_cost)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id, call_type, call_date)
            DO UPDATE SET
                call_count = call_count + 1,
                estimated_cost = estimated_cost + ?
            """,
            (user_id, call_type, today, estimated_cost, estimated_cost),
        )
        conn.commit()

    counter(f"llm.budget.call.{call_type}")
    logger.debug("Recorded LLM call: user=%s, type=%s", user_id, call_type)


def get_daily_usage_report(for_date: date | None = None) -> dict:
    """
    Get usage report for a specific date.

    Args:
        for_date: Date to report on (defaults to today)

    Returns:
        Dict with usage statistics
    """
    report_date = (for_date or date.today()).isoformat()

    with get_db_connection() as conn:
        # Total calls and cost
        cursor = conn.execute(
            """
            SELECT
                COALESCE(SUM(call_count), 0) as total_calls,
                COALESCE(SUM(estimated_cost), 0) as total_cost
            FROM llm_usage
            WHERE call_date = ?
            """,
            (report_date,),
        )
        row = cursor.fetchone()
        total_calls = row[0]
        total_cost = row[1]

        # Breakdown by call type
        cursor = conn.execute(
            """
            SELECT call_type, SUM(call_count) as calls, SUM(estimated_cost) as cost
            FROM llm_usage
            WHERE call_date = ?
            GROUP BY call_type
            """,
            (report_date,),
        )
        by_type = {row[0]: {"calls": row[1], "cost": row[2]} for row in cursor.fetchall()}

        # Unique users
        cursor = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM llm_usage WHERE call_date = ?
            """,
            (report_date,),
        )
        unique_users = cursor.fetchone()[0]

    return {
        "date": report_date,
        "total_calls": total_calls,
        "total_estimated_cost": round(total_cost, 4),
        "unique_users": unique_users,
        "by_type": by_type,
        "limits": {
            "user_daily": DEFAULT_USER_DAILY_LIMIT,
            "global_daily": DEFAULT_GLOBAL_DAILY_LIMIT,
        },
    }
