"""

from __future__ import annotations

Feature Gates System

Allows easy A/B testing and rollback of features without code changes.
Toggle features via environment variables or API calls.

Usage:
    from mailq.runtime.gates import feature_gates

    if feature_gates.is_enabled('digest_urgency_grouping'):
        # Use new grouped version
    else:
        # Use old version
"""

import os


class FeatureGates:
    """
    Feature gate manager - controls which features are enabled/disabled.

    Gates can be controlled via:
    1. Environment variables (e.g., FEATURE_DIGEST_URGENCY_GROUPING=true)
    2. Runtime API calls (persisted in memory for the session)
    """

    def __init__(self) -> None:
        # Default feature states
        self._defaults: dict[str, bool] = {
            # Digest Generation
            # ACTIVE: Group digest by urgency (critical/time-sensitive)
            "digest_urgency_grouping": True,
            # ACTIVE: Template-based formatting (current implementation)
            "digest_template_based": True,
            # ACTIVE: Use real data as examples (vs hardcoded)
            "digest_dynamic_examples": True,
            # EXPERIMENTAL: Deterministic extraction + LLM JSON + Jinja template
            "digest_hybrid_v2": False,
            # EXPERIMENTAL: Hybrid renderer (entity cards + subject line fallback) - Phase 1
            "hybrid_renderer": True,  # ENABLED for Chrome extension testing
            # Classification
            "use_verifier": True,  # Use verifier LLM for suspicious classifications
            "use_rules_engine": True,  # Use rules engine for T0 matches
            "bridge_mode": True,  # Use bridge importance mapper (with guardrails + mapper rules)
            # Test mode: disable rules engine and feedback learning (ENABLED FOR TUNING)
            "test_mode": True,
            # Performance
            "cache_classifications": True,  # Cache classifications for 24 hours
            "batch_gmail_api": True,  # Batch Gmail API calls
            # Future gates (disabled by default)
            "experimental_entity_linking": False,  # Experimental: Better entity linking
            "experimental_smart_scheduling": False,  # Experimental: Smart event scheduling
            # NOTE: digest_pipeline_v2 removed Nov 2025 - V2 is now the only pipeline
        }

        # Runtime overrides (set via API)
        self._overrides: dict[str, bool] = {}

    def is_enabled(self, feature_name: str) -> bool:
        """
        Check if a feature is enabled.

        Priority:
        1. Runtime override (API call)
        2. Environment variable
        3. Default value

        Args:
            feature_name: Feature gate name (e.g., 'digest_urgency_grouping')

        Returns:
            True if enabled, False otherwise
        """
        # Check runtime override first
        if feature_name in self._overrides:
            return self._overrides[feature_name]

        # Check environment variable
        env_var = f"FEATURE_{feature_name.upper()}"
        env_value = os.getenv(env_var)
        if env_value is not None:
            return env_value.lower() in ("true", "1", "yes", "on")

        # Fall back to default
        return self._defaults.get(feature_name, False)

    def enable(self, feature_name: str) -> None:
        """
        Enable a feature at runtime

        Side Effects:
            - Modifies _overrides dict (in-memory state)
            - Changes feature flag behavior for subsequent checks
        """
        self._overrides[feature_name] = True

    def disable(self, feature_name: str) -> None:
        """
        Disable a feature at runtime

        Side Effects:
            - Modifies _overrides dict (in-memory state)
            - Changes feature flag behavior for subsequent checks
        """
        self._overrides[feature_name] = False

    def reset(self, feature_name: str) -> None:
        """
        Reset feature to default (remove override)

        Side Effects:
            - Removes key from _overrides dict (in-memory state)
            - Restores feature flag to default or environment variable value
        """
        if feature_name in self._overrides:
            del self._overrides[feature_name]

    def get_all_states(self) -> dict[str, bool]:
        """Get current state of all features"""
        return {name: self.is_enabled(name) for name in self._defaults}

    def get_config(self) -> dict[str, dict[str, object]]:
        """Get full configuration including defaults and current state"""
        return {
            name: {
                "enabled": self.is_enabled(name),
                "default": self._defaults[name],
                "has_override": name in self._overrides,
                "env_var": f"FEATURE_{name.upper()}",
            }
            for name in self._defaults
        }


# Global singleton instance
feature_gates = FeatureGates()


# Convenience functions
def is_enabled(feature_name: str) -> bool:
    """Check if feature is enabled (convenience wrapper)"""
    return feature_gates.is_enabled(feature_name)
