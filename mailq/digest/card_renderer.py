"""

from __future__ import annotations

Card Renderer - Render context digest as compact HTML card

Renders:
- Header with date
- Narrative text (with clickable entity links)
- Footer with "Anything still important?" link

Single-screen, mobile-friendly layout.
"""

import html
from datetime import datetime

from mailq.contracts.entities import DigestEntity
from mailq.contracts.synthesis import DigestTimeline
from mailq.gmail.gmail_link_builder import GmailLinkBuilder
from mailq.observability.logging import get_logger

logger = get_logger(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 600px;
            margin: 20px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}

        .context-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .header {{
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin-bottom: 20px;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 12px;
        }}

        .content {{
            font-size: 15px;
            line-height: 1.6;
            color: #444;
        }}

        .content a {{
            color: #0066cc;
            text-decoration: none;
        }}

        .content a:hover {{
            text-decoration: underline;
        }}

        .content div {{
            line-height: 1.3;
        }}

        .content p {{
            margin-bottom: 12px;
        }}

        .footer {{
            margin-top: 24px;
            padding-top: 16px;
            border-top: 1px solid #e0e0e0;
            font-size: 13px;
            color: #999;
            text-align: center;
        }}

        .footer a {{
            color: #999;
            text-decoration: none;
        }}

        .footer a:hover {{
            color: #666;
            text-decoration: underline;
        }}

        .label-summary {{
            margin-bottom: 16px;
            line-height: 1.6;
        }}

        .label-summary a {{
            color: #0066cc;
            text-decoration: underline;
            text-decoration-thickness: 1px;
            text-underline-offset: 2px;
        }}

        .label-summary a:hover {{
            color: #0052a3;
        }}

        .lightning {{
            font-size: 20px;
            margin-right: 8px;
        }}

        .category-summaries {{
            margin-top: 24px;
            padding-top: 20px;
            border-top: 2px solid #f0f0f0;
        }}

        .category-section {{
            margin-bottom: 20px;
        }}

        .category-title {{
            font-size: 16px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 10px;
        }}

        .entity-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}

        .entity-item {{
            margin-bottom: 12px;
            background: #f9f9f9;
            border-radius: 8px;
            padding: 12px 16px;
            border-left: 3px solid #e0e0e0;
        }}

        .entity-item a {{
            color: #0b57d0;
            text-decoration: none;
            font-weight: 600;
        }}

        .entity-item a:hover {{
            text-decoration: underline;
        }}

        .item-number {{
            font-weight: 700;
            margin-right: 8px;
            color: #0b57d0;
        }}

        .item-snippet {{
            margin-top: 6px;
            font-size: 13px;
            color: #555;
        }}

        .item-metadata {{
            margin-top: 4px;
            font-size: 12px;
            color: #7a7a7a;
        }}

        @media (max-width: 600px) {{
            body {{
                margin: 0;
                padding: 12px;
            }}

            .context-card {{
                padding: 16px;
            }}

            .header {{
                font-size: 16px;
            }}

            .content {{
                font-size: 14px;
            }}

            .category-box {{
                padding: 10px 12px;
            }}
        }}
    </style>
</head>
<body>
    <div class="context-card">
        <div class="header">
            {header_title}
        </div>

        <div class="content">{content}</div>

        {category_summaries_section}

        <div class="footer">
            {email_summary_section}
        </div>
    </div>
