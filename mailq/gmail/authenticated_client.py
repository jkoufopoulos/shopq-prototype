"""Authenticated Gmail API client

Provides high-level Gmail API operations with OAuth authentication.
Integrates GmailOAuthService for credential management.

This module bridges the OAuth service with the existing Gmail adapter facade,
providing authenticated API access for email fetching, labeling, and sending.
"""

from __future__ import annotations

from typing import Any

from googleapiclient.errors import HttpError

from mailq.gmail.client import fetch_messages_batched, fetch_messages_with_retry, parse_messages
from mailq.gmail.oauth import GmailOAuthService
from mailq.observability.logging import get_logger
from mailq.observability.telemetry import counter, log_event
from mailq.storage.models import ParsedEmail

logger = get_logger(__name__)


class GmailClient:
    """
    Authenticated Gmail API client

    Provides high-level operations for:
    - Fetching unread emails
    - Applying labels
    - Sending emails
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

    def apply_label(
        self,
        message_id: str,
        label_name: str,
        remove_unread: bool = False,
    ) -> bool:
        """
        Apply label to a message

        Args:
            message_id: Gmail message ID
            label_name: Label name to apply
            remove_unread: If True, also remove UNREAD label

        Returns:
            True if successful

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            # Get or create label ID
            label_id = self._get_or_create_label(label_name)

            # Build modify request
            modify_request = {"addLabelIds": [label_id]}

            if remove_unread:
                modify_request["removeLabelIds"] = ["UNREAD"]

            # Apply label
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body=modify_request,
            ).execute()

            logger.info(
                "Applied label '%s' to message %s for user: %s",
                label_name,
                message_id,
                self.user_id,
            )
            counter("gmail.label_applied.count")

            return True

        except HttpError as e:
            logger.error("Failed to apply label: %s", e)
            log_event(
                "gmail.apply_label.error",
                status=e.resp.status,
                label=label_name,
                user_id=self.user_id,
            )
            raise
        except Exception as e:
            logger.error("Unexpected error applying label: %s", e)
            raise

    def _get_or_create_label(self, label_name: str) -> str:
        """
        Get label ID by name, creating if it doesn't exist

        Args:
            label_name: Label name

        Returns:
            Label ID

        Raises:
            HttpError: If API call fails
        """
        try:
            # List existing labels
            response = self.service.users().labels().list(userId="me").execute()
            labels = response.get("labels", [])

            # Check if label exists
            for label in labels:
                if label["name"] == label_name:
                    return label["id"]

            # Create new label
            logger.info("Creating new label: %s for user: %s", label_name, self.user_id)
            label_object = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }

            created = self.service.users().labels().create(userId="me", body=label_object).execute()

            counter("gmail.label_created.count")
            log_event("gmail.label_created", label=label_name, user_id=self.user_id)

            return created["id"]

        except HttpError as e:
            logger.error("Failed to get/create label '%s': %s", label_name, e)
            raise

    def send_email(
        self,
        to: str,
        subject: str,
        body_html: str,
        from_email: str | None = None,
    ) -> str:
        """
        Send an email via Gmail API

        Args:
            to: Recipient email address
            subject: Email subject
            body_html: HTML body content
            from_email: Sender email (uses authenticated user if None)

        Returns:
            Sent message ID

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            import base64
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            # Get user's email if not provided
            if not from_email:
                profile = self.service.users().getProfile(userId="me").execute()
                from_email = profile["emailAddress"]

            # Create message
            message = MIMEMultipart("alternative")
            message["to"] = to
            message["from"] = from_email
            message["subject"] = subject

            # Attach HTML body
            html_part = MIMEText(body_html, "html")
            message.attach(html_part)

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Send via Gmail API
            sent = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )

            message_id = sent["id"]
            logger.info(
                "Sent email to %s (message_id: %s) for user: %s", to, message_id, self.user_id
            )
            counter("gmail.email_sent.count")
            log_event("gmail.email_sent", to=to, user_id=self.user_id)

            return message_id

        except HttpError as e:
            logger.error("Failed to send email to %s: %s", to, e)
            log_event("gmail.send_email.error", status=e.resp.status, to=to, user_id=self.user_id)
            raise
        except Exception as e:
            logger.error("Unexpected error sending email: %s", e)
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
