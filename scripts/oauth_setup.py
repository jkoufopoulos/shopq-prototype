#!/usr/bin/env python3
"""Terminal OAuth setup script for Gmail API

Interactive CLI for users to authorize Gmail access and store credentials.

Usage:
    python scripts/oauth_setup.py                    # Setup for default user
    python scripts/oauth_setup.py user@example.com   # Setup for specific user
    python scripts/oauth_setup.py --revoke           # Revoke credentials

Requirements:
    - SHOPQ_ENCRYPTION_KEY environment variable must be set
    - credentials/credentials.json with OAuth client secrets must exist
    - Database must be initialized (shopq/data/shopq.db)

Example:
    # Generate encryption key first
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # Set encryption key
    export SHOPQ_ENCRYPTION_KEY="your-key-here"

    # Run setup
    python scripts/oauth_setup.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shopq.gmail.oauth import GmailOAuthService
from shopq.infrastructure.database import init_database
from shopq.storage.user_credentials_repository import UserCredentialsRepository


def print_banner():
    """Print welcome banner"""
    print("=" * 60)
    print("          ShopQ - Gmail OAuth Setup")
    print("=" * 60)
    print()


def check_prerequisites() -> tuple[bool, list[str]]:
    """
    Check that all prerequisites are met

    Returns:
        Tuple of (success, error_messages)
    """
    errors = []

    # Check encryption key
    if not os.getenv("SHOPQ_ENCRYPTION_KEY"):
        errors.append(
            "❌ SHOPQ_ENCRYPTION_KEY environment variable not set.\n"
            "   Generate one with:\n"
            '   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )

    # Check database
    from shopq.infrastructure.database import DB_PATH

    if not DB_PATH.exists():
        errors.append(
            f"❌ Database not found at {DB_PATH}\n"
            "   Run: python -c 'from shopq.infrastructure.database import init_database; init_database()'"
        )

    # Check client secrets
    client_secrets_path = os.getenv(
        "GMAIL_OAUTH_CLIENT_SECRETS",
        "credentials/credentials.json",
    )
    if not Path(client_secrets_path).exists():
        errors.append(
            f"❌ OAuth client secrets not found at {client_secrets_path}\n"
            "   Download from Google Cloud Console:\n"
            "   1. Go to https://console.cloud.google.com/apis/credentials\n"
            "   2. Create OAuth 2.0 Client ID (Desktop app type)\n"
            "   3. Download JSON and save to credentials/credentials.json"
        )

    return len(errors) == 0, errors


def setup_oauth(user_id: str = "default"):
    """
    Run interactive OAuth setup

    Args:
        user_id: User identifier (email or "default")
    """
    print_banner()

    # Check prerequisites
    success, errors = check_prerequisites()
    if not success:
        print("❌ Prerequisites not met:\n")
        for error in errors:
            print(error)
            print()
        sys.exit(1)

    print("✅ All prerequisites met\n")

    # Initialize services
    try:
        oauth_service = GmailOAuthService()
        creds_repo = UserCredentialsRepository()
    except Exception as e:
        print(f"❌ Failed to initialize services: {e}")
        sys.exit(1)

    # Check if user already has credentials
    existing = creds_repo.get_by_user_id(user_id, decrypt=False)
    if existing:
        print(f"⚠️  User '{user_id}' already has stored credentials")
        print(f"   Created: {existing['created_at']}")
        print(f"   Last updated: {existing['updated_at']}")
        print()
        response = input("Overwrite existing credentials? [y/N]: ").strip().lower()
        if response != "y":
            print("❌ Setup cancelled")
            sys.exit(0)
        print()

    # Start OAuth flow
    print(f"🔐 Setting up Gmail OAuth for user: {user_id}")
    print()
    print("Starting OAuth flow...")
    print("A browser window will open for authorization.")
    print()

    try:
        # Use desktop flow (opens browser automatically)
        flow = oauth_service.initiate_desktop_oauth_flow()

        # Run local server to handle OAuth callback
        # This will open browser and wait for user to authorize
        credentials = flow.run_local_server(
            host="localhost",
            port=8080,
            authorization_prompt_message="Please visit this URL to authorize: {url}",
            success_message="Authorization successful! You can close this window.",
            open_browser=True,
        )

        # Extract token dictionary
        token_dict = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }

        # Store credentials
        oauth_service.store_user_credentials(user_id, token_dict)

        print()
        print("✅ OAuth setup successful!")
        print()
        print(f"   User: {user_id}")
        print(f"   Scopes: {', '.join(credentials.scopes)}")
        print()
        print("Credentials have been encrypted and stored securely in the database.")
        print()

        # Test the connection
        print("Testing Gmail API connection...")
        try:
            service = oauth_service.build_gmail_service(user_id)
            profile = service.users().getProfile(userId="me").execute()
            email = profile.get("emailAddress")
            print(f"✅ Successfully connected to Gmail for: {email}")
            print()
        except Exception as e:
            print(f"⚠️  Warning: Could not test connection: {e}")
            print("   Credentials are stored but may not be valid.")
            print()

    except KeyboardInterrupt:
        print("\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ OAuth setup failed: {e}")
        sys.exit(1)


def revoke_oauth(user_id: str = "default"):
    """
    Revoke and delete OAuth credentials

    Args:
        user_id: User identifier
    """
    print_banner()
    print(f"🗑️  Revoking credentials for user: {user_id}")
    print()

    # Initialize services
    try:
        oauth_service = GmailOAuthService()
    except Exception as e:
        print(f"❌ Failed to initialize services: {e}")
        sys.exit(1)

    # Confirm
    response = (
        input(f"Are you sure you want to revoke credentials for '{user_id}'? [y/N]: ")
        .strip()
        .lower()
    )
    if response != "y":
        print("❌ Revocation cancelled")
        sys.exit(0)

    try:
        oauth_service.revoke_credentials(user_id)
        print()
        print("✅ Credentials revoked and deleted successfully")
        print()
    except Exception as e:
        print(f"\n❌ Failed to revoke credentials: {e}")
        sys.exit(1)


def list_users():
    """List all users with stored credentials"""
    print_banner()
    print("📋 Users with stored Gmail credentials:")
    print()

    try:
        creds_repo = UserCredentialsRepository()
        users = creds_repo.list_all_users()

        if not users:
            print("   No users found with stored credentials")
            print()
            return

        for user_id in users:
            creds = creds_repo.get_by_user_id(user_id, decrypt=False)
            if creds:
                print(f"   • {user_id}")
                print(f"     Created: {creds['created_at']}")
                print(f"     Last updated: {creds['updated_at']}")
                if creds.get("last_refresh_at"):
                    print(f"     Last refreshed: {creds['last_refresh_at']}")
                if creds.get("last_sync_at"):
                    print(f"     Last synced: {creds['last_sync_at']}")
                print()

    except Exception as e:
        print(f"❌ Failed to list users: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Setup Gmail OAuth credentials for ShopQ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup OAuth for default user
  python scripts/oauth_setup.py

  # Setup OAuth for specific user
  python scripts/oauth_setup.py user@example.com

  # Revoke credentials
  python scripts/oauth_setup.py --revoke
  python scripts/oauth_setup.py --revoke user@example.com

  # List all users
  python scripts/oauth_setup.py --list
        """,
    )

    parser.add_argument(
        "user_id",
        nargs="?",
        default="default",
        help="User ID (email address or 'default' for single-user mode)",
    )

    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke and delete credentials instead of setting them up",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all users with stored credentials",
    )

    args = parser.parse_args()

    # Ensure database exists
    try:
        init_database()
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        sys.exit(1)

    if args.list:
        list_users()
    elif args.revoke:
        revoke_oauth(args.user_id)
    else:
        setup_oauth(args.user_id)


if __name__ == "__main__":
    main()