</body>
</html>
"""


class CardRenderer:
    """Render context digest as HTML card"""

    def __init__(self):
        pass

    @staticmethod
    def format_header(timestamp: datetime) -> str:
        """
        Format digest heading consistently with email subject.

        Args:
            timestamp: Localized datetime for the digest

        Returns:
            Formatted heading string, e.g. "Your Inbox --Tuesday, November 04 at 08:24 AM"
        """
        if timestamp is None:
            timestamp = datetime.now().astimezone()

        if timestamp.tzinfo is None:
            # Assume local timezone if naive
            timestamp = timestamp.astimezone()

        return f"Your Inbox — {timestamp.strftime('%A, %B %d')} at {timestamp.strftime('%I:%M %p')}"

    def render(
        self,
        digest_text: str,
        timeline: DigestTimeline | None = None,
        entities: list[DigestEntity] | None = None,
        time_hours: int = 24,
        current_time: datetime | None = None,
        header_title: str | None = None,
        label_counts: dict[str, int] | None = None,
    ) -> str:
        """
        Render digest as HTML card.

        Args:
            digest_text: Generated narrative text
            timeline: Optional timeline (for entity linking and noise breakdown)
            entities: Optional list of entities (for linking)
            time_hours: Time window in hours for filtering category links (default 24)
            current_time: Optional datetime for header
            header_title: Optional custom header title
            label_counts: Optional dict of client label -> email count for footer,
                e.g. {"receipts": 8, "messages": 3, "everything-else": 10}

        Returns:
            HTML string
        """
        import os

        local_now = current_time or datetime.now().astimezone()
        header_title = header_title or self.format_header(local_now)

        # Process content (add links if entities provided)
        content = digest_text or ""

        # Check if debug mode is enabled
        debug_featured = os.getenv("DEBUG_FEATURED", "false").lower() == "true"

        if entities:
            content = self._add_entity_links(content, entities, debug_hints=debug_featured)

        content_html = self._format_digest_text(content)

        # Check if narrative already contains inline sections (from hybrid renderer)
        # If so, skip adding noise summary and styled sections (prevents duplicates)
        has_inline_sections = any(emoji in content_html for emoji in ["🚨", "📦", "📅", "💼"])

        # Add noise summary if timeline provided AND no inline sections
        # (hybrid renderer includes its own footer)
        if timeline and timeline.noise_breakdown and not has_inline_sections:
            noise_summary = self._render_noise_summary(
                timeline.noise_breakdown, time_hours=time_hours
            )
            content_html += noise_summary

        sections_html = ""
        if entities and not has_inline_sections:
            # Only generate if narrative lacks inline sections (prevents duplicates)
            sections_html = self._build_sections_html(entities)

        # Build email summary footer with client label links
        email_summary_html = self._render_email_summary(label_counts)

        # Render template
        return HTML_TEMPLATE.format(
            header_title=header_title,
            content=content_html,
            category_summaries_section=sections_html,
            email_summary_section=email_summary_html,
        )

    def _add_entity_links(
        self, text: str, entities: list[DigestEntity], debug_hints: bool = False
    ) -> str:
        """
        Add clickable links to entities mentioned in text using numbered references.

        Args:
            text: Narrative text
            entities: List of entities (assumed to be in same order as numbered in prompt)
            debug_hints: If True, append [score, reason] debug hints

        Returns:
            Text with HTML links added
        """

        logger.info("\n🔗 Entity linking: %s entities to link", len(entities))

        # First pass: Replace numbered references (1), (2), (3) with links
        # This is more reliable than fuzzy text matching
        for i, entity in enumerate(entities, start=1):
            # Build Gmail link
            if hasattr(entity, "source_thread_id") and entity.source_thread_id:
                gmail_link = GmailLinkBuilder.thread_link(entity.source_thread_id)
            elif entity.source_email_id:
                gmail_link = GmailLinkBuilder.message_link(entity.source_email_id)
            else:
                gmail_link = GmailLinkBuilder.search_link(f'subject:"{entity.source_subject}"')

            # Check if reference is already linked (from hybrid renderer)
            reference = f"({i})"

            # Skip if already inside an <a> tag (prevents double nesting)
            # Pattern: <a href="...">...(N)</a>
            import re

            if re.search(rf"<a[^>]*>.*?\({i}\)</a>", text):
                logger.info("  ⏭️  %s already linked, skipping", reference)
                continue

            # Replace (1), (2), etc. with clickable link
            link_html = (
                f'<a href="{gmail_link}" target="_blank" '
                f'style="color: #1a73e8; text-decoration: none;">({i})</a>'
            )
            text = text.replace(reference, link_html)
            logger.info("  🔢 %s → %s...", reference, entity.source_subject[:50])

        # DISABLED: Fuzzy fallback linking is no longer needed with numbered references
        # Numbered references (1), (2), (3) provide 100% reliable linking
        # Keeping fuzzy linker causes duplicate links (e.g., "new sign-in" AND "(2)")
        _ = debug_hints  # kept for future extension
        logger.info("\n✅ Entity linking complete using numbered references only")
        return text

    def _format_digest_text(self, text: str) -> str:
        """Convert narrative text into HTML-safe markup with preserved breaks."""
        if not text:
            return ""

        # If content already contains HTML tags (e.g., from hybrid renderer), return as-is
        if "<p" in text or "<div" in text:
            return text

        normalized = text.replace("\r\n", "\n")
        normalized = normalized.strip()

        # Replace blank lines with paragraph spacing
        normalized = normalized.replace("\n\n", "<br><br>")
        return normalized.replace("\n", "<br>")

    def _render_email_summary(self, label_counts: dict[str, int] | None) -> str:
        """
        Render email summary as prose sentence with linked label names.

        Delegates prose generation to GmailLinkBuilder.render_label_summary_prose() for DRY.

        Args:
            label_counts: Dict of client label -> email count, e.g.
                {"receipts": 8, "messages": 3, "everything-else": 10}

        Returns:
            HTML string for email summary section
        """
        # Get label counts from shared helper
        counts_line = GmailLinkBuilder.render_label_counts_line(label_counts)

        # Build HTML: counts line above branding
        html_parts = []

        if counts_line:
            html_parts.append(f'<div class="label-counts">{counts_line}</div>')

        html_parts.append('<div class="footer-brand">MailQ · Settings</div>')

        return "\n".join(html_parts)

    def _build_sections_html(self, entities: list[DigestEntity]) -> str:
        """Render structured sections for critical/time-sensitive/routine entities."""
        if not entities:
            return ""

        section_config = [
            ("critical", "🚨 CRITICAL"),
            ("time_sensitive", "⏰ Coming Up"),
            ("routine", "💼 Worth Knowing"),
        ]

        buckets: dict[str, list[dict]] = {key: [] for key, _ in section_config}

        for index, entity in enumerate(entities, start=1):
            importance = getattr(entity, "importance", "routine")
            section_key = importance if importance in buckets else "routine"

            title = self._entity_display_title(entity)
            snippet = self._entity_display_snippet(entity)
            link = self._entity_link(entity)

            buckets[section_key].append(
                {"number": index, "title": title, "snippet": snippet, "link": link}
            )

        html_parts = ['<div class="category-summaries">']
        added_section = False

        for key, label in section_config:
            items = buckets.get(key, [])
            if not items:
                continue

            added_section = True
            html_parts.append('<div class="category-section">')
            html_parts.append(f'<div class="category-title">{label}</div>')
            html_parts.append('<ul class="entity-list">')

            for item in items:
                number = item["number"]
                title = html.escape(item["title"]) if item["title"] else f"Item {number}"
                snippet_text = html.escape(item["snippet"]) if item["snippet"] else ""
                link = item["link"]

                if link:
                    title_html = f'<a href="{html.escape(link)}" target="_blank">{title}</a>'
                else:
                    title_html = title

                html_parts.append('<li class="entity-item">')
                html_parts.append(f'<span class="item-number">({number})</span> {title_html}')
                if snippet_text:
                    html_parts.append(f'<div class="item-snippet">{snippet_text}</div>')
                html_parts.append("</li>")

            html_parts.append("</ul></div>")

        html_parts.append("</div>")
        if not added_section:
            return ""
        return "\n".join(html_parts)

    def _entity_display_title(self, entity: DigestEntity) -> str:
        """Choose a human-friendly title for an entity."""
        if hasattr(entity, "title") and entity.title:
            return entity.title.strip()
        if hasattr(entity, "from_whom") and entity.from_whom:
            return entity.from_whom.strip()
        if hasattr(entity, "merchant") and entity.merchant:
            return entity.merchant.strip()
        subject = getattr(entity, "source_subject", "") or ""
        if subject:
            return subject.strip()
        return entity.__class__.__name__

    def _entity_display_snippet(self, entity: DigestEntity) -> str:
        """Get a concise snippet for supporting context."""
        snippet = getattr(entity, "source_snippet", "") or ""
        if snippet:
            snippet = snippet.strip()
            if len(snippet) > 140:
                snippet = snippet[:137].rstrip() + "…"
            return snippet

        if hasattr(entity, "message") and entity.message:
            message = entity.message.strip()
            if len(message) > 140:
                message = message[:137].rstrip() + "…"
            return message

        return ""

    def _entity_link(self, entity: DigestEntity) -> str:
        """Build the best Gmail link available for an entity."""
        data = {
            "thread_id": getattr(entity, "source_thread_id", None),
            "message_id": getattr(entity, "source_email_id", None),
        }
        return GmailLinkBuilder.build_link_for_entity(data)

    def _render_noise_summary(self, noise_breakdown: dict[str, int], time_hours: int = 24) -> str:
        """
        Render noise summary section showing categorized routine emails.

        Args:
            noise_breakdown: Dict of category counts {'newsletters': 10, 'promotional': 5, ...}
            time_hours: Time window in hours for filtering links (default 24)

        Returns:
            HTML string for noise summary section
        """
        _ = time_hours
        # Category to Gmail label mapping (4-label system)
        # All noise categories map to MailQ-Everything-Else
        category_to_label = {
            "newsletters": "MailQ-Everything-Else",
            "promotional": "MailQ-Everything-Else",
            "receipts": "MailQ-Receipts",
            "messages": "MailQ-Messages",
            "events": "MailQ-Everything-Else",
            "old_calendar": "MailQ-Everything-Else",
            "subscription_renewal": "MailQ-Everything-Else",
            "social_notifications": "MailQ-Everything-Else",
            "read_receipts": "MailQ-Everything-Else",
            "other": "MailQ-Everything-Else",
        }

        # Group counts by Gmail label (multiple categories can map to same label)
        label_counts = {}
        label_friendly_names = {
            "MailQ-Everything-Else": "everything else",
            "MailQ-Receipts": "receipts",
            "MailQ-Messages": "messages",
            "MailQ-Action-Required": "action items",
        }

        for category, count in noise_breakdown.items():
            label = category_to_label.get(category, "MailQ-Everything-Else")

            # Skip compound queries for now (they're for "other" category)
            if " OR " in label:
                # For "other", add to Everything-Else
                label = "MailQ-Everything-Else"

            if label not in label_counts:
                label_counts[label] = 0
            label_counts[label] += count

        # Calculate total
        total = sum(label_counts.values())

        if total == 0:
            return ""

        # Build category lines
        category_lines = []
        for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
            if count == 0:
                continue

            friendly_name = label_friendly_names.get(label, label.replace("MailQ-", "").lower())

            # Create Gmail search link to show ALL emails with this label
            # Note: We show ALL emails (not just recent or unread) to allow
            # viewing full history. IMPORTANT: Use in:anywhere to include
            # archived emails (MailQ archives after organizing).
            # Excludes trash and spam by default (Gmail's standard behavior)
            if " OR " in label:
                # Handle compound queries (legacy support)
                # Build proper Gmail search with parentheses
                from urllib.parse import quote_plus

                label_parts = label.split(" OR ")
                label_query = (
                    "(" + " OR ".join(f"label:{part.strip()}" for part in label_parts) + ")"
                )
                search_query = f"{label_query} in:anywhere -in:trash -in:spam"
                gmail_link = f"https://mail.google.com/mail/u/0/#search/{quote_plus(search_query)}"
            elif label.startswith("MailQ-"):
                from urllib.parse import quote_plus

                search_query = f"label:{label} in:anywhere -in:trash -in:spam"
                gmail_link = f"https://mail.google.com/mail/u/0/#search/{quote_plus(search_query)}"
            else:
                # Generic query (shouldn't happen with current categories)
                gmail_link = f"https://mail.google.com/mail/u/0/#search/{label}"

            category_lines.append(f'<a href="{gmail_link}">{count} {friendly_name}</a>')

        # Format as paragraph
        if len(category_lines) == 1:
            categories_text = category_lines[0]
        elif len(category_lines) == 2:
            categories_text = f"{category_lines[0]} and {category_lines[1]}"
        else:
            # Join with commas and "and" for the last one
            categories_text = ", ".join(category_lines[:-1]) + f", and {category_lines[-1]}"

        # Build summary text without specific time window
        # (emails are from inbox regardless of age - some may be fresh, some may be older)
        separator = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        return (
            f"{separator}\n\nOtherwise, there are {total} low-priority emails "
            f"in your inbox: {categories_text}."
        )

    def _render_orphaned_time_sensitive(self, orphaned_emails: list[dict]) -> str:
        """
        Render time-sensitive emails that failed entity extraction.

        Args:
            orphaned_emails: List of time-sensitive emails without entities

        Returns:
            HTML string for orphaned emails section
        """
        if not orphaned_emails:
            return ""

        # Build list of orphaned emails with Gmail links
        lines = []
        for email in orphaned_emails:
            subject = email.get("subject", "No subject")
            email.get("snippet", "")[:80]  # First 80 chars
            thread_id = email.get("thread_id", email.get("id", ""))

            # Create Gmail link to full thread conversation
            if thread_id:
                gmail_link = GmailLinkBuilder.thread_link(thread_id)
                # Show subject as link
                line = f'<a href="{gmail_link}">{subject}</a>'
            else:
                line = subject

            lines.append(f"- {line}")

        # Format as section
        return "\n\nAlso time-sensitive:\n" + "\n".join(lines)

    def render_to_file(
        self,
        digest_text: str,
        output_path: str,
        timeline: DigestTimeline | None = None,
        entities: list[DigestEntity] | None = None,
    ) -> None:
        """
        Render and save to HTML file.

        Args:
            digest_text: Generated narrative
            output_path: Path to save HTML file
            timeline: Optional timeline
            entities: Optional entities
        """
        html = self.render(digest_text, timeline, entities)

        with open(output_path, "w") as f:
            f.write(html)

        logger.info("Rendered digest saved to: %s", output_path)


def render_card(digest_text: str, entities: list[DigestEntity] | None = None) -> str:
    """
    Convenience function to render card.

    Args:
        digest_text: Generated narrative
        entities: Optional entities for linking

    Returns:
        HTML string
    """
    renderer = CardRenderer()
    return renderer.render(digest_text, entities=entities)
