"""Tests for Gmail label mapper

Tests the 4-label client system:
- MailQ-Receipts: Purchase confirmations
- MailQ-Messages: Personal/professional correspondence
- MailQ-Action-Required: Items requiring user action
- MailQ-Everything-Else: Newsletters, notifications, promotions, etc.

Note: client_label is computed from type + attention (action_required/none),
NOT from type + importance (critical/time_sensitive/routine).
"""

from __future__ import annotations

import unittest

from mailq.classification.mapper import compute_client_label, map_to_gmail_labels


class TestComputeClientLabel(unittest.TestCase):
    """Test compute_client_label function"""

    def test_receipt_type_returns_receipts(self):
        """Receipts always map to 'receipts' regardless of attention"""
        self.assertEqual(compute_client_label("receipt", "none"), "receipts")
        self.assertEqual(compute_client_label("receipt", "action_required"), "receipts")

    def test_message_type_returns_messages(self):
        """Messages always map to 'messages' regardless of attention"""
        self.assertEqual(compute_client_label("message", "none"), "messages")
        self.assertEqual(compute_client_label("message", "action_required"), "messages")

    def test_otp_type_returns_everything_else(self):
        """OTPs map to 'everything-else' regardless of attention"""
        self.assertEqual(compute_client_label("otp", "none"), "everything-else")
        self.assertEqual(compute_client_label("otp", "action_required"), "everything-else")

    def test_action_required_returns_action_required(self):
        """attention=action_required maps to 'action-required' for non-special types"""
        self.assertEqual(compute_client_label("notification", "action_required"), "action-required")
        self.assertEqual(compute_client_label("event", "action_required"), "action-required")
        self.assertEqual(compute_client_label("newsletter", "action_required"), "action-required")

    def test_no_action_returns_everything_else(self):
        """attention=none maps to 'everything-else' for non-special types"""
        self.assertEqual(compute_client_label("notification", "none"), "everything-else")
        self.assertEqual(compute_client_label("newsletter", "none"), "everything-else")
        self.assertEqual(compute_client_label("promotion", "none"), "everything-else")
        self.assertEqual(compute_client_label("event", "none"), "everything-else")


class TestMapToGmailLabels(unittest.TestCase):
    """Test map_to_gmail_labels function returns correct Gmail label strings"""

    def test_receipt_maps_to_mailq_receipts(self):
        """Receipt type maps to MailQ-Receipts"""
        result = {
            "type": "receipt",
            "type_conf": 0.95,
            "attention": "none",
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Receipts"])

    def test_message_maps_to_mailq_messages(self):
        """Message type maps to MailQ-Messages"""
        result = {
            "type": "message",
            "type_conf": 0.88,
            "attention": "none",
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Messages"])

    def test_action_required_notification_maps_to_action_required(self):
        """Notification with action_required maps to MailQ-Action-Required"""
        result = {
            "type": "notification",
            "type_conf": 0.93,
            "attention": "action_required",
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Action-Required"])

    def test_informational_notification_maps_to_everything_else(self):
        """Notification with no action required maps to MailQ-Everything-Else

        Example: "You allowed MailQ access to your Google Account"
        """
        result = {
            "type": "notification",
            "type_conf": 0.93,
            "attention": "none",
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Everything-Else"])

    def test_newsletter_maps_to_everything_else(self):
        """Newsletter maps to MailQ-Everything-Else"""
        result = {
            "type": "newsletter",
            "type_conf": 0.92,
            "attention": "none",
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Everything-Else"])

    def test_otp_maps_to_everything_else_despite_action(self):
        """OTP maps to MailQ-Everything-Else even when action_required (ephemeral)"""
        result = {
            "type": "otp",
            "type_conf": 0.99,
            "attention": "action_required",
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Everything-Else"])

    def test_confidence_is_preserved(self):
        """Label confidence matches type_conf"""
        result = {
            "type": "receipt",
            "type_conf": 0.87,
            "attention": "none",
        }
        mapping = map_to_gmail_labels(result)
        self.assertAlmostEqual(mapping["labels_conf"]["MailQ-Receipts"], 0.87, places=2)

    def test_missing_attention_defaults_to_none(self):
        """Missing attention field defaults to none (everything-else)"""
        result = {
            "type": "notification",
            "type_conf": 0.85,
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Everything-Else"])

    def test_uncategorized_type_maps_to_everything_else(self):
        """Uncategorized type maps to MailQ-Everything-Else"""
        result = {
            "type": "uncategorized",
            "type_conf": 0.5,
            "attention": "none",
        }
        mapping = map_to_gmail_labels(result)
        self.assertEqual(mapping["labels"], ["MailQ-Everything-Else"])


if __name__ == "__main__":
    unittest.main()
