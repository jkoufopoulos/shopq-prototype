"""
Tests for compute_client_label() function.

This function is the SINGLE SOURCE OF TRUTH for type+attention → client_label mapping.
Rules are defined in docs/TAXONOMY.md.

See: mailq/storage/classification.py
"""

from mailq.storage.classification import compute_client_label


class TestComputeClientLabel:
    """Tests for the client_label computation logic.

    The compute_client_label function takes (email_type, attention) and returns
    a client_label. The attention field is "action_required" or "none".

    This is different from importance (critical/time_sensitive/routine) which
    determines digest sections, not Gmail labels.
    """

    # =========================================================================
    # Rule 1: type=receipt → "receipts"
    # =========================================================================

    def test_receipt_no_action_returns_receipts(self):
        """Receipts with no action required → receipts bucket."""
        assert compute_client_label("receipt", "none") == "receipts"

    def test_receipt_action_required_returns_receipts(self):
        """Receipts with action required → receipts (receipts take priority)."""
        assert compute_client_label("receipt", "action_required") == "receipts"

    # =========================================================================
    # Rule 2: type=message → "messages"
    # =========================================================================

    def test_message_no_action_returns_messages(self):
        """Messages with no action required → messages bucket."""
        assert compute_client_label("message", "none") == "messages"

    def test_message_action_required_returns_messages(self):
        """Messages with action required → messages (messages take priority)."""
        assert compute_client_label("message", "action_required") == "messages"

    # =========================================================================
    # Rule 3: type=otp → "everything-else" (despite being critical)
    # =========================================================================

    def test_otp_no_action_returns_everything_else(self):
        """OTPs are always everything-else.

        Per TAXONOMY.md otp_rules:
        - type: otp
        - importance: critical
        - client_label: everything-else

        OTPs are ephemeral and don't require user action in the digest context.
        They're handled by guardrails (force_critical) and filtered from digest.
        """
        assert compute_client_label("otp", "none") == "everything-else"

    def test_otp_action_required_returns_everything_else(self):
        """OTPs with action_required → everything-else (otp takes priority)."""
        assert compute_client_label("otp", "action_required") == "everything-else"

    # =========================================================================
    # Rule 4: attention=action_required → "action-required" (for non-receipt/message/otp)
    # =========================================================================

    def test_notification_action_required_returns_action_required(self):
        """Notifications requiring action (fraud, security) → action-required."""
        assert compute_client_label("notification", "action_required") == "action-required"

    def test_event_action_required_returns_action_required(self):
        """Events requiring action → action-required."""
        assert compute_client_label("event", "action_required") == "action-required"

    def test_newsletter_action_required_returns_action_required(self):
        """Newsletters requiring action (rare but possible) → action-required."""
        assert compute_client_label("newsletter", "action_required") == "action-required"

    def test_promotion_action_required_returns_action_required(self):
        """Promotions requiring action (rare) → action-required."""
        assert compute_client_label("promotion", "action_required") == "action-required"

    # =========================================================================
    # Rule 5: Everything else → "everything-else"
    # =========================================================================

    def test_newsletter_no_action_returns_everything_else(self):
        """Newsletters with no action → everything-else."""
        assert compute_client_label("newsletter", "none") == "everything-else"

    def test_notification_no_action_returns_everything_else(self):
        """Notifications with no action → everything-else."""
        assert compute_client_label("notification", "none") == "everything-else"

    def test_event_no_action_returns_everything_else(self):
        """Events with no action → everything-else."""
        assert compute_client_label("event", "none") == "everything-else"

    def test_promotion_no_action_returns_everything_else(self):
        """Promotions with no action → everything-else."""
        assert compute_client_label("promotion", "none") == "everything-else"

    def test_uncategorized_no_action_returns_everything_else(self):
        """Uncategorized emails → everything-else."""
        assert compute_client_label("uncategorized", "none") == "everything-else"


class TestClientLabelTaxonomyAlignment:
    """Tests verifying alignment with TAXONOMY.md examples."""

    def test_order_confirmation(self):
        """Order confirmation (type=receipt) → receipts."""
        # TAXONOMY.md order_lifecycle.order_confirmation
        assert compute_client_label("receipt", "none") == "receipts"

    def test_shipped_notification(self):
        """Shipped notification (type=receipt) → receipts."""
        # TAXONOMY.md order_lifecycle.shipped
        assert compute_client_label("receipt", "none") == "receipts"

    def test_out_for_delivery(self):
        """Out for delivery (type=receipt) → receipts."""
        # TAXONOMY.md order_lifecycle.out_for_delivery
        assert compute_client_label("receipt", "none") == "receipts"

    def test_fraud_alert_action_required(self):
        """Fraud alert requiring action (type=notification, attention=action_required) → action-required."""
        # TAXONOMY.md importance.critical includes fraud_alerts
        # But client_label uses attention, not importance
        assert compute_client_label("notification", "action_required") == "action-required"

    def test_informational_security_notice(self):
        """Informational security notice (no action required) → everything-else.

        Example: "You allowed MailQ access to your Google Account"
        This is critical importance but does NOT require user action.
        """
        assert compute_client_label("notification", "none") == "everything-else"

    def test_downtown_dharma_event(self):
        """Listserv event announcement (type=event) → everything-else."""
        # TAXONOMY.md listserv.examples[0] - Downtown Dharma event
        assert compute_client_label("event", "none") == "everything-else"

    def test_downtown_dharma_newsletter(self):
        """Listserv teaching (type=newsletter) → everything-else."""
        # TAXONOMY.md listserv.examples[1] - Downtown Dharma teaching
        assert compute_client_label("newsletter", "none") == "everything-else"

    def test_downtown_dharma_discussion(self):
        """Listserv discussion (type=message) → messages."""
        # TAXONOMY.md listserv.examples[2] - Downtown Dharma discussion
        assert compute_client_label("message", "none") == "messages"

    def test_autopay_notification(self):
        """Autopay notification (type=receipt) → receipts."""
        # TAXONOMY.md billing_lifecycle.autopay_notification
        assert compute_client_label("receipt", "none") == "receipts"

    def test_bill_ready_notice(self):
        """Bill ready notice (type=receipt) → receipts."""
        # TAXONOMY.md billing_lifecycle.bill_ready
        assert compute_client_label("receipt", "none") == "receipts"
