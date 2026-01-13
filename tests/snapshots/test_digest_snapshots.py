"""
Digest Snapshot Tests - Deterministic Rendering Verification

These tests ensure that the digest HTML output is deterministic and reproducible.
Same input emails → Same HTML output (byte-identical).

Purpose:
- Verify deterministic rendering (no LLM variance)
- Catch accidental template breakage
- Document expected digest structure
- Prevent DTO schema drift

Test Categories:
1. Critical emails only
2. Mix of importance levels
3. Empty digest (no emails)
4. Single email
5. Temporal decay edge cases
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Snapshot directory
SNAPSHOT_DIR = Path(__file__).parent / "golden"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def normalize_html(html: str) -> str:
    """
    Normalize HTML for comparison by removing timestamp-dependent content.

    Removes:
    - Generated timestamps (e.g., "Updated 2 hours ago")
    - Dynamic dates
    - Session IDs

    Keeps:
    - Email content
    - Structure
    - Styling
    """
    import re

    # Remove timestamp lines
    html = re.sub(r"Updated \d+ (hour|minute|second)s? ago", "Updated recently", html)

    # Remove generated_at timestamps
    html = re.sub(r'"generated_at":\s*"[^"]*"', '"generated_at": "NORMALIZED"', html)

    # Remove timezone-specific dates
    html = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "NORMALIZED_TIMESTAMP", html)

    return html.strip()


def save_snapshot(name: str, html: str):
    """Save HTML snapshot to golden directory"""
    snapshot_path = SNAPSHOT_DIR / f"{name}.html"
    snapshot_path.write_text(html, encoding="utf-8")


def load_snapshot(name: str) -> str | None:
    """Load HTML snapshot from golden directory"""
    snapshot_path = SNAPSHOT_DIR / f"{name}.html"
    if not snapshot_path.exists():
        return None
    return snapshot_path.read_text(encoding="utf-8")


@pytest.mark.skip(
    reason="Snapshot infrastructure test - enable after building DigestDTOv3 pipeline"
)
def test_critical_emails_digest_snapshot():
    """
    Golden dataset with 3 critical emails → known HTML structure

    Verifies:
    - Critical section renders correctly
    - Links are pre-built (not hallucinated)
    - Importance levels are deterministic
    """
    from mailq.digest.context_digest import generate_context_digest

    # Fixed input: 3 critical emails
    emails = [
        {
            "id": "msg-1",
            "subject": "URGENT: Server down in production",
            "snippet": "All services are unavailable. Need immediate action.",
            "from": "alerts@company.com",
            "type": "notification",
            "importance": "critical",
            "attention": "action_required",
            "domains": ["professional", "security"],
        },
        {
            "id": "msg-2",
            "subject": "Fraud alert on your account",
            "snippet": "Suspicious activity detected. Verify now.",
            "from": "security@bank.com",
            "type": "notification",
            "importance": "critical",
            "attention": "action_required",
            "domains": ["finance", "security"],
        },
        {
            "id": "msg-3",
            "subject": "Meeting in 30 minutes",
            "snippet": "Quarterly planning session starts soon.",
            "from": "boss@company.com",
            "type": "event",
            "importance": "critical",
            "attention": "action_required",
            "domains": ["professional"],
        },
    ]

    # Generate digest
    digest = generate_context_digest(emails, verbose=False)
    actual_html = normalize_html(digest["html"])

    # Load or create snapshot
    expected_html = load_snapshot("critical_digest_v3")

    if expected_html is None:
        # First run: create snapshot
        save_snapshot("critical_digest_v3", actual_html)
        pytest.skip("Created new snapshot - rerun to verify")

    # Verify byte-identical output
    assert actual_html == expected_html, "Digest HTML changed! Update snapshot if intentional."


@pytest.mark.skip(
    reason="Snapshot infrastructure test - enable after building DigestDTOv3 pipeline"
)
def test_mixed_importance_digest_snapshot():
    """
    Mix of critical, time_sensitive, and routine emails

    Verifies:
    - All sections render correctly
    - Importance grouping is deterministic
    - Routine emails categorized correctly
    """
    from mailq.digest.context_digest import generate_context_digest

    emails = [
        {
            "id": "msg-1",
            "subject": "URGENT: Production issue",
            "snippet": "Critical alert",
            "from": "alerts@company.com",
            "type": "notification",
            "importance": "critical",
        },
        {
            "id": "msg-2",
            "subject": "Meeting tomorrow",
            "snippet": "Planning session",
            "from": "boss@company.com",
            "type": "event",
            "importance": "time_sensitive",
        },
        {
            "id": "msg-3",
            "subject": "FYI: New blog post",
            "snippet": "Check out our latest article",
            "from": "marketing@company.com",
            "type": "newsletter",
            "importance": "routine",
        },
    ]

    digest = generate_context_digest(emails, verbose=False)
    actual_html = normalize_html(digest["html"])

    expected_html = load_snapshot("mixed_digest_v3")

    if expected_html is None:
        save_snapshot("mixed_digest_v3", actual_html)
        pytest.skip("Created new snapshot")

    assert actual_html == expected_html


@pytest.mark.skip(
    reason="Snapshot infrastructure test - enable after building DigestDTOv3 pipeline"
)
def test_empty_digest_snapshot():
    """
    Empty inbox → empty digest

    Verifies:
    - Handles empty input gracefully
    - No errors on empty list
    - Renders "All caught up" message
    """
    from mailq.digest.context_digest import generate_context_digest

    emails = []

    digest = generate_context_digest(emails, verbose=False)
    actual_html = normalize_html(digest["html"])

    expected_html = load_snapshot("empty_digest_v3")

    if expected_html is None:
        save_snapshot("empty_digest_v3", actual_html)
        pytest.skip("Created new snapshot")

    assert actual_html == expected_html


@pytest.mark.skip(
    reason="Snapshot infrastructure test - enable after building DigestDTOv3 pipeline"
)
def test_single_email_digest_snapshot():
    """
    Single email → minimal digest

    Verifies:
    - Singular/plural handling
    - Minimal structure
    """
    from mailq.digest.context_digest import generate_context_digest

    emails = [
        {
            "id": "msg-1",
            "subject": "Hello",
            "snippet": "Just saying hi",
            "from": "friend@example.com",
            "type": "message",
            "importance": "routine",
        },
    ]

    digest = generate_context_digest(emails, verbose=False)
    actual_html = normalize_html(digest["html"])

    expected_html = load_snapshot("single_email_digest_v3")

    if expected_html is None:
        save_snapshot("single_email_digest_v3", actual_html)
        pytest.skip("Created new snapshot")

    assert actual_html == expected_html


@pytest.mark.skip(
    reason="Snapshot infrastructure test - enable after building DigestDTOv3 pipeline"
)
def test_temporal_decay_digest_snapshot():
    """
    Emails with temporal decay edge cases

    Verifies:
    - Expired events filtered out
    - Near-deadline items boosted
    - Time-based importance adjustments
    """
    from datetime import datetime, timedelta

    from mailq.digest.context_digest import generate_context_digest

    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    last_week = now - timedelta(days=7)

    emails = [
        {
            "id": "msg-1",
            "subject": "Event tomorrow at 3pm",
            "snippet": "Don't forget!",
            "from": "calendar@company.com",
            "type": "event",
            "importance": "time_sensitive",
            "temporal": {"start_iso": tomorrow.isoformat(), "end_iso": tomorrow.isoformat()},
        },
        {
            "id": "msg-2",
            "subject": "Event last week",
            "snippet": "This already happened",
            "from": "calendar@company.com",
            "type": "event",
            "importance": "time_sensitive",
            "temporal": {"start_iso": last_week.isoformat(), "end_iso": last_week.isoformat()},
        },
    ]

    digest = generate_context_digest(emails, verbose=False)
    actual_html = normalize_html(digest["html"])

    expected_html = load_snapshot("temporal_decay_digest_v3")

    if expected_html is None:
        save_snapshot("temporal_decay_digest_v3", actual_html)
        pytest.skip("Created new snapshot")

    assert actual_html == expected_html


def test_normalize_html_function():
    """Test the HTML normalization function"""
    html_with_timestamps = """
    <div>
        <p>Updated 2 hours ago</p>
        <p>"generated_at": "2025-01-14T12:34:56"</p>
        <p>2025-01-14T12:34:56</p>
    </div>
    """

    normalized = normalize_html(html_with_timestamps)

    assert "Updated recently" in normalized
    assert '"generated_at": "NORMALIZED"' in normalized
    assert "NORMALIZED_TIMESTAMP" in normalized
    assert "2025-01-14T12:34:56" not in normalized
