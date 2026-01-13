"""
Synthesis and Rendering Stage for Digest Pipeline.

Renders digest HTML with Gmail links, section grouping, and styled output.
Extracted from digest_stages_v2.py to reduce file size.
"""

from __future__ import annotations

import html as html_lib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mailq.contracts.entities import DigestEntity
from mailq.digest.digest_pipeline import DigestContext, StageResult
from mailq.digest.llm_synthesis import (
    USE_RAW_DIGEST,
    generate_llm_digest_synthesis,
    generate_noise_narrative,
    generate_raw_llm_digest,
)
from mailq.gmail.gmail_link_builder import GmailLinkBuilder
from mailq.observability.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# CSS template for digest HTML (golden digest style)
DIGEST_CSS = """
        body {
            font-family: "Charter", "Bitstream Charter", "Sitka Text", Cambria, serif;
            font-size: 16px;
            line-height: 1.15;
            color: #2c2c2c;
            max-width: 680px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #ffffff;
        }
        .greeting {
            margin-bottom: 32px;
            color: #4a4a4a;
        }
        .section {
            margin-bottom: 28px;
        }
        .section-content {
            margin-bottom: 14px;
        }
        .item-number {
            display: inline;
        }
        a {
            color: #0066cc;
            text-decoration: underline;
            text-decoration-thickness: 1px;
            text-underline-offset: 2px;
        }
        a:hover {
            color: #0052a3;
        }
        .footer {
            margin-top: 48px;
            padding-top: 24px;
            border-top: 1px solid #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            color: #999;
            text-align: center;
        }
        .label-counts {
            margin-bottom: 12px;
            font-size: 14px;
            color: #666;
        }
        .label-counts a {
            color: #666;
            text-decoration: none;
        }
        .label-counts a:hover {
            color: #333;
            text-decoration: underline;
        }
        .footer-brand {
            color: #999;
        }
        .footer-brand a {
            color: #999;
            text-decoration: none;
        }
        .footer-brand a:hover {
            color: #666;
            text-decoration: underline;
        }
"""


def wrap_digest_html(content_parts: list[str], type_counts: dict[str, int] | None = None) -> str:
    """
    Wrap content in HTML document with golden digest CSS.

    Args:
        content_parts: List of HTML content strings
        type_counts: Optional dict of email type -> count for footer (e.g., {"newsletter": 10})

    Returns:
        Complete HTML document string
    """
    content = "\n".join(content_parts)

    # Build footer with email type breakdown (not Gmail labels)
    type_counts_html = ""
    if type_counts:
        counts_line = GmailLinkBuilder.render_type_counts_line(type_counts)
        if counts_line:
            type_counts_html = f'<div class="label-counts">{counts_line}</div>'

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{DIGEST_CSS}
    </style>
</head>
<body>
{content}
<div class="footer">
    {type_counts_html}
    <div class="footer-brand">MailQ · <a href="#">Settings</a></div>
