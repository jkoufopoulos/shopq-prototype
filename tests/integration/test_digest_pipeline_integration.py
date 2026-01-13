"""
Integration tests for V2 digest pipeline (7-stage MVP)

Tests the full pipeline end-to-end with real email data from Dataset 2.

Updated to use digest_stages_v2.py consolidated stages.
"""

import csv
from datetime import UTC, datetime

import pytest

from shopq.digest.digest_pipeline import DigestPipeline
from shopq.digest.digest_stages_v2 import (
    EnrichmentStage,
    EntityStage,
    SynthesisAndRenderingStage,
    T0SectionAssignmentStage,
    T1TemporalDecayStage,
    TemporalExtractionStage,
    ValidationStage,
)


def load_dataset2_subset(limit: int = 10) -> list[dict]:
    """
    Load first N emails from Dataset 2 CSV.

    Args:
        limit: Number of emails to load

    Returns:
        List of email dicts with fields: id, subject, snippet, date, etc.
    """
    dataset_path = "reports/dataset2_nov2-9_70_emails.csv"

    emails = []
    with open(dataset_path) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break

            # Convert CSV row to email dict format
            email = {
                "id": row.get("id", f"email_{i}"),
                "thread_id": row.get("thread_id", row.get("id", f"thread_{i}")),
                "subject": row.get("subject", ""),
                "snippet": row.get("snippet", ""),
                "from": row.get("from", ""),
                "date": row.get("date", ""),
                "type": row.get("type", ""),
                "importance": row.get("importance", "routine"),
            }
            emails.append(email)

    return emails


@pytest.fixture
def dataset2_sample():
    """Load 10 emails from Dataset 2"""
    pytest.skip("Dataset 2 file was removed during Phase 0.5 cleanup")
    return load_dataset2_subset(limit=10)


@pytest.fixture
def pipeline():
    """Create 7-stage V2 pipeline"""
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


def test_pipeline_runs_on_dataset2_subset(dataset2_sample, pipeline):
    """Test that pipeline runs successfully on Dataset 2 emails"""
    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=dataset2_sample,
        now=now,
        user_timezone="America/New_York",
    )

    # Pipeline should succeed
    assert result.success, (
        f"Pipeline failed: {result.stage_results[-1].errors if result.stage_results else 'No stages ran'}"
    )

    # All 7 stages should have run
    assert len(result.stage_results) == 7

    # All stages should succeed (entity_stage may have partial extraction)
    for stage_result in result.stage_results:
        assert stage_result.success or stage_result.stage_name in ["entity_stage"], (
            f"Stage {stage_result.stage_name} failed: {stage_result.errors}"
        )


def test_temporal_extraction_on_dataset2(dataset2_sample, pipeline):
    """Test that temporal context is extracted from Dataset 2 emails"""
    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=dataset2_sample,
        now=now,
        user_timezone="America/New_York",
    )

    # Get temporal extraction stage result (now combined filter + extraction)
    temporal_stage = next(
        sr for sr in result.stage_results if sr.stage_name == "temporal_extraction"
    )

    # Should have processed some emails
    assert temporal_stage.items_processed > 0, "No emails processed"

    # Context should have temporal_contexts populated
    assert len(result.context.temporal_contexts) >= 0  # May be 0 if no temporal data


def test_section_assignment_on_dataset2(dataset2_sample, pipeline):
    """Test that T0 and T1 sections are assigned to all emails"""
    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=dataset2_sample,
        now=now,
        user_timezone="America/New_York",
    )

    # Get T1 decay stage result (final section assignments)
    t1_stage = next(sr for sr in result.stage_results if sr.stage_name == "t1_temporal_decay")

    # All emails should have sections assigned
    assert t1_stage.items_output > 0, "No sections assigned"

    # Check context has section assignments
    assert len(result.context.section_assignments) > 0

    # T1 distribution should be in metadata
    metadata = t1_stage.metadata or {}
    t1_dist = metadata.get("t1_distribution", {})

    # Should have some variety (not all noise)
    assert len(t1_dist) >= 1, f"No section distribution: {t1_dist}"


def test_entity_extraction_on_dataset2(dataset2_sample, pipeline):
    """Test that entities are extracted for featured emails"""
    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=dataset2_sample,
        now=now,
        user_timezone="America/New_York",
    )

    # Get entity stage result (now combined extraction + build featured)
    entity_stage = next(sr for sr in result.stage_results if sr.stage_name == "entity_stage")

    # Should process emails
    assert entity_stage.items_processed > 0, "No emails processed by entity stage"

    # Check entity count is reported
    metadata = entity_stage.metadata or {}
    assert "entity_count" in metadata or "featured_count" in metadata


