"""

from __future__ import annotations

Verifier endpoint for Phase 6: Selective second-pass LLM

Challenges first classification with "disagreeable rubric" prompt to catch
obvious errors (e.g., marking review requests as action_required).
"""

from typing import Any

from shopq.llm.prompts import get_verifier_prompt
from shopq.observability.logging import get_logger

logger = get_logger(__name__)


def build_verifier_prompt(
    email: dict[str, Any],
    first_result: dict[str, Any],
    features: dict[str, Any],
    contradictions: list[str],
) -> str:
    """
    Build disagreeable rubric prompt that challenges first classification.

    Prompt strategy:
    - Present first classification
    - Highlight contradictions/suspicious signals
    - Ask LLM to find flaws and correct if needed
    - Require specific rubric violations if correcting

    Args:
        email: {subject, snippet, from}
        first_result: First-pass classification
        features: Extracted features (has_order_id, has_otp, etc.)
        contradictions: List of detected contradictions

    Returns:
        Verifier prompt string

    Side Effects:
        None (pure function - builds local data structures only)
    """

    # Build feature list
    feature_list = []
    for key, value in features.items():
        if value:
            feature_list.append(key.replace("_", " "))

    features_str = ", ".join(feature_list) if feature_list else "none detected"
    contradictions_str = ", ".join(contradictions) if contradictions else "none"

    # Load prompt from external file
    return get_verifier_prompt(
        from_field=email["from"],
        subject=email["subject"],
        snippet=email["snippet"][:200],
        type=first_result["type"],
        type_conf=first_result.get("type_conf", 0),
        importance=first_result.get("importance", "routine"),
        importance_conf=first_result.get("importance_conf", 0),
        attention=first_result["attention"],
        attention_conf=first_result.get("attention_conf", 0),
        domains=", ".join(first_result.get("domains", [])),
        reason=first_result.get("reason", "No reason given"),
        features_str=features_str,
        contradictions_str=contradictions_str,
    )


def verify_classification(
    classifier: Any,
    email: dict[str, Any],
    first_result: dict[str, Any],
    features: dict[str, Any],
    contradictions: list[str],
) -> dict[str, Any]:
    """
    Run verifier LLM call with strict rubric validation prompt.

    Args:
        classifier: MemoryClassifier instance (contains llm_classifier)
        email: {subject, snippet, from}
        first_result: First-pass classification
        features: Extracted email features
        contradictions: Detected contradictions

    Returns:
        {
            verdict: "confirm" | "reject",
            correction: {...} if verdict=reject,
            rubric_violations: [...],
            confidence_delta: float,
            why_bad: str
        }
    """

    prompt = build_verifier_prompt(email, first_result, features, contradictions)

    try:
        # Call LLM with custom verifier prompt (lower temperature for conservative corrections)
        raw_result = classifier.llm_classifier.classify_with_custom_prompt(
            prompt=prompt,
            temperature=0.1,  # More conservative than first pass (0.2)
            max_tokens=300,
        )

        # Parse verifier response
        verdict = raw_result.get("verdict", "confirm")
        correction = raw_result.get("correction", None)
        rubric_violations = raw_result.get("rubric_violations", [])
        confidence_delta = raw_result.get("confidence_delta", 0.0)
        why_bad = raw_result.get("why_bad", "")

        # Normalize verdict: accept both "reject" (new) and "correct"
        # (old) for backwards compatibility
        if verdict == "correct":
            verdict = "reject"  # Normalize old naming to new naming

        # Defensive: ensure verdict is valid
        if verdict not in ["confirm", "reject"]:
            logger.warning("Invalid verifier verdict '%s'; defaulting to confirm", verdict)
            verdict = "confirm"

        # Defensive: if verdict=reject but no correction provided, fall back to confirm
        if verdict == "reject" and not correction:
            logger.warning("Verifier verdict=reject without correction; falling back to confirm")
            verdict = "confirm"

        return {
            "verdict": verdict,
            "correction": correction,
            "rubric_violations": rubric_violations,
            "confidence_delta": confidence_delta,
            "why_bad": why_bad,
        }

    except Exception as e:
        # On error, confirm first classification (fail-safe)
        logger.error("Verifier error: %s", e)
        return {
            "verdict": "confirm",
            "correction": None,
            "rubric_violations": [],
            "confidence_delta": 0.0,
            "why_bad": f"Verifier error: {str(e)[:100]}",
        }
