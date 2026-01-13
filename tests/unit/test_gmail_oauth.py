"""Unit tests for Gmail OAuth service

Tests cover:
- OAuth flow initiation
- Token exchange
- Credential storage and retrieval
- Token refresh logic
- Service building
- Credential revocation
- Error handling
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from cryptography.fernet import Fernet

from mailq.gmail.oauth import GMAIL_SCOPES, GmailOAuthService
from mailq.storage.user_credentials_repository import (
    CredentialEncryptionError,
    UserCredentialsRepository,
)


@pytest.fixture
def encryption_key():
    """Generate test encryption key"""
    key = Fernet.generate_key().decode()
    os.environ["MAILQ_ENCRYPTION_KEY"] = key
    yield key
    if "MAILQ_ENCRYPTION_KEY" in os.environ:
        del os.environ["MAILQ_ENCRYPTION_KEY"]


@pytest.fixture
def mock_credentials_repo():
    """Mock UserCredentialsRepository"""
    return Mock(spec=UserCredentialsRepository)


@pytest.fixture
def oauth_service(encryption_key, mock_credentials_repo):
    """Create OAuth service with mocked dependencies"""
    return GmailOAuthService(credentials_repo=mock_credentials_repo)


@pytest.fixture
def mock_client_secrets(tmp_path):
    """Create temporary client secrets file"""
    secrets_file = tmp_path / "credentials.json"
    secrets_file.write_text(
        """{
        "installed": {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }"""
    )
    return str(secrets_file)


def test_initiate_oauth_flow(oauth_service, mock_client_secrets):
    """Test OAuth flow initiation"""
    oauth_service.client_secrets_file = mock_client_secrets

    auth_url, flow = oauth_service.initiate_oauth_flow()

    assert "accounts.google.com" in auth_url
    assert "client_id=test-client-id" in auth_url
    assert flow is not None


def test_initiate_oauth_flow_missing_secrets(oauth_service):
    """Test OAuth flow fails with missing client secrets"""
    oauth_service.client_secrets_file = "/nonexistent/credentials.json"

    with pytest.raises(FileNotFoundError) as exc_info:
        oauth_service.initiate_oauth_flow()

    assert "not found" in str(exc_info.value).lower()


def test_initiate_desktop_oauth_flow(oauth_service, mock_client_secrets):
    """Test desktop OAuth flow initiation"""
    oauth_service.client_secrets_file = mock_client_secrets

    flow = oauth_service.initiate_desktop_oauth_flow()

    assert flow is not None
    # redirect_uri is None until run_local_server() is called
    assert flow.redirect_uri is None or flow.redirect_uri.startswith("http://localhost")


@patch("mailq.gmail.oauth.Flow")
def test_exchange_code_for_tokens(mock_flow_class, oauth_service):
    """Test authorization code exchange for tokens"""
    # Mock flow and credentials
    mock_flow = Mock()
    mock_credentials = Mock()
    mock_credentials.token = "test-access-token"
    mock_credentials.refresh_token = "test-refresh-token"
    mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
    mock_credentials.client_id = "test-client-id"
    mock_credentials.client_secret = "test-client-secret"
    mock_credentials.scopes = GMAIL_SCOPES

    mock_flow.credentials = mock_credentials
    mock_flow.fetch_token = Mock()

    # Exchange code
    token_dict = oauth_service.exchange_code_for_tokens(
        mock_flow,
        "http://localhost:8080/?code=test-auth-code&state=test-state",
    )

    # Verify token exchange was called
    mock_flow.fetch_token.assert_called_once()

    # Verify token dict structure
    assert token_dict["token"] == "test-access-token"
    assert token_dict["refresh_token"] == "test-refresh-token"
    assert token_dict["client_id"] == "test-client-id"
    assert token_dict["scopes"] == GMAIL_SCOPES


def test_store_user_credentials(oauth_service, mock_credentials_repo):
    """Test storing user credentials"""
    token_dict = {
        "token": "test-token",
        "refresh_token": "test-refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "scopes": GMAIL_SCOPES,
    }

    oauth_service.store_user_credentials("test@example.com", token_dict)

    # Verify store_credentials was called
    mock_credentials_repo.store_credentials.assert_called_once()
    call_args = mock_credentials_repo.store_credentials.call_args

    assert call_args[1]["user_id"] == "test@example.com"
    assert call_args[1]["token_dict"] == token_dict
    assert call_args[1]["scopes"] == GMAIL_SCOPES


def test_get_authenticated_credentials_not_found(oauth_service, mock_credentials_repo):
    """Test getting credentials when none exist"""
    mock_credentials_repo.get_by_user_id.return_value = None

    credentials = oauth_service.get_authenticated_credentials("test@example.com")

    assert credentials is None


def test_get_authenticated_credentials_valid(oauth_service, mock_credentials_repo):
    """Test getting valid credentials"""
    mock_credentials_repo.get_by_user_id.return_value = {
        "user_id": "test@example.com",
        "token_dict": {
            "token": "test-token",
            "refresh_token": "test-refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-secret",
        },
        "scopes": GMAIL_SCOPES,
        "token_expiry": datetime.now(UTC) + timedelta(hours=1),
    }

    mock_credentials_repo.is_token_expired.return_value = False

    credentials = oauth_service.get_authenticated_credentials("test@example.com")

    assert credentials is not None
    assert credentials.token == "test-token"
    assert credentials.refresh_token == "test-refresh"


def test_get_authenticated_credentials_auto_refresh(oauth_service, mock_credentials_repo):
    """Test auto-refresh when token is expired"""
    mock_credentials_repo.get_by_user_id.return_value = {
        "user_id": "test@example.com",
        "token_dict": {
            "token": "old-token",
            "refresh_token": "test-refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-secret",
        },
        "scopes": GMAIL_SCOPES,
        "token_expiry": datetime.now(UTC) - timedelta(hours=1),  # Expired
    }

    mock_credentials_repo.is_token_expired.return_value = True

    # Mock the refresh
    with patch("mailq.gmail.oauth.Request"):
        with patch.object(oauth_service, "refresh_credentials") as mock_refresh:
            mock_refreshed_creds = Mock()
            mock_refresh.return_value = mock_refreshed_creds

            credentials = oauth_service.get_authenticated_credentials("test@example.com")

            # Verify refresh was called
            mock_refresh.assert_called_once()
            assert credentials == mock_refreshed_creds


@patch("mailq.gmail.oauth.Request")
def test_refresh_credentials(mock_request, oauth_service, mock_credentials_repo):
    """Test token refresh"""
    # Mock existing credentials
    mock_creds = Mock()
    mock_creds.token = "old-token"
    mock_creds.refresh_token = "test-refresh"
    mock_creds.token_uri = "https://oauth2.googleapis.com/token"
    mock_creds.client_id = "test-client-id"
    mock_creds.client_secret = "test-secret"
    mock_creds.scopes = GMAIL_SCOPES

    # Mock refresh updating token
    def mock_refresh_func(request):
        mock_creds.token = "new-token"

    mock_creds.refresh = mock_refresh_func

    # Perform refresh
    oauth_service.refresh_credentials("test@example.com", mock_creds)

    # Verify new token was stored
    mock_credentials_repo.store_credentials.assert_called_once()
    call_args = mock_credentials_repo.store_credentials.call_args

    assert call_args[1]["user_id"] == "test@example.com"
    assert call_args[1]["token_dict"]["token"] == "new-token"

    # Verify refresh timestamp updated
    mock_credentials_repo.update_refresh_timestamp.assert_called_once_with("test@example.com")


def test_refresh_credentials_no_refresh_token(oauth_service, mock_credentials_repo):
    """Test refresh fails without refresh token"""
    mock_creds = Mock()
    mock_creds.refresh_token = None

    with pytest.raises(ValueError) as exc_info:
        oauth_service.refresh_credentials("test@example.com", mock_creds)

    assert "No refresh token" in str(exc_info.value)


@patch("mailq.gmail.oauth.build")
def test_build_gmail_service(mock_build, oauth_service, mock_credentials_repo):
    """Test building Gmail API service"""
    # Mock credentials
    mock_credentials_repo.get_by_user_id.return_value = {
        "user_id": "test@example.com",
        "token_dict": {
            "token": "test-token",
            "refresh_token": "test-refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-secret",
        },
        "scopes": GMAIL_SCOPES,
    }
    mock_credentials_repo.is_token_expired.return_value = False

    # Mock service builder
    mock_service = Mock()
    mock_build.return_value = mock_service

    service = oauth_service.build_gmail_service("test@example.com")

    # Verify build was called with correct parameters
    mock_build.assert_called_once()
    assert mock_build.call_args[0][0] == "gmail"
    assert mock_build.call_args[0][1] == "v1"
    assert service == mock_service


def test_build_gmail_service_no_credentials(oauth_service, mock_credentials_repo):
    """Test building service fails without credentials"""
    mock_credentials_repo.get_by_user_id.return_value = None

    with pytest.raises(ValueError) as exc_info:
        oauth_service.build_gmail_service("test@example.com")

    assert "No credentials found" in str(exc_info.value)


@patch("mailq.gmail.oauth.Request")
def test_revoke_credentials(mock_request, oauth_service, mock_credentials_repo):
    """Test credential revocation"""
    # Mock credentials
    mock_creds = Mock()
    mock_credentials_repo.get_by_user_id.return_value = {
        "token_dict": {
            "token": "test-token",
            "refresh_token": "test-refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-secret",
        },
        "scopes": GMAIL_SCOPES,
    }
    mock_credentials_repo.is_token_expired.return_value = False

    with patch.object(oauth_service, "get_authenticated_credentials", return_value=mock_creds):
        oauth_service.revoke_credentials("test@example.com")

        # Verify revoke was called
        mock_creds.revoke.assert_called_once()

        # Verify credentials were deleted
        mock_credentials_repo.delete_credentials.assert_called_once_with("test@example.com")


def test_revoke_credentials_no_credentials(oauth_service, mock_credentials_repo):
    """Test revoke still deletes even if no credentials exist"""
    mock_credentials_repo.get_by_user_id.return_value = None

    with patch.object(oauth_service, "get_authenticated_credentials", return_value=None):
        oauth_service.revoke_credentials("test@example.com")

        # Verify delete was still called
        mock_credentials_repo.delete_credentials.assert_called_once_with("test@example.com")


def test_encryption_key_required():
    """Test that encryption key environment variable is required"""
    # Remove encryption key
    if "MAILQ_ENCRYPTION_KEY" in os.environ:
        del os.environ["MAILQ_ENCRYPTION_KEY"]

    with pytest.raises(ValueError) as exc_info:
        UserCredentialsRepository()

    assert "MAILQ_ENCRYPTION_KEY" in str(exc_info.value)


def test_credential_encryption_decryption(encryption_key):
    """Test that credentials are properly encrypted and decrypted"""
    repo = UserCredentialsRepository()

    token_dict = {
        "token": "sensitive-access-token",
        "refresh_token": "sensitive-refresh-token",
        "client_secret": "sensitive-secret",
    }

    # Encrypt
    encrypted = repo._encrypt_token(token_dict)

    # Verify it's actually encrypted (not plaintext)
    assert "sensitive-access-token" not in encrypted
    assert isinstance(encrypted, str)

    # Decrypt
    decrypted = repo._decrypt_token(encrypted)

    assert decrypted == token_dict


def test_credential_encryption_error_handling(encryption_key):
    """Test encryption error handling"""
    repo = UserCredentialsRepository()

    # Try to decrypt invalid data
    with pytest.raises(CredentialEncryptionError):
        repo._decrypt_token("not-valid-encrypted-data")