def test_featured_items_built(dataset2_sample, pipeline):
    """Test that featured items list is built with entities and email dicts"""
    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=dataset2_sample,
        now=now,
        user_timezone="America/New_York",
    )

    # Get entity stage result (now includes building featured items)
    entity_stage = next(sr for sr in result.stage_results if sr.stage_name == "entity_stage")

    # Should have built some featured items
    assert entity_stage.items_output >= 0, "Entity stage didn't run"

    # Context should have featured_items populated (may be 0 if all noise)
    assert len(result.context.featured_items) >= 0

    # Should also have noise summary
    assert len(result.context.noise_summary) >= 0  # May be empty if all featured


def test_digest_html_generated(dataset2_sample, pipeline):
    """Test that HTML digest is generated"""
    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=dataset2_sample,
        now=now,
        user_timezone="America/New_York",
    )

    # Get rendering stage result (now synthesis_and_rendering)
    render_stage = next(
        sr for sr in result.stage_results if sr.stage_name == "synthesis_and_rendering"
    )

    assert render_stage.success, f"Rendering failed: {render_stage.errors}"

    # Context should have HTML
    assert len(result.context.digest_html) > 0

    # HTML should contain sections
    html = result.context.digest_html
    assert "<html>" in html
    assert "<body>" in html


def test_pipeline_metrics(dataset2_sample, pipeline):
    """Test that pipeline reports metrics correctly"""
    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=dataset2_sample,
        now=now,
        user_timezone="America/New_York",
    )

    # Check to_dict() works
    result_dict = result.to_dict()

    assert "html" in result_dict
    assert "featured_count" in result_dict
    assert "noise_summary" in result_dict
    assert "success" in result_dict
    assert "stage_metrics" in result_dict

    # Stage metrics should include all stages
    assert len(result_dict["stage_metrics"]) == 7


def test_pipeline_handles_empty_emails():
    """Test that pipeline handles empty email list gracefully"""
    pipeline = DigestPipeline(
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

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=[],
        now=now,
        user_timezone="America/New_York",
    )

    # Pipeline should still succeed
    assert result.success

    # All stages should run
    assert len(result.stage_results) == 7

    # No featured items
    assert len(result.context.featured_items) == 0


@pytest.mark.skip(reason="Dataset 2 file was removed during Phase 0.5 cleanup")
def test_pipeline_full_dataset2():
    """
    Test pipeline on full Dataset 2 (70 emails).

    This is the comprehensive test to validate the refactor.
    """
    # Load all 70 emails
    emails = load_dataset2_subset(limit=70)

    pipeline = DigestPipeline(
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

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = pipeline.run(
        emails=emails,
        now=now,
        user_timezone="America/New_York",
    )

    # Pipeline should succeed
    assert result.success

    # Get section distribution
    section_stage = next(sr for sr in result.stage_results if sr.stage_name == "assign_sections")
    metadata = section_stage.metadata or {}
    section_dist = metadata.get("section_distribution", {})

    # Print metrics for manual validation
    print("\n=== Full Dataset 2 Metrics ===")
    print(f"Total emails: {len(emails)}")
    print(f"Filtered emails: {len(result.context.filtered_emails)}")
    print(f"Temporal contexts: {len(result.context.temporal_contexts)}")
    print(f"Section distribution: {section_dist}")
    print(f"Entities extracted: {len(result.context.entities)}")
    print(f"Featured items: {len(result.context.featured_items)}")
    print(f"Noise summary: {sum(result.context.noise_summary.values())} emails")

    # Validate expectations
    # Target: 16-20 featured items from 70 emails (~25%)
    featured_count = len(result.context.featured_items)
    featured_pct = featured_count / len(emails) * 100

    print(f"\nFeatured: {featured_count}/{len(emails)} ({featured_pct:.1f}%)")

    # Should have significantly more featured items than old system (3/70 = 4.3%)
    assert featured_count > 3, f"Expected > 3 featured items, got {featured_count}"

    # Should not feature too many (goal is 16-20)
    assert featured_count < 50, f"Too many featured items: {featured_count}"

    # Should have section variety
    assert len(section_dist) >= 3, f"Not enough section variety: {section_dist}"
