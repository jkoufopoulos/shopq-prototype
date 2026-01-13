"""
LLM-based Digest Synthesis

Generates editorial-quality digest HTML using Gemini.
Extracted from digest_stages_v2.py to reduce file size.

The LLM synthesis creates prose-style summaries matching the golden digest style:
- Consolidation of similar items
- Short, meaningful link text
- Conversational tone
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from mailq.contracts.entities import DigestEntity
from mailq.gmail.gmail_link_builder import GmailLinkBuilder
from mailq.observability.logging import get_logger
from mailq.utils.redaction import sanitize_for_prompt

if TYPE_CHECKING:
    from mailq.digest.digest_pipeline import DigestContext

logger = get_logger(__name__)

# Feature flag for LLM digest generation
USE_LLM_SYNTHESIS = os.getenv("MAILQ_LLM_SYNTHESIS", "true").lower() == "true"

# Feature flag for raw LLM digest (bypasses all classification/section logic)
USE_RAW_DIGEST = os.getenv("MAILQ_RAW_DIGEST", "false").lower() == "true"


def _replace_link_placeholders(html_content: str) -> str:
    """
    Replace [[ID|text]] placeholders with proper <a href> links.

    The LLM outputs placeholders like [[19ae69570871f78e|Experian statement]]
    which we convert to clickable Gmail links.

    Gmail IDs are hex strings (alphanumeric), not just digits.
    This ensures links are always correct (deterministic) regardless of LLM behavior.

    The link text can contain brackets (e.g., "[P+S] Potluck"), so we match
    greedily up to the closing ]] instead of stopping at the first ].
    """
    pattern = r"\[\[([a-zA-Z0-9]+)\|(.+?)\]\]"

    def replacer(match: re.Match) -> str:
        email_id = match.group(1)
        link_text = match.group(2)
        gmail_link = GmailLinkBuilder.message_link(email_id)
        return f'<a href="{gmail_link}">{link_text}</a>'

    return re.sub(pattern, replacer, html_content)


def _strip_dismissive_lines(html_content: str) -> str:
    """
    Remove "The rest is..." dismissive lines from LLM output.

    The footer now handles label counts automatically, so we strip these
    generic lines that the LLM may still generate despite prompt updates.

    Patterns removed:
    - "The rest is receipts, delivery updates, and routine notifications."
    - "The rest is <a href=...>receipts</a>..."
    - Any "The rest is..." sentence with or without links
    """
    # Pattern matches "The rest is" followed by anything until end of sentence/tag
    # Handles both plain text and HTML with <a> tags
    patterns = [
        # Full div containing just "The rest is..." (standalone section)
        r'<div class="section-content">\s*The rest is[^<]*(?:<a[^>]*>[^<]*</a>[^<]*)*\.\s*</div>',
        # Just the sentence itself (within a larger section)
        r"The rest is[^<.]*(?:<a[^>]*>[^<]*</a>[^<.]*)*\.",
    ]

    for pattern in patterns:
        html_content = re.sub(pattern, "", html_content, flags=re.IGNORECASE)

    # Clean up any empty sections or sections with only whitespace
    html_content = re.sub(
        r'<div class="section">\s*(<div class="section-content">\s*</div>\s*)*</div>',
        "",
        html_content,
    )
    html_content = re.sub(
        r'<div class="section">\s*\n*\s*</div>',
        "",
        html_content,
    )

    # Clean up any trailing whitespace or extra line breaks before footer
    html_content = re.sub(r"\n\s*\n+", "\n\n", html_content)
    html_content = re.sub(r"<br>\s*\n*\s*(<div class=\"footer\"|$)", r"\1", html_content)

    return html_content.strip()


def generate_llm_digest_synthesis(
    context: DigestContext,
    items_by_section: dict[str, list[Any]],
    noise_emails: list[dict[str, Any]],
) -> str | None:
    """
    Generate full digest HTML using LLM synthesis.

    This uses the digest_synthesis_prompt to generate editorial-quality output
    matching the golden digest style: consolidation, short link text, prose summaries.

    Args:
        context: DigestContext with now, greeting, weather, user_name
        items_by_section: Dict mapping section names to lists of items
        noise_emails: List of noise/routine emails for summary

    Returns:
        HTML content string (inner body, not full document), or None if LLM fails

    Side Effects:
        - Calls external LLM API (Gemini)
        - Logs LLM call results
    """
    if not USE_LLM_SYNTHESIS:
        return None

    try:
        from pathlib import Path

        import vertexai
        from vertexai.generative_models import GenerativeModel

        # Initialize Vertex AI
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "mailq-467118")
        location = os.getenv("GEMINI_LOCATION", "us-central1")
        vertexai.init(project=project, location=location)

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        logger.info(f"LLM digest synthesis using model: {model_name}")
        model = GenerativeModel(model_name)

        # Load prompt template (v2 is more opinionated about prioritization)
        prompt_version = os.getenv("MAILQ_SYNTHESIS_PROMPT", "v2")
        if prompt_version == "v1":
            prompt_file = "digest_synthesis_prompt.txt"
        else:
            prompt_file = "digest_synthesis_prompt_v2.txt"
        prompt_path = Path(__file__).parent.parent / "llm" / "prompts" / prompt_file
        prompt_template = prompt_path.read_text()

        # Build context section
        user_name = getattr(context, "user_name", "") or "there"
        weather = getattr(context, "weather", {}) or {}
        now = context.now
        # Get pre-generated greeting (includes correct time of day)
        greeting = getattr(context, "greeting", "")

        temp = weather.get("temp", "N/A")
        condition = weather.get("condition", "N/A")
        city = weather.get("city", "N/A")
        date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

        context_section = f"""## User Context
