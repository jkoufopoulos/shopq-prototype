#!/usr/bin/env python3
"""
Fetch emails from Gmail for the last N days and export to JSON for labeling.

This script:
1. Authenticates with Gmail (prompts OAuth if needed)
2. Fetches all emails from the last N days (default: 30)
3. Exports to data/labeling/emails_to_label.json

Usage:
    python scripts/labeling/fetch_emails.py [--days 30] [--max-results 500]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from shopq.gmail.oauth import GmailOAuthService, GMAIL_SCOPES
from shopq.gmail.parser import parse_message, GmailParsingError


def authenticate_gmail(user_id: str = "labeling_user") -> any:
    """Authenticate with Gmail and return the service object."""
    oauth_service = GmailOAuthService()

    # Try to get existing credentials
    try:
        credentials = oauth_service.get_authenticated_credentials(user_id)
        if credentials:
            print(f"Using existing credentials for {user_id}")
            return oauth_service.build_gmail_service(user_id)
    except Exception as e:
        print(f"No existing credentials found: {e}")

    # Need to authenticate
    print("\nNo valid credentials found. Starting OAuth flow...")
    print("A browser window will open for you to authorize Gmail access.\n")

    flow = oauth_service.initiate_desktop_oauth_flow(scopes=GMAIL_SCOPES)
    credentials = flow.run_local_server(port=8080)

    # Store credentials
    token_dict = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    oauth_service.store_user_credentials(user_id, token_dict)

    print(f"Credentials stored for {user_id}")
    return oauth_service.build_gmail_service(user_id)


def fetch_emails_since(
    service,
    days: int,
    max_results: int = 1000,
    purchases_only: bool = True,
) -> list[dict]:
    """Fetch emails from the last N days.

    Args:
        service: Gmail API service
        days: Number of days to fetch
        max_results: Maximum emails to fetch (0 = no limit)
        purchases_only: If True, only fetch from Gmail's Purchases category
    """
    # Calculate date query
    since_date = datetime.now(UTC) - timedelta(days=days)
    query = f"after:{since_date.strftime('%Y/%m/%d')}"

    # Use Gmail's Purchases category to filter
    label_ids = None
    if purchases_only:
        query += " category:purchases"
        print(f"Filtering to Gmail's Purchases category only")

    print(f"Fetching emails since {since_date.strftime('%Y-%m-%d')}...")
    print(f"Query: {query}")

    # List messages
    all_messages = []
    page_token = None

    while True:
        # If max_results is 0, fetch all; otherwise limit batch size
        if max_results > 0:
            remaining = max_results - len(all_messages)
            if remaining <= 0:
                break
            batch_size = min(100, remaining)
        else:
            batch_size = 100

        request = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=batch_size,
            pageToken=page_token
        )
        response = request.execute()

        messages = response.get("messages", [])
        if not messages:
            break

        all_messages.extend(messages)
        print(f"  Found {len(all_messages)} messages so far...")

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    print(f"\nTotal messages found: {len(all_messages)}")
    return all_messages


def get_message_details(service, message_id: str) -> dict | None:
    """Fetch full message details."""
    try:
        return service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()
    except Exception as e:
        print(f"  Error fetching message {message_id}: {e}")
        return None


def extract_email_data(raw_message: dict) -> dict | None:
    """Extract relevant data from raw Gmail message."""
    try:
        # Get basic info from headers
        payload = raw_message.get("payload", {})
        headers = payload.get("headers", [])

        def get_header(name: str) -> str:
            for h in headers:
                if h.get("name", "").lower() == name.lower():
                    return h.get("value", "")
            return ""

        # Extract body
        body_text = ""
        body_html = ""

        def extract_body_parts(part):
            nonlocal body_text, body_html
            mime_type = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")

            if data:
                import base64
                try:
                    decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
                    if mime_type == "text/plain" and not body_text:
                        body_text = decoded
                    elif mime_type == "text/html" and not body_html:
                        body_html = decoded
                except Exception:
                    pass

            # Recurse into parts
            for subpart in part.get("parts", []):
                extract_body_parts(subpart)

        extract_body_parts(payload)

        # Get snippet from Gmail (useful preview)
        snippet = raw_message.get("snippet", "")

        # Parse internal date
        internal_date_ms = raw_message.get("internalDate", "0")
        received_at = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=UTC)

        return {
            "message_id": raw_message["id"],
            "thread_id": raw_message.get("threadId", ""),
            "subject": get_header("Subject"),
            "from_address": get_header("From"),
            "to_address": get_header("To"),
            "date": get_header("Date"),
            "received_at": received_at.isoformat(),
            "snippet": snippet,
            "body_text": body_text[:5000] if body_text else "",  # Truncate large bodies
            "body_html": body_html[:10000] if body_html else "",
            "labels": raw_message.get("labelIds", []),
        }
    except Exception as e:
        print(f"  Error extracting email data: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch Gmail emails for labeling")
    parser.add_argument("--days", type=int, default=30, help="Number of days to fetch (default: 30)")
    parser.add_argument("--max-results", type=int, default=0, help="Maximum emails to fetch (0 = no limit)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    parser.add_argument("--all-emails", action="store_true", help="Fetch all emails, not just Purchases category")
    args = parser.parse_args()

    # Set default output path
    output_path = args.output or str(project_root / "data" / "labeling" / "emails_to_label.json")

    purchases_only = not args.all_emails

    print("=" * 60)
    print("ShopQ Email Fetcher for Labeling")
    print("=" * 60)
    print(f"Fetching emails from last {args.days} days")
    print(f"Max results: {args.max_results if args.max_results > 0 else 'unlimited'}")
    print(f"Filter: {'Purchases category only' if purchases_only else 'All emails'}")
    print(f"Output: {output_path}")
    print()

    # Authenticate
    service = authenticate_gmail()

    # Fetch message list
    messages = fetch_emails_since(service, args.days, args.max_results, purchases_only=purchases_only)

    if not messages:
        print("No messages found!")
        return

    # Fetch full details for each message
    print(f"\nFetching full details for {len(messages)} messages...")
    emails = []

    for i, msg in enumerate(messages):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i + 1}/{len(messages)}...")

        raw = get_message_details(service, msg["id"])
        if raw:
            data = extract_email_data(raw)
            if data:
                emails.append(data)

    print(f"\nSuccessfully processed {len(emails)} emails")

    # Add labeling metadata
    output_data = {
        "metadata": {
            "fetched_at": datetime.now(UTC).isoformat(),
            "days_fetched": args.days,
            "total_emails": len(emails),
            "labeling_status": "pending",
        },
        "emails": emails,
    }

    # Save to JSON
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")
    print(f"\nNext step: Run 'python scripts/labeling/label_emails.py' to label these emails")


if __name__ == "__main__":
    main()
