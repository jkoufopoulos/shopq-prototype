"""

from __future__ import annotations

Feedback API endpoints for user corrections
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from mailq.api.routes.dashboard import render_dashboard
from mailq.concepts.feedback import FeedbackManager
from mailq.observability.logging import get_logger

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
logger = get_logger(__name__)

# Feedback manager instance (injected by main app)
feedback_manager: FeedbackManager | None = None


def set_feedback_manager(fm: FeedbackManager) -> None:
    """
    Inject feedback manager instance

    Side Effects:
        - Modifies global feedback_manager variable
    """
    global feedback_manager
    feedback_manager = fm


def _teach_rules_engine(
    from_field: str,
    subject: str,
    snippet: str,
    actual_labels: list[str],
    user_id: str,
) -> None:
    """
    Teach RulesEngine from user correction.

    This bridges the feedback endpoint to EmailClassifier.learn_from_correction(),
    ensuring user corrections update the rules table for the classification cascade.

    Side Effects:
        - Writes to rules table in mailq.db (via RulesEngine.learn_from_classification)
        - Logs learning events
    """
    from datetime import datetime

    from mailq.classification.classifier import get_classifier
    from mailq.storage.models import ParsedEmail, RawEmail

    if not actual_labels:
        logger.warning("No actual_labels provided, skipping RulesEngine learning")
        return

    try:
        # Create a minimal ParsedEmail for learn_from_correction
        base = RawEmail(
            message_id=f"feedback-{datetime.now().isoformat()}",
            thread_id=f"feedback-thread-{datetime.now().isoformat()}",
            received_ts=datetime.now().isoformat(),
            subject=subject,
            from_address=from_field,
            to_address="user@feedback.local",
            body=snippet,
        )
        parsed = ParsedEmail(base=base, body_text=snippet, body_html=None)

        # Get classifier and call learn_from_correction
        classifier = get_classifier()
        classifier.learn_from_correction(parsed, actual_labels, user_id)

        logger.info(
            "RulesEngine learned from feedback: %s → %s",
            from_field[:30],
            actual_labels[0] if actual_labels else "N/A",
        )

    except Exception as e:
        # Don't fail the request if RulesEngine learning fails
        # FeedbackManager already recorded the correction
        logger.warning("Failed to teach RulesEngine: %s", e)


class FeedbackInput(BaseModel):
    email_id: str = Field(..., min_length=1, max_length=500, description="Unique email identifier")
    user_id: str = Field(
        default="default", min_length=1, max_length=100, description="User identifier"
    )
    from_field: str = Field(
        ..., alias="from", min_length=1, max_length=500, description="Sender email address"
    )
    subject: str = Field(..., min_length=1, max_length=1000, description="Email subject line")
    snippet: str = Field(default="", max_length=5000, description="Email snippet/preview")
    predicted_labels: list[str] = Field(
        ..., min_length=1, description="Labels predicted by classifier"
    )
    actual_labels: list[str] = Field(
        ..., min_length=1, description="Actual labels provided by user"
    )
    predicted_result: dict = Field(..., description="Full predicted classification result")
    headers: dict | None = Field(default=None, description="Optional email headers")

    @field_validator("email_id")
    @classmethod
    def validate_email_id(cls, v: str) -> str:
        """Validate email_id is not empty

        Side Effects:
            None (pure validator - validates and transforms input only)
        """
        if not v or not v.strip():
            raise ValueError("email_id cannot be empty or whitespace-only")
        return v.strip()

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        """Validate subject is not empty

        Side Effects:
            None (pure validator - validates and transforms input only)
        """
        if not v or not v.strip():
            raise ValueError("subject cannot be empty or whitespace-only")
        return v.strip()

    @field_validator("predicted_labels", "actual_labels")
    @classmethod
    def validate_labels(cls, v: list[str]) -> list[str]:
        """Validate labels list is not empty

        Side Effects:
            None (pure validator - validates input only)
        """
        if not v:
            raise ValueError("Labels list cannot be empty")
        return v

    @field_validator("predicted_result")
    @classmethod
    def validate_predicted_result(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate predicted_result has required fields

        Side Effects:
            None (pure validator - validates input only)
        """
        if "type" not in v:
            raise ValueError("predicted_result missing required 'type' field")
        return v

    class Config:
        populate_by_name = True


