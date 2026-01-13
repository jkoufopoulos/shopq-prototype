"""
Type-safe email classification orchestrator.

Implements the classification cascade:
    TypeMapper → RulesEngine → VertexGeminiClassifier → Fallback

This module unifies classification logic into a single conceptual room (P1)
with explicit stage dependencies (P4) and typed outputs (P3).

Pure classification - no side effects (P2). Learning is separate.
"""

from __future__ import annotations

from typing import Any

from shopq.classification.importance_mapping.guardrails import GuardrailMatcher
from shopq.classification.rules_engine import RulesEngine
from shopq.classification.type_mapper import get_type_mapper
from shopq.classification.vertex_gemini_classifier import VertexGeminiClassifier
from shopq.observability.confidence import LEARNING_MIN_CONFIDENCE
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter, log_event
from shopq.storage.models import ClassifiedEmail, ParsedEmail
from shopq.utils.email import extract_email_address

logger = get_logger(__name__)


class EmailClassifier:
    """
    Type-safe classification orchestrator.

    Cascade order (first match wins):
    1. TypeMapper - Deterministic rules (calendar invites, known senders)
    2. RulesEngine - User-learned patterns from previous classifications
    3. VertexGeminiClassifier - LLM with production prompts
    4. Fallback - Simple keyword matching (safety net)

    Example:
        >>> classifier = EmailClassifier()
        >>> email = ParsedEmail(...)
        >>> result = classifier.classify(email)
        >>> result.category  # 'event', 'notification', etc.
        >>> result.gmail_labels  # ['ShopQ-Everything-Else']
    """

    def __init__(self):
        """Initialize classifier with all cascade stages."""
        self.type_mapper = get_type_mapper()
        self.rules = RulesEngine()
        self.llm = VertexGeminiClassifier()
        self.guardrails = GuardrailMatcher()

        logger.info(
            "EmailClassifier initialized with TypeMapper, RulesEngine, "
            "VertexGeminiClassifier, and GuardrailMatcher"
        )

    def classify(
        self,
        email: ParsedEmail,
        use_rules: bool = True,
        use_llm: bool = True,
    ) -> ClassifiedEmail:
        """
        Classify email using cascade: TypeMapper → Rules → LLM → Fallback.

        This is a pure function - no side effects (no DB writes, no learning).

        Args:
            email: Parsed email to classify
            use_rules: Whether to try rules engine (skip for fresh users)
            use_llm: Whether to try LLM (skip for testing or cost control)

        Returns:
            ClassifiedEmail with all dimensions populated
        """
        subject = email.base.subject
        snippet = email.body_text or ""
        from_field = email.base.from_address
        sender_email = extract_email_address(from_field)

        # Track LLM result for attention/importance
        llm_result: dict[str, Any] | None = None

        # Stage 1: Try TypeMapper (deterministic rules)
        type_hint = self.type_mapper.get_deterministic_type(
            sender_email=sender_email,
            subject=subject,
            snippet=snippet,
        )

        if type_hint:
            # TypeMapper matched - use for type, but still get attention/importance from LLM
            logger.info(
                "TypeMapper match: %s (%.0f%%) - %s",
                type_hint["type"],
                type_hint["confidence"] * 100,
                type_hint["matched_rule"],
            )
            counter("classification.type_mapper_hit")

            # Get attention/importance from LLM if enabled
            if use_llm:
                try:
                    llm_result = self.llm.classify(subject, snippet, from_field)
                except Exception as e:
                    logger.warning("LLM failed after TypeMapper match: %s", e)
                    llm_result = None

            # Build result with TypeMapper's type
            return self._build_classified_email(
                email=email,
                category=type_hint["type"],
                type_conf=type_hint["confidence"],
                llm_result=llm_result,
                decider="type_mapper",
                reason=f"TypeMapper: {type_hint['matched_rule']}",
            )

        # Stage 2: Try RulesEngine (user-learned patterns)
        if use_rules:
            rule_result = self.rules.classify(subject, snippet, from_field)

            if rule_result["source"] == "rule":
                logger.info(
                    "RulesEngine match: %s (%.0f%%)",
                    rule_result["category"],
                    rule_result["confidence"] * 100,
                )
                counter("classification.rules_hit")

                # Rules only give type - get attention/importance from LLM if enabled
                if use_llm:
                    try:
                        llm_result = self.llm.classify(subject, snippet, from_field)
                    except Exception as e:
                        logger.warning("LLM failed after RulesEngine match: %s", e)
                        llm_result = None

                # Convert rule category to type
                rule_type = self._rule_category_to_type(rule_result["category"])

                return self._build_classified_email(
                    email=email,
                    category=rule_type,
                    type_conf=rule_result["confidence"],
                    llm_result=llm_result,
                    decider="rule",
                    reason=f"RulesEngine: matched {from_field}",
                )

        # Stage 3: Try LLM (VertexGeminiClassifier)
        if use_llm:
            try:
                llm_result = self.llm.classify(subject, snippet, from_field)

                if llm_result and llm_result.get("type"):
                    logger.info(
                        "LLM classification: %s (%.0f%%) | %s",
                        llm_result["type"],
                        llm_result.get("type_conf", 0) * 100,
                        subject[:60],
                    )
                    counter("classification.llm_hit")

                    return self._build_classified_email(
                        email=email,
                        category=llm_result["type"],
                        type_conf=llm_result.get("type_conf", 0.7),
                        llm_result=llm_result,
                        decider=llm_result.get("decider", "gemini"),
                        reason=llm_result.get("reason", "LLM classification"),
                    )

            except Exception as e:
                logger.warning("LLM classification failed: %s", e)
                counter("classification.llm_error")
                log_event("classification.llm_error", error=str(e))

        # Stage 4: Fallback (keyword-based)
        logger.info("Using fallback classification for: %s", subject[:50])
        counter("classification.fallback")

        fallback_result = self._rules_based_fallback(email)
        return self._build_classified_email(
            email=email,
            category=fallback_result["category"],
            type_conf=fallback_result["confidence"],
            llm_result=None,
            decider="fallback",
            reason="Keyword-based fallback",
        )

    def classify_and_learn(
        self,
        email: ParsedEmail,
        user_id: str = "default",
    ) -> ClassifiedEmail:
        """
        Classify email and learn from high-confidence LLM results.

        Use this method when you want classification to update the rules engine
        for future emails from the same sender.

        Side Effects:
            - Writes to rules table if confidence >= LEARNING_MIN_CONFIDENCE
            - Only learns from LLM classifications (decider='gemini')
            - Does not learn from TypeMapper or existing rules

        Args:
            email: Parsed email to classify
            user_id: User ID for personalized rules

        Returns:
            ClassifiedEmail with all dimensions populated
        """
        # First, classify normally
        result = self.classify(email, use_rules=True, use_llm=True)

        # Only learn from LLM classifications with high confidence
        # Don't learn from type_mapper (deterministic) or existing rules
        if result.decider == "gemini" and result.confidence >= LEARNING_MIN_CONFIDENCE:
            try:
                # Get primary Gmail label for learning
                labels = result.gmail_labels
                primary_label = labels[0] if labels else "ShopQ-Everything-Else"

                self.rules.learn_from_classification(
                    _subject=email.base.subject,
                    _snippet=email.body_text or "",
                    from_field=email.base.from_address,
                    category=primary_label,
                    user_id=user_id,
                    confidence=result.confidence,
                )

                logger.info(
                    "Learned rule for %s → %s (%.0f%%)",
                    email.base.from_address[:30],
                    primary_label,
                    result.confidence * 100,
                )
                counter("classification.rule_learned")

            except Exception as e:
                logger.warning("Failed to learn from classification: %s", e)
                counter("classification.learn_error")

        return result

    def learn_from_correction(
        self,
        email: ParsedEmail,
        corrected_labels: list[str],
        user_id: str = "default",
    ) -> None:
        """
        Learn from user correction (explicit feedback).

        Use this when a user corrects a classification. User corrections
        are treated as high confidence (0.95).

        Side Effects:
            - Writes to rules table with USER_CORRECTION_CONFIDENCE
            - Creates or updates sender pattern

        Args:
            email: The email that was corrected
            corrected_labels: The correct Gmail labels from user
            user_id: User ID for personalized rules
        """
        from shopq.observability.confidence import USER_CORRECTION_CONFIDENCE

        if not corrected_labels:
            logger.warning("No corrected labels provided, skipping learning")
            return

        primary_label = corrected_labels[0]

        try:
            self.rules.learn_from_classification(
                _subject=email.base.subject,
                _snippet=email.body_text or "",
                from_field=email.base.from_address,
                category=primary_label,
                user_id=user_id,
                confidence=USER_CORRECTION_CONFIDENCE,
            )

            logger.info(
                "Learned correction: %s → %s (user feedback)",
                email.base.from_address[:30],
                primary_label,
            )
            counter("classification.correction_learned")

        except Exception as e:
            logger.warning("Failed to learn from correction: %s", e)
            counter("classification.correction_error")

    def _build_classified_email(
        self,
        email: ParsedEmail,
        category: str,
        type_conf: float,
        llm_result: dict[str, Any] | None,
        decider: str,
        reason: str,
    ) -> ClassifiedEmail:
        """
        Build ClassifiedEmail from classification results.

        Merges type from cascade stage with attention from LLM if available.
        Applies guardrails to override importance for safety-critical patterns.
        """
        # Default values
        attention = "none"
        attention_conf = 0.7
        llm_importance: str | None = None
        importance_conf = type_conf  # Default to type confidence
        relationship = "from_unknown"
        relationship_conf = 0.7

        # Use LLM result for attention/relationship if available
        if llm_result:
            attention = llm_result.get("attention", "none")
            attention_conf = llm_result.get("attention_conf", 0.7)
            llm_importance = llm_result.get("importance")
            importance_conf = llm_result.get("importance_conf", type_conf)
            relationship = llm_result.get("relationship", "from_unknown")
            relationship_conf = llm_result.get("relationship_conf", 0.7)

        # Apply guardrails to override importance for safety-critical patterns
        # This runs AFTER LLM classification to ensure security alerts, OTPs, etc.
        # are correctly escalated even if LLM misclassifies them
        subject = email.base.subject
        snippet = email.body_text or ""
        guardrail_result = self.guardrails.evaluate({"subject": subject, "snippet": snippet})

        if guardrail_result:
            logger.info(
                "Guardrail override: %s → %s (rule: %s)",
                llm_importance or "routine",
                guardrail_result.importance,
                guardrail_result.rule_name,
            )
            counter("classification.guardrail_applied")
            llm_importance = guardrail_result.importance
            importance_conf = 1.0  # Guardrails are high confidence
            # Append guardrail reason
            reason = f"{reason} | guardrail:{guardrail_result.rule_name}"

        # Build classified email with decider and reason as model fields
        return ClassifiedEmail(
            parsed=email,
            category=category,
            attention=attention,
            confidence=type_conf,
            type_confidence=type_conf,
            attention_confidence=attention_conf,
            importance_confidence=importance_conf,
            llm_importance=llm_importance,
            relationship=relationship,
            relationship_confidence=relationship_conf,
            decider=decider,
            reason=reason,
        )

    def _rule_category_to_type(self, category: str) -> str:
        """Convert old rule categories to type taxonomy."""
        # Strip ShopQ- prefix if present
        category_clean = category.replace("ShopQ-", "").replace("ShopQ/", "").lower()

        # Map to canonical types
        category_map = {
            "promotions": "promotion",
            "receipts": "receipt",
            "newsletters": "newsletter",
            "events": "event",
            "notifications": "notification",
            "messages": "message",
            "otp": "otp",
            # Handle singular forms too
            "promotion": "promotion",
            "receipt": "receipt",
            "newsletter": "newsletter",
            "event": "event",
            "notification": "notification",
            "message": "message",
        }

        return category_map.get(category_clean, "notification")

    def _rules_based_fallback(self, email: ParsedEmail) -> dict[str, Any]:
        """
        Simple keyword-based classification fallback.

        Used when TypeMapper, Rules, and LLM all fail or are disabled.
        Low confidence - just a safety net.
        """
        subject = email.base.subject.lower()
        snippet = (email.body_text or "").lower()
        text = f"{subject} {snippet}"

        # Check patterns in priority order
        if any(
            kw in text for kw in ["verification code", "otp", "one-time", "2fa", "sign-in code"]
        ):
            return {"category": "otp", "confidence": 0.7}

        if any(kw in text for kw in ["fraud", "suspicious", "unauthorized", "security alert"]):
            return {"category": "notification", "confidence": 0.7, "importance": "critical"}

        if any(kw in text for kw in ["receipt", "order confirmed", "payment received", "invoice"]):
            return {"category": "receipt", "confidence": 0.6}

        if any(kw in text for kw in ["sale", "% off", "discount", "deal", "limited time"]):
            return {"category": "promotion", "confidence": 0.65}

        if any(kw in text for kw in ["meeting", "invitation", "calendar", "rsvp", "event"]):
            return {"category": "event", "confidence": 0.6}

        if any(kw in text for kw in ["unsubscribe", "newsletter", "weekly", "digest"]):
            return {"category": "newsletter", "confidence": 0.6}

        # Default to notification
        return {"category": "notification", "confidence": 0.5}


def get_classifier() -> EmailClassifier:
    """Get or create singleton EmailClassifier instance."""
    global _classifier_instance
    if "_classifier_instance" not in globals() or _classifier_instance is None:
        _classifier_instance = EmailClassifier()
    return _classifier_instance


_classifier_instance: EmailClassifier | None = None
