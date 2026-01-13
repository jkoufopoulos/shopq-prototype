"""

from __future__ import annotations

API endpoints for tracking and observability data
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from mailq.infrastructure.database import get_db_connection
from mailq.observability.tracking import EmailThreadTracker

router = APIRouter()


@router.get("/api/tracking/sessions")
async def list_sessions() -> dict[str, Any]:
    """List all tracking sessions

    Side Effects:
        - Reads from email_threads table in mailq.db
    """
    # Query for unique sessions
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT session_id,
                   COUNT(*) as thread_count,
                   MIN(timestamp) as first_email,
                   MAX(timestamp) as last_email
            FROM email_threads
            GROUP BY session_id
            ORDER BY session_id DESC
            LIMIT 50
        """)

        sessions = []
        for row in cursor.fetchall():
            sessions.append(
                {
                    "session_id": row[0],
                    "thread_count": row[1],
                    "first_email": row[2],
                    "last_email": row[3],
                }
            )

    return {"sessions": sessions, "total": len(sessions)}


@router.get("/api/tracking/session/{session_id}")
async def get_session_report(session_id: str) -> dict[str, Any]:
    """Get detailed report for a session

    Side Effects:
        - Reads from email_threads and summary_emails tables in mailq.db
    """
    tracker = EmailThreadTracker()

    # Get summary
    summary = tracker.get_session_summary(session_id)

    if summary["total_threads"] == 0:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Get all threads
    threads = tracker.get_session_threads(session_id)

    # Get unlinked summaries
    unlinked = tracker.get_unlinked_summaries(session_id)

    return {
        "session_id": session_id,
        "summary": summary,
        "threads": threads,
        "unlinked_summaries": unlinked,
    }


@router.get("/api/tracking/latest")
async def get_latest_session() -> dict[str, Any]:
    """Get the most recent tracking session"""
    tracker = EmailThreadTracker()

    # Get latest session ID
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT session_id
            FROM email_threads
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="No tracking sessions found")

        session_id = row[0]

    # Get full report for this session
    summary = tracker.get_session_summary(session_id)
    threads = tracker.get_session_threads(session_id)
    unlinked = tracker.get_unlinked_summaries(session_id)

    return {
        "session_id": session_id,
        "summary": summary,
        "threads": threads,
        "unlinked_summaries": unlinked,
    }


@router.get("/api/tracking/thread/{thread_id}")
async def get_thread_history(thread_id: str) -> dict[str, Any]:
    """Get complete history for a specific thread

    Side Effects:
        - Reads from email_threads table in mailq.db
    """
    import json
    import sqlite3

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM email_threads
            WHERE thread_id = ?
            ORDER BY timestamp DESC
        """,
            (thread_id,),
        )

        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

        history = []
        for row in rows:
            thread = dict(row)
            # Parse JSON fields
            thread["domains"] = json.loads(thread["domains"]) if thread["domains"] else []
            thread["domain_confidence"] = (
                json.loads(thread["domain_confidence"]) if thread["domain_confidence"] else {}
            )
            thread["entity_details"] = (
                json.loads(thread["entity_details"]) if thread["entity_details"] else None
            )
            history.append(thread)

    return {"thread_id": thread_id, "history": history}


@router.post("/api/tracking/export/{session_id}")
async def export_session_csv(session_id: str) -> dict[str, Any]:
    """Export session data as CSV"""
    tracker = EmailThreadTracker()

    # Check session exists
    summary = tracker.get_session_summary(session_id)
    if summary["total_threads"] == 0:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Export to temp file
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".csv", prefix=f"mailq_session_{session_id}_")
    os.close(fd)

    tracker.export_csv(session_id, path)

    # Read file content
    with open(path) as f:
        csv_content = f.read()

    # Clean up
    os.unlink(path)

    return {
        "session_id": session_id,
        "csv": csv_content,
        "filename": f"mailq_session_{session_id}.csv",
    }
