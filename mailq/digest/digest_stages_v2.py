"""
Digest Stage Implementations - V2 (7-Stage Pipeline)

Consolidated from 9 stages to 7 stages for MVP:
1. TemporalExtractionStage - Filter expired + extract temporal context
2. T0SectionAssignmentStage - Intrinsic: "What IS this email?" (no time comparisons)
3. T1TemporalDecayStage - Time-adjusted: "When to show it?" (uses `now`)
4. EntityStage - Extract entities + build featured items
5. EnrichmentStage - Temporal enrichment + weather + greeting
6. SynthesisAndRenderingStage - Timeline grouping + rich HTML + Gmail links
7. ValidationStage - Fact verification + schema validation

Principles Applied:
- P1: Each stage is a focused concept (7 stages, not 13)
- P2: Side effects documented in docstrings
- P3: Type-safe contracts (DigestStage protocol)
- P4: Dependencies declared and validated
- P5: Extracted from V1, not rewritten (tuning, not debt)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mailq.contracts.entities import DigestEntity
from mailq.digest.digest_pipeline import DigestContext, StageResult

if TYPE_CHECKING:
    from mailq.digest.digest_pipeline import DigestPipeline
# Synthesis stage extracted to separate module
from mailq.digest.section_assignment_t0 import assign_section_t0
from mailq.digest.synthesis_stage import SynthesisAndRenderingStage
from mailq.digest.temporal import apply_temporal_decay_batch, extract_temporal_context
from mailq.observability.logging import get_logger

logger = get_logger(__name__)


# Stage 1: Temporal Extraction
@dataclass
class TemporalExtractionStage:
    """
    Extract temporal information and filter expired events.

    Combines two operations that both work with temporal data:
    1. Filter out expired events (past grace period)
    2. Extract temporal context (event_time, delivery_date, etc.)

    Dependencies: None (first stage)

    Side Effects: (P2)
        - Populates context.filtered_emails (removes expired events)
        - Populates context.temporal_contexts[email_id] = {
            "event_time": datetime | None,
            "event_end_time": datetime | None,
            "delivery_date": datetime | None,
            "purchase_date": datetime | None,
            "expiration_date": datetime | None,
        }
    """

    name: str = "temporal_extraction"
    depends_on: list[str] = field(default_factory=list)

    def process(self, context: DigestContext) -> StageResult:
        """
        Filter expired events and extract temporal context.

        Side Effects:
            - Populates context.filtered_emails with non-expired emails
            - Populates context.temporal_contexts dict (email_id -> temporal context)
            - Logs filtered count and extraction rate
        """
        from mailq.classification.temporal import filter_expired_events

        initial_count = len(context.emails)

        # Step 1: Filter expired events (using evaluation time, not current time)
        context.filtered_emails = filter_expired_events(context.emails.copy(), now=context.now)
        filtered_count = initial_count - len(context.filtered_emails)

        if filtered_count > 0:
            logger.info(f"Filtered {filtered_count} expired events")

        # Step 2: Extract temporal context from ALL emails (including filtered)
        # We extract from all because T0 assignment needs temporal_ctx
        extracted_count = 0
        for email in context.emails:
            temporal_ctx = extract_temporal_context(email, context.now)
            if temporal_ctx:
                email_id = email.get("id", email.get("thread_id", "unknown"))
                context.temporal_contexts[email_id] = temporal_ctx
                extracted_count += 1

        extraction_rate = extracted_count / len(context.emails) if context.emails else 0

        logger.info(
            f"Temporal extraction: {extracted_count}/{len(context.emails)} "
            f"({extraction_rate:.1%}) with temporal context"
        )

        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=initial_count,
            items_output=len(context.filtered_emails),
            metadata={
                "filtered_count": filtered_count,
                "extraction_rate": f"{extraction_rate:.1%}",
            },
        )


# Stage 2: T0 Section Assignment
@dataclass
class T0SectionAssignmentStage:
    """
    Assign T0 section based on intrinsic email properties ONLY.

    T0 = "What IS this email?" - No `now` parameter, testable without mocking time.

    Examples:
        - Email IS an event → T0 = "today" (regardless of when event is)
        - Email IS a delivery → T0 = "today" (regardless of when delivery is)
        - Email IS a receipt → T0 = "worth_knowing"
        - Email IS a newsletter → T0 = "noise"

    Dependencies: temporal_extraction

    Side Effects: (P2)
        - Populates context.section_assignments_t0[email_id] = t0_section
    """

    name: str = "t0_section_assignment"
    depends_on: list[str] = field(default_factory=lambda: ["temporal_extraction"])

    def process(self, context: DigestContext) -> StageResult:
        """
        Assign T0 (intrinsic) section to every email.

        Side Effects:
            - Populates context.section_assignments_t0 dict (email_id -> T0 section)
            - T0 sections: "critical", "today", "coming_up", "worth_knowing", "noise"
            - Logs T0 section distribution
        """
        section_counts: dict[str, int] = {}

        # Use filtered_emails (excludes expired events)
        emails_to_process = context.filtered_emails if context.filtered_emails else context.emails

        for email in emails_to_process:
            email_id = email.get("id", email.get("thread_id", "unknown"))
            temporal_ctx = context.temporal_contexts.get(email_id)

            t0_section = assign_section_t0(email=email, temporal_ctx=temporal_ctx)

            context.section_assignments_t0[email_id] = t0_section
            section_counts[t0_section] = section_counts.get(t0_section, 0) + 1

        logger.info(f"T0 distribution: {section_counts}")

        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(emails_to_process),
            items_output=len(context.section_assignments_t0),
            metadata={"t0_distribution": section_counts},
        )


# Stage 3: T1 Temporal Decay
@dataclass
class T1TemporalDecayStage:
    """
    Apply temporal decay to T0 sections, producing T1 (time-adjusted) sections.

    T1 = "When should we show it?" - Uses `now` parameter, changes based on viewing time.

    Decay rules:
        - Events/deliveries past grace period (1h) → SKIP
        - Events/deliveries within 24h → TODAY
        - Events/deliveries 1-7 days out → COMING_UP
        - Events/deliveries >7 days out → WORTH_KNOWING
        - Critical never decays → CRITICAL
        - Noise never decays → NOISE

    Dependencies: t0_section_assignment

    Side Effects: (P2)
        - Populates context.section_assignments[email_id] = t1_section
    """

    name: str = "t1_temporal_decay"
    depends_on: list[str] = field(default_factory=lambda: ["t0_section_assignment"])

    def process(self, context: DigestContext) -> StageResult:
        """
        Apply temporal decay to T0 sections, producing T1 sections.

        Side Effects:
            - Populates context.section_assignments dict (email_id -> T1 section)
            - T1 sections: "critical", "today", "coming_up", "worth_knowing", "noise", "skip"
            - Logs T1 distribution and decay changes
        """
        t0_sections = getattr(context, "section_assignments_t0", {})

        # Use filtered_emails (excludes expired events)
        emails_to_process = context.filtered_emails if context.filtered_emails else context.emails

        t1_sections = apply_temporal_decay_batch(
            section_assignments_t0=t0_sections,
            emails=emails_to_process,
            temporal_contexts=context.temporal_contexts,
            now=context.now,
            user_timezone=getattr(context, "user_timezone", "UTC"),
        )

        context.section_assignments = t1_sections

        # Calculate distribution and changes
        t1_counts: dict[str, int] = {}
        decay_changes = 0

        for email_id, t1_section in t1_sections.items():
            t1_counts[t1_section] = t1_counts.get(t1_section, 0) + 1
            if t0_sections.get(email_id) != t1_section:
                decay_changes += 1

        logger.info(f"T1 distribution: {t1_counts} ({decay_changes} decayed)")

        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(t0_sections),
            items_output=len(t1_sections),
            metadata={"t1_distribution": t1_counts, "decay_changes": decay_changes},
        )


# Stage 4: Entity Extraction
@dataclass
class EntityStage:
    """
    Extract entities and build featured items list.

    Combines two related operations:
    1. Extract entities for featured emails (pattern-based)
    2. Build featured items list (entity if available, else email dict)

    Dependencies: t1_temporal_decay

    Side Effects: (P2)
        - Populates context.entities (Entity objects for rich display)
        - Populates context.featured_items (list of Entity | dict)
        - Populates context.noise_summary (category counts)
    """

    name: str = "entity_stage"
    depends_on: list[str] = field(default_factory=lambda: ["t1_temporal_decay"])

    def process(self, context: DigestContext) -> StageResult:
        """
        Extract entities and build featured items.

        Side Effects:
            - Populates context.entities list with Entity objects
            - Populates context.featured_items list (Entity or email dict)
            - Populates context.noise_summary dict (category -> count)
            - Logs entity extraction rate
        """
        from mailq.classification.extractor import HybridExtractor

        extractor = HybridExtractor()
        featured_sections = {"critical", "today", "coming_up", "worth_knowing"}

        # Use filtered_emails (excludes expired events)
        emails_to_process = context.filtered_emails if context.filtered_emails else context.emails

        # Step 1: Extract entities for featured emails
        entity_map: dict[str, DigestEntity] = {}

        for email in emails_to_process:
            email_id = email.get("id", email.get("thread_id", "unknown"))
            section = context.section_assignments.get(email_id)

            if section not in featured_sections:
                continue

            try:
                entities = extractor.extract_from_email(email)
                if entities:
                    context.entities.extend(entities)
                    for entity in entities:
                        entity_map[entity.source_email_id] = entity
            except Exception as e:
                logger.debug(f"Entity extraction failed for {email_id}: {e}")

        # Step 2: Build featured items and noise summary
        # Debug: Log sample of email types to trace the data
        if emails_to_process:
            sample_types = [e.get("type", "MISSING") for e in emails_to_process[:5]]
            logger.info(f"[DEBUG] Sample email types: {sample_types}")

        for email in emails_to_process:
            email_id = email.get("id", email.get("thread_id", "unknown"))
            section = context.section_assignments.get(email_id)

            if section in featured_sections:
                item = entity_map.get(email_id, email)
                context.featured_items.append(item)
            elif section == "noise":
                category = email.get("type", "other")
                context.noise_summary[category] = context.noise_summary.get(category, 0) + 1

        entity_rate = len(entity_map) / len(context.featured_items) if context.featured_items else 0

        logger.info(
            f"Entity stage: {len(context.featured_items)} featured, "
            f"{len(entity_map)} entities ({entity_rate:.1%}), "
            f"{sum(context.noise_summary.values())} noise, "
            f"noise_by_type={dict(context.noise_summary)}"
        )

        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(emails_to_process),
            items_output=len(context.featured_items),
            metadata={
                "entity_count": len(entity_map),
                "featured_count": len(context.featured_items),
                "noise_count": sum(context.noise_summary.values()),
            },
        )


# Stage 5: Enrichment
@dataclass
class EnrichmentStage:
    """
    Apply enrichments: temporal decay on entities, weather, greeting.

    Combines:
    1. Temporal enrichment (escalate/demote based on time)
    2. Weather enrichment (for greeting)
    3. Greeting generation

    Dependencies: entity_stage

    Side Effects: (P2)
        - Modifies entity.resolved_importance
        - Populates context.weather (dict with temp, condition, city)
        - Populates context.greeting (personalized greeting string)
    """

    name: str = "enrichment"
    depends_on: list[str] = field(default_factory=lambda: ["entity_stage"])
    city_hint: str | None = None
    region_hint: str | None = None  # State/province for weather disambiguation (e.g., "New York")

    def process(self, context: DigestContext) -> StageResult:
        """
        Apply temporal enrichment and add weather/greeting.

        Side Effects:
            - Modifies entity.resolved_importance for Entity objects
            - Populates context.weather dict
            - Populates context.greeting string
            - Logs enrichment results
        """
        from mailq.classification.enrichment import enrich_entities_with_temporal_decay
        from mailq.classification.models import Entity

        # Step 1: Temporal enrichment on entities
        entities = [item for item in context.featured_items if isinstance(item, DigestEntity)]

        if entities:
            # Cast to Entity for type checker (DigestEntity is the Protocol that Entity implements)
            enriched = enrich_entities_with_temporal_decay(
                [e for e in entities if isinstance(e, Entity)], now=context.now
            )
            entity_map = {e.source_email_id: e for e in enriched}

            updated_items: list[DigestEntity | dict[str, Any]] = []
            for item in context.featured_items:
                if isinstance(item, DigestEntity):
                    updated_items.append(entity_map.get(item.source_email_id, item))
                else:
                    updated_items.append(item)
            context.featured_items = updated_items

        # Step 2: Weather enrichment (optional, graceful degradation)
        weather = None
        city = self.city_hint or getattr(context, "city_hint", None)
        region = self.region_hint or getattr(context, "region_hint", None)

        try:
            from mailq.gmail.weather_service import WeatherService

            weather_service = WeatherService()
            if not city:
                from mailq.gmail.location_service import get_user_location

                location = get_user_location()
                if location:
                    city = location.get("city")
                    region = region or location.get("region")  # Use fallback region if not provided
            if city:
                # Pass region for disambiguation (e.g., "Brooklyn" + "New York" → Brooklyn, NY)
                weather = weather_service.get_weather(city, region=region)
        except Exception as e:
            logger.debug(f"Weather enrichment failed: {e}")

        # Store weather in context for rendering
        if weather:
            context.weather = {
                "temp": weather.get("temp"),
                "condition": weather.get("condition"),
                "city": city,
            }

        # Step 3: Generate greeting (with optional user name)
        context.greeting = self._generate_greeting(
            context.now, context.weather, getattr(context, "user_name", "")
        )

        logger.info(f"Enrichment: {len(entities)} entities enriched, weather={bool(weather)}")

        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(context.featured_items),
            items_output=len(context.featured_items),
            metadata={"weather_available": bool(weather), "city": city},
        )

    def _generate_greeting(
        self, now: datetime, weather: dict[str, Any] | None, user_name: str = ""
    ) -> str:
        """Generate personalized greeting with weather and optional user name."""
        # Debug: Log the datetime being used for greeting
        logger.info(
            f"[GREETING DEBUG] now={now.isoformat()}, tzinfo={now.tzinfo}, "
            f"hour={now.hour}, weekday={now.strftime('%A')}"
        )

        # Time-based greeting
        hour = now.hour
        if hour < 12:
            time_greeting = "Good morning"
        elif hour < 17:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"

        # Add user name if provided
        if user_name:
            time_greeting = f"{time_greeting}, {user_name}"

        # Date formatting - use ordinal suffix (9th, 21st, etc.)
        day_name = now.strftime("%A")
        day_num = now.day
        if 4 <= day_num <= 20 or 24 <= day_num <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day_num % 10 - 1]
        month_name = now.strftime("%B")
        date_str = f"{month_name} {day_num}{suffix}"

        # Weather string
        if weather and weather.get("temp") and weather.get("condition"):
            condition = weather["condition"].lower()
            # Match emoji based on keywords in condition
            emoji = ""
            if "snow" in condition or "flurr" in condition:
                emoji = "❄️"
            elif "rain" in condition or "shower" in condition or "drizzle" in condition:
                emoji = "🌧️"
            elif "thunder" in condition or "storm" in condition:
                emoji = "⛈️"
            elif "cloud" in condition or "overcast" in condition:
                emoji = "⛅" if "partly" in condition or "partial" in condition else "☁️"
            elif "clear" in condition or "sunny" in condition:
                emoji = "☀️"
            elif "fog" in condition or "mist" in condition or "haz" in condition:
                emoji = "🌫️"
            city = weather.get("city", "")
            weather_str = f"—currently {weather['temp']}°F and {condition} {emoji} in {city}"
        else:
            weather_str = ""

        return f"{time_greeting}. It's {day_name}, {date_str}{weather_str}."


# Stage 6: SynthesisAndRenderingStage (imported from synthesis_stage.py)


# Stage 7: Validation
@dataclass
class ValidationStage:
    """
    Validate digest output: fact verification + schema validation.

    Combines:
    1. Fact verification (NarrativeVerifier) - check numbers, dates, names
    2. Schema validation - ensure HTML and featured items are valid

    Dependencies: synthesis_and_rendering

    Side Effects: (P2)
        - Sets context.verified (bool)
        - Sets context.validation_errors (list)
        - Logs validation results
    """

    name: str = "validation"
    depends_on: list[str] = field(default_factory=lambda: ["synthesis_and_rendering"])

    def process(self, context: DigestContext) -> StageResult:
        """
        Validate digest output.

        Side Effects:
            - Sets context.verified (bool)
            - Sets context.validation_errors (list of error strings)
            - Logs validation results
        """
        from mailq.contracts.entities import (
            DigestDeadlineEntity,
            DigestEventEntity,
            DigestNotificationEntity,
        )
        from mailq.digest.narrative_verifier import NarrativeVerifier

        errors: list[str] = []

        # Step 1: Fact verification (if entities present)
        entities = [item for item in context.featured_items if isinstance(item, DigestEntity)]
        if entities and context.digest_html:
            try:
                verifier = NarrativeVerifier()
                is_verified, verification_errors = verifier.verify(context.digest_html, entities)
                if not is_verified:
                    errors.extend(verification_errors)
            except Exception as e:
                logger.warning(f"Verification failed: {e}")

        # Step 2: Schema validation
        if not context.digest_html:
            errors.append("digest_html is empty")
        elif not isinstance(context.digest_html, str):
            errors.append(f"digest_html is not string: {type(context.digest_html)}")

        for idx, item in enumerate(context.featured_items):
            if isinstance(
                item,
                (DigestEntity, DigestNotificationEntity, DigestEventEntity, DigestDeadlineEntity),
            ):
                if not getattr(item, "source_email_id", None):
                    errors.append(f"Entity {idx} missing source_email_id")
            elif isinstance(item, dict):
                if "id" not in item and "thread_id" not in item:
                    errors.append(f"Item {idx} missing id/thread_id")
            else:
                errors.append(f"Item {idx} has invalid type: {type(item)}")

        # Store results
        context.verified = len(errors) == 0
        context.validation_errors = errors

        if errors:
            logger.warning(f"Validation found {len(errors)} issues: {errors[:3]}")
        else:
            logger.info("Validation passed")

        return StageResult(
            success=True,  # Don't fail pipeline on validation warnings
            stage_name=self.name,
            items_processed=len(context.featured_items) + 1,
            items_output=len(context.featured_items) + 1,
            metadata={"verified": context.verified, "error_count": len(errors)},
        )


# Pipeline Factory
def create_v2_pipeline() -> DigestPipeline:
    """
    Create the 7-stage V2 digest pipeline.

    Returns:
        DigestPipeline configured with all 7 stages
    """
    from mailq.digest.digest_pipeline import DigestPipeline

    return DigestPipeline(
        [
            TemporalExtractionStage(),
            T0SectionAssignmentStage(),
            T1TemporalDecayStage(),
            EntityStage(),
            EnrichmentStage(),
            SynthesisAndRenderingStage(),
            ValidationStage(),
        ]
    )
