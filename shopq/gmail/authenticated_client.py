"""Authenticated Gmail API client (read-only)

Provides high-level Gmail API operations with OAuth authentication.
Integrates GmailOAuthService for credential management.

This module bridges the OAuth service with the existing Gmail adapter facade,
providing authenticated read-only API access for email fetching.
"""

from __future__ import annotations

from typing import Any

from googleapiclient.errors import HttpError

from shopq.gmail.client import fetch_messages_batched, fetch_messages_with_retry, parse_messages
from shopq.gmail.oauth import GmailOAuthService
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event
from shopq.storage.models import ParsedEmail

logger = get_logger(__name__)


class GmailClient:
    """
    Authenticated Gmail API client (read-only)

    Provides high-level operations for:
    - Fetching unread emails
    - Managing credentials
    """

    def __init__(self, user_id: str = "default", oauth_service: GmailOAuthService | None = None):
        """
        Initialize Gmail client

        Args:
            user_id: User identifier (email or "default")
            oauth_service: OAuth service instance (created if None)
        """
        self.user_id = user_id
        self.oauth_service = oauth_service or GmailOAuthService()
        self._service = None

    @property
    def service(self) -> Any:
        """
        Get or build authenticated Gmail API service

        Returns:
            Authenticated Gmail API service

        Raises:
            ValueError: If no credentials found or service build fails
        """
        if self._service is None:
            self._service = self.oauth_service.build_gmail_service(self.user_id)
        return self._service

    def fetch_unread_emails(
        self,
        max_results: int = 100,
        label_ids: list[str] | None = None,
    ) -> list[ParsedEmail]:
        """
        Fetch unread emails from inbox

        Args:
            max_results: Maximum number of emails to fetch
            label_ids: Filter by label IDs (default: ["INBOX", "UNREAD"])

        Returns:
            List of ParsedEmail objects

        Raises:
            HttpError: If Gmail API call fails
        """
        label_ids = label_ids or ["INBOX", "UNREAD"]

        logger.info(
            "Fetching unread emails for user: %s (max: %d, labels: %s)",
            self.user_id,
            max_results,
            label_ids,
        )

        try:
            # Define list_ids callable
            def list_ids() -> list[str]:
                """List message IDs matching criteria"""
                response = (
                    self.service.users()
                    .messages()
                    .list(userId="me", labelIds=label_ids, maxResults=max_results)
                    .execute()
                )

                messages = response.get("messages", [])
                return [msg["id"] for msg in messages]

            # Define get_message callable
            def get_message(message_id: str) -> dict[str, Any]:
                """Get single message by ID"""
                return (
                    self.service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )

            # Use existing adapter functions with retry/circuit breaker
            messages = fetch_messages_with_retry(
                lambda: fetch_messages_batched(list_ids, get_message)
            )

            # Parse messages
            parsed = parse_messages(messages)

            logger.info("Fetched and parsed %d emails for user: %s", len(parsed), self.user_id)
            counter("gmail.fetch_unread.count", len(parsed))

            return parsed

        except HttpError as e:
            logger.error("Gmail API error fetching emails: %s", e)
            log_event("gmail.fetch_unread.error", status=e.resp.status, user_id=self.user_id)
            raise
        except Exception as e:
            logger.error("Unexpected error fetching emails: %s", e)
            log_event("gmail.fetch_unread.error", error=str(e), user_id=self.user_id)
            raise

    def get_profile(self) -> dict[str, Any]:
        """
        Get Gmail profile information

        Returns:
            Profile dict with keys: emailAddress, messagesTotal, threadsTotal, historyId

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            logger.info("Fetched profile for user: %s", self.user_id)
            return profile

        except HttpError as e:
            logger.error("Failed to fetch profile: %s", e)
            log_event("gmail.get_profile.error", status=e.resp.status, user_id=self.user_id)
            raise

    def refresh_credentials(self) -> None:
        """
        Manually refresh OAuth credentials

        Raises:
            ValueError: If refresh fails
        """
        logger.info("Manually refreshing credentials for user: %s", self.user_id)
        self.oauth_service.refresh_credentials(self.user_id)

        # Rebuild service with new credentials
        self._service = None
        logger.info("Credentials refreshed and service rebuilt for user: %s", self.user_id)


# Convenience function for creating authenticated clients
def get_gmail_client(user_id: str = "default") -> GmailClient:
    """
    Get authenticated Gmail client for user

    Args:
        user_id: User identifier (email or "default")

    Returns:
        GmailClient instance

    Raises:
        ValueError: If no credentials found
    """
    return GmailClient(user_id)