</div>
</body>
</html>"""


@dataclass
class SynthesisAndRenderingStage:
    """
    Synthesize timeline and render rich HTML with Gmail links.

    Uses hybrid_digest_renderer for production-quality output:
    - Grouped items by section (critical, today, coming_up, worth_knowing)
    - Gmail archive links via GmailLinkBuilder
    - HTML-escaped user content (XSS prevention)
    - Noise summary

    Dependencies: enrichment

    Side Effects: (P2)
        - Sets context.digest_html (full HTML document)
    """

    name: str = "synthesis_and_rendering"
    depends_on: list[str] = field(default_factory=lambda: ["enrichment"])

    def process(self, context: DigestContext) -> StageResult:
        """
        Render digest with rich HTML and Gmail links.

        Side Effects:
            - Sets context.digest_html (HTML string)
            - Uses html.escape for all user content (XSS prevention)
            - Logs rendering completion
        """
        # RAW DIGEST MODE: Bypass all classification/section logic
        # Enable via: request param raw_digest=true OR env var MAILQ_RAW_DIGEST=true
        use_raw = context.raw_digest or USE_RAW_DIGEST
        if use_raw:
            logger.info(
                f"Raw digest mode enabled (request={context.raw_digest}, "
                f"env={USE_RAW_DIGEST}), processing {len(context.emails)} emails"
            )
            type_counts = self._compute_type_counts(context.emails)
            raw_html = generate_raw_llm_digest(context, context.emails)
            if raw_html:
                context.digest_html = wrap_digest_html([raw_html], type_counts=type_counts)
                logger.info(f"Raw digest rendered: {len(context.emails)} emails")
                return StageResult(
                    success=True,
                    stage_name=self.name,
                    items_processed=len(context.emails),
                    items_output=1,
                    metadata={"renderer": "raw_llm", "email_count": len(context.emails)},
                )
            logger.warning("Raw digest generation failed, falling back to standard pipeline")

        # Group items by T1 section
        items_by_section: dict[str, list[Any]] = {
            "critical": [],
            "today": [],
            "coming_up": [],
            "worth_knowing": [],
        }

        for item in context.featured_items:
            if isinstance(item, DigestEntity):
                item_email_id = item.source_email_id
            else:
                item_email_id = item.get("id", item.get("thread_id", "unknown"))

            section = context.section_assignments.get(item_email_id, "worth_knowing")
            if section in items_by_section:
                items_by_section[section].append(item)

        # Collect noise emails for LLM synthesis
        noise_emails = []
        for email in context.emails:
            email_id = email.get("id", email.get("thread_id", "unknown"))
            section = context.section_assignments.get(email_id, "")
            if section == "noise":
                noise_emails.append(email)

        # Use noise_summary for footer (email types, not Gmail labels)
        type_counts = context.noise_summary

        # Check if all featured sections are empty
        total_featured = sum(len(items) for items in items_by_section.values())

        if total_featured == 0 and (noise_emails or context.noise_summary):
            # No urgent/featured items - generate a noise narrative instead
            logger.info(
                f"No featured items, generating noise narrative "
                f"(noise_summary: {context.noise_summary}, noise_emails: {len(noise_emails)})"
            )
            noise_html = generate_noise_narrative(context, context.noise_summary, noise_emails)
            if noise_html:
                # Include greeting if available
                greeting = getattr(context, "greeting", "")
                content_parts = []
                if greeting:
                    content_parts.append(f'<div class="greeting">{html_lib.escape(greeting)}</div>')
                content_parts.append(noise_html)

                context.digest_html = wrap_digest_html(content_parts, type_counts=type_counts)
                logger.info(
                    f"Rendered digest via noise narrative: {len(noise_emails)} routine emails"
                )
                return StageResult(
                    success=True,
                    stage_name=self.name,
                    items_processed=len(noise_emails),
                    items_output=1,
                    metadata={"renderer": "noise_narrative", "noise_count": len(noise_emails)},
                )

        # Try LLM synthesis first (feature-flagged)
        llm_html = generate_llm_digest_synthesis(context, items_by_section, noise_emails)
        if llm_html:
            context.digest_html = wrap_digest_html([llm_html], type_counts=type_counts)
            total_items = sum(len(items) for items in items_by_section.values())
            logger.info(f"Rendered digest via LLM synthesis: {total_items} featured items")
            return StageResult(
                success=True,
                stage_name=self.name,
                items_processed=len(context.featured_items),
                items_output=1,
                metadata={"renderer": "llm_synthesis", "items_rendered": total_items},
            )

        # Fallback: deterministic template rendering
        html_parts = self._render_deterministic(context, items_by_section)

        # Wrap in HTML document with CSS
        context.digest_html = wrap_digest_html(html_parts, type_counts=type_counts)

        item_count = sum(len(items) for items in items_by_section.values())
        logger.info(f"Rendered digest: {len(context.featured_items)} items, {item_count} linked")

        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(context.featured_items),
            items_output=1,
            metadata={"items_rendered": item_count},
        )

    def _render_deterministic(
        self, context: DigestContext, items_by_section: dict[str, list[Any]]
    ) -> list[str]:
        """
        Render deterministic HTML content (fallback when LLM disabled).

        Args:
            context: DigestContext with greeting and noise_summary
            items_by_section: Dict mapping section names to item lists

        Returns:
            List of HTML content strings
        """
        html_parts = []

        # Greeting
        greeting = getattr(context, "greeting", "")
        if greeting:
            html_parts.append(f'<div class="greeting">{html_lib.escape(greeting)}</div>')

        # Section rendering - combine critical + today into "Today/Urgent"
        combined_sections = [
            (["critical", "today"], "**Today/Urgent**"),
            (["coming_up"], "**Coming Up**"),
            (["worth_knowing"], "**Worth Knowing**"),
        ]

        item_number = 1
        for section_keys, section_header in combined_sections:
            items = []
            for key in section_keys:
                items.extend(items_by_section.get(key, []))
            if not items:
                continue

            html_parts.append('<div class="section">')
            html_parts.append(f'<p class="section-content">{section_header}</p>')

            for item in items:
                item_html = self._render_item(item, item_number)
                html_parts.append(item_html)
                item_number += 1

            html_parts.append("</div>")

        # Noise summary section
        if context.noise_summary:
            html_parts.append("<br>")
            html_parts.append('<div class="section">')
            noise_items = [f"{count} {cat}" for cat, count in context.noise_summary.items()]
            noise_text = ", ".join(noise_items)
            html_parts.append(f'<div class="section-content">You also have: {noise_text}.</div>')
            html_parts.append("</div>")

        return html_parts

    def _render_item(self, item: Any, item_number: int) -> str:
        """Render a single item as HTML."""
        if isinstance(item, DigestEntity):
            raw_title = (
                getattr(item, "title", None) or getattr(item, "source_subject", None) or "Untitled"
            )
            title = html_lib.escape(str(raw_title))
            thread_id: str | None = getattr(item, "source_thread_id", None)
            entity_email_id: str | None = getattr(item, "source_email_id", None)
        else:
            title = html_lib.escape(item.get("subject", "Untitled"))
            thread_id = item.get("thread_id")
            entity_email_id = item.get("id")

        # Build Gmail link
        if thread_id:
            gmail_link = GmailLinkBuilder.thread_link(thread_id)
        elif entity_email_id:
            gmail_link = GmailLinkBuilder.message_link(entity_email_id)
        else:
            gmail_link = "#"

        return (
            f'<div class="section-content">'
            f'<span class="item-number">({item_number})</span> '
            f'<a href="{gmail_link}">{title}</a>'
            f"</div>"
        )

    def _compute_label_counts(self, emails: list[dict]) -> dict[str, int]:
        """
        Compute email counts per client label.

        Args:
            emails: List of email dicts with 'client_label' field

        Returns:
            Dict mapping client label to count

        Side Effects:
            - Logs warnings for emails missing client_label or with unknown labels
        """
        counts: dict[str, int] = {
            "action-required": 0,
            "receipts": 0,
            "messages": 0,
            "everything-else": 0,
        }

        missing_label_count = 0
        unknown_label_count = 0
        unknown_labels_seen: set[str] = set()

        for email in emails:
            label = email.get("client_label")
            if label is None:
                classification = email.get("classification", {})
                if isinstance(classification, dict):
                    label = classification.get("client_label")

            if label is None:
                missing_label_count += 1
                label = "everything-else"

            if label in counts:
                counts[label] += 1
            else:
                unknown_label_count += 1
                unknown_labels_seen.add(str(label))
                counts["everything-else"] += 1

        if missing_label_count > 0:
            logger.warning(
                f"Found {missing_label_count}/{len(emails)} emails missing client_label "
                f"(counted as everything-else). Check classification pipeline."
            )

        if unknown_label_count > 0:
            logger.warning(
                f"Found {unknown_label_count} emails with unknown labels: {unknown_labels_seen}. "
                f"Valid labels: {list(counts.keys())}"
            )

        return counts

    def _compute_type_counts(self, emails: list[dict]) -> dict[str, int]:
        """
        Compute email counts per type (newsletter, notification, receipt, etc.).

        Used for footer display when bypassing the normal pipeline (raw digest mode).

        Args:
            emails: List of email dicts with 'type' field

        Returns:
            Dict mapping email type to count

        Side Effects:
            None (pure function - computes counts only)
        """
        counts: dict[str, int] = {}

        for email in emails:
            email_type = email.get("type", "other")
            if email_type is None:
                email_type = "other"
            email_type = email_type.lower()
            counts[email_type] = counts.get(email_type, 0) + 1

        return counts
