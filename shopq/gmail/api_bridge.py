"""

from __future__ import annotations

API Bridge Adapter - Converts between API models and domain models

This adapter bridges the existing FastAPI (shopq/api.py) with the refactored
domain layer (domain/models.py, domain/classify.py).

Purpose:
- Convert EmailInput (API) → ParsedEmail (domain)
- Convert ClassifiedEmail (domain) → ClassificationResult (API)
- Maintain API compatibility while using refactored backend
"""

import hashlib
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError

from shopq.classification.mapper import compute_client_label
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event
from shopq.storage.classification import ClassificationContract
from shopq.storage.models import ClassifiedEmail, ParsedEmail, RawEmail

logger = get_logger(__name__)


def api_email_to_parsed(api_email: Any, email_id: str | None = None) -> ParsedEmail:
    """
    Convert API EmailInput to domain ParsedEmail.

    Args:
        api_email: EmailInput from FastAPI (has .subject, .snippet, .sender)
        email_id: Optional email ID (for tracking)

    Returns:
        ParsedEmail ready for classification
    """
    # Generate deterministic message_id if not provided
    if not email_id:
        content = f"{api_email.sender}{api_email.subject}{api_email.snippet}"
        email_id = hashlib.sha256(content.encode()).hexdigest()[:16]

    # Generate thread_id (same as message_id for single emails from API)
    thread_id = email_id

    # Use deterministic pseudo-timestamp derived from email_id for idempotency stability
    digest = hashlib.sha256(email_id.encode()).hexdigest()
    seconds = int(digest[:8], 16) % 86400  # Fit within a day for readability
    received_ts = (datetime(1970, 1, 1) + timedelta(seconds=seconds)).isoformat() + "Z"

    # Create RawEmail (base)
    base = RawEmail(
        message_id=email_id,
        thread_id=thread_id,
        received_ts=received_ts,
        subject=api_email.subject,
        from_address=api_email.sender,
        to_address="api@shopq.com",  # Placeholder for API emails
        body=api_email.snippet,  # Use snippet as body for API emails
    )

    # Create ParsedEmail
    parsed = ParsedEmail(base=base, body_text=api_email.snippet, body_html=None)

    counter("api_bridge.email_converted")
    return parsed


def classified_to_api_result(classified: ClassifiedEmail) -> dict[str, Any]:
    """
    Convert domain ClassifiedEmail to API ClassificationResult.

    Args:
        classified: ClassifiedEmail from domain layer

    Returns:
        Dict matching ClassificationResult schema for API response

    Side Effects:
        Validates result against ClassificationContract, logs validation failures
    """
    # Use computed gmail_labels from ClassifiedEmail (via mapper)
    labels = classified.gmail_labels
    labels_conf = classified.gmail_labels_conf

    # Compute client_label from type + attention (single source of truth)
    # This is the UI-facing categorization: receipts, action-required, messages, everything-else
    # Note: Uses attention (action_required/none), NOT importance (critical/time_sensitive/routine)
    client_label = compute_client_label(classified.category, classified.attention)

    # Get decider and reason from model (set by EmailClassifier)
    decider = classified.decider
    reason = classified.reason

    # Build API result with dimension-specific confidence scores
    # Note: domains/domain_conf removed - not used in 4-label system
    result = {
        "message_id": classified.parsed.base.message_id,  # Contract field
        "id": classified.parsed.base.message_id,  # Legacy compat
        "from": classified.parsed.base.from_address,
        "labels": labels,
        "labels_conf": labels_conf,
        "type": classified.category,
        "type_conf": classified.type_confidence,  # Use type-specific confidence
        "attention": classified.attention,
        "attention_conf": classified.attention_confidence,  # Use attention-specific confidence
        "client_label": client_label,  # UI label: 4-bucket categorization
        "relationship": classified.relationship,
        "relationship_conf": classified.relationship_confidence,
        "decider": decider,  # From EmailClassifier cascade (type_mapper, rule, gemini, fallback)
        "reason": reason,  # From EmailClassifier (explains classification source)
        "importance": classified.importance,  # Computed from domain model property
        "importance_conf": classified.importance_confidence,  # Use LLM's importance_conf
        "confidence": classified.confidence,  # Overall confidence
        "model_name": "rules+llm",  # Model identifier
        "model_version": "v1.0",  # Version tracking
        "prompt_version": "refactored-2025-01",  # Prompt version
    }

    # Validate against ClassificationContract (API boundary validation)
    # This ensures API responses conform to the expected schema
    try:
        validated = ClassificationContract.model_validate(result)
        counter("api_bridge.validation_success")
        # Return normalized dict from contract
        return validated.normalized_dict
    except ValidationError as e:
        # Validation failure at API boundary is a serious issue
        # Log with full context for debugging
        logger.error(
            "API validation failed - ClassificationContract mismatch",
            extra={
                "message_id": classified.parsed.base.message_id,
                "validation_errors": e.errors(),
                "result_keys": list(result.keys()),
            },
        )
        log_event(
            "api_bridge.validation_failed",
            message_id=classified.parsed.base.message_id,
            error_count=len(e.errors()),
            first_error=str(e.errors()[0]) if e.errors() else "unknown",
        )
        counter("api_bridge.validation_failed")

        # Graceful degradation: Return original result
        # Note: This allows system to continue but may cause downstream issues
        # Consider alerting if failure rate exceeds threshold (e.g., >0.5%)
        return result


def batch_api_to_parsed(api_emails: list[Any]) -> list[ParsedEmail]:
    """
    Convert batch of API EmailInputs to ParsedEmails.

    Args:
        api_emails: List of EmailInput from FastAPI

    Returns:
        List of ParsedEmail for pipeline processing

    Side Effects:
        - Increments telemetry counter (via counter function)
    """
    parsed_emails = []

    for i, api_email in enumerate(api_emails):
        # Use index as email_id for batch processing
        email_id = f"api-email-{i:04d}"
        parsed = api_email_to_parsed(api_email, email_id=email_id)
        parsed_emails.append(parsed)

    counter("api_bridge.batch_converted", len(api_emails))
    return parsed_emails


def batch_classified_to_api_results(
    classified_emails: list[ClassifiedEmail],
) -> list[dict[str, Any]]:
    """
    Convert batch of ClassifiedEmails to API results.

    Args:
        classified_emails: List of ClassifiedEmail from domain layer

    Returns:
        List of dicts matching ClassificationResult schema
    """
    results = []

    for classified in classified_emails:
        result = classified_to_api_result(classified)
        results.append(result)

    counter("api_bridge.batch_results_converted", len(results))
    return results