- Name: {user_name}
- Current date/time: {date_str}
- Weather: {temp}°F, {condition} in {city}
- **GREETING (use exactly as written):** {greeting}
"""

        # Build emails by section
        def format_email_for_prompt(item: Any, section_name: str = "") -> str:
            """Format a single email/entity for the prompt with temporal context."""
            if isinstance(item, DigestEntity):
                subject = (
                    getattr(item, "source_subject", "") or getattr(item, "title", "") or "Untitled"
                )
                sender = getattr(item, "source_from", "") or ""
                snippet = getattr(item, "source_snippet", "") or ""
                thread_id = getattr(item, "source_thread_id", None)
                email_id = getattr(item, "source_email_id", None)
                # Extract temporal info from entity
                event_time = getattr(item, "event_time", None)
                # event_end_time reserved for future duration display
            else:
                subject = item.get("subject", "Untitled")
                sender = item.get("from", "")
                snippet = item.get("snippet", "")[:150]
                thread_id = item.get("thread_id")
                email_id = item.get("id")
                # Check temporal context attached to email
                temporal_ctx = item.get("temporal_context", {})
                event_time = temporal_ctx.get("event_time") if temporal_ctx else None
                # event_end_time reserved for future duration display

            # Build Gmail link
            if thread_id:
                gmail_link = GmailLinkBuilder.thread_link(thread_id)
            elif email_id:
                gmail_link = GmailLinkBuilder.message_link(email_id)
            else:
                gmail_link = "#"

            # Sanitize for prompt
            subject = sanitize_for_prompt(subject, 150)
            sender = sanitize_for_prompt(sender.split("<")[0].strip().strip('"'), 50)
            snippet = sanitize_for_prompt(snippet, 150)

            # Build temporal context string for LLM
            temporal_str = ""
            if event_time:
                try:
                    # Parse if string, or use directly if datetime
                    if isinstance(event_time, str):
                        from datetime import datetime as dt

                        event_dt = dt.fromisoformat(event_time.replace("Z", "+00:00"))
                    else:
                        event_dt = event_time

                    # Convert event_dt to user's timezone for display and comparison
                    # event_dt is stored in UTC, now is in user's local timezone
                    if now.tzinfo is not None and event_dt.tzinfo is not None:
                        event_dt_local = event_dt.astimezone(now.tzinfo)
                    else:
                        event_dt_local = event_dt

                    # Format relative to today (both now in same timezone)
                    if event_dt_local.date() == now.date():
                        time_str = event_dt_local.strftime("%I:%M %p").lstrip("0")
                        temporal_str = f"  **Event: TODAY at {time_str}**\n"
                    elif event_dt_local.date() == (now + timedelta(days=1)).date():
                        time_str = event_dt_local.strftime("%I:%M %p").lstrip("0")
                        temporal_str = f"  Event: Tomorrow at {time_str}\n"
                    else:
                        date_str = event_dt_local.strftime("%a, %b %d at %I:%M %p").lstrip("0")
                        temporal_str = f"  Event: {date_str}\n"
                except Exception:
                    pass  # Skip temporal string on parse error

            # Add section enforcement hint
            section_hint = ""
            if section_name in ("critical", "today"):
                section_hint = "  [MUST appear in Today/Urgent section]\n"

            return (
                f"- Subject: {subject}\n"
                f"  From: {sender}\n"
                f"  Preview: {snippet}\n"
                f"{temporal_str}"
                f"{section_hint}"
                f"  Gmail Link: {gmail_link}"
            )

        emails_section = "## Emails by Section\n\n"

        # Today/Urgent (critical + today)
        today_items = items_by_section.get("critical", []) + items_by_section.get("today", [])
        emails_section += "### Today/Urgent\n"
        emails_section += (
            "**IMPORTANT: All items listed here MUST appear in the "
            "Today/Urgent section of your output.**\n"
        )
        if today_items:
            for item in today_items:
                emails_section += format_email_for_prompt(item, section_name="today") + "\n"
        else:
            emails_section += "(No items - schedule is clear)\n"
        emails_section += "\n"

        # Coming Up
        coming_up_items = items_by_section.get("coming_up", [])
        emails_section += "### Coming Up\n"
        if coming_up_items:
            for item in coming_up_items:
                emails_section += format_email_for_prompt(item, section_name="coming_up") + "\n"
        else:
            emails_section += "(No items)\n"
        emails_section += "\n"

        # Worth Knowing
        worth_knowing_items = items_by_section.get("worth_knowing", [])
        emails_section += "### Worth Knowing\n"
        if worth_knowing_items:
            for item in worth_knowing_items:
                emails_section += format_email_for_prompt(item, section_name="worth_knowing") + "\n"
        else:
            emails_section += "(No items)\n"
        emails_section += "\n"

        # Newsletters only for "worth reading" in summary (not deliveries/payments)
        # Filter to just newsletter types to avoid LLM including delivery recaps
        newsletter_types = {"newsletter", "update", "marketing"}
        newsletters = [e for e in noise_emails if e.get("type", "") in newsletter_types]

        emails_section += "### Newsletters (for 'worth reading' in summary)\n"
        if newsletters:
            for email in newsletters[:10]:  # Max 10 newsletters
                subject = sanitize_for_prompt(email.get("subject", ""), 100)
                sender = sanitize_for_prompt(
                    email.get("from", "").split("<")[0].strip().strip('"'), 50
                )
                snippet = sanitize_for_prompt(email.get("snippet", "")[:100], 100)
                thread_id = email.get("thread_id")
                email_id = email.get("id")

                if thread_id:
                    gmail_link = GmailLinkBuilder.thread_link(thread_id)
                elif email_id:
                    gmail_link = GmailLinkBuilder.message_link(email_id)
                else:
                    gmail_link = "#"

                emails_section += (
                    f"- {subject}\n"
                    f"  From: {sender}\n"
                    f"  Preview: {snippet}\n"
                    f"  Gmail Link: {gmail_link}\n"
                )
        else:
            emails_section += "(No newsletters - just use dismissive line)\n"

        emails_section += (
            "\nNote: Other noise emails (deliveries, payments, receipts) "
            "are handled by the dismissive summary line. Do NOT list them.\n"
        )

        # Combine prompt
        full_prompt = (
            f"{prompt_template}\n\n{context_section}\n{emails_section}\n\n"
            "Generate the digest HTML content now:"
        )

        response = model.generate_content(full_prompt)
        html_content = response.text.strip()

        # Clean up any markdown code blocks the LLM might add
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.startswith("```"):
            html_content = html_content[3:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
        html_content = html_content.strip()

        # Post-process: Replace [[ID|text]] placeholders with actual <a href> links
        html_content = _replace_link_placeholders(html_content)

        # Post-process: Remove "The rest is..." dismissive lines (footer handles this)
        html_content = _strip_dismissive_lines(html_content)

        logger.info(f"LLM digest synthesis generated: {len(html_content)} chars")
        return html_content

    except Exception as e:
        logger.exception(f"LLM digest synthesis failed: {e}")  # Full traceback for debugging
        return None


def generate_noise_narrative(
    context: DigestContext,
    noise_summary: dict[str, int],
    noise_emails: list[dict[str, Any]],
) -> str | None:
    """
    Generate a narrative summary when inbox has no urgent items.

    This is used when the digest has no critical, today, coming_up, or worth_knowing
    items—just routine noise. Creates a friendly summary highlighting 1-3 notable
    emails from the routine pile.

    Args:
        context: DigestContext with now, greeting, weather, user_name
        noise_summary: Dict mapping email types to counts (e.g., {"receipt": 10, "newsletter": 5})
        noise_emails: List of noise/routine emails with full details

    Returns:
        HTML content string for the narrative section, or None if LLM fails

    Side Effects:
        - Calls external LLM API (Gemini)
        - Logs LLM call results
    """
    if not USE_LLM_SYNTHESIS:
        return None

    if not noise_summary and not noise_emails:
        return None

    try:
        from pathlib import Path

        import vertexai
        from vertexai.generative_models import GenerativeModel

        # Initialize Vertex AI
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "mailq-467118")
        location = os.getenv("GEMINI_LOCATION", "us-central1")
        vertexai.init(project=project, location=location)

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        logger.info(f"Noise narrative synthesis using model: {model_name}")
        model = GenerativeModel(model_name)

        # Load prompt template
        prompt_path = (
            Path(__file__).parent.parent / "llm" / "prompts" / "noise_narrative_prompt.txt"
        )
        prompt_template = prompt_path.read_text()

        # Build context section
        user_name = getattr(context, "user_name", "") or "there"
        now = context.now
        date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

        context_section = f"""## User Context
