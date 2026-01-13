"""
Enforces safety-critical classification rules that override LLM outputs.

Prevents dangerous misclassifications (e.g., OTP codes in digest, fraud alerts
missed) by applying regex patterns with strict precedence (never > force_critical
> force_non_critical).

Key: GuardrailMatcher.evaluate() checks email against YAML-defined rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from mailq.observability.logging import get_logger

logger = get_logger(__name__)

DEFAULT_GUARDRAIL_PATH = Path("config/guardrails.yaml")


@dataclass
class GuardrailRule:
    name: str
    description: str
    subject_terms: list[str]
    snippet_terms: list[str]
    snippet_none_terms: list[str]  # Exclusion terms - if any match, rule doesn't apply
    subject_regex: list[re.Pattern]
    snippet_regex: list[re.Pattern]

    @classmethod
    def from_dict(cls, payload: dict) -> GuardrailRule:
        subject_terms = [term.lower() for term in payload.get("subject_any", [])]
        snippet_terms = [term.lower() for term in payload.get("snippet_any", [])]
        snippet_none_terms = [term.lower() for term in payload.get("snippet_none", [])]
        subject_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in payload.get("subject_regex", [])
        ]
        snippet_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in payload.get("snippet_regex", [])
        ]
        return cls(
            name=payload.get("name", "guardrail"),
            description=payload.get("description", ""),
            subject_terms=subject_terms,
            snippet_terms=snippet_terms,
            snippet_none_terms=snippet_none_terms,
            subject_regex=subject_regex,
            snippet_regex=snippet_regex,
        )

    def matches(self, subject: str, snippet: str) -> bool:
        subject_lower = subject.lower()
        snippet_lower = snippet.lower()

        if self.subject_terms and not any(term in subject_lower for term in self.subject_terms):
            return False

        if self.snippet_terms and not any(term in snippet_lower for term in self.snippet_terms):
            return False

        # Exclusion check: if snippet contains any "none" terms, rule doesn't match
        # This allows excluding authorized sign-ins from security alerts
        if self.snippet_none_terms and any(
            term in snippet_lower for term in self.snippet_none_terms
        ):
            return False

        if self.subject_regex and not any(
            pattern.search(subject) for pattern in self.subject_regex
        ):
            return False

        return not (
            self.snippet_regex
            and not any(pattern.search(snippet) for pattern in self.snippet_regex)
        )


@dataclass
class GuardrailResult:
    importance: str
    reason: str
    rule_name: str
    category: str


class GuardrailMatcher:
    """Applies guardrail precedence: never_surface > force_critical > force_non_critical."""

    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_GUARDRAIL_PATH
        self.rules: dict[str, list[GuardrailRule]] = {
            "never_surface": [],
            "force_critical": [],
            "force_non_critical": [],
        }
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            logger.warning("Guardrail config %s not found; guardrails disabled.", self.path)
            return

        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.error("Failed to load guardrail config %s: %s", self.path, exc)
            return

        guardrails = data.get("guardrails", {})
        for category in self.rules:
            entries = guardrails.get(category, [])
            self.rules[category] = [GuardrailRule.from_dict(entry or {}) for entry in entries]

        logger.info(
            "Loaded guardrails from %s (%s)",
            self.path,
            {k: len(v) for k, v in self.rules.items()},
        )

    def evaluate(self, email: dict) -> GuardrailResult | None:
        subject = email.get("subject", "") or ""
        snippet = email.get("snippet", "") or ""

        for category in ("never_surface", "force_critical", "force_non_critical"):
            for rule in self.rules.get(category, []):
                if rule.matches(subject, snippet):
                    importance = self._importance_for_category(category)
                    reason = rule.description or f"guardrail:{category}:{rule.name}"
                    return GuardrailResult(
                        importance=importance,
                        reason=reason,
                        rule_name=rule.name,
                        category=category,
                    )

        return None

    @staticmethod
    def _importance_for_category(category: str) -> str:
        if category == "force_critical":
            return "critical"
        # never_surface and force_non_critical both drop to routine
        return "routine"


__all__ = ["GuardrailMatcher", "GuardrailResult"]
