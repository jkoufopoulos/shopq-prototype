"""

from __future__ import annotations

Context Digest Orchestrator - Main pipeline

Wires together all modules:
1. Extract entities from emails
2. Classify importance
3. Deduplicate entities
4. Build timeline
5. Enrich with weather
6. Generate narrative (LLM)
7. Verify facts
8. Render card

Graceful degradation at every stage.
"""

import os
from datetime import UTC, datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo

from mailq.digest.card_renderer import CardRenderer
from mailq.gmail.gmail_link_builder import GmailLinkBuilder
from mailq.observability.logging import get_logger

logger = get_logger(__name__)


class ContextDigest:
    """Main orchestrator for Context Digest generation"""

    def __init__(self, verbose: bool = False):
        # Check for DEBUG environment variable
        debug_mode = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")
        self.verbose = verbose or debug_mode
        self.debug = debug_mode

        # Initialize fallback renderer (V2 pipeline uses digest_stages_v2.py instead)
        self.renderer = CardRenderer()

    def _log(self, message: str, level: str = "INFO"):
        """
        Log message with level filtering

        Levels:
        - ERROR: Always logged
        - WARN: Always logged
        - INFO: Logged if verbose=True
        - DEBUG: Logged only if DEBUG env var is set
        """
        if level == "ERROR":
            logger.error("[ContextDigest] %s", message)
        elif level == "WARN":
            logger.warning("[ContextDigest] %s", message)
        elif level == "DEBUG":
            if self.debug:
                logger.debug("[ContextDigest] %s", message)
        elif level == "INFO" and self.verbose:
            logger.info("[ContextDigest] %s", message)

    @staticmethod
    def _str_field(value: Any, default: str = "") -> str:
        if value is None:
            return default
        return str(value)

    def _thread_id_from_email(self, email: dict) -> str:
        return self._str_field(email.get("thread_id") or email.get("id") or "")

    def _categorize_routine_by_type(self, emails: list[dict]) -> dict[str, int]:
        """
        Categorize routine emails by Gemini type for the "everything else" summary.

        Uses email.get("type") from Gemini classification directly.
        Groups by thread_id to count conversations, not individual messages.

        Args:
            emails: List of routine emails

        Returns:
            {'newsletters': 15, 'notifications': 3, 'receipts': 2, ...}
        """
        from mailq.shared.constants import get_friendly_type_name

        # Group by thread_id first to count conversations
        thread_to_type: dict[str, str] = {}

        for email in emails:
            thread_id = email.get("thread_id", email.get("id", ""))
            if not thread_id or thread_id in thread_to_type:
                continue

            email_type = email.get("type", "uncategorized")
            friendly_name = get_friendly_type_name(email_type)
            thread_to_type[thread_id] = friendly_name

        # Count by category
        category_counts: dict[str, int] = {}
        for category in thread_to_type.values():
            category_counts[category] = category_counts.get(category, 0) + 1

        return category_counts

    def _categorize_emails_by_importance(self, emails: list[dict]) -> dict[str, list[dict]]:
        """
        Group emails by importance for fallback summary.

        Args:
            emails: List of email dicts with 'importance' field

        Returns:
            {'critical': [...], 'time_sensitive': [...], 'routine': [...]}
        """
        groups: dict[str, list[dict]] = {
            "critical": [],
            "time_sensitive": [],
            "routine": [],
        }
        for email in emails:
            importance = email.get("importance", "routine")
            if importance in groups:
                groups[importance].append(email)
            else:
                groups["routine"].append(email)
        return groups

    def _store_debug_data(
        self, emails: list[dict], entities: list, timeline, importance_groups: dict
    ):
        """Store debug data for /api/debug endpoints"""
        try:
            from mailq.api.routes.debug import set_last_digest

            set_last_digest(
                {
                    "total_ranked": len(entities),
                    "filtered_remaining": len(entities) - len(timeline.featured),
                    "featured": timeline.featured,
                    "all_entities": entities,
                    "importance_groups": importance_groups,
                    "all_emails": emails,
                    "noise_breakdown": timeline.noise_breakdown,
                }
            )

            self._log("✅ Debug data stored for /api/debug endpoints")
        except Exception as e:
            self._log(f"⚠️  Failed to store debug data: {e}")

    def _resolve_current_time(
        self,
        timezone_name: str | None,
        client_now: str | None,
        timezone_offset: int | None,
    ) -> tuple[datetime, str | None]:
        """
        Resolve the best-guess current datetime in the user's timezone.

        Args:
            timezone_name: IANA timezone string from client (e.g., 'America/New_York')
            client_now: ISO timestamp captured on client
            timezone_offset: Offset in minutes from UTC

        Returns:
            Tuple of (localized datetime, resolved timezone string or None)
        """
        resolved_tz = None

        # Validate timezone_offset range to prevent overflow attacks
        # Valid range: -840 (UTC-14) to +840 (UTC+14)
        if timezone_offset is not None and not (-840 <= timezone_offset <= 840):
            self._log(
                f"⚠️  Invalid timezone_offset {timezone_offset} "
                f"(valid range: -840 to +840), ignoring"
            )
            timezone_offset = None

        self._log(
            f"Resolving current time with timezone={timezone_name}, "
            f"offset={timezone_offset}, client_now={client_now}"
        )

        if timezone_name:
            try:
                resolved_tz = timezone_name
                tz: dt_timezone | ZoneInfo = ZoneInfo(timezone_name)

                if client_now:
                    try:
                        candidate = datetime.fromisoformat(client_now.replace("Z", "+00:00"))
                        if candidate.tzinfo is None:
                            candidate = candidate.replace(tzinfo=UTC)
                        resolved_dt = candidate.astimezone(tz)
                        self._log(
                            f"Resolved time via timezone name: "
                            f"{resolved_dt.isoformat()} ({resolved_tz})"
                        )
                        return (resolved_dt, resolved_tz)
                    except ValueError:
                        pass

                resolved_dt = datetime.now(UTC).astimezone(tz)
                self._log(
                    f"Resolved time via timezone name (fallback now): "
                    f"{resolved_dt.isoformat()} ({resolved_tz})"
                )
                return (resolved_dt, resolved_tz)
            except Exception as exc:
                self._log(f"⚠️  Failed to apply client timezone '{timezone_name}': {exc}")
                resolved_tz = None

        if resolved_tz is None and timezone_offset is not None:
            try:
                offset_delta = timedelta(minutes=-timezone_offset)
                tz = dt_timezone(offset_delta)
                total_minutes = abs(timezone_offset)
                hours, minutes = divmod(total_minutes, 60)
                sign = "-" if timezone_offset > 0 else "+"
                resolved_tz = f"UTC{sign}{hours:02d}:{minutes:02d}"

                if client_now:
                    try:
                        candidate = datetime.fromisoformat(client_now.replace("Z", "+00:00"))
                        if candidate.tzinfo is None:
                            candidate = candidate.replace(tzinfo=UTC)
                        resolved_dt = candidate.astimezone(tz)
                        self._log(
                            f"Resolved time via offset: {resolved_dt.isoformat()} ({resolved_tz})"
                        )
                        return (resolved_dt, resolved_tz)
                    except ValueError:
                        pass

                now_utc = datetime.now(UTC)
                resolved_dt = now_utc.astimezone(tz)
                self._log(
                    f"Resolved time via offset (fallback now): "
                    f"{resolved_dt.isoformat()} ({resolved_tz})"
                )
                return (resolved_dt, resolved_tz)
            except Exception as exc:
                self._log(f"⚠️  Failed to apply timezone offset '{timezone_offset}': {exc}")
                resolved_tz = None

        # Fall back to server local timezone aware datetime
        now = datetime.now().astimezone()
        self._log(f"Resolved local time: {now.isoformat()} (timezone={resolved_tz})")
        return (now, resolved_tz)

    def generate(
        self,
        emails: list[dict[str, Any]],
        timezone: str | None = None,
        client_now: str | None = None,
        timezone_offset: int | None = None,
        city_hint: str | None = None,
        region_hint: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        raw_digest: bool = False,
    ) -> dict[str, Any]:
        """
        Generate context digest from emails using V2 pipeline.

        Args:
            emails: List of email dicts with 'id', 'subject', 'snippet', 'type', 'attention'
            timezone: IANA timezone string (e.g., 'America/New_York')
            client_now: ISO timestamp from client
            timezone_offset: UTC offset in minutes
            city_hint: Client city for weather enrichment
            region_hint: Client region/state for weather disambiguation (e.g., 'New York')
            user_id: User ID for applying explicit preferences (optional)
            user_name: User's first name for personalized greeting (optional)
            raw_digest: If True, bypass pipeline and use pure LLM judgment (A/B testing)

        Returns:
            {
                'text': narrative text,
                'html': rendered HTML card,
                'word_count': int,
                'entities_count': int,
                'featured_count': int,
                'noise_breakdown': dict,
                'verified': bool,
                'errors': list (if verification failed)
            }
        """
        # V2 pipeline is now the only pipeline (V1 deleted Nov 2025)
        return self.generate_v2(
            emails=emails,
            timezone=timezone,
            client_now=client_now,
            timezone_offset=timezone_offset,
            city_hint=city_hint,
            region_hint=region_hint,
            user_id=user_id,
            user_name=user_name,
            raw_digest=raw_digest,
        )

    def _fallback_email_based_summary(
        self,
        emails: list[dict],
        importance_groups: dict,
        current_time: datetime | None = None,
        resolved_timezone: str | None = None,
        city_hint: str | None = None,
    ) -> dict:
        """
        Fallback to simple email-based summary if entity extraction fails.

        Args:
            emails: Original emails
            importance_groups: Importance classifications

        Returns:
            Simple digest dict
        """
        self._log("Using fallback email-based summary")

        local_now = current_time or datetime.now().astimezone()
        local_now.strftime("%A, %B %d")

        # Count by importance
        critical = importance_groups.get("critical", [])
        time_sensitive = importance_groups.get("time_sensitive", [])
        routine = importance_groups.get("routine", [])

        # Count featured items for response (critical + time-sensitive emails)
        featured_count = len(critical) + len(time_sensitive)

        # Build summary with structured sections (deterministic, no LLM)
        lines = []

        if len(emails) == 0:
            lines.append("Your inbox is clear!")
        else:
            # Use structured format with emoji sections
            item_number = 1

            # 🚨 CRITICAL section (bills, security alerts, financial)
            if len(critical) > 0:
                # fmt: off
                lines.append('<div style="font-weight: 600; margin-top: 16px; margin-bottom: 2px; color: #d32f2f;">🚨 CRITICAL</div>')  # noqa: E501
                lines.append('<ul style="margin: 0; padding: 0 0 16px 20px; list-style-position: outside; margin-block-start: 0; margin-block-end: 0; padding-inline-start: 20px; line-height: 1.1;">')  # noqa: E501
                # fmt: on
                for email in critical:
                    thread_id = email.get("thread_id", email.get("id", ""))
                    subject = email.get("subject", "No subject")
                    gmail_link = GmailLinkBuilder.thread_link(thread_id)
                    li_style = "margin: 0; padding: 0; line-height: 1.1;"
                    a_style = "color: #1a73e8; text-decoration: none;"
                    lines.append(
                        f'<li style="{li_style}">{subject} '
                        f'<a href="{gmail_link}" target="_blank" style="{a_style}">'
                        f"({item_number})</a></li>"
                    )
                    item_number += 1
                lines.append("</ul>")

            # 📅 COMING UP section (time-sensitive events, appointments)
            if len(time_sensitive) > 0:
                # fmt: off
                lines.append('<div style="font-weight: 600; margin-top: 16px; margin-bottom: 2px; color: #388e3c;">📅 COMING UP</div>')  # noqa: E501
                lines.append('<ul style="margin: 0; padding: 0 0 16px 20px; list-style-position: outside; margin-block-start: 0; margin-block-end: 0; padding-inline-start: 20px; line-height: 1.1;">')  # noqa: E501
                # fmt: on
                for email in time_sensitive:
                    thread_id = email.get("thread_id", email.get("id", ""))
                    subject = email.get("subject", "No subject")
                    gmail_link = GmailLinkBuilder.thread_link(thread_id)
                    li_style = "margin: 0; padding: 0; line-height: 1.1;"
                    a_style = "color: #1a73e8; text-decoration: none;"
                    lines.append(
                        f'<li style="{li_style}">{subject} '
                        f'<a href="{gmail_link}" target="_blank" style="{a_style}">'
                        f"({item_number})</a></li>"
                    )
                    item_number += 1
                lines.append("</ul>")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Everything else separator
            if len(routine) > 0:
                lines.append('<p style="margin-top: 16px;">Have a great day!</p>')

                # Categorize routine emails by type for aggregated summary
                # Uses Gemini's type classification directly
                noise_breakdown = self._categorize_routine_by_type(routine)

                if noise_breakdown:
                    # Header with count
                    routine_count = len(routine)
                    header_style = "margin-top: 12px; margin-bottom: 8px; font-weight: 600;"
                    lines.append(
                        f'<p style="{header_style} color: #666;">'
                        f"Everything else ({routine_count} emails):</p>"
                    )

                    # Bulleted breakdown (fmt: off for long style string)
                    # fmt: off
                    lines.append('<ul style="margin: 0; padding: 0 0 0 20px; list-style-position: outside; color: #666; font-size: 14px;">')  # noqa: E501
                    # fmt: on
                    sorted_items = sorted(noise_breakdown.items(), key=lambda x: -x[1])
                    for category, count in sorted_items:
                        # Create Gmail search link for this category
                        gmail_link = GmailLinkBuilder.search_link("label:MailQ/Everything-Else")
                        a_style = "color: #1a73e8; text-decoration: none;"
                        lines.append(
                            f'<li style="margin: 0 0 4px 0; padding: 0;">• '
                            f'<a href="{gmail_link}" style="{a_style}">'
                            f"{count} {category}</a></li>"
                        )
                    lines.append("</ul>")
                else:
                    routine_count = len(routine)
                    lines.append(
                        f'<p style="margin-top: 12px; color: #666;">'
                        f"Everything else ({routine_count} emails)</p>"
                    )

        # Deterministic summary (no LLM-generated opening)
        text = "".join(lines)

        # Simple HTML
        html = self.renderer.render(text, current_time=local_now)

        # Get final noise breakdown (categorize all routine emails by Gemini type)
        final_noise_breakdown = self._categorize_routine_by_type(routine) if routine else {}

        return {
            "text": text,
            "html": html,
            "word_count": len(text.split()),
            "entities_count": 0,
            "featured_count": featured_count,
            "noise_breakdown": final_noise_breakdown,
            "critical_count": len(critical),
            "time_sensitive_count": len(time_sensitive),
            "routine_count": len(routine),
            "verified": True,  # Fallback is always "verified"
            "errors": [],
            "fallback": True,
            "generated_at_local": local_now.isoformat(),
            "timezone": resolved_timezone,
            "city": city_hint,
            "sections": {"critical": [], "time_sensitive": [], "routine": []},
        }

    def generate_v2(
        self,
        emails: list[dict[str, Any]],
        timezone: str | None = None,
        client_now: str | None = None,
        timezone_offset: int | None = None,
        city_hint: str | None = None,
        region_hint: str | None = None,
        user_id: str | None = None,  # noqa: ARG002 Reserved for future use
        user_name: str | None = None,
        raw_digest: bool = False,
    ) -> dict[str, Any]:
        """
        Generate context digest using NEW section-first pipeline (Phase 2).

        This is the refactored pipeline that assigns sections BEFORE entity extraction,
        solving the problem where only 4.3% of emails were featured.

        Args:
            emails: List of email dicts with 'id', 'subject', 'snippet', 'type', 'attention'
            timezone: IANA timezone string (e.g., 'America/New_York')
            client_now: ISO timestamp from client
            timezone_offset: UTC offset in minutes
            city_hint: Client city for weather enrichment
            region_hint: Client region/state for weather disambiguation (e.g., 'New York')
            user_id: User ID for applying explicit preferences (optional)
            user_name: User's first name for personalized greeting (optional)

        Returns:
            {
                'text': narrative text,
                'html': rendered HTML card,
                'word_count': int,
                'entities_count': int,
                'featured_count': int,
                'noise_breakdown': dict,
                'verified': bool,
                'errors': list (if verification failed)
            }

        Architecture (7-Stage MVP Pipeline):
            Uses digest_stages_v2.py with consolidated stages:
            1. TemporalExtractionStage - filter expired + extract temporal context
            2. T0SectionAssignmentStage - intrinsic: "What IS this email?" (no time)
            3. T1TemporalDecayStage - time-adjusted: "When to show it?" (uses now)
            4. EntityStage - extract entities + build featured items
            5. EnrichmentStage - temporal enrichment + weather + greeting
            6. SynthesisAndRenderingStage - timeline + rich HTML + Gmail links
            7. ValidationStage - fact verification + schema validation

        Key Design Decisions:
            - T0/T1 separation preserved for testability (T0 has no time dependency)
            - HTML output matches golden digest format (digest_prototype.html)
            - Gmail archive links via GmailLinkBuilder
            - XSS prevention via html.escape()
        """
        # V2 Pipeline: 7 consolidated stages (MVP)
        # See digest_stages_v2.py for implementation details
        from mailq.digest.digest_pipeline import DigestPipeline
        from mailq.digest.digest_stages_v2 import (
            EnrichmentStage,
            EntityStage,
            SynthesisAndRenderingStage,
            T0SectionAssignmentStage,
            T1TemporalDecayStage,
            TemporalExtractionStage,
            ValidationStage,
        )
        from mailq.digest.noise_elevation import NoiseElevationStage

        # Resolve current time
        current_time, resolved_timezone = self._resolve_current_time(
            timezone, client_now, timezone_offset
        )

        self._log(
            f"🕐 [V2 Pipeline] Resolved time: {current_time.isoformat()} "
            f"(timezone={resolved_timezone})"
        )

        # Create 8-stage pipeline
        # 1. TemporalExtraction - filter expired + extract temporal context
        # 2. T0SectionAssignment - intrinsic: "What IS this email?"
        # 3. T1TemporalDecay - time-adjusted: "When to show it?"
        # 4. NoiseElevation - rescue important emails from noise (hybrid detection)
        # 5. EntityStage - extract entities + build featured items
        # 6. EnrichmentStage - temporal enrichment + weather + greeting
        # 7. SynthesisAndRendering - timeline + rich HTML + Gmail links
        # 8. ValidationStage - fact verification + schema validation
        pipeline = DigestPipeline(
            [
                TemporalExtractionStage(),
                T0SectionAssignmentStage(),
                T1TemporalDecayStage(),
                NoiseElevationStage(),  # Hybrid: keywords + Editor LLM
                EntityStage(),
                EnrichmentStage(city_hint=city_hint, region_hint=region_hint),
                SynthesisAndRenderingStage(),
                ValidationStage(),
            ]
        )

        # Run pipeline
        self._log(f"Running V2 pipeline on {len(emails)} emails... (raw_digest={raw_digest})")
        result = pipeline.run(
            emails=emails,
            now=current_time,
            user_timezone=resolved_timezone or "UTC",
            user_name=user_name or "",
            raw_digest=raw_digest,
        )

        # Check if pipeline succeeded
        if not result.success:
            self._log("⚠️ V2 Pipeline failed, falling back to email-based summary", level="WARN")
            # Fall back to deterministic email-based summary (NOT generate() to avoid recursion)
            importance_groups = self._categorize_emails_by_importance(emails)
            return self._fallback_email_based_summary(
                emails=emails,
                importance_groups=importance_groups,
                current_time=current_time,
                resolved_timezone=resolved_timezone,
                city_hint=city_hint,
            )

        # Convert pipeline result to API response format
        context = result.context

        # Log metrics
        self._log("✅ V2 Pipeline complete:")
        self._log(f"   - Filtered emails: {len(context.filtered_emails)}")
        self._log(f"   - Temporal contexts extracted: {len(context.temporal_contexts)}")
        self._log(f"   - Section assignments: {len(context.section_assignments)}")
        self._log(f"   - Entities extracted: {len(context.entities)}")
        self._log(f"   - Featured items: {len(context.featured_items)}")
        self._log(f"   - Noise summary: {sum(context.noise_summary.values())} emails")

        # Build response (matching old generate() API)
        response = result.to_dict()

        # Add backward-compatible fields
        response["generated_at_local"] = current_time.isoformat()
        response["timezone"] = resolved_timezone
        response["city"] = city_hint
        response["verified"] = True  # Simplified for Phase 2
        response["fallback"] = False
        response["pipeline_version"] = "v2"

        # Add section breakdown for debugging
        section_counts: dict[str, int] = {}
        for _email_id, section in context.section_assignments.items():
            section_counts[section] = section_counts.get(section, 0) + 1

        response["section_distribution"] = section_counts

        return response

    def generate_and_save(self, emails: list[dict[str, Any]], output_path: str) -> dict[str, Any]:
        """
        Generate digest and save HTML to file.

        Args:
            emails: List of emails
            output_path: Path to save HTML

        Returns:
            Digest dict
        """
        result = self.generate(emails)

        # Save HTML
        with open(output_path, "w") as f:
            f.write(result["html"])

        self._log(f"✅ Saved to {output_path}")

        return result


def generate_context_digest(emails: list[dict[str, Any]], verbose: bool = False) -> dict[str, Any]:
    """
    Convenience function to generate context digest.

    Args:
        emails: List of email dicts
        verbose: Print debug logs

    Returns:
        Digest dict
    """
    digest = ContextDigest(verbose=verbose)
    return digest.generate(emails)