@router.post("")
async def record_feedback(feedback: FeedbackInput) -> dict[str, Any]:
    """
    Record user correction for learning.

    This endpoint records user corrections and teaches the system to classify
    future emails from this sender correctly.

    Side Effects:
        - Writes to corrections table in mailq.db (via feedback_manager.record_correction)
        - Writes to learned_patterns table in mailq.db (FeedbackManager learning)
        - Writes to rules table in mailq.db (RulesEngine learning via EmailClassifier)
        - Updates feedback statistics
        - Sends telemetry events (if enabled)
    """
    import os

    from mailq.runtime.gates import feature_gates

    # Check if feedback is disabled (test mode)
    # Two ways to disable:
    # 1. Feature gate test_mode (runtime toggleable)
    # 2. FEEDBACK_DISABLED env var (legacy)
    if (
        feature_gates.is_enabled("test_mode")
        or os.getenv("FEEDBACK_DISABLED", "false").lower() == "true"
    ):
        return {
            "success": True,
            "message": "Feedback collection disabled (test mode)",
            "correction_id": None,
        }

    if not feedback_manager:
        raise HTTPException(status_code=500, detail="Feedback manager not initialized")

    try:
        # 1. Record correction in FeedbackManager (writes to corrections + learned_patterns)
        correction_id = feedback_manager.record_correction(
            email_id=feedback.email_id,
            user_id=feedback.user_id,
            from_field=feedback.from_field,
            subject=feedback.subject,
            snippet=feedback.snippet,
            predicted_labels=feedback.predicted_labels,
            actual_labels=feedback.actual_labels,
            predicted_result=feedback.predicted_result,
            headers=feedback.headers,
        )

        # 2. Also teach EmailClassifier's RulesEngine (writes to rules table)
        # This ensures the cascade (TypeMapper → RulesEngine → LLM) learns from corrections
        _teach_rules_engine(
            from_field=feedback.from_field,
            subject=feedback.subject,
            snippet=feedback.snippet,
            actual_labels=feedback.actual_labels,
            user_id=feedback.user_id,
        )

        return {
            "success": True,
            "correction_id": correction_id,
            "message": "Feedback recorded. System will learn from this correction.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {e!s}") from e


@router.get("/stats")
async def get_feedback_stats(user_id: str = "default") -> dict[str, Any]:
    """Get feedback statistics

    Side Effects:
        - Reads from corrections and learned_patterns tables in mailq.db
    """
    if not feedback_manager:
        raise HTTPException(status_code=500, detail="Feedback manager not initialized")

    try:
        stats = feedback_manager.get_correction_stats(user_id)
        patterns = feedback_manager.get_high_confidence_patterns()

        return {
            "stats": stats,
            "high_confidence_patterns": len(patterns),
            "patterns_preview": patterns[:5],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {e!s}") from e


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard() -> HTMLResponse:
    """Visual dashboard for feedback and learning

    Side Effects:
        - Reads from corrections and learned_patterns tables in mailq.db
    """
    if not feedback_manager:
        raise HTTPException(status_code=500, detail="Feedback manager not initialized")

    try:
        stats = feedback_manager.get_correction_stats()
        patterns = feedback_manager.get_high_confidence_patterns(min_support=3)
        recent = feedback_manager.get_recent_corrections(limit=20)
        top_senders = feedback_manager.get_top_corrected_senders(limit=10)

        return render_dashboard(stats, patterns, recent, top_senders)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render dashboard: {e!s}") from e


@router.get("/pending-rules")
async def get_pending_rules(user_id: str = "default") -> dict[str, Any]:
    """Get rules awaiting promotion

    Side Effects:
        - Reads from learned_patterns table in mailq.db
    """
    from mailq.classification.rules_manager import RulesManager

    rules_mgr = RulesManager()

    pending = rules_mgr.get_pending_rules(user_id)

    return {"pending_rules": pending, "count": len(pending)}
