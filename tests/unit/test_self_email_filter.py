"""

from __future__ import annotations

Tests for self-email filter (MailQ digest emails)
"""

import pytest

from mailq.classification.filters import filter_self_emails, is_self_email


class TestSelfEmailDetection:
    """Test detection of MailQ's own digest emails"""

    def test_mailq_digest_subject(self):
        """Detect MailQ digest by distinctive subject line"""
        email = {
            "subject": "Your Inbox --Saturday, November 01 at 01:03 AM",
            "from": "jkoufopoulos@gmail.com",
            "snippet": (
                "Your Inbox --Saturday, November 01 at 01:03 AM Hey! It's a clear "
                "53° in New York tonight"
            ),
        }

        assert is_self_email(email, "jkoufopoulos@gmail.com")

    def test_mailq_digest_subject_without_user_email(self):
        """Digest email identifiable even without user_email parameter"""
        email = {
            "subject": "Your Inbox --Saturday, November 01 at 01:03 AM",
            "from": "someone@gmail.com",
            "snippet": "Your Inbox...",
        }

        # Should still detect by subject pattern alone
        assert is_self_email(email)

    def test_mailq_digest_label(self):
        """Detect by MailQ/Digest label"""
        email = {
            "subject": "Some subject",
            "from": "jkoufopoulos@gmail.com",
            "labelIds": ["INBOX", "MailQ/Digest"],
        }

        assert is_self_email(email)

    def test_mailq_digest_label_case_insensitive(self):
        """Label detection should be case-insensitive"""
        email = {
            "subject": "Some subject",
            "from": "jkoufopoulos@gmail.com",
            "labelIds": ["INBOX", "MAILQ/DIGEST"],
        }

        assert is_self_email(email)

    def test_regular_email_from_self(self):
        """Regular email from self (not digest) should NOT be filtered"""
        email = {
            "subject": "PDF",  # From ground truth - Susan Fago email
            "from": "jkoufopoulos@gmail.com",
            "snippet": "Here is the PDF you requested",
        }

        # Subject doesn't match digest pattern → keep
        assert not is_self_email(email, "jkoufopoulos@gmail.com")

    def test_email_from_others(self):
        """Email from other people should NOT be filtered"""
        email = {
            "subject": "Your Con Edison bill is ready",
            "from": "noreply@billing.coned.com",
            "snippet": "Your Con Edison Bill is ready",
        }

        assert not is_self_email(email, "jkoufopoulos@gmail.com")

    def test_inbox_from_self_generic(self):
        """Email from self with 'inbox' in subject (generic pattern)"""
        email = {
            "subject": "About our inbox management strategy",
            "from": "jkoufopoulos@gmail.com",
            "snippet": "Some notes...",
        }

        # Contains "inbox" from self → could be self-email
        assert is_self_email(email, "jkoufopoulos@gmail.com")


class TestFilterSelfEmails:
    """Test batch filtering of self-emails"""

    def test_filter_removes_digest_emails(self):
        """Filter should remove digest emails, keep regular emails"""
        emails = [
            # MailQ digest (should be filtered)
            {
                "subject": "Your Inbox --Saturday, November 01 at 01:03 AM",
                "from": "jkoufopoulos@gmail.com",
            },
            # Regular email (should keep)
            {
                "subject": "Your Con Edison bill is ready",
                "from": "noreply@billing.coned.com",
            },
            # Another regular email (should keep)
            {"subject": "Security alert", "from": "no-reply@accounts.google.com"},
        ]

        filtered = filter_self_emails(emails, "jkoufopoulos@gmail.com")

        assert len(filtered) == 2  # Filtered 1 digest email
        assert "Con Edison" in filtered[0]["subject"]
        assert "Security" in filtered[1]["subject"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
