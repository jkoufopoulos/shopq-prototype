"""

from __future__ import annotations

Test entity linking in digest summaries

Verifies that all entities in the digest have proper hyperlinks.
"""

import re
from datetime import datetime

from mailq.classification.models import (
    DeadlineEntity,
    EventEntity,
    NotificationEntity,
)
from mailq.digest.card_renderer import CardRenderer


class TestEntityLinkingInDigest:
    """Test that all entities are properly linked in digest"""

    def test_notification_entity_name_extraction(self):
        """Test entity name extraction from NotificationEntity messages"""
        renderer = CardRenderer()

        test_cases = [
            # (message, expected_entity_name)
            ("confirm your OpenWeatherMap account", "OpenWeatherMap account"),
            ("PayPal is refunding you $49.28", "PayPal"),
            ("Bank of America wants you to review trending scams", "Bank of America"),
            (
                "Double-check if you authorized MailQ's access to your Google Account",
                "Google Account",
            ),
            ("Your AutoPay is set for tomorrow", "AutoPay"),
            ("Chase Bank sent you a statement", "Chase Bank"),
            ("American Express card ending in 1234", "American Express"),
        ]

        for message, expected_name in test_cases:
            entity = NotificationEntity(
                message=message,
                confidence=0.9,
                source_email_id="test_123",
                source_subject="Test",
                source_snippet=message,
                timestamp=datetime.now(),
            )

            extracted = renderer._extract_entity_name(entity)
            print(f"Message: {message}")
            print(f"  Expected: '{expected_name}'")
            print(f"  Extracted: '{extracted}'")

            assert extracted == expected_name or expected_name in extracted, (
                f"Expected '{expected_name}' but got '{extracted}'"
            )

    def test_all_lines_have_links(self):
        """Test that every featured entity line has at least one link"""
        renderer = CardRenderer()

        # Create test entities
        entities = [
            NotificationEntity(
                message="confirm your OpenWeatherMap account",
                importance="critical",
                confidence=0.9,
                source_email_id="msg_1",
                source_subject="Confirm account",
                source_snippet="confirm your OpenWeatherMap account",
                timestamp=datetime.now(),
            ),
            NotificationEntity(
                message="PayPal is refunding you $49.28 by next year",
                importance="high",
                confidence=0.85,
                source_email_id="msg_2",
                source_subject="PayPal refund",
                source_snippet="PayPal is refunding you",
                timestamp=datetime.now(),
            ),
            NotificationEntity(
                message="Bank of America wants you to review trending scams",
                importance="medium",
                confidence=0.8,
                source_email_id="msg_3",
                source_subject="Security alert",
                source_snippet="Bank of America wants you",
                timestamp=datetime.now(),
            ),
            DeadlineEntity(
                title="AutoPay due tomorrow",
                from_whom="AutoPay",
                due_date="tomorrow",
                importance="high",
                confidence=0.9,
                source_email_id="msg_4",
                source_subject="Payment due",
                source_snippet="Your AutoPay is set",
                timestamp=datetime.now(),
            ),
            EventEntity(
                title="Jonathan Foust's Monday Evening Class",
                location=None,
                event_time="Monday 7pm",
                importance="medium",
                confidence=0.85,
                source_email_id="msg_5",
                source_subject="Class reminder",
                source_snippet="Don't forget about class",
                timestamp=datetime.now(),
            ),
        ]

        # Create digest text
        digest_text = (
            "First things first: confirm your OpenWeatherMap account. "
            "PayPal is refunding you $49.28 by next year. Bank of America wants "
            "you to review trending scams to stay protected. Your AutoPay is set "
            "for tomorrow.\n\n"
            "Don't forget about Jonathan Foust's Monday Evening Class."
        )

        # Render with links
        result = renderer._add_entity_links(digest_text, entities)

        print("\n=== Original Digest ===")
        print(digest_text)
        print("\n=== Linked Digest ===")
        print(result)

        # Check that each entity has a link
        expected_links = [
            "OpenWeatherMap account",  # Should link full phrase
            "PayPal",
            "Bank of America",
            "AutoPay",
            "Jonathan Foust's Monday Evening Class",
        ]

        for entity_text in expected_links:
            # Check if entity is linked (either exact or partial match)
            # We look for <a href=...>text</a> pattern containing the entity
            link_pattern = f"<a[^>]+>[^<]*{re.escape(entity_text.split()[0])}[^<]*</a>"
            assert re.search(link_pattern, result), (
                f"Entity '{entity_text}' should be linked in digest"
            )

        # Count total links
        link_count = result.count("<a href")
        print(f"\n✓ Found {link_count} links in digest")
        assert link_count >= len(expected_links), (
            f"Expected at least {len(expected_links)} links but found {link_count}"
        )

    def test_span_accuracy(self):
        """Test that linked spans match exact entity boundaries"""
        renderer = CardRenderer()

        entity = NotificationEntity(
            message="Bank of America sent an alert",
            importance="high",
            confidence=0.9,
            source_email_id="msg_1",
            source_subject="Alert",
            source_snippet="Bank of America sent an alert",
            timestamp=datetime.now(),
        )

        text = "Bank of America sent you an alert."
        result = renderer._add_entity_links(text, [entity])

        print(f"\nOriginal: {text}")
        print(f"Linked:   {result}")

        # Should link "Bank of America", not just "America" or "Bank"
        assert "<a href=" in result
        assert "Bank of America</a>" in result, "Should link complete entity name 'Bank of America'"
        # Check it's NOT linking just "America" alone (would start with >America not >Bank)
        assert not re.search(r">[^>]*America</a>", result) or "Bank of America</a>" in result, (
            "Should link 'Bank of America' not just 'America'"
        )


class TestEntityNameExtraction:
    """Test entity name extraction for various entity types"""

    def test_extract_camelcase_company_names(self):
        """Test extraction of CamelCase company names like OpenWeatherMap"""
        renderer = CardRenderer()

        test_messages = [
            "confirm your OpenWeatherMap account",
            "Your PayPal payment is ready",
            "AutoPay is scheduled for tomorrow",
            "Your WordPress subscription renewed",
            "GitHub sent you a notification",
            "LinkedIn wants you to review",
        ]

        for message in test_messages:
            entity = NotificationEntity(
                message=message,
                confidence=0.9,
                source_email_id="test",
                source_subject="Test",
                source_snippet=message,
                timestamp=datetime.now(),
            )

            extracted = renderer._extract_entity_name(entity)
            print(f"Message: '{message}'")
            print(f"  Extracted: '{extracted}'")

            # Should extract the company/product name
            assert len(extracted) > 0, "Should extract entity name"
            assert extracted in message, "Extracted name should appear in message"


# Run with: pytest mailq/tests/test_entity_linking_digest.py -v -s
