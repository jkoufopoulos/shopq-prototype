"""Gmail OAuth2 authentication service

Handles OAuth2 flow for Gmail API access:
- Initiate authorization flow
- Exchange authorization code for tokens
- Refresh expired tokens automatically
- Build authenticated Gmail API service

SECURITY:
- Tokens stored encrypted in database via UserCredentialsRepository
- Auto-refresh before expiry (5-minute buffer)
- Supports both desktop (local server) and web (redirect URL) flows
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

from mailq.observability.logging import get_logger
from mailq.observability.telemetry import counter, log_event
from mailq.storage.user_credentials_repository import UserCredentialsRepository

logger = get_logger(__name__)

# Gmail API scopes
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",  # Read emails
    "https://www.googleapis.com/auth/gmail.modify",  # Modify labels
    "https://www.googleapis.com/auth/gmail.send",  # Send emails (for digest)
]


class GmailOAuthService:
    """
    Service for managing Gmail OAuth2 authentication

    Handles the complete OAuth2 flow including:
    - Authorization URL generation
    - Token exchange
    - Token refresh
    - Authenticated API client creation
    """

    def __init__(self, credentials_repo: UserCredentialsRepository | None = None):
        """
        Initialize OAuth service

        Args:
            credentials_repo: Repository for credential storage (auto-created if None)
        """
        self.credentials_repo = credentials_repo or UserCredentialsRepository()

        # Get OAuth client config path
        self.client_secrets_file = os.getenv(
            "GMAIL_OAUTH_CLIENT_SECRETS",
            "credentials/credentials.json",
        )

    def initiate_oauth_flow(
        self,
        redirect_uri: str = "http://localhost:8080/",
        scopes: list[str] | None = None,
    ) -> tuple[str, Flow]:
        """
        Initiate OAuth2 authorization flow

        Args:
            redirect_uri: OAuth redirect URI (default: localhost for desktop flow)
            scopes: List of OAuth scopes to request (default: GMAIL_SCOPES)

        Returns:
            Tuple of (authorization_url, flow_object)
            User should be directed to authorization_url

        Raises:
            FileNotFoundError: If client secrets file not found
            ValueError: If client secrets file is invalid
        """
        scopes = scopes or GMAIL_SCOPES

        try:
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=scopes,
                redirect_uri=redirect_uri,
            )

            auth_url, _ = flow.authorization_url(
                access_type="offline",  # Get refresh token
                prompt="consent",  # Force consent screen to get refresh token
                include_granted_scopes="true",  # Incremental authorization
            )

            logger.info("Generated OAuth authorization URL")
            return auth_url, flow

        except FileNotFoundError as e:
            logger.error("Client secrets file not found: %s", self.client_secrets_file)
            raise FileNotFoundError(
                f"Gmail OAuth client secrets not found at {self.client_secrets_file}. "
                f"Download from Google Cloud Console and place at this path. "
                f"Set GMAIL_OAUTH_CLIENT_SECRETS env var to override location."
            ) from e
        except Exception as e:
            logger.error("Failed to initiate OAuth flow: %s", e)
            raise ValueError(f"Invalid client secrets file: {e}") from e

    def initiate_desktop_oauth_flow(
        self,
        scopes: list[str] | None = None,
    ) -> InstalledAppFlow:
        """
        Initiate OAuth2 flow for desktop/terminal application

        Uses InstalledAppFlow which handles the local server and browser redirect.

        Args:
            scopes: List of OAuth scopes to request (default: GMAIL_SCOPES)

        Returns:
            InstalledAppFlow object ready to run_local_server()

        Raises:
            FileNotFoundError: If client secrets file not found
        """
        scopes = scopes or GMAIL_SCOPES

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=scopes,
            )

            logger.info("Created desktop OAuth flow")
            return flow

        except FileNotFoundError as e:
            logger.error("Client secrets file not found: %s", self.client_secrets_file)
            raise FileNotFoundError(
                f"Gmail OAuth client secrets not found at {self.client_secrets_file}"
            ) from e

    def exchange_code_for_tokens(
        self,
        flow: Flow,
        authorization_response: str,
    ) -> dict[str, Any]:
        """
        Exchange authorization code for access tokens

        Args:
            flow: Flow object from initiate_oauth_flow()
            authorization_response: Full authorization response URL with code

        Returns:
            Token dictionary with keys: token, refresh_token, token_uri, client_id, etc.

        Raises:
            ValueError: If token exchange fails
        """
        try:
            flow.fetch_token(authorization_response=authorization_response)

            # Extract credentials
            credentials = flow.credentials

            token_dict = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
            }

            logger.info("Successfully exchanged authorization code for tokens")
            counter("oauth.code_exchanged.count")
            log_event("oauth.code_exchanged", scopes=credentials.scopes)
            return token_dict

        except Exception as e:
            logger.error("Failed to exchange authorization code: %s", e)
            raise ValueError(f"Token exchange failed: {e}") from e

    def store_user_credentials(
        self,
        user_id: str,
        token_dict: dict[str, Any],
    ) -> None:
        """
        Store user credentials in encrypted database

        Args:
            user_id: User identifier (email or "default" for MVP)
            token_dict: Token dictionary from exchange_code_for_tokens()

        Side Effects:
            - Writes encrypted tokens to user_credentials table in mailq.db
            - Updates existing credentials if user_id already exists
            - Commits transaction via credentials_repo.store_credentials
            - Writes log entry for credential storage
        """
        # Extract actual expiry from Google's response if available
        # Google returns expires_in (seconds), typically 3600 (1 hour)
        expires_in = token_dict.get("expires_in", 3600)  # Default to 1 hour
        expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

        scopes = token_dict.get("scopes", GMAIL_SCOPES)

        self.credentials_repo.store_credentials(
            user_id=user_id,
            token_dict=token_dict,
            scopes=scopes,
            token_expiry=expiry,
        )

        logger.info("Stored credentials for user: %s", user_id)

    def get_authenticated_credentials(
        self,
        user_id: str,
        auto_refresh: bool = True,
    ) -> Credentials | None:
        """
        Get authenticated credentials for user

        Args:
            user_id: User identifier
            auto_refresh: If True, automatically refresh expired tokens (default: True)

        Returns:
            Google OAuth2 Credentials object or None if not found

        Raises:
            CredentialEncryptionError: If decryption fails
        """
        # Get credentials from database
        creds_data = self.credentials_repo.get_by_user_id(user_id, decrypt=True)

        if not creds_data:
            logger.warning("No credentials found for user: %s", user_id)
            return None

        # Build Credentials object
        token_dict = creds_data["token_dict"]
        credentials = Credentials(
            token=token_dict.get("token"),
            refresh_token=token_dict.get("refresh_token"),
            token_uri=token_dict.get("token_uri"),
            client_id=token_dict.get("client_id"),
            client_secret=token_dict.get("client_secret"),
            scopes=creds_data["scopes"],
        )

        # Check if token needs refresh
        if auto_refresh and self.credentials_repo.is_token_expired(user_id):
            logger.info("Token expired or expiring soon, refreshing for user: %s", user_id)
            credentials = self.refresh_credentials(user_id, credentials)

        return credentials

    def refresh_credentials(
        self,
        user_id: str,
        credentials: Credentials | None = None,
    ) -> Credentials:
        """
        Refresh expired credentials

        Args:
            user_id: User identifier
            credentials: Existing credentials to refresh (fetched if None)

        Returns:
            Refreshed Credentials object

        Raises:
            ValueError: If refresh fails
            CredentialEncryptionError: If decryption fails

        Side Effects:
            - Calls Google OAuth2 API to refresh token
            - Writes updated encrypted tokens to user_credentials table in mailq.db
            - Updates last_refresh_at timestamp in database
            - Increments telemetry counter (oauth.token_refreshed)
            - Writes telemetry log event
        """
        if credentials is None:
            credentials = self.get_authenticated_credentials(user_id, auto_refresh=False)

        if not credentials:
            raise ValueError(f"No credentials found for user: {user_id}")

        if not credentials.refresh_token:
            raise ValueError(f"No refresh token available for user: {user_id}")

        try:
            # Refresh the token
            credentials.refresh(Request())

            # Update stored credentials
            new_token_dict = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
            }

            # Extract actual expiry from credentials if available
            # Google Credentials object has expiry datetime, calculate seconds from now
            if hasattr(credentials, "expiry") and credentials.expiry:
                new_expiry = credentials.expiry
                # Make timezone-aware if needed
                if new_expiry.tzinfo is None:
                    new_expiry = new_expiry.replace(tzinfo=UTC)
            else:
                # Fallback to 1 hour from now
                new_expiry = datetime.now(UTC) + timedelta(hours=1)

            self.credentials_repo.store_credentials(
                user_id=user_id,
                token_dict=new_token_dict,
                scopes=credentials.scopes or GMAIL_SCOPES,
                token_expiry=new_expiry,
            )

            self.credentials_repo.update_refresh_timestamp(user_id)

            logger.info("Successfully refreshed credentials for user: %s", user_id)
            counter("oauth.token_refreshed.count")
            log_event("oauth.token_refreshed", user_id=user_id)
            return credentials

        except Exception as e:
            logger.error("Failed to refresh credentials for user %s: %s", user_id, e)
            raise ValueError(f"Token refresh failed: {e}") from e

    def build_gmail_service(
        self,
        user_id: str,
        auto_refresh: bool = True,
    ) -> Any:
        """
        Build authenticated Gmail API service

        Args:
            user_id: User identifier
            auto_refresh: If True, automatically refresh expired tokens (default: True)

        Returns:
            Authenticated Gmail API service object (googleapiclient.discovery.Resource)

        Raises:
            ValueError: If no credentials found or service build fails
            CredentialEncryptionError: If decryption fails
        """
        credentials = self.get_authenticated_credentials(user_id, auto_refresh=auto_refresh)

        if not credentials:
            raise ValueError(f"No credentials found for user: {user_id}")

        try:
            service = build("gmail", "v1", credentials=credentials)
            logger.info("Built Gmail API service for user: %s", user_id)
            return service

        except Exception as e:
            logger.error("Failed to build Gmail service for user %s: %s", user_id, e)
            raise ValueError(f"Failed to build Gmail service: {e}") from e

    def revoke_credentials(self, user_id: str) -> None:
        """
        Revoke and delete user credentials

        Args:
            user_id: User identifier

        Raises:
            ValueError: If revocation fails

        Side Effects:
            - Calls Google OAuth2 API to revoke token
            - Deletes row from user_credentials table in mailq.db
            - Commits transaction via credentials_repo.delete_credentials
            - Increments telemetry counter (oauth.credentials_revoked)
            - Writes telemetry log event
            - Writes log entries for revocation and deletion
        """
        try:
            credentials = self.get_authenticated_credentials(user_id, auto_refresh=False)

            if credentials:
                # Revoke the token
                credentials.revoke(Request())
                logger.info("Revoked OAuth token for user: %s", user_id)

        except Exception as e:
            logger.warning("Failed to revoke token (may already be invalid): %s", e)

        # Delete from database regardless of revocation success
        self.credentials_repo.delete_credentials(user_id)
        logger.info("Deleted credentials for user: %s", user_id)
        counter("oauth.credentials_revoked.count")
        log_event("oauth.credentials_revoked", user_id=user_id)
