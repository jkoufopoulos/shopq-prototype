"""
Applies guardrail overrides to Gemini importance for digest sectioning.

Guardrails can override Gemini's importance output for safety-critical patterns:
- force_critical: OTPs, security alerts, fraud alerts
- force_non_critical: autopay confirmations, OAuth confirmations
- never_surface: calendar responses, canceled events

NOTE: mapper_rules.yaml is now deprecated - Gemini outputs importance directly.
Guardrails provide the only overrides needed on top of Gemini's output.

Key: BridgeImportanceMapper.map_email() applies guardrails → Gemini importance fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mailq.classification.importance_mapping.guardrails import GuardrailMatcher, GuardrailResult
from mailq.observability.logging import get_logger

# HIGH FIX: Import fallback to prevent pipeline breakage if structured logging fails
try:
    from mailq.observability.structured import get_logger as get_structured_logger

    s_logger = get_structured_logger()  # Structured logger for decision trails
except (ImportError, AttributeError):
    # Fallback: NoOp logger if structured logging unavailable
    pass

    class NoOpLogger:
        def log_event(self, *args: Any, **kwargs: Any) -> None:
            pass

        def map_decision(self, *args: Any, **kwargs: Any) -> None:
            pass

        def map_guardrail_applied(self, *args: Any, **kwargs: Any) -> None:
            pass

    s_logger = NoOpLogger()  # type: ignore[assignment]

logger = get_logger(__name__)


@dataclass
class BridgeDecision:
    """Result of importance mapping with guardrail application."""

    importance: str | None
    reason: str
    source: str
    rule_name: str | None = None
    guardrail: str | None = None
    missing_llm: bool = False


class BridgeImportanceMapper:
    """Applies guardrail overrides to Gemini importance.

    Simplified from previous version:
    - Removed mapper_rules.yaml logic (Gemini outputs importance directly)
    - Only applies guardrails (force_critical, force_non_critical, never_surface)
    - Falls back to Gemini importance when no guardrail matches
    """

    def __init__(
        self,
        guardrails_path: Path | None = None,
        guardrail_matcher: GuardrailMatcher | None = None,
        # Deprecated parameter - kept for backwards compatibility
        rules_path: Path | None = None,
    ):
        self.guardrails = guardrail_matcher or GuardrailMatcher(guardrails_path)
        if rules_path:
            logger.warning(
                "mapper_rules.yaml is deprecated - Gemini outputs importance directly. "
                "Guardrails provide the only overrides."
            )

    def map_email(self, email: dict) -> BridgeDecision:
        """Apply guardrails to email, returning override or Gemini importance.

        Args:
            email: Email dict with 'importance' from Gemini classification

        Returns:
            BridgeDecision with:
            - importance: guardrail override or Gemini importance
            - source: 'guardrail' or 'gemini'
            - guardrail: guardrail category if applied
        """
        email_id = email.get("id", "unknown")

        # Check guardrails (absolute overrides)
        guardrail = self.guardrails.evaluate(email)
        if guardrail:
            decision = self._decision_from_guardrail(guardrail)
            # STRUCTURED LOG: Guardrail applied
            s_logger.map_guardrail_applied(
                email_id=email_id,
                rule_name=guardrail.rule_name,
                importance=guardrail.importance,
            )
            return decision

        # No guardrail match - use Gemini importance (single source of truth)
        gemini_importance = email.get("importance", "routine")

        # Validate importance is a known value
        if gemini_importance not in ("critical", "time_sensitive", "routine"):
            logger.warning(
                "Unknown importance '%s' for email %s, defaulting to routine",
                gemini_importance,
                email_id,
            )
            gemini_importance = "routine"

        decision = BridgeDecision(
            importance=gemini_importance,
            reason=f"gemini importance: {gemini_importance}",
            source="gemini",
            rule_name=None,
        )

        # STRUCTURED LOG: Using Gemini importance
        s_logger.map_decision(
            email_id=email_id,
            importance=gemini_importance,
            source="gemini",
            rule_name=None,
        )

        return decision

    def _decision_from_guardrail(self, result: GuardrailResult) -> BridgeDecision:
        """Convert guardrail result to bridge decision."""
        return BridgeDecision(
            importance=result.importance,
            reason=result.reason,
            source="guardrail",
            rule_name=result.rule_name,
            guardrail=result.category,
        )


__all__ = ["BridgeImportanceMapper", "BridgeDecision"]
