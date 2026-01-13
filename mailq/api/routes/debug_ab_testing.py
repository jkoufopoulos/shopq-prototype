"""
A/B Testing debug endpoints.

Extracted from debug.py to reduce file size.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/ab-testing/summary")
async def get_ab_testing_summary(limit: int = Query(default=100)) -> dict[str, Any]:
    """
    Get summary statistics from recent A/B tests.

    Shows:
    - Total tests run
    - Win rate for each pipeline
    - Average latency delta
    - Average entity/word count deltas
    - Success rates
    - Recommendation for rollout

    Side Effects:
        - Reads from ab_test_runs table in mailq.db via runner.get_summary_stats()
    """
    from mailq.concepts.ab_testing import get_ab_test_runner

    runner = get_ab_test_runner()
    stats = runner.get_summary_stats(limit=limit)

    return {
        "timestamp": datetime.now().isoformat(),
        "stats": stats,
        "limit": limit,
    }


@router.get("/ab-testing/recent")
async def get_recent_ab_tests(limit: int = Query(default=20)) -> dict[str, Any]:
    """
    Get recent A/B test results with detailed metrics.

    Returns individual test results showing:
    - Test ID and timestamp
    - Winner and reason
    - Latency comparison
    - Entity/word count comparison
    - Success status for both pipelines

    Side Effects:
        - Reads from ab_test_runs table in mailq.db
    """
    from mailq.infrastructure.database import get_db_connection

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                test_id, timestamp, total_emails,
                v1_success, v2_success,
                latency_delta_ms, entity_count_delta, word_count_delta,
                winner, reason
            FROM ab_test_runs
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append(
            {
                "test_id": row[0],
                "timestamp": row[1],
                "total_emails": row[2],
                "v1_success": bool(row[3]),
                "v2_success": bool(row[4]),
                "latency_delta_ms": row[5],
                "entity_count_delta": row[6],
                "word_count_delta": row[7],
                "winner": row[8],
                "reason": row[9],
            }
        )

    return {
        "timestamp": datetime.now().isoformat(),
        "count": len(results),
        "results": results,
    }


@router.get("/ab-testing/{test_id}")
async def get_ab_test_details(test_id: str) -> dict[str, Any]:
    """
    Get detailed metrics for a specific A/B test.

    Returns:
    - Full metrics for both V1 and V2 pipelines
    - Request data used for test
    - Comparison analysis

    Side Effects:
        - Reads from ab_test_runs and ab_test_metrics tables in mailq.db
    """
    from mailq.infrastructure.database import get_db_connection

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get test run
        cursor.execute(
            """
            SELECT
                test_id, timestamp, total_emails,
                v1_success, v2_success,
                latency_delta_ms, entity_count_delta, word_count_delta,
                winner, reason, request_data_json
            FROM ab_test_runs
            WHERE test_id = ?
        """,
            (test_id,),
        )

        run_row = cursor.fetchone()
        if not run_row:
            return {"error": f"Test {test_id} not found"}

        # Get metrics for both pipelines
        cursor.execute(
            """
            SELECT
                pipeline_version, success, error_message,
                latency_ms, total_emails,
                word_count, entity_count, featured_count, critical_count,
                html_length, has_weather, verified,
                session_id, timestamp
            FROM ab_test_metrics
            WHERE test_id = ?
            ORDER BY pipeline_version
        """,
            (test_id,),
        )

        metrics_rows = cursor.fetchall()

    # Parse metrics
    metrics = {}
    for row in metrics_rows:
        version = row[0]
        metrics[version] = {
            "success": bool(row[1]),
            "error_message": row[2],
            "latency_ms": row[3],
            "total_emails": row[4],
            "word_count": row[5],
            "entity_count": row[6],
            "featured_count": row[7],
            "critical_count": row[8],
            "html_length": row[9],
            "has_weather": bool(row[10]),
            "verified": bool(row[11]),
            "session_id": row[12],
            "timestamp": row[13],
        }

    return {
        "test_id": run_row[0],
        "timestamp": run_row[1],
        "total_emails": run_row[2],
        "winner": run_row[8],
        "reason": run_row[9],
        "comparison": {
            "latency_delta_ms": run_row[5],
            "entity_count_delta": run_row[6],
            "word_count_delta": run_row[7],
        },
        "v1_metrics": metrics.get("v1", {}),
        "v2_metrics": metrics.get("v2", {}),
        "request_data": run_row[10],  # JSON string
    }
