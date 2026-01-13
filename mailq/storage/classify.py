"""
Email classification domain logic using EmailClassifier orchestrator.

This module provides the main interface for email classification:
- Uses EmailClassifier cascade: TypeMapper → Rules → LLM → Fallback
- Ensures digest correctness NEVER depends on LLM availability
- Never fails: cascade always returns a valid classification
"""

from __future__ import annotations

from mailq.classification.classifier import EmailClassifier, get_classifier
from mailq.storage.models import ClassifiedEmail, ParsedEmail

# Module-level classifier instance (singleton)
_classifier: EmailClassifier | None = None


def _get_classifier() -> EmailClassifier:
    """Get or create the module-level classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = get_classifier()
    return _classifier


def classify_email(
    email: ParsedEmail,
    use_llm: bool = True,
    use_rules: bool = True,
) -> ClassifiedEmail:
    """
    Classify email using the EmailClassifier cascade.

    Uses cascade: TypeMapper → RulesEngine → VertexGeminiClassifier → Fallback

    Args:
        email: Parsed email to classify
        use_llm: Whether to attempt LLM classification (for testing/cost control)
        use_rules: Whether to use learned rules (skip for fresh users)

    Returns:
        ClassifiedEmail (always succeeds, never raises)

    Safety guarantees:
    1. If TypeMapper matches → use deterministic result
    2. If rules match → use learned pattern
    3. If LLM enabled and succeeds → use LLM result
    4. Fallback: keyword-based classification (always works)
    """
    classifier = _get_classifier()
    return classifier.classify(email, use_rules=use_rules, use_llm=use_llm)


def batch_classify_emails(
    emails: list[ParsedEmail],
    use_llm: bool = True,
    use_rules: bool = True,
) -> list[ClassifiedEmail]:
    """
    Classify multiple emails sequentially.

    This is a simple sequential wrapper. For true batch optimization,
    use EmailClassifier.classify_batch() directly.

    Args:
        emails: List of parsed emails
        use_llm: Whether to attempt LLM classification
        use_rules: Whether to use learned rules

    Returns:
        List of classified emails (always same length as input)
    """
    classifier = _get_classifier()
    return [classifier.classify(email, use_rules=use_rules, use_llm=use_llm) for email in emails]
