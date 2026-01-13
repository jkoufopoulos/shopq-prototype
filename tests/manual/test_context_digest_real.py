"""

from __future__ import annotations

Test Context Digest with Real Emails from Database

Fetches classified emails from digest_emails table and generates context digest.
"""

import sys

sys.path.insert(0, "/Users/justinkoufopoulos/Projects/mailq-prototype")

import sqlite3
from datetime import datetime, timedelta

from shopq.digest.context_digest import ContextDigest


def fetch_recent_emails(hours: int = 24):
    """Fetch emails from database from last N hours"""
    db_path = "/Users/justinkoufopoulos/Projects/mailq-prototype/shopq.sqlite"

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get emails from last N hours
        cutoff_time = datetime.now() - timedelta(hours=hours)

        query = """
        SELECT
            id,
            sender,
            subject,
            snippet,
            timestamp,
            type,
            type_conf,
            domains,
            attention,
            attention_conf,
            relationship,
            relationship_conf
        FROM digest_emails
        WHERE timestamp >= ?
        ORDER BY timestamp DESC
        """

        cursor.execute(query, (cutoff_time.isoformat(),))
        rows = cursor.fetchall()

        conn.close()

        print(f"📧 Found {len(rows)} emails in database from last {hours} hours")

        # Convert to dict format
        emails = []
        for row in rows:
            email = {
                "id": row[0],
                "from_email": row[1],
                "from_name": row[1].split("@")[0] if "@" in row[1] else row[1],
                "subject": row[2],
                "snippet": row[3],
                "timestamp": row[4],
                "type": row[5],
                "type_conf": row[6] or 0.0,
                "domains": row[7].split(",") if row[7] else [],
                "attention": row[8] or "none",
                "attention_conf": row[9] or 0.0,
                "relationship": row[10] or "from_unknown",
                "relationship_conf": row[11] or 0.0,
            }
            emails.append(email)

        return emails

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return []
    except Exception as e:
        print(f"❌ Error fetching emails: {e}")
        return []


def test_with_real_emails(hours: int = 24):
    """Test context digest with real emails"""
    print("=" * 60)
    print("Context Digest - Real Email Test")
    print("=" * 60)

    # Fetch emails
    emails = fetch_recent_emails(hours)

    if len(emails) == 0:
        print("\n⚠️  No emails found in database")
        print("\nTrying with longer time range...")
        emails = fetch_recent_emails(hours=168)  # Try 7 days

    if len(emails) == 0:
        print("\n❌ Still no emails found. Database might be empty.")
        print("\nTo populate database:")
        print("1. Open Gmail in Chrome with extension installed")
        print("2. Click 'Organize Inbox' to classify emails")
        print("3. Run this script again")
        return None

    print("\n📊 Email Breakdown:")
    types = {}
    for email in emails:
        email_type = email.get("type", "unknown")
        types[email_type] = types.get(email_type, 0) + 1

    for email_type, count in sorted(types.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {email_type}: {count}")

    # Show sample emails
    print("\n📧 Sample Emails (first 5):")
    for i, email in enumerate(emails[:5]):
        print(f"{i + 1}. [{email['type']}] {email['subject'][:60]}")

    # Generate context digest
    print("\n🌟 Generating Context Digest...")
    print("=" * 60)

    digest = ContextDigest(verbose=True)
    result = digest.generate(emails)

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print("\n📊 Statistics:")
    print(f"   Total emails: {len(emails)}")
    print(f"   Word count: {result['word_count']}")
    print(f"   Entities extracted: {result['entities_count']}")
    print(f"   Featured: {result['featured_count']}")
    print(f"   Critical: {result.get('critical_count', 0)}")
    print(f"   Time-sensitive: {result.get('time_sensitive_count', 0)}")
    print(f"   Routine: {result.get('routine_count', 0)}")
    print(f"   Verified: {'✅' if result['verified'] else '❌'}")
    print(f"   Fallback mode: {'Yes' if result.get('fallback') else 'No'}")

    if result.get("noise_breakdown"):
        print("\n📊 Noise Breakdown:")
        for category, count in result["noise_breakdown"].items():
            print(f"   - {category}: {count}")

    if not result["verified"] and result.get("errors"):
        print("\n⚠️  Verification Warnings:")
        for error in result["errors"][:5]:  # Show first 5
            print(f"   - {error}")

    print("\n📧 Generated Digest:")
    print("=" * 60)
    print(result["text"])
    print("=" * 60)

    # Save HTML output
    output_path = "test_output_real.html"
    with open(output_path, "w") as f:
        f.write(result["html"])

    print(f"\n✅ HTML saved to: {output_path}")
    print(f"\nTo view: open {output_path}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test context digest with real emails")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    args = parser.parse_args()

    test_with_real_emails(hours=args.hours)
