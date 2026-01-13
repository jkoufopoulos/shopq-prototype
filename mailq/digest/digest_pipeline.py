"""
Digest Pipeline - Unified concept for digest generation (P1: Concepts Are Rooms)

Replaces scattered logic across 15+ files:
- context_digest.py (1399 lines)
- hybrid_digest_renderer.py
- digest/formatting.py
- digest/categorizer.py
- temporal_enrichment.py
- entity_extractor.py
- filters.py

Single Responsibility: Transform raw emails → structured digest

Principles:
- P1: One concept, one room (all digest logic here + stage modules)
- P2: Side effects are loud (documented in stage docstrings)
- P3: Compiler is senior engineer (typed contracts, protocols)
- P4: Synchronizations explicit (stage dependencies declared + validated)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from mailq.contracts.entities import DigestEntity
from mailq.observability.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Data Structures (P3: Type Safety)
# ============================================================================


@dataclass
class DigestContext:
    """
    Shared context across pipeline stages.

    This is passed through the pipeline and populated by stages.
    Each stage reads from and writes to specific fields.

    Type Safety: All fields are typed to catch errors at compile time (P3)
    """

    # Inputs (set at pipeline start)
    now: datetime
    user_timezone: str
    emails: list[dict[str, Any]]
    user_name: str = ""  # Optional user name for personalized greeting
    raw_digest: bool = False  # A/B test: bypass pipeline and use pure LLM judgment

    # Stage outputs (populated as pipeline progresses)
    filtered_emails: list[dict[str, Any]] = field(default_factory=list)
    temporal_contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    section_assignments_t0: dict[str, str] = field(default_factory=dict)  # T0 intrinsic sections
    section_assignments: dict[str, str] = field(default_factory=dict)  # T1 time-adjusted sections
    entities: list[DigestEntity] = field(default_factory=list)
    featured_items: list[DigestEntity | dict[str, Any]] = field(default_factory=list)
    noise_summary: dict[str, int] = field(default_factory=dict)
    digest_html: str = ""

    # Enrichment outputs (V2 pipeline)
    weather: dict[str, Any] = field(default_factory=dict)
    greeting: str = ""

    # Noise elevation outputs (hybrid importance detection)
    elevation_reasons: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Validation outputs (V2 pipeline)
    verified: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class StageResult:
    """
    Output contract for pipeline stages (P3: Type Safety)

    Every stage must return this structure.
    """

    success: bool
    stage_name: str
    items_processed: int
    items_output: int
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ============================================================================
# Stage Contract (P3: Type Safety, P4: Explicit Dependencies)
# ============================================================================


class DigestStage(Protocol):
    """
    Contract: All digest stages must implement this protocol (P3)

    Side Effects: Stages may modify context in place (P2: Loud side effects)
                  Each stage documents its side effects in docstring

    Dependencies: Stages declare dependencies explicitly (P4: Explicit sync)
    """

    name: str
    depends_on: list[str]  # P4: Explicit dependencies

    def process(self, context: DigestContext) -> StageResult:
        """
        Process emails and update context.

        Args:
            context: Shared digest context (read and write)

        Returns:
            StageResult with success status and metadata

        Side Effects: (P2 - documented in subclass)
            Each stage documents what it modifies in context
        """
        ...


# ============================================================================
# Pipeline Orchestrator (P4: Dependency Validation)
# ============================================================================


class PipelineValidationError(Exception):
    """Raised when pipeline stage dependencies are invalid"""

    pass


@dataclass
class DigestPipeline:
    """
    Declarative digest pipeline with explicit stage dependencies (P4).

    Validates:
    - Stage dependencies are satisfied before execution
    - Stages run in correct order
    - Type contracts are honored (P3)

    Example:
        pipeline = DigestPipeline([
            FilterExpiredEventsStage(),
            TemporalContextExtractionStage(),  # depends_on: ["filter_expired"]
            SectionAssignmentStage(),           # depends_on: ["extract_temporal_context"]
            EntityExtractionStage(),            # depends_on: ["assign_sections"]
            RenderingStage(),                   # depends_on: ["extract_entities"]
        ])

        result = pipeline.run(emails, now=datetime.now())
    """

    stages: list[DigestStage]

    def validate_dependencies(self) -> list[str]:
        """
        Validate all stage dependencies can be satisfied (P4).

        Returns:
            List of validation errors (empty if valid)

        Principle: P4 (Synchronizations Explicit)
        - Dependencies must be declared
        - Dependencies must be satisfied before stage runs
        - Fail fast at pipeline construction, not execution
        """
        errors = []
        completed_stages = set()

        for stage in self.stages:
            # Check if dependencies are satisfied
            for dep in stage.depends_on:
                if dep not in completed_stages:
                    errors.append(
                        f"Stage '{stage.name}' depends on '{dep}' "
                        f"which has not run yet (or doesn't exist)"
                    )

            completed_stages.add(stage.name)

        return errors

    def run(
        self,
        emails: list[dict[str, Any]],
        now: datetime,
        user_timezone: str = "UTC",
        user_name: str = "",
        raw_digest: bool = False,
    ) -> DigestResult:
        """
        Execute digest pipeline with dependency validation.

        Args:
            emails: Raw email dicts from Gmail API
            now: Current time for temporal calculations
            user_timezone: User's timezone (IANA format)
            user_name: Optional user name for personalized greeting
            raw_digest: If True, bypass pipeline and use pure LLM judgment

        Returns:
            DigestResult with context and stage metrics

        Raises:
            PipelineValidationError: If stage dependencies are invalid (P4)

        Principle: P4 (Synchronizations Explicit)
        - Validates dependencies before execution
        - Fails fast on contract violations
        """
        # Validate pipeline before running (P4: Fail fast)
        validation_errors = self.validate_dependencies()
        if validation_errors:
            raise PipelineValidationError(
                "Pipeline validation failed:\n" + "\n".join(validation_errors)
            )

        # Initialize context
        context = DigestContext(
            now=now,
            user_timezone=user_timezone,
            emails=emails,
            user_name=user_name,
            raw_digest=raw_digest,
        )

        # Execute stages in order
        stage_results = []
        for stage in self.stages:
            try:
                logger.info(f"Running stage: {stage.name}")
                result = stage.process(context)
                stage_results.append(result)

                if not result.success:
                    # Stage failed, log and halt
                    logger.error(f"Stage '{stage.name}' failed: {result.errors}")
                    break

                logger.info(
                    f"Stage '{stage.name}' complete: "
                    f"{result.items_processed} processed, "
                    f"{result.items_output} output"
                )

            except Exception as e:
                logger.exception(f"Stage '{stage.name}' raised exception")
                stage_results.append(
                    StageResult(
                        success=False,
                        stage_name=stage.name,
                        items_processed=0,
                        items_output=0,
                        errors=[str(e)],
                    )
                )
                break

        return DigestResult(
            context=context,
            stage_results=stage_results,
            success=all(r.success for r in stage_results),
        )


@dataclass
class DigestResult:
    """Final digest output with metrics"""

    context: DigestContext
    stage_results: list[StageResult]
    success: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format"""
        return {
            "html": self.context.digest_html,
            "featured_count": len(self.context.featured_items),
            "noise_summary": self.context.noise_summary,
            "elevation_reasons": self.context.elevation_reasons,
            "success": self.success,
            "stage_metrics": [
                {
                    "stage": r.stage_name,
                    "processed": r.items_processed,
                    "output": r.items_output,
                    "metadata": r.metadata,
                }
                for r in self.stage_results
            ],
        }