- Name: {user_name}
- Current date/time: {date_str}
"""

        # Build noise summary
        summary_section = "## Noise Summary (by type)\n"
        total_count = sum(noise_summary.values()) if noise_summary else len(noise_emails)
        if noise_summary:
            for email_type, count in sorted(noise_summary.items(), key=lambda x: -x[1]):
                summary_section += f"- {email_type}: {count}\n"
        summary_section += f"\nTotal routine emails: {total_count}\n"

        # Build sample emails section (top 10 most recent)
        samples_section = "## Sample Emails (most recent)\n"
        # Sort by date if available, else just take first 10
        sorted_emails = sorted(
            noise_emails,
            key=lambda e: e.get("date", e.get("internalDate", "")),
            reverse=True,
        )[:10]

        for email in sorted_emails:
            subject = sanitize_for_prompt(email.get("subject", ""), 100)
            sender = sanitize_for_prompt(email.get("from", "").split("<")[0].strip().strip('"'), 50)
            email_type = email.get("type", "notification")
            snippet = sanitize_for_prompt(email.get("snippet", "")[:100], 100)
            thread_id = email.get("thread_id")
            email_id = email.get("id")

            if thread_id:
                gmail_link = GmailLinkBuilder.thread_link(thread_id)
            elif email_id:
                gmail_link = GmailLinkBuilder.message_link(email_id)
            else:
                gmail_link = "#"

            samples_section += (
                f"- Subject: {subject}\n"
                f"  From: {sender}\n"
                f"  Type: {email_type}\n"
                f"  Preview: {snippet}\n"
                f"  Gmail Link: {gmail_link}\n"
            )

        # Combine prompt
        full_prompt = (
            f"{prompt_template}\n\n{context_section}\n{summary_section}\n"
            f"{samples_section}\n\nGenerate the narrative section HTML now:"
        )

        response = model.generate_content(full_prompt)
        html_content = response.text.strip()

        # Clean up any markdown code blocks
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.startswith("```"):
            html_content = html_content[3:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
        html_content = html_content.strip()

        # Post-process: Replace [[ID|text]] placeholders with actual <a href> links
        html_content = _replace_link_placeholders(html_content)

        logger.info(f"Noise narrative generated: {len(html_content)} chars")
        return html_content

    except Exception as e:
        logger.exception(f"Noise narrative synthesis failed: {e}")
        return None


def generate_raw_llm_digest(
    context: DigestContext,
    emails: list[dict[str, Any]],
) -> str | None:
    """
    Generate digest by feeding ALL emails directly to LLM.

    This bypasses all classification, section assignment, and filtering logic.
    Pure LLM judgment on what matters - useful for A/B testing pipeline value.

    Args:
        context: DigestContext with now, greeting, weather, user_name
        emails: ALL emails from the inbox (no filtering)

    Returns:
        HTML content string (inner body, not full document), or None if LLM fails

    Side Effects:
        - Calls external LLM API (Gemini)
        - Logs LLM call results
    """
    if not emails:
        logger.info("Raw digest: No emails to process")
        return None

    try:
        from pathlib import Path

        import vertexai
        from vertexai.generative_models import GenerativeModel

        # Initialize Vertex AI
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "mailq-467118")
        location = os.getenv("GEMINI_LOCATION", "us-central1")
        vertexai.init(project=project, location=location)

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        logger.info(f"Raw LLM digest using model: {model_name}, emails: {len(emails)}")
        model = GenerativeModel(model_name)

        # Load prompt template
        prompt_path = Path(__file__).parent.parent / "llm" / "prompts" / "digest_raw_prompt.txt"
        prompt_template = prompt_path.read_text()

        # Build context section
        user_name = getattr(context, "user_name", "") or "there"
        weather = getattr(context, "weather", {}) or {}
        now = context.now

        temp = weather.get("temp", "N/A")
        condition = weather.get("condition", "N/A")
        city = weather.get("city", "N/A")
        date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

        context_section = f"""- Name: {user_name}
