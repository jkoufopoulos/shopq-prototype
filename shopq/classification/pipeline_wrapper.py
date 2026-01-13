"""

from __future__ import annotations

Pipeline Wrapper - Wraps refactored pipeline for use by existing API

This module bridges the existing shopq/api.py with the refactored backend.
It provides a simple interface that matches the existing MemoryClassifier API.
"""

import os
from typing import Any

from shopq.gmail.api_bridge import api_email_to_parsed, classified_to_api_result
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter
from shopq.storage.classify import batch_classify_emails

logger = get_logger(__name__)


class RefactoredPipelineClassifier:
    """
    Wrapper around refactored pipeline that matches MemoryClassifier interface.

    This allows the existing API to use the refactored backend with minimal changes.
    """

    def __init__(self):
        """Initialize the classifier with configuration from environment."""
        # Check if LLM should be enabled (defaults to True to match production)
        self.use_llm = os.getenv("SHOPQ_USE_LLM", "true").lower() == "true"

        logger.info("RefactoredPipelineClassifier initialized (use_llm=%s)", self.use_llm)
        counter("pipeline_wrapper.initialized")

    def classify(
        self,
        subject: str,
        snippet: str,
        from_field: str,
        _user_prefs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Classify a single email using the refactored pipeline.

        Args:
            subject: Email subject
            snippet: Email snippet/preview
            from_field: Sender email address
            user_prefs: User preferences (optional)

        Returns:
            Classification result dict matching existing API format
        """

        # Create mock API email
        class MockEmail:
            def __init__(self, subject, snippet, sender):
                self.subject = subject
                self.snippet = snippet
                self.sender = sender

        api_email = MockEmail(subject, snippet, from_field)

        # Convert to domain model
        parsed_email = api_email_to_parsed(api_email)

        # Classify using refactored pipeline (single email)
        classified_emails = batch_classify_emails(
            emails=[parsed_email], use_llm=self.use_llm, use_rules=True
        )

        if not classified_emails:
            # Fallback if classification somehow fails
            counter("pipeline_wrapper.classify_failed")
            return self._create_fallback_result(from_field)

        classified = classified_emails[0]

        # Convert to API result format
        api_result = classified_to_api_result(classified)

        # Transform to match MemoryClassifier output format
        # Use actual decider from classifier cascade (type_mapper, rule, gemini, fallback)
        result = {
            "type": api_result["type"],
            "type_conf": api_result["type_conf"],
            "attention": api_result["attention"],
            "attention_conf": api_result["attention_conf"],
            "relationship": api_result["relationship"],
            "relationship_conf": api_result["relationship_conf"],
            "decider": api_result["decider"],  # Use actual decider from cascade
            "reason": api_result["reason"],
            "labels": api_result["labels"],  # API expects 'labels' field
            "labels_conf": api_result["labels_conf"],
            "gmail_labels": api_result["labels"],  # Also keep for backward compat
            "gmail_labels_conf": api_result["labels_conf"],
            "client_label": api_result.get("client_label"),  # UI label for extension mapper
        }

        counter("pipeline_wrapper.classify_success")
        return result

    def _create_fallback_result(self, _from_field: str) -> dict[str, Any]:
        """Create a safe fallback result if classification fails."""
        return {
            "type": "notification",
            "type_conf": 0.5,
            "attention": "none",
            "attention_conf": 0.5,
            "relationship": "from_unknown",
            "relationship_conf": 0.5,
            "decider": "fallback",
            "reason": "classification_error_fallback",
            "labels": ["ShopQ-Everything-Else"],
            "labels_conf": {"ShopQ-Everything-Else": 0.5},
            "gmail_labels": ["ShopQ-Everything-Else"],
            "gmail_labels_conf": {"ShopQ-Everything-Else": 0.5},
            "client_label": "everything-else",
        }


def classify_batch_refactored(
    emails: list[Any],
    use_llm: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Classify a batch of emails using the refactored pipeline.

    Args:
        emails: List of API EmailInput objects
        use_llm: Override use_llm setting (optional)

    Returns:
        List of classification results matching existing API format
    """
    if use_llm is None:
        use_llm = os.getenv("SHOPQ_USE_LLM", "true").lower() == "true"

    # Convert API emails to domain models
    parsed_emails = []
    for i, email in enumerate(emails):
        email_id = f"api-batch-{i:04d}"
        parsed = api_email_to_parsed(email, email_id=email_id)
        parsed_emails.append(parsed)

    # Classify using refactored pipeline with EmailClassifier cascade
    classified_emails = batch_classify_emails(emails=parsed_emails, use_llm=use_llm, use_rules=True)

    # Convert to API results
    results = []
    for classified in classified_emails:
        api_result = classified_to_api_result(classified)

        # Transform to match MemoryClassifier output format
        # Use actual decider from classifier cascade (type_mapper, rule, gemini, fallback)
        result = {
            "type": api_result["type"],
            "type_conf": api_result["type_conf"],
            "attention": api_result["attention"],
            "attention_conf": api_result["attention_conf"],
            "importance": api_result.get("importance", "routine"),
            "importance_conf": api_result.get("importance_conf", api_result["type_conf"]),
            "relationship": api_result["relationship"],
            "relationship_conf": api_result["relationship_conf"],
            "decider": api_result["decider"],  # Use actual decider from cascade
            "reason": api_result["reason"],
            "labels": api_result["labels"],  # API expects 'labels' field
            "labels_conf": api_result["labels_conf"],
            "gmail_labels": api_result["labels"],  # Also keep for backward compat
            "gmail_labels_conf": api_result["labels_conf"],
            "client_label": api_result.get("client_label"),  # UI label for extension mapper
            "from": api_result["from"],
        }
        results.append(result)

    counter("pipeline_wrapper.batch_classify_success", len(results))
    return results
