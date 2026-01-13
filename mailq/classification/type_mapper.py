"""
Global deterministic type classification rules.

Ensures consistent type assignment across all users for known patterns
(e.g., calendar invitations from calendar-notification@google.com are always type=event).

Not user-specific - these are universal truths about email types.
Complements RulesEngine (which learns user-specific patterns).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from mailq.observability.logging import get_logger

logger = get_logger(__name__)


class TypeMapper:
    """
    Global deterministic type assignment rules.

    Philosophy:
    - High precision (≥95%), conservative coverage
    - Not user-specific (works day 1 for all users)
    - Fast (in-memory pattern matching, no DB/LLM calls)
    - Versioned (rules in config file under version control)

    Example:
        >>> mapper = TypeMapper()
        >>> result = mapper.get_deterministic_type(
        ...     "calendar-notification@google.com",
        ...     "Notification: Team Sync @ Wed Nov 13",
        ...     "You have a calendar event..."
        ... )
        >>> result["type"]
        'event'
    """

    def __init__(self, rules_path: str | Path | None = None):
        """
        Initialize TypeMapper with rules from YAML config.

        Args:
            rules_path: Path to type_mapper_rules.yaml (optional, uses default if None)
        """
        if rules_path is None:
            # Config is at repo root: config/type_mapper_rules.yaml
            # Path: type_mapper.py -> classification/ -> mailq/ -> repo root -> config/
            rules_path = Path(__file__).parent.parent.parent / "config" / "type_mapper_rules.yaml"

        self.rules = self._load_rules(rules_path)
        self.version = self.rules.get("version", "unknown")

        # Count total rules for logging
        rule_count = sum(
            len(type_rules.get("sender_domains", []))
            + len(type_rules.get("subject_patterns", []))
            + len(type_rules.get("body_phrases", []))
            for type_name, type_rules in self.rules.items()
            if isinstance(type_rules, dict)
        )

        logger.info(
            f"Type mapper initialized: version {self.version}, "
            f"{len([k for k in self.rules if k not in ['version', 'last_updated']])} types, "
            f"{rule_count} total rules"
        )

    def _load_rules(self, rules_path: str | Path) -> dict:
        """Load type rules from YAML config."""
        try:
            with open(rules_path) as f:
                config = yaml.safe_load(f)

            if not config:
                logger.warning(f"Type mapper config is empty: {rules_path}")
                return {}

            logger.info(f"Loaded type mapper rules version {config.get('version', 'unknown')}")
            return config

        except FileNotFoundError:
            logger.warning(f"Type mapper config not found: {rules_path}, using empty ruleset")
            return {}
        except Exception as e:
            logger.warning(f"Failed to load type mapper rules: {e}, using empty ruleset")
            return {}

    def get_deterministic_type(
        self, sender_email: str, subject: str, snippet: str, has_ics_attachment: bool = False
    ) -> dict[str, Any] | None:
        """
        Get deterministic type if email matches known patterns.

        Args:
            sender_email: Full sender email (e.g., "calendar-notification@google.com")
            subject: Email subject line
            snippet: Email snippet/preview text
            has_ics_attachment: Whether email has .ics calendar attachment

        Returns:
            {
                "type": "event",
                "confidence": 0.98,
                "matched_rule": "sender_domain: calendar-notification@google.com",
                "decider": "type_mapper"
            }
            or None if no match

        Example:
            >>> mapper = TypeMapper()
            >>> result = mapper.get_deterministic_type(
            ...     "calendar-notification@google.com",
            ...     "Notification: Meeting @ Wed",
            ...     "You have a calendar event"
            ... )
            >>> result["type"]
            'event'
        """
        sender_lower = sender_email.lower().strip()
        subject_lower = subject.lower().strip()
        snippet_lower = snippet.lower().strip()

        # Iterate through type categories (event, receipt, etc.)
        for type_name, type_rules in self.rules.items():
            # Skip metadata fields
            if type_name in ["version", "last_updated"] or not isinstance(type_rules, dict):
                continue

            matched_rule = None

            # Check sender domains
            for domain_pattern in type_rules.get("sender_domains", []):
                if self._matches_domain(sender_lower, domain_pattern):
                    matched_rule = f"sender_domain: {domain_pattern}"
                    break

            # Check subject patterns
            if not matched_rule:
                for pattern in type_rules.get("subject_patterns", []):
                    try:
                        if re.search(pattern, subject_lower, re.IGNORECASE):
                            matched_rule = f"subject_pattern: {pattern}"
                            break
                    except re.error as e:
                        logger.warning(f"Invalid regex pattern '{pattern}': {e}")
                        continue

            # Check body phrases
            if not matched_rule:
                for phrase in type_rules.get("body_phrases", []):
                    if phrase.lower() in snippet_lower:
                        matched_rule = f"body_phrase: {phrase}"
                        break

            # Check attachments
            if not matched_rule and has_ics_attachment:
                for ext in type_rules.get("attachment_extensions", []):
                    if ext == ".ics" or ext == ".vcs":
                        matched_rule = f"attachment: {ext}"
                        break

            # If any rule matched, return this type
            if matched_rule:
                confidence = type_rules.get("confidence", 0.95)

                logger.info(
                    f"Type mapper match: type={type_name}, "
                    f"confidence={confidence}, "
                    f"rule={matched_rule}"
                )

                return {
                    "type": type_name,
                    "confidence": confidence,
                    "matched_rule": matched_rule,
                    "decider": "type_mapper",
                }

        # No deterministic match
        return None

    def _matches_domain(self, email: str, pattern: str) -> bool:
        """
        Match email address against domain pattern (supports wildcards).

        Args:
            email: Full email address (lowercase)
            pattern: Domain pattern (may contain wildcards)

        Returns:
            True if email matches pattern

        Examples:
            >>> mapper = TypeMapper()
            >>> mapper._matches_domain(
            ...     "calendar-notification@google.com",
            ...     "calendar-notification@google.com"
            ... )
            True

            >>> mapper._matches_domain(
            ...     "calendar-notification@google.com",
            ...     "*@google.com"
            ... )
            True

            >>> mapper._matches_domain(
            ...     "user@gmail.com",
            ...     "*@google.com"
            ... )
            False
        """
        pattern = pattern.lower()

        # Exact match
        if pattern == email:
            return True

        # Wildcard pattern
        if "*" in pattern:
            # Convert wildcard pattern to regex
            # Escape special regex chars except *
            regex_pattern = re.escape(pattern).replace(r"\*", ".*")
            return bool(re.match(f"^{regex_pattern}$", email))

        return False


# Singleton instance (loaded once at startup)
_type_mapper_instance: TypeMapper | None = None


def get_type_mapper() -> TypeMapper:
    """
    Get singleton TypeMapper instance.

    Loads rules from config/type_mapper_rules.yaml on first call,
    then reuses the same instance.

    Returns:
        TypeMapper instance

    Example:
        >>> mapper = get_type_mapper()
        >>> result = mapper.get_deterministic_type(...)
    """
    global _type_mapper_instance
    if _type_mapper_instance is None:
        _type_mapper_instance = TypeMapper()
    return _type_mapper_instance
