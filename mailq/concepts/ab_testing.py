"""
A/B Testing Infrastructure for Digest Pipeline Migration

Enables side-by-side comparison of V1 (old context_digest.py) and V2 (new concepts/ pipeline).

Features:
- Run both pipelines on same input
- Collect comparative metrics (latency, entity count, word count, etc.)
- Store results for analysis
- Generate comparison reports

Side Effects:
    - Writes to database (ab_test_runs table)
    - Logs telemetry events
    - May write comparison reports to quality_logs/

Core Principles Applied:
    - P1: A/B testing logic in one file
    - P2: Side effects documented in docstrings
    - P3: Full type hints with strict mypy compliance
    - P4: Explicit configuration via environment variables
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mailq.infrastructure.database import get_db_connection
from mailq.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineMetrics:
    """Metrics collected from a single pipeline execution"""

    pipeline_version: str  # "v1" or "v2"
    success: bool
    error_message: str | None = None

    # Performance metrics
    latency_ms: float = 0.0
    total_emails: int = 0

    # Output metrics
    word_count: int = 0
    entity_count: int = 0
    featured_count: int = 0
    critical_count: int = 0

    # Quality metrics
    html_length: int = 0
    has_weather: bool = False
    verified: bool = False

    # Metadata
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ABTestResult:
    """Complete A/B test result with both pipeline metrics"""

    test_id: str
    request_data: dict[str, Any]

    v1_metrics: PipelineMetrics
    v2_metrics: PipelineMetrics

    # Store actual pipeline results for return to client
    v1_result: dict[str, Any] | None = None
    v2_result: dict[str, Any] | None = None

    # Comparison analysis
    latency_delta_ms: float = 0.0  # V2 - V1 (negative = V2 faster)
    entity_count_delta: int = 0  # V2 - V1
    word_count_delta: int = 0  # V2 - V1

    winner: str = "tie"  # "v1", "v2", or "tie"
    reason: str = ""

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ABTestRunner:
    """
    Run A/B tests comparing V1 and V2 digest pipelines.

    Side Effects:
        - Writes to database (ab_test_runs, ab_test_metrics tables)
        - Logs telemetry events
        - May write comparison reports to quality_logs/
    """

    def __init__(self) -> None:
        """Initialize A/B test runner"""
        self.enabled = os.getenv("AB_TEST_ENABLED", "false").lower() in ("true", "1", "yes")
        self.verbose = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

        # Initialize database tables
        self._ensure_tables_exist()

    def _ensure_tables_exist(self) -> None:
        """
        Create A/B testing database tables if they don't exist.

        Side Effects:
            - Creates tables in mailq.db if not present
            - Logs table creation
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Table for A/B test runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_runs (
                    test_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    total_emails INTEGER NOT NULL,
                    v1_success INTEGER NOT NULL,
                    v2_success INTEGER NOT NULL,
                    latency_delta_ms REAL NOT NULL,
                    entity_count_delta INTEGER NOT NULL,
                    word_count_delta INTEGER NOT NULL,
                    winner TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    request_data_json TEXT NOT NULL
                )
            """)

            # Table for individual pipeline metrics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    latency_ms REAL NOT NULL,
                    total_emails INTEGER NOT NULL,
                    word_count INTEGER NOT NULL,
                    entity_count INTEGER NOT NULL,
                    featured_count INTEGER NOT NULL,
                    critical_count INTEGER NOT NULL,
                    html_length INTEGER NOT NULL,
                    has_weather INTEGER NOT NULL,
                    verified INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (test_id) REFERENCES ab_test_runs(test_id)
                )
            """)

            conn.commit()

        if self.verbose:
            logger.info("A/B testing tables ensured to exist")

    async def run_test(
        self,
        request_data: dict[str, Any],
        run_v1_func: Any,  # Async callable that returns dict
        run_v2_func: Any,  # Async callable that returns dict
    ) -> ABTestResult:
        """
        Run both V1 and V2 pipelines and compare results.

        Args:
            request_data: Request payload to test
            run_v1_func: Async function to run V1 pipeline
            run_v2_func: Async function to run V2 pipeline

        Returns:
            ABTestResult with metrics from both pipelines

        Side Effects:
            - Executes both pipeline functions
            - Writes result to database
            - Logs telemetry events
        """
        test_id = f"ab_test_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        email_count = len(request_data.get("current_data", []))
        logger.info(f"[A/B Test] Starting test {test_id} with {email_count} emails")

        # Run V1 pipeline
        v1_start = time.time()
        v1_result = None
        v1_error = None
        try:
            v1_result = await run_v1_func(request_data)
            v1_success = True
        except Exception as e:
            v1_error = str(e)
            v1_success = False
            logger.error(f"[A/B Test] V1 failed: {v1_error}")

        v1_latency_ms = (time.time() - v1_start) * 1000

        # Run V2 pipeline
        v2_start = time.time()
        v2_result = None
        v2_error = None
        try:
            v2_result = await run_v2_func(request_data)
            v2_success = True
        except Exception as e:
            v2_error = str(e)
            v2_success = False
            logger.error(f"[A/B Test] V2 failed: {v2_error}")

        v2_latency_ms = (time.time() - v2_start) * 1000

        # Collect V1 metrics
        v1_metrics = PipelineMetrics(
            pipeline_version="v1",
            success=v1_success,
            error_message=v1_error,
            latency_ms=v1_latency_ms,
            total_emails=len(request_data.get("current_data", [])),
            word_count=v1_result.get("word_count", 0) if v1_result else 0,
            entity_count=v1_result.get("entities_count", 0) if v1_result else 0,
            featured_count=v1_result.get("featured_count", 0) if v1_result else 0,
            critical_count=v1_result.get("critical_count", 0) if v1_result else 0,
            html_length=len(v1_result.get("html", "")) if v1_result else 0,
            has_weather=bool(v1_result.get("weather_data")) if v1_result else False,
            verified=v1_result.get("verified", False) if v1_result else False,
            session_id=v1_result.get("session_id", "") if v1_result else "",
        )

        # Collect V2 metrics
        v2_metrics = PipelineMetrics(
            pipeline_version="v2",
            success=v2_success,
            error_message=v2_error,
            latency_ms=v2_latency_ms,
            total_emails=len(request_data.get("current_data", [])),
            word_count=v2_result.get("word_count", 0) if v2_result else 0,
            entity_count=v2_result.get("entities_count", 0) if v2_result else 0,
            featured_count=v2_result.get("featured_count", 0) if v2_result else 0,
            critical_count=v2_result.get("critical_count", 0) if v2_result else 0,
            html_length=len(v2_result.get("html", "")) if v2_result else 0,
            has_weather=bool(v2_result.get("weather_data")) if v2_result else False,
            verified=v2_result.get("verified", False) if v2_result else False,
            session_id=v2_result.get("session_id", "") if v2_result else "",
        )

        # Calculate deltas
        latency_delta = v2_latency_ms - v1_latency_ms
        entity_delta = v2_metrics.entity_count - v1_metrics.entity_count
        word_delta = v2_metrics.word_count - v1_metrics.word_count

        # Determine winner
        winner, reason = self._determine_winner(v1_metrics, v2_metrics, latency_delta)

        # Create result
        result = ABTestResult(
            test_id=test_id,
            request_data=request_data,
            v1_metrics=v1_metrics,
            v2_metrics=v2_metrics,
            v1_result=v1_result,
            v2_result=v2_result,
            latency_delta_ms=latency_delta,
            entity_count_delta=entity_delta,
            word_count_delta=word_delta,
            winner=winner,
            reason=reason,
        )

        # Store result
        self._store_result(result)

        logger.info(
            f"[A/B Test] Completed {test_id}: {winner} wins - {reason} "
            f"(V1: {v1_latency_ms:.0f}ms, V2: {v2_latency_ms:.0f}ms)"
        )

        return result

    def _determine_winner(
        self, v1: PipelineMetrics, v2: PipelineMetrics, latency_delta: float
    ) -> tuple[str, str]:
        """
        Determine which pipeline performed better.

        Args:
            v1: V1 pipeline metrics
            v2: V2 pipeline metrics
            latency_delta: V2 latency - V1 latency (negative = V2 faster)

        Returns:
            Tuple of (winner, reason)
        """
        # If one failed, the other wins
        if not v1.success and v2.success:
            return "v2", "V1 failed, V2 succeeded"
        if v1.success and not v2.success:
            return "v1", "V2 failed, V1 succeeded"
        if not v1.success and not v2.success:
            return "tie", "Both pipelines failed"

        # Both succeeded - compare quality and performance
        reasons = []

        # Quality comparison
        if v2.entity_count > v1.entity_count:
            reasons.append(f"V2 extracted {v2.entity_count - v1.entity_count} more entities")
        elif v1.entity_count > v2.entity_count:
            reasons.append(f"V1 extracted {v1.entity_count - v2.entity_count} more entities")

        # Performance comparison (only significant if >100ms difference)
        if latency_delta < -100:
            reasons.append(f"V2 was {abs(latency_delta):.0f}ms faster")
        elif latency_delta > 100:
            reasons.append(f"V1 was {latency_delta:.0f}ms faster")

        # Feature comparison
        if v2.featured_count > v1.featured_count:
            reasons.append(f"V2 featured {v2.featured_count - v1.featured_count} more emails")
        elif v1.featured_count > v2.featured_count:
            reasons.append(f"V1 featured {v1.featured_count - v2.featured_count} more emails")

        # Decide winner based on quality > performance
        if v2.entity_count > v1.entity_count:
            return "v2", "; ".join(reasons) or "V2 extracted more entities"
        if v1.entity_count > v2.entity_count:
            return "v1", "; ".join(reasons) or "V1 extracted more entities"
        if latency_delta < -100:
            return "v2", "; ".join(reasons) or "V2 was significantly faster"
        if latency_delta > 100:
            return "v1", "; ".join(reasons) or "V1 was significantly faster"
        return "tie", "; ".join(reasons) or "Similar quality and performance"

    def _store_result(self, result: ABTestResult) -> None:
        """
        Store A/B test result in database.

        Side Effects:
            - Writes to ab_test_runs table
            - Writes to ab_test_metrics table (2 rows)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Store test run
            cursor.execute(
                """
                INSERT INTO ab_test_runs (
                    test_id, timestamp, total_emails,
                    v1_success, v2_success,
                    latency_delta_ms, entity_count_delta, word_count_delta,
                    winner, reason, request_data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result.test_id,
                    result.timestamp,
                    result.v1_metrics.total_emails,
                    int(result.v1_metrics.success),
                    int(result.v2_metrics.success),
                    result.latency_delta_ms,
                    result.entity_count_delta,
                    result.word_count_delta,
                    result.winner,
                    result.reason,
                    json.dumps(result.request_data),
                ),
            )

            # Store V1 metrics
            self._store_pipeline_metrics(cursor, result.test_id, result.v1_metrics)

            # Store V2 metrics
            self._store_pipeline_metrics(cursor, result.test_id, result.v2_metrics)

            conn.commit()

        if self.verbose:
            logger.info(f"Stored A/B test result: {result.test_id}")

    def _store_pipeline_metrics(
        self, cursor: sqlite3.Cursor, test_id: str, metrics: PipelineMetrics
    ) -> None:
        """
        Store metrics for a single pipeline execution.

        Side Effects:
            - Inserts row into ab_test_metrics table
        """
        cursor.execute(
            """
            INSERT INTO ab_test_metrics (
                test_id, pipeline_version, success, error_message,
                latency_ms, total_emails,
                word_count, entity_count, featured_count, critical_count,
                html_length, has_weather, verified,
                session_id, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                test_id,
                metrics.pipeline_version,
                int(metrics.success),
                metrics.error_message,
                metrics.latency_ms,
                metrics.total_emails,
                metrics.word_count,
                metrics.entity_count,
                metrics.featured_count,
                metrics.critical_count,
                metrics.html_length,
                int(metrics.has_weather),
                int(metrics.verified),
                metrics.session_id,
                metrics.timestamp,
            ),
        )

    def get_summary_stats(self, limit: int = 100) -> dict[str, Any]:
        """
        Get summary statistics from recent A/B tests.

        Args:
            limit: Number of recent tests to analyze

        Returns:
            Dictionary with summary statistics

        Side Effects:
            - Reads from database
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get recent test results
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_tests,
                    SUM(CASE WHEN winner = 'v1' THEN 1 ELSE 0 END) as v1_wins,
                    SUM(CASE WHEN winner = 'v2' THEN 1 ELSE 0 END) as v2_wins,
                    SUM(CASE WHEN winner = 'tie' THEN 1 ELSE 0 END) as ties,
                    AVG(latency_delta_ms) as avg_latency_delta,
                    AVG(entity_count_delta) as avg_entity_delta,
                    AVG(word_count_delta) as avg_word_delta,
                    SUM(v1_success) as v1_success_count,
                    SUM(v2_success) as v2_success_count
                FROM ab_test_runs
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )

            row = cursor.fetchone()

        if not row or row[0] == 0:
            return {
                "total_tests": 0,
                "message": "No A/B tests run yet",
            }

        total = row[0]
        return {
            "total_tests": total,
            "v1_wins": row[1],
            "v2_wins": row[2],
            "ties": row[3],
            "v1_win_rate": (row[1] / total * 100) if total > 0 else 0,
            "v2_win_rate": (row[2] / total * 100) if total > 0 else 0,
            "avg_latency_delta_ms": row[4],
            "avg_entity_count_delta": row[5],
            "avg_word_count_delta": row[6],
            "v1_success_rate": (row[7] / total * 100) if total > 0 else 0,
            "v2_success_rate": (row[8] / total * 100) if total > 0 else 0,
            "recommendation": self._get_recommendation(row[1], row[2], row[4]),
        }

    def _get_recommendation(
        self, v1_wins: int, v2_wins: int, _avg_latency_delta: float | None
    ) -> str:
        """Generate recommendation based on A/B test results"""
        if v1_wins + v2_wins == 0:
            return "Not enough data"

        v2_win_rate = v2_wins / (v1_wins + v2_wins) if (v1_wins + v2_wins) > 0 else 0

        if v2_win_rate > 0.8:
            return "Strong recommendation: Deploy V2 to production"
        if v2_win_rate > 0.6:
            return "Moderate recommendation: V2 shows improvement, consider gradual rollout"
        if v2_win_rate > 0.4:
            return "Neutral: V1 and V2 are comparable, monitor more tests"
        return "Caution: V1 outperforming V2, investigate V2 issues before rollout"


# Global singleton
_ab_test_runner: ABTestRunner | None = None


def get_ab_test_runner() -> ABTestRunner:
    """
    Get global ABTestRunner singleton.

    Returns:
        Global ABTestRunner instance

    Side Effects:
        - Initializes singleton on first call
        - Creates database tables if needed
    """
    global _ab_test_runner
    if _ab_test_runner is None:
        _ab_test_runner = ABTestRunner()
    return _ab_test_runner
