"""Memory-enhanced email classifier using rules + LLM with Vertex AI"""

from __future__ import annotations

from typing import Any

from shopq.classification.mapper import map_to_gmail_labels, validate_classification_result
from shopq.classification.rules_engine import RulesEngine
from shopq.classification.type_mapper import get_type_mapper
from shopq.classification.vertex_gemini_classifier import VertexGeminiClassifier
from shopq.observability.confidence import LEARNING_MIN_CONFIDENCE
from shopq.observability.logging import get_logger
from shopq.storage.classification import get_valid_email_types
from shopq.utils.email import extract_email_address

logger = get_logger(__name__)


class MemoryClassifier:
    def __init__(self, category_manager=None):
        self.category_manager = category_manager
        self.enable_learning = True  # Control whether to learn new rules

        # Initialize rules engine (uses centralized database pool)
        self.rules = RulesEngine()

        # Initialize type mapper (global deterministic type rules)
        self.type_mapper = get_type_mapper()

        # Initialize Vertex AI Gemini classifier
        self.llm_classifier = VertexGeminiClassifier(self.category_manager)

        logger.info(
            "Memory classifier initialized with Vertex AI (multi-dimensional) + "
            "type mapper + connection pool"
        )

    def classify(
        self,
        subject: str,
        snippet: str,
        from_field: str,
        user_id: str = "default",
        user_prefs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Classify email using type mapper → rules → LLM, then map to Gmail labels.

        Classification flow:
        1. Try type mapper (global deterministic rules, e.g., calendar invites)
        2. Try user-specific rules (learned patterns)
        3. Use LLM (Gemini) for everything else

        Returns complete classification result with Gmail labels.
        """

        # Extract sender email for type mapper
        sender_email = extract_email_address(from_field)

        # Step 0: Try type mapper first (global deterministic rules)
        type_hint = self.type_mapper.get_deterministic_type(sender_email, subject, snippet)

        if type_hint:
            # Type mapper matched - use deterministic type
            logger.info(
                "Type mapper match: %s (%.0f%%) - %s",
                type_hint["type"],
                type_hint["confidence"] * 100,
                type_hint["matched_rule"],
            )

            # Still use LLM for domains/attention, but override type
            semantic_result = self.llm_classifier.classify(subject, snippet, from_field)

            # Validate LLM output before using
            if not validate_classification_result(semantic_result):
                logger.warning("LLM output validation failed in type_mapper path, using fallback")
                semantic_result = self._fallback_semantic(from_field)

            semantic_result["type"] = type_hint["type"]
            semantic_result["type_conf"] = type_hint["confidence"]
            semantic_result["decider"] = type_hint["decider"]

            # Append type mapper info to reason
            semantic_result["reason"] = (
                f"{semantic_result.get('reason', '')} "
                f"[type from type_mapper: {type_hint['matched_rule']}]"
            )
        else:
            # Step 1: Try user-specific rules
            rule_result = self.rules.classify(subject, snippet, from_field, user_id)

            # Step 2: If rule matched, convert to multi-dimensional format
            if rule_result["source"] == "rule":
                # Rules only give us type (old flat category)
                # Need to infer domain from the category name
                semantic_result = self._rule_to_semantic(rule_result, from_field)

                # Validate rule-generated result for consistency
                if not validate_classification_result(semantic_result):
                    logger.warning("Rule-to-semantic validation failed, using fallback")
                    semantic_result = self._fallback_semantic(from_field)

                logger.info(
                    "Rules match: %s (%.0f%%)",
                    rule_result["category"],
                    rule_result["confidence"] * 100,
                )
            else:
                # Step 3: Use LLM for new emails
                logger.info("No rule match, using Gemini...")
                semantic_result = self.llm_classifier.classify(subject, snippet, from_field)

                # LOG CONFIDENCE SCORES
                logger.info(
                    "Confidence for '%s': type=%.2f, domains=%s",
                    subject[:40],
                    semantic_result["type_conf"],
                    semantic_result.get("domain_conf", {}),
                )

                # Validate schema
                if not validate_classification_result(semantic_result):
                    logger.warning("Schema validation failed, using fallback")
                    semantic_result = self._fallback_semantic(from_field)

        # Step 4: Map semantics → Gmail labels
        user_prefs = user_prefs or {}
        mapping = map_to_gmail_labels(semantic_result, user_prefs)

        # Step 5: Add Gmail labels to result
        semantic_result["gmail_labels"] = mapping["labels"]
        semantic_result["gmail_labels_conf"] = mapping["labels_conf"]

        # Step 6: Learn from LLM result (if enabled and high confidence)
        # Now includes verifier-corrected classifications since they're validated
        # Skip learning if type was set by type mapper (deterministic, not learned)
        if (
            self.enable_learning
            and semantic_result["decider"] in ["gemini", "gemini_verifier"]
            and semantic_result["type_conf"] >= LEARNING_MIN_CONFIDENCE
        ):
            try:
                # Learn the primary Gmail label as the "category"
                primary_label = mapping["labels"][0] if mapping["labels"] else "Uncategorized"
                self.rules.learn_from_classification(
                    subject,
                    snippet,
                    from_field,
                    primary_label,  # Store Gmail label as category
                    user_id,
                    confidence=semantic_result["type_conf"],
                )
            except Exception as e:
                logger.warning("Failed to learn rule: %s", e)

        return semantic_result

    def classify_with_memory(
        self,
        subject: str,
        snippet: str,
        from_field: str,
        user_id: str = "default",
        user_prefs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Legacy compatibility helper"""
        return self.classify(subject, snippet, from_field, user_id=user_id, user_prefs=user_prefs)

    def reset_circuit_breaker(self) -> None:
        """Reset LLM circuit breaker state.

        Call at the start of eval runs to ensure clean state.

        Side Effects:
            Clears circuit breaker event history in underlying LLM classifier.
        """
        if hasattr(self.llm_classifier, "circuit_breaker"):
            self.llm_classifier.circuit_breaker.reset()
            logger.info("Circuit breaker reset for eval run")

    def _rule_to_semantic(self, rule_result: dict[str, Any], from_field: str) -> dict[str, Any]:
        """Convert old flat rule result to new multi-dimensional format"""

        category = rule_result["category"]  # e.g., "Promotions" or "ShopQ-Promotions"
        conf = rule_result["confidence"]

        # Strip ShopQ- prefix if present (handle both ShopQ- and ShopQ/ formats)
        category_clean = category.replace("ShopQ-", "").replace("ShopQ/", "")

        # Handle both flat and hierarchical labels
        parts = category_clean.split("/")

        if len(parts) == 2:
            # Hierarchical label like "Finance/Notification"
            domain_str = parts[0].lower()
            type_str = parts[1].lower()
        elif len(parts) == 1:
            # Flat label - need to infer BOTH domain AND type
            category_lower = category_clean.lower()

            # Map old flat categories to domain + type
            # NOTE: work/personal domains ONLY for messages
            # finance/shopping domains for all types
            category_mappings = {
                "promotions": ("shopping", "promotion"),
                "receipts": ("shopping", "receipt"),
                "newsletters": (
                    "unknown",
                    "newsletter",
                ),  # Newsletters usually don't need domain
                "events": ("unknown", "event"),  # Events usually don't need domain
                "notifications": ("unknown", "notification"),
                "messages": (
                    "unknown",
                    "message",
                ),  # Messages get work/personal from LLM
                "finance": ("finance", "notification"),  # Legacy: finance notifications
                "professional": (
                    "unknown",
                    "newsletter",
                ),  # Legacy: professional newsletters (no domain)
                "personal": (
                    "unknown",
                    "message",
                ),  # Legacy: personal messages (LLM will set)
                "shopping": ("shopping", "promotion"),  # Legacy: shopping promotions
            }

            if category_lower in category_mappings:
                domain_str, type_str = category_mappings[category_lower]
            else:
                # Unknown old category
                domain_str = "unknown"
                type_str = "uncategorized"
        else:
            domain_str = "unknown"
            type_str = "uncategorized"

        # Validate domain
        valid_domains = ["finance", "professional", "personal", "shopping", "unknown"]
        domain = domain_str if domain_str in valid_domains else "unknown"

        # Validate type - use canonical types from contracts
        valid_types = get_valid_email_types()
        email_type = type_str if type_str in valid_types else "uncategorized"

        # Build multi-dimensional result
        return {
            "type": email_type,
            "type_conf": conf,
            "domains": [domain] if domain != "unknown" else [],
            "domain_conf": {
                "finance": conf if domain == "finance" else 0.0,
                "professional": conf if domain == "professional" else 0.0,
                "personal": conf if domain == "personal" else 0.0,
                "shopping": conf if domain == "shopping" else 0.0,
                "unknown": conf if domain == "unknown" else 0.0,
            },
            "attention": "none",  # Rules don't track attention
            "attention_conf": 0.5,
            "relationship": "from_unknown",  # Rules don't track relationship
            "relationship_conf": 0.7,
            "decider": "rule",
            "reason": f"matched rule for {from_field}",
            "propose_rule": {
                "should_propose": False,
                "pattern": from_field.lower(),
                "kind": "exact",
                "support_count": 0,
            },
        }

    def _fallback_semantic(self, from_field: str) -> dict[str, Any]:
        """Safe fallback when everything fails"""
        return {
            "type": "uncategorized",
            "type_conf": 0.5,
            "domains": [],
            "domain_conf": {
                "finance": 0.0,
                "professional": 0.0,
                "personal": 0.0,
                "shopping": 0.0,
                "unknown": 1.0,
            },
            "attention": "none",
            "attention_conf": 0.5,
            "relationship": "from_unknown",
            "relationship_conf": 0.7,
            "decider": "fallback",
            "reason": "all_classification_failed",
            "propose_rule": {
                "should_propose": False,
                "pattern": from_field.lower(),
                "kind": "exact",
                "support_count": 0,
            },
        }

    def get_stats(self, user_id: str = "default") -> dict[str, Any]:
        """Get classification statistics"""
        return {
            "total_rules": self.rules.get_rule_count(user_id),
            "model_version": "mvp-v1-multidim",
        }
