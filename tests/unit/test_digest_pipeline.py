"""
Unit tests for digest pipeline foundation

Tests:
- Pipeline dependency validation (P4)
- Stage execution order
- Type contracts (P3)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from mailq.digest.digest_pipeline import (
    DigestContext,
    DigestPipeline,
    PipelineValidationError,
    StageResult,
)

# ============================================================================
# Mock Stages for Testing
# ============================================================================


@dataclass
class MockStageA:
    """Mock stage with no dependencies"""

    name: str = "stage_a"
    depends_on: list[str] = field(default_factory=list)

    def process(self, context: DigestContext) -> StageResult:
        context.filtered_emails = context.emails.copy()
        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(context.emails),
            items_output=len(context.filtered_emails),
        )


@dataclass
class MockStageB:
    """Mock stage that depends on stage_a"""

    name: str = "stage_b"
    depends_on: list[str] = field(default_factory=lambda: ["stage_a"])

    def process(self, context: DigestContext) -> StageResult:
        # Requires stage_a to have populated filtered_emails
        context.section_assignments = {
            email.get("id", "unknown"): "today" for email in context.filtered_emails
        }
        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(context.filtered_emails),
            items_output=len(context.section_assignments),
        )


@dataclass
class MockStageC:
    """Mock stage that depends on stage_b"""

    name: str = "stage_c"
    depends_on: list[str] = field(default_factory=lambda: ["stage_b"])

    def process(self, context: DigestContext) -> StageResult:
        # Requires stage_b to have populated section_assignments
        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(context.section_assignments),
            items_output=1,
        )


# ============================================================================
# Tests
# ============================================================================


def test_pipeline_validates_correct_dependencies():
    """Pipeline should accept valid dependency ordering"""
    pipeline = DigestPipeline(
        [
            MockStageA(),  # No dependencies
            MockStageB(),  # Depends on stage_a
            MockStageC(),  # Depends on stage_b
        ]
    )

    errors = pipeline.validate_dependencies()
    assert len(errors) == 0, f"Expected no errors, got: {errors}"


def test_pipeline_rejects_invalid_dependencies():
    """Pipeline should reject invalid dependency ordering"""
    pipeline = DigestPipeline(
        [
            MockStageB(),  # Depends on stage_a (which hasn't run yet)
            MockStageA(),  # Should come first
        ]
    )

    errors = pipeline.validate_dependencies()
    assert len(errors) > 0
    assert "depends on 'stage_a'" in errors[0]


def test_pipeline_rejects_missing_dependencies():
    """Pipeline should reject stages with unsatisfied dependencies"""
    pipeline = DigestPipeline(
        [
            MockStageB(),  # Depends on stage_a (which doesn't exist)
        ]
    )

    errors = pipeline.validate_dependencies()
    assert len(errors) > 0
    assert "depends on 'stage_a'" in errors[0]


def test_pipeline_raises_on_validation_failure():
    """Pipeline should raise PipelineValidationError on invalid dependencies"""
    pipeline = DigestPipeline(
        [
            MockStageB(),  # Invalid: depends on stage_a which doesn't exist
        ]
    )

    with pytest.raises(PipelineValidationError) as exc_info:
        pipeline.run(emails=[], now=datetime.now(UTC))

    assert "Pipeline validation failed" in str(exc_info.value)


def test_pipeline_executes_stages_in_order():
    """Pipeline should execute stages in order and populate context"""
    emails = [
        {"id": "1", "subject": "Test 1"},
        {"id": "2", "subject": "Test 2"},
    ]

    pipeline = DigestPipeline(
        [
            MockStageA(),
            MockStageB(),
            MockStageC(),
        ]
    )

    result = pipeline.run(emails, now=datetime.now(UTC))

    # Check all stages succeeded
    assert result.success
    assert len(result.stage_results) == 3

    # Check stages ran in order
    assert result.stage_results[0].stage_name == "stage_a"
    assert result.stage_results[1].stage_name == "stage_b"
    assert result.stage_results[2].stage_name == "stage_c"

    # Check context was populated correctly
    assert len(result.context.filtered_emails) == 2
    assert len(result.context.section_assignments) == 2


def test_pipeline_halts_on_stage_failure():
    """Pipeline should halt execution when a stage fails"""

    @dataclass
    class FailingStage:
        name: str = "failing_stage"
        depends_on: list[str] = field(default_factory=lambda: ["stage_a"])

        def process(self, context: DigestContext) -> StageResult:
            return StageResult(
                success=False,
                stage_name=self.name,
                items_processed=0,
                items_output=0,
                errors=["Intentional failure"],
            )

    @dataclass
    class FinalStage:
        name: str = "final_stage"
        depends_on: list[str] = field(default_factory=lambda: ["failing_stage"])

        def process(self, context: DigestContext) -> StageResult:
            return StageResult(
                success=True,
                stage_name=self.name,
                items_processed=0,
                items_output=0,
            )

    pipeline = DigestPipeline(
        [
            MockStageA(),
            FailingStage(),
            FinalStage(),  # Should not run
        ]
    )

    result = pipeline.run(emails=[{"id": "1"}], now=datetime.now(UTC))

    # Pipeline should fail
    assert not result.success

    # Only 2 stages should have run (stage_a and failing_stage)
    assert len(result.stage_results) == 2
    assert result.stage_results[0].success  # stage_a succeeded
    assert not result.stage_results[1].success  # failing_stage failed


def test_pipeline_halts_on_exception():
    """Pipeline should halt and record error when stage raises exception"""

    @dataclass
    class ExceptionStage:
        name: str = "exception_stage"
        depends_on: list[str] = field(default_factory=lambda: ["stage_a"])

        def process(self, context: DigestContext) -> StageResult:
            raise ValueError("Intentional exception")

    @dataclass
    class FinalStage:
        name: str = "final_stage"
        depends_on: list[str] = field(default_factory=lambda: ["exception_stage"])

        def process(self, context: DigestContext) -> StageResult:
            return StageResult(
                success=True,
                stage_name=self.name,
                items_processed=0,
                items_output=0,
            )

    pipeline = DigestPipeline(
        [
            MockStageA(),
            ExceptionStage(),
            FinalStage(),  # Should not run
        ]
    )

    result = pipeline.run(emails=[{"id": "1"}], now=datetime.now(UTC))

    # Pipeline should fail
    assert not result.success

    # Only 2 stages should have results
    assert len(result.stage_results) == 2
    assert result.stage_results[0].success  # stage_a succeeded
    assert not result.stage_results[1].success  # exception_stage failed
    assert "Intentional exception" in result.stage_results[1].errors[0]


def test_digest_context_initialization():
    """DigestContext should initialize with typed fields"""
    now = datetime.now(UTC)
    emails = [{"id": "1"}]

    context = DigestContext(
        now=now,
        user_timezone="America/New_York",
        emails=emails,
    )

    assert context.now == now
    assert context.user_timezone == "America/New_York"
    assert context.emails == emails

    # Check default fields
    assert context.filtered_emails == []
    assert context.temporal_contexts == {}
    assert context.section_assignments == {}
    assert context.entities == []
    assert context.featured_items == []
    assert context.noise_summary == {}
    assert context.digest_html == ""


def test_stage_result_structure():
    """StageResult should have required fields"""
    result = StageResult(
        success=True,
        stage_name="test_stage",
        items_processed=10,
        items_output=5,
        metadata={"test": "value"},
        errors=[],
    )

    assert result.success
    assert result.stage_name == "test_stage"
    assert result.items_processed == 10
    assert result.items_output == 5
    assert result.metadata == {"test": "value"}
    assert result.errors == []


def test_digest_result_to_dict():
    """DigestResult.to_dict() should return API-compatible dict"""
    context = DigestContext(
        now=datetime.now(UTC),
        user_timezone="UTC",
        emails=[],
    )
    context.featured_items = ["item1", "item2"]
    context.noise_summary = {"newsletter": 5, "promotion": 10}
    context.digest_html = "<html>test</html>"

    stage_results = [
        StageResult(
            success=True,
            stage_name="stage_1",
            items_processed=10,
            items_output=8,
            metadata={"key": "value"},
        )
    ]

    from mailq.digest.digest_pipeline import DigestResult

    result = DigestResult(
        context=context,
        stage_results=stage_results,
        success=True,
    )

    result_dict = result.to_dict()

    assert result_dict["html"] == "<html>test</html>"
    assert result_dict["featured_count"] == 2
    assert result_dict["noise_summary"] == {"newsletter": 5, "promotion": 10}
    assert result_dict["success"] is True
    assert len(result_dict["stage_metrics"]) == 1
    assert result_dict["stage_metrics"][0]["stage"] == "stage_1"
    assert result_dict["stage_metrics"][0]["processed"] == 10
    assert result_dict["stage_metrics"][0]["output"] == 8