- Current date/time: {date_str}
- Weather: {temp}F, {condition} in {city}"""

        # Build simple email list - just the essentials
        emails_section = ""
        for email in emails[:50]:  # Cap at 50 to avoid token limits
            email_id = email.get("id", "unknown")
            subject = sanitize_for_prompt(email.get("subject", ""), 150)
            sender = sanitize_for_prompt(email.get("from", "").split("<")[0].strip().strip('"'), 50)
            snippet = sanitize_for_prompt(email.get("snippet", "")[:200], 200)

            emails_section += f"""
- ID: {email_id}
  Subject: {subject}
  From: {sender}
  Preview: {snippet}
"""

        # Build prompt
        full_prompt = prompt_template.replace("{context}", context_section)
        full_prompt = full_prompt.replace("{emails}", emails_section)

        response = model.generate_content(full_prompt)
        html_content = response.text.strip()

        # Clean up any markdown code blocks
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.startswith("```"):
            html_content = html_content[3:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
        html_content = html_content.strip()

        # Post-process: Replace [[ID|text]] placeholders with actual <a href> links
        html_content = _replace_link_placeholders(html_content)

        logger.info(
            f"Raw LLM digest generated: {len(html_content)} chars from {len(emails)} emails"
        )
        return html_content

    except Exception as e:
        logger.exception(f"Raw LLM digest failed: {e}")
        return None
