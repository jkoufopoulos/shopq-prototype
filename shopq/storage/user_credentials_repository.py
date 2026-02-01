"""User credentials repository for OAuth token management

Provides secure storage and retrieval of user OAuth credentials with encryption.

SECURITY:
- Tokens encrypted with Fernet (symmetric encryption)
- Encryption key must be set via SHOPQ_ENCRYPTION_KEY environment variable
- Token expiry tracked for automatic refresh
- User IDs scoped for multi-tenant support
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet

from shopq.observability.logging import get_logger
from shopq.storage import BaseRepository

logger = get_logger(__name__)


class CredentialEncryptionError(Exception):
    """Raised when credential encryption/decryption fails"""

    pass


class UserCredentialsRepository(BaseRepository):
    """
    Repository for managing encrypted user OAuth credentials

    Stores Gmail API OAuth tokens securely in the database with encryption.
    Supports token refresh tracking and expiry management.
    """

    def __init__(self):
        super().__init__("user_credentials")
        self._cipher = self._get_cipher()

    def _get_cipher(self) -> Fernet:
        """
        Get Fernet cipher for encryption/decryption

        Returns:
            Fernet cipher instance

        Raises:
            ValueError: If SHOPQ_ENCRYPTION_KEY is not set
        """
        encryption_key = os.getenv("SHOPQ_ENCRYPTION_KEY")

        if not encryption_key:
            raise ValueError(
                "SHOPQ_ENCRYPTION_KEY environment variable must be set. "
                "Generate one with: python -c "
                "'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'"
            )

        try:
            return Fernet(encryption_key.encode())
        except Exception as e:
            raise ValueError(f"Invalid encryption key format: {e}") from e

    def _encrypt_token(self, token_dict: dict[str, Any]) -> str:
        """
        Encrypt token dictionary

        Args:
            token_dict: Token data to encrypt

        Returns:
            Encrypted token as base64 string

        Raises:
            CredentialEncryptionError: If encryption fails
        """
        try:
            token_json = json.dumps(token_dict)
            encrypted_bytes = self._cipher.encrypt(token_json.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error("Failed to encrypt token: %s", e)
            raise CredentialEncryptionError(f"Encryption failed: {e}") from e

    def _decrypt_token(self, encrypted_token: str) -> dict[str, Any]:
        """
        Decrypt token string

        Args:
            encrypted_token: Encrypted token from database

        Returns:
            Decrypted token dictionary

        Raises:
            CredentialEncryptionError: If decryption fails
        """
        try:
            decrypted_bytes = self._cipher.decrypt(encrypted_token.encode())
            return json.loads(decrypted_bytes.decode())
        except Exception as e:
            logger.error("Failed to decrypt token: %s", e)
            raise CredentialEncryptionError(f"Decryption failed: {e}") from e

    def store_credentials(
        self,
        user_id: str,
        token_dict: dict[str, Any],
        scopes: list[str],
        token_expiry: datetime | None = None,
    ) -> None:
        """
        Store or update user credentials

        Args:
            user_id: User identifier (email or "default" for MVP)
            token_dict: OAuth token data (access_token, refresh_token, etc.)
            scopes: List of OAuth scopes granted
            token_expiry: Token expiration timestamp (UTC)

        Raises:
            CredentialEncryptionError: If encryption fails

        Side Effects:
            - Inserts or updates row in user_credentials table in shopq.db
            - Encrypts token before storage
            - Logs info message about credential storage
        """
        encrypted_token = self._encrypt_token(token_dict)
        scopes_json = json.dumps(scopes)
        expiry_str = token_expiry.isoformat() if token_expiry else None

        # Check if credentials already exist
        existing = self.get_by_user_id(user_id, decrypt=False)

        if existing:
            # Update existing credentials
            self.execute(
                """
                UPDATE user_credentials
                SET encrypted_token_json = ?,
                    scopes = ?,
                    token_expiry = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (encrypted_token, scopes_json, expiry_str, user_id),
            )
            logger.info("Updated credentials for user: %s", user_id)
        else:
            # Insert new credentials
            self.execute(
                """
                INSERT INTO user_credentials (user_id, encrypted_token_json, scopes, token_expiry)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, encrypted_token, scopes_json, expiry_str),
            )
            logger.info("Stored new credentials for user: %s", user_id)

    def get_by_user_id(self, user_id: str, decrypt: bool = True) -> dict[str, Any] | None:
        """
        Get credentials for a user

        Args:
            user_id: User identifier
            decrypt: If True, decrypt the token (default: True)

        Returns:
            Dictionary with credentials or None if not found
            Keys: user_id, token_dict, scopes, token_expiry, created_at, updated_at

        Raises:
            CredentialEncryptionError: If decryption fails
        """
        row = self.query_one("SELECT * FROM user_credentials WHERE user_id = ?", (user_id,))

        if not row:
            return None

        scopes = json.loads(row["scopes"])
        token_expiry = datetime.fromisoformat(row["token_expiry"]) if row["token_expiry"] else None

        result = {
            "user_id": row["user_id"],
            "scopes": scopes,
            "token_expiry": token_expiry,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_refresh_at": row["last_refresh_at"],
            "last_sync_at": row["last_sync_at"],
            "sync_history_id": row["sync_history_id"],
        }

        if decrypt:
            result["token_dict"] = self._decrypt_token(row["encrypted_token_json"])
        else:
            result["encrypted_token_json"] = row["encrypted_token_json"]

        return result

    def is_token_expired(self, user_id: str, buffer_seconds: int = 300) -> bool:
        """
        Check if token is expired or will expire soon

        Args:
            user_id: User identifier
            buffer_seconds: Consider expired if expiring within this many seconds (default: 5 min)

        Returns:
            True if token is expired or expiring soon, False otherwise
            Returns True if expiry is not set (to trigger refresh)
        """
        credentials = self.get_by_user_id(user_id, decrypt=False)

        if not credentials or not credentials["token_expiry"]:
            return True  # No expiry = needs refresh

        now = datetime.now(UTC)
        expiry = credentials["token_expiry"]

        # Make expiry timezone-aware if it isn't
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)

        # Check if expired or expiring soon (within buffer)
        from datetime import timedelta

        return expiry <= now + timedelta(seconds=buffer_seconds)

    def update_refresh_timestamp(self, user_id: str) -> None:
        """
        Update last refresh timestamp

        Args:
            user_id: User identifier

        Side Effects:
            - Updates last_refresh_at timestamp in user_credentials table
            - Writes to shopq.db
        """
        self.execute(
            "UPDATE user_credentials SET last_refresh_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,),
        )

    def update_sync_state(self, user_id: str, history_id: str | None = None) -> None:
        """
        Update last sync timestamp and history ID

        Args:
            user_id: User identifier
            history_id: Gmail API history ID for incremental sync

        Side Effects:
            - Updates last_sync_at and sync_history_id in user_credentials table
            - Writes to shopq.db
        """
        self.execute(
            """
            UPDATE user_credentials
            SET last_sync_at = CURRENT_TIMESTAMP,
                sync_history_id = ?
            WHERE user_id = ?
            """,
            (history_id, user_id),
        )

    def delete_credentials(self, user_id: str) -> None:
        """
        Delete user credentials

        Args:
            user_id: User identifier

        Side Effects:
            - Deletes row from user_credentials table in shopq.db
            - Permanently removes encrypted OAuth tokens
            - Logs info message about credential deletion
        """
        self.execute(f"DELETE FROM {self.table_name} WHERE user_id = ?", (user_id,))
        logger.info("Deleted credentials for user: %s", user_id)

    def list_all_users(self) -> list[str]:
        """
        Get list of all user IDs with stored credentials

        Returns:
            List of user IDs
        """
        rows = self.query_all("SELECT user_id FROM user_credentials ORDER BY created_at")
        return [row["user_id"] for row in rows]
