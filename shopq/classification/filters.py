"""
Classification Filters

Consolidates email filtering logic:
- Self-email detection (ShopQ digest exclusion)
- GitHub quality issue filtering (meta-issue prevention)

Phase 2 Architecture Cleanup - Issue #60
Merged from: self_emails.py, github_quality.py
"""

from __future__ import annotations

from shopq.observability.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Section 1: Self-Email Filter (from self_emails.py)
# =============================================================================


def is_self_email(email: dict, user_email: str | None = None) -> bool:
    """
    Check if email is ShopQ's own digest email.

    Side Effects: None (pure function)

    Args:
        email: Email dict with 'from', 'subject', 'labelIds'
        user_email: User's email address (optional, for matching sender)

    Returns:
        True if email should be EXCLUDED (ShopQ digest email)
        False if email should be included
    """
    sender = email.get("from", "").lower()
    subject = email.get("subject", "").lower()
    labels = email.get("labelIds", [])

    # Pattern 1: Subject line of digest email
    # Example: "Your Inbox --Saturday, November 01 at 01:03 AM"
    if "your inbox --" in subject:
        # Also check if from self (if user_email provided)
        if user_email and user_email.lower() in sender:
            return True
        # Even without user_email, this subject is distinctive enough
        if not user_email:
            return True

    # Pattern 2: Has ShopQ/Digest label
    if "ShopQ/Digest" in labels or "MAILQ/DIGEST" in [label.upper() for label in labels]:
        return True

    # Pattern 3: Sender matches user and subject contains "inbox"
    sender_matches_user = bool(user_email and user_email.lower() in sender)
    subject_mentions_inbox = "inbox" in subject
    return sender_matches_user and subject_mentions_inbox


def filter_self_emails(emails: list[dict], user_email: str | None = None) -> list[dict]:
    """
    Filter out ShopQ's own digest emails.

    Side Effects: None (pure function - returns new filtered list)

    Args:
        emails: List of email dicts
        user_email: User's email address

    Returns:
        Filtered list with self-emails removed
    """
    return [email for email in emails if not is_self_email(email, user_email)]


# =============================================================================
# Section 2: GitHub Quality Filter (from github_quality.py)
# =============================================================================


def is_github_quality_issue(email: dict) -> bool:
    """
    Detect GitHub notifications about quality issues.

    Filters out GitHub notifications about ShopQ quality issues to prevent
    meta-issues (notifications about the digest system) from appearing in
    the digest itself.

    Side Effects: None (pure function)

    Args:
        email: Email dict with 'from'/'from_email' and 'subject' fields

    Returns:
        True if email is a GitHub quality issue notification, False otherwise
    """
    # Handle both 'from' (logger format) and 'from_email' (API converted format)
    sender = email.get("from_email", email.get("from", "")).lower()
    subject = email.get("subject", "")

    # Check if from GitHub notifications
    if "notifications@github.com" not in sender:
        return False

    # Check if about this repository's quality issues
    # Pattern: [jkoufopoulos/mailq-prototype] [Quality] Issue title
    return "jkoufopoulos/mailq-prototype" in subject and "[Quality]" in subject


def filter_github_quality_issues(emails: list[dict]) -> list[dict]:
    """
    Remove GitHub quality issue notifications from email list.

    Side Effects:
    - INFO log when quality issues are filtered

    Args:
        emails: List of email dicts

    Returns:
        Filtered list without GitHub quality issues
    """
    filtered = [e for e in emails if not is_github_quality_issue(e)]

    removed_count = len(emails) - len(filtered)
    if removed_count > 0:
        logger.info("Filtered %s GitHub quality issue notification(s)", removed_count)

    return filtered
