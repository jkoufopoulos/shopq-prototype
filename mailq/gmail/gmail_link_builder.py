"""

from __future__ import annotations

Gmail Link Builder - Generate Gmail URLs for threads and searches

Provides utilities to build:
1. Thread links: https://mail.google.com/mail/u/0/#inbox/{threadId}
2. Message links: https://mail.google.com/mail/u/0/#inbox/{messageId}
3. Category search links: https://mail.google.com/mail/u/0/#search/{query}
4. Custom search links for exploration

All search queries are URL-encoded.
"""

from collections.abc import Mapping
from urllib.parse import quote_plus

from mailq.observability.logging import get_logger

logger = get_logger(__name__)


class GmailLinkBuilder:
    """Build Gmail URLs for threads and searches"""

    BASE_URL = "https://mail.google.com/mail/u/0"

    # Category to Gmail label mapping (4-label system from TAXONOMY.md)
    # Only the 4 client labels are used: Receipts, Messages, Action-Required, Everything-Else
    CATEGORY_LABEL_MAP: dict[str, str] = {
        "Receipts": "label:MailQ-Receipts",
        "Messages": "label:MailQ-Messages",
        "Action Required": "label:MailQ-Action-Required",
        "Everything Else": "label:MailQ-Everything-Else",
    }

    @classmethod
    def thread_link(cls, thread_id: str) -> str:
        """
        Build Gmail thread link.

        Args:
            thread_id: Gmail thread ID

        Returns:
            Full Gmail thread URL

        Side Effects:
            None (pure function - builds URL string only)

        Security:
            Thread ID is URL-encoded to prevent XSS if embedded in HTML.
            Gmail thread IDs are typically alphanumeric, but encoding
            provides defense-in-depth.
        """
        # Use hash-based navigation to keep links compatible with Gmail mobile apps.
        # Desktop web clients also resolve #inbox/{threadId} correctly.
        # URL-encode the ID for defense-in-depth (prevents XSS if ID is malformed)
        safe_id = quote_plus(thread_id) if thread_id else ""
        return f"{cls.BASE_URL}/#inbox/{safe_id}"

    @classmethod
    def message_link(cls, message_id: str) -> str:
        """
        Build Gmail message link (fallback when thread_id unavailable).

        Args:
            message_id: Gmail message ID

        Returns:
            Full Gmail message URL

        Side Effects:
            None (pure function - builds URL string only)

        Security:
            Message ID is URL-encoded to prevent XSS if embedded in HTML.
        """
        safe_id = quote_plus(message_id) if message_id else ""
        return f"{cls.BASE_URL}/#inbox/{safe_id}"

    @classmethod
    def search_link(cls, query: str) -> str:
        """
        Build Gmail search link.

        Args:
            query: Gmail search query (will be URL-encoded)

        Returns:
            Full Gmail search URL

        Side Effects:
            None (pure function - builds and encodes URL string only)
        """
        encoded_query = quote_plus(query)
        return f"{cls.BASE_URL}/#search/{encoded_query}"

    @classmethod
    def category_search_link(cls, category: str, days: int | None = None) -> str:
        """
        Build Gmail search link for a category.

        Args:
            category: Category name (Personal, Money, Events, etc.)
            days: Number of days to look back (optional, None = no time filter)

        Returns:
            Full Gmail search URL for category (empty string if category unknown)

        Side Effects:
            - Logs warning if category is unknown (fallback to sanitized label)
        """
        label_query = cls.CATEGORY_LABEL_MAP.get(category)

        # Edge case: unknown category
        if not label_query:
            logger.warning("Unknown category '%s' - cannot build Gmail link", category)
            sanitized = category.replace(" & ", "-").replace(" ", "-")
            label_query = f"label:MailQ-{sanitized}"
            logger.info("Trying fallback: %s", label_query)

        # Add time filter only if specified
        if days:
            query = f"{label_query} is:unread newer_than:{days}d"
        else:
            query = f"{label_query} is:unread"

        return cls.search_link(query)

    @classmethod
    def unfeatured_items_link(cls, hours: int = 48) -> str:
        """
        Build Gmail search link for unfeatured items from last N hours.

        This helps users explore items that weren't featured in the digest.

        Args:
            hours: Number of hours to look back (default 48)

        Returns:
            Full Gmail search URL

        Side Effects:
            None (pure function - builds URL string only)
        """
        # Convert hours to days for Gmail query
        days = max(1, hours // 24)

        # Search for any MailQ-labeled items from last N days (4-label system)
        query = (
            "("
            "label:MailQ-Receipts OR label:MailQ-Messages OR "
            "label:MailQ-Action-Required OR label:MailQ-Everything-Else"
            f") newer_than:{days}d"
        )

        return cls.search_link(query)

    @classmethod
    def earlier_threads_link(cls, days: int = 7) -> str:
        """
        Build Gmail search link for older tracked threads.

        Args:
            days: Minimum age in days (default 7)

        Returns:
            Full Gmail search URL

        Side Effects:
            None (pure function - builds URL string only)
        """
        # Search for MailQ-labeled items older than N days (4-label system)
        query = (
            "("
            "label:MailQ-Receipts OR label:MailQ-Messages OR "
            "label:MailQ-Action-Required OR label:MailQ-Everything-Else"
            f") older_than:{days}d"
        )

        return cls.search_link(query)

    @classmethod
    def action_required_link(cls, days: int = 7) -> str:
        """
        Build Gmail search link for action-required items.

        Args:
            days: Number of days to look back (default 7)

        Returns:
            Full Gmail search URL

        Side Effects:
            None (pure function - builds URL string only)
        """
        query = f"label:MailQ-Action-Required newer_than:{days}d"
        return cls.search_link(query)

    # Client label mappings (from TAXONOMY.md)
    CLIENT_LABEL_MAP: dict[str, str] = {
        "action-required": "MailQ/Action-Required",
        "receipts": "MailQ/Receipts",
        "messages": "MailQ/Messages",
        "everything-else": "MailQ/Everything-Else",
    }

    @classmethod
    def client_label_link(cls, client_label: str) -> str:
        """
        Build Gmail deep link to a client label (user-facing label).

        Args:
            client_label: One of 'action-required', 'receipts', 'messages', 'everything-else'

        Returns:
            Full Gmail label URL

        Side Effects:
            None (pure function - builds URL string only)
        """
        label_name = cls.CLIENT_LABEL_MAP.get(client_label, f"MailQ/{client_label}")
        # Gmail label URLs use #label/ with URL-encoded label name
        # Slashes in label names become %2F
        encoded_label = quote_plus(label_name)
        return f"{cls.BASE_URL}/#label/{encoded_label}"

    @classmethod
    def build_client_label_links(cls) -> dict[str, str]:
        """
        Build all client label deep links for digest footer.

        Returns:
            Dict mapping client label names to Gmail URLs

        Side Effects:
            None (pure function - builds dict of URL strings only)
        """
        return {label: cls.client_label_link(label) for label in cls.CLIENT_LABEL_MAP}

    @classmethod
    def render_label_summary_prose(cls, label_counts: dict[str, int] | None) -> str:
        """
        Render label counts as prose sentence with Gmail deep links.

        This is the single source of truth for footer label summary formatting.
        Used by both digest_stages_v2.py and card_renderer.py.

        Args:
            label_counts: Dict of client label -> count, e.g.
                {"action-required": 2, "receipts": 8, "messages": 3}

        Returns:
            HTML prose with links like "The rest is X receipts..."
            Empty string if no counts or all counts are zero.

        Side Effects:
            None (pure function - builds HTML string from label counts)

        Example:
            >>> GmailLinkBuilder.render_label_summary_prose({"receipts": 8, "messages": 3})
            'The rest is <a href="...">8 receipts</a> and <a href="...">3 messages</a>.'
        """
        import html

        if not label_counts:
            return ""

        total = sum(label_counts.values())
        if total == 0:
            return ""

        # Display names for labels (lowercase, plural for prose)
        label_display_names = {
            "action-required": "action items",
            "receipts": "receipts",
            "messages": "messages",
            "everything-else": "routine notifications",
        }

        # Build label links
        label_links = cls.build_client_label_links()

        # Order: receipts, messages, everything-else (action-required usually in digest body)
        label_order = ["receipts", "messages", "everything-else"]

        linked_terms = []
        for label in label_order:
            count = label_counts.get(label, 0)
            if count > 0:
                link = label_links.get(label, "#")
                display_name = label_display_names.get(label, label)
                # HTML-escape link to prevent XSS in href attribute
                safe_link = html.escape(link, quote=True)
                linked_terms.append(f'<a href="{safe_link}">{count} {display_name}</a>')

        # Build prose sentence
        if not linked_terms:
            return ""
        if len(linked_terms) == 1:
            return f"The rest is {linked_terms[0]}."
        if len(linked_terms) == 2:
            return f"The rest is {linked_terms[0]} and {linked_terms[1]}."
        # Oxford comma style: "a, b, and c"
        return f"The rest is {', '.join(linked_terms[:-1])}, and {linked_terms[-1]}."

    @classmethod
    def render_label_counts_line(cls, label_counts: dict[str, int] | None) -> str:
        """
        Render all label counts as a compact line with Gmail deep links.

        Shows ALL labels (including action-required) to reinforce trust by
        showing the user the full picture of what was processed.

        Args:
            label_counts: Dict of client label -> count

        Returns:
            HTML line like "10 action required · 2 messages · 5 receipts · 10 everything else"
            Empty string if no counts.

        Side Effects:
            None (pure function - builds HTML string from label counts)
        """
        import html

        if not label_counts:
            return ""

        total = sum(label_counts.values())
        if total == 0:
            return ""

        # Display names for labels (compact format)
        label_display_names = {
            "action-required": "action required",
            "messages": "messages",
            "receipts": "receipts",
            "everything-else": "everything else",
        }

        # Build label links
        label_links = cls.build_client_label_links()

        # Order: action-required first (most important), then others
        label_order = ["action-required", "messages", "receipts", "everything-else"]

        linked_terms = []
        for label in label_order:
            count = label_counts.get(label, 0)
            if count > 0:
                link = label_links.get(label, "#")
                display_name = label_display_names.get(label, label)
                safe_link = html.escape(link, quote=True)
                linked_terms.append(f'<a href="{safe_link}">{count} {display_name}</a>')

        if not linked_terms:
            return ""

        # Join with middot separator
        return " · ".join(linked_terms)

    @classmethod
    def render_type_counts_line(cls, type_counts: dict[str, int] | None) -> str:
        """
        Render email type counts as clickable links to Gmail type labels.

        Shows email types (newsletter, notification, receipt, etc.) as links
        that navigate to the corresponding MailQ type label in Gmail.

        Args:
            type_counts: Dict of email type -> count (from noise_summary)

        Returns:
            HTML line like '<a href="...">15 newsletters</a> · <a href="...">12 notifications</a>'
            Empty string if no counts.

        Side Effects:
            None (pure function - builds HTML string from type counts)
        """
        import html
        from urllib.parse import quote

        if not type_counts:
            return ""

        total = sum(type_counts.values())
        if total == 0:
            return ""

        # Display names for types (plural, user-friendly)
        type_display_names = {
            "newsletter": "newsletters",
            "notification": "notifications",
            "receipt": "receipts",
            "promotion": "promotions",
            "message": "messages",
            "event": "events",
            "otp": "one-time codes",
            "shipping": "shipping updates",
            "order": "order updates",
            "other": "other",
        }

        # Map type to Gmail label name (MailQ/Type format with capitalization)
        type_to_gmail_label = {
            "newsletter": "MailQ/Newsletter",
            "notification": "MailQ/Notification",
            "receipt": "MailQ/Receipt",
            "promotion": "MailQ/Promotion",
            "message": "MailQ/Message",
            "event": "MailQ/Event",
            "otp": "MailQ/OTP",
            "shipping": "MailQ/Shipping",
            "order": "MailQ/Order",
            "other": "MailQ/Other",
        }

        # Sort by count descending
        sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])

        terms = []
        for email_type, count in sorted_types:
            if count > 0:
                # Use display name, pluralize if needed
                display_name = type_display_names.get(email_type.lower(), email_type.lower())
                # Handle singular (1 newsletter vs 2 newsletters)
                if count == 1 and display_name.endswith("s"):
                    display_name = display_name[:-1]

                # Build Gmail label URL
                gmail_label = type_to_gmail_label.get(email_type.lower())
                if gmail_label:
                    # URL encode the label (/ becomes %2F)
                    encoded_label = quote(gmail_label, safe="")
                    link = f"https://mail.google.com/mail/u/0/#label/{encoded_label}"
                    safe_link = html.escape(link, quote=True)
                    terms.append(f'<a href="{safe_link}">{count} {display_name}</a>')
                else:
                    # No link for unknown types
                    terms.append(f"{count} {display_name}")

        if not terms:
            return ""

        # Join with middot separator
        return " · ".join(terms)

    @classmethod
    def build_link_for_entity(cls, entity_dict: Mapping[str, str | None]) -> str:
        """
        Build Gmail link for an entity (thread or message).

        Args:
            entity_dict: Entity dict with optional 'thread_id' or 'message_id'

        Returns:
            Gmail URL or empty string if no ID available

        Side Effects:
            None (pure function - builds URL string only)
        """
        thread_id = entity_dict.get("thread_id")
        message_id = entity_dict.get("message_id")

        if thread_id:
            return cls.thread_link(thread_id)
        if message_id:
            return cls.message_link(message_id)
        return ""


def build_thread_link(thread_id: str) -> str:
    """Convenience function for building thread link

    Side Effects:
        None (pure function - delegates to GmailLinkBuilder)
    """
    return GmailLinkBuilder.thread_link(thread_id)


def build_category_link(category: str, days: int = 7) -> str:
    """Convenience function for building category search link

    Side Effects:
        - Logs warning if category is unknown (via GmailLinkBuilder.category_search_link)
    """
    return GmailLinkBuilder.category_search_link(category, days)


def build_exploration_links() -> dict[str, str]:
    """
    Build all exploration links for digest footer.

    Returns:
        Dict with 'unfeatured', 'earlier_threads', 'action_required' keys

    Side Effects:
        None (pure function - builds dict of URL strings only)
    """
    return {
        "unfeatured": GmailLinkBuilder.unfeatured_items_link(hours=48),
        "earlier_threads": GmailLinkBuilder.earlier_threads_link(days=7),
        "action_required": GmailLinkBuilder.action_required_link(days=7),
    }
