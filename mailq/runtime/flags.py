"""
Feature Flag System for MailQ

Enables gradual rollout of new features with percentage-based and user-based targeting.

Side Effects:
    - Reads environment variables (FORCE_DIGEST_V2, DIGEST_V2_ROLLOUT_PERCENTAGE)
    - May write to logs if feature flag usage is tracked

Core Principles Applied:
    - P2: Side Effects Are Loud (documented in docstrings)
    - P3: The Compiler Is Your Senior Engineer (full type hints)
    - P4: Synchronizations Are Explicit (flag state is visible)
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from mailq.observability.logging import get_logger

logger = get_logger(__name__)


class FeatureFlags:
    """
    Feature flag system with percentage-based rollout and override support.

    Supports:
    - Percentage-based rollout (0-100%)
    - User-based targeting (consistent hashing)
    - Environment variable overrides (for testing/debugging)
    - Explicit enable/disable overrides

    Side Effects:
        - Reads environment variables on initialization
        - Logs feature flag checks if DEBUG mode enabled
    """

    def __init__(self) -> None:
        """Initialize feature flags from environment variables"""
        self.flags: dict[str, dict[str, Any]] = {
            "DIGEST_V2": {
                "enabled": self._get_env_bool("FORCE_DIGEST_V2", None),
                # Default 100% - V2 is production, V1 pending archive
                "rollout_percentage": self._get_env_int("DIGEST_V2_ROLLOUT_PERCENTAGE", 100),
                "description": "New concepts/ digest pipeline (V1 deprecated)",
            },
        }

        # Check if verbose logging is enabled
        self.verbose = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

    def is_enabled(
        self,
        flag_name: str,
        user_id: str | None = None,
        default: bool = False,
    ) -> bool:
        """
        Check if a feature flag is enabled for a given user.

        Args:
            flag_name: Name of the feature flag (e.g., "DIGEST_V2")
            user_id: Optional user identifier for consistent targeting
            default: Default value if flag not found

        Returns:
            True if feature is enabled, False otherwise

        Side Effects:
            - Logs flag check if DEBUG mode enabled

        Behavior:
            1. If explicit override exists (FORCE_DIGEST_V2=true/false), use it
            2. If user_id provided, use consistent hashing for percentage rollout
            3. If no user_id, use random percentage (not recommended for production)
            4. If flag not found, return default
        """
        if flag_name not in self.flags:
            if self.verbose:
                logger.warning(f"Feature flag '{flag_name}' not found, using default={default}")
            return default

        flag_config = self.flags[flag_name]

        # 1. Check explicit override (FORCE_DIGEST_V2=true/false)
        if flag_config["enabled"] is not None:
            enabled: bool = bool(flag_config["enabled"])
            if self.verbose:
                logger.info(
                    f"Feature '{flag_name}' explicitly {'enabled' if enabled else 'disabled'}"
                )
            return enabled

        # 2. Percentage-based rollout
        rollout_percentage = flag_config["rollout_percentage"]

        if rollout_percentage == 0:
            if self.verbose:
                logger.info(f"Feature '{flag_name}' disabled (0% rollout)")
            return False

        if rollout_percentage >= 100:
            if self.verbose:
                logger.info(f"Feature '{flag_name}' enabled (100% rollout)")
            return True

        # 3. Use consistent hashing for user-based targeting
        if user_id:
            # Hash user_id to get deterministic percentage (0-99)
            hash_value = int(hashlib.sha256(user_id.encode()).hexdigest(), 16)
            user_percentage = hash_value % 100
            enabled_by_hash: bool = user_percentage < rollout_percentage

            if self.verbose:
                logger.info(
                    f"Feature '{flag_name}' {'enabled' if enabled_by_hash else 'disabled'} "
                    f"for user {user_id[:8]}... (rollout={rollout_percentage}%)"
                )
            return enabled_by_hash

        # 4. No user_id - default to disabled for safety
        # (avoid non-deterministic behavior in production)
        if self.verbose:
            logger.warning(
                f"Feature '{flag_name}' check without user_id, defaulting to disabled "
                f"(rollout={rollout_percentage}% requires user_id for consistency)"
            )
        return False

    def get_all_flags(self) -> dict[str, dict[str, Any]]:
        """
        Get all feature flags and their current configuration.

        Returns:
            Dictionary of flag names to their configuration

        Side Effects:
            None (read-only)
        """
        return self.flags.copy()

    def _get_env_bool(self, key: str, default: bool | None) -> bool | None:
        """
        Get boolean from environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set

        Returns:
            True if value is "true"/"1"/"yes", False if "false"/"0"/"no", None if not set
        """
        value = os.getenv(key)
        if value is None:
            return default

        value_lower = value.lower()
        if value_lower in ("true", "1", "yes"):
            return True
        if value_lower in ("false", "0", "no"):
            return False
        logger.warning(f"Invalid boolean value for {key}={value}, using default={default}")
        return default

    def _get_env_int(self, key: str, default: int) -> int:
        """
        Get integer from environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set or invalid

        Returns:
            Integer value or default
        """
        value = os.getenv(key)
        if value is None:
            return default

        try:
            return int(value)
        except ValueError:
            logger.warning(f"Invalid integer value for {key}={value}, using default={default}")
            return default


# Global singleton instance
_feature_flags: FeatureFlags | None = None


def get_feature_flags() -> FeatureFlags:
    """
    Get global FeatureFlags singleton instance.

    Returns:
        Global FeatureFlags instance

    Side Effects:
        - Initializes singleton on first call (reads environment variables)
    """
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags()
    return _feature_flags


def is_enabled(flag_name: str, user_id: str | None = None, default: bool = False) -> bool:
    """
    Convenience function to check if a feature flag is enabled.

    Args:
        flag_name: Name of the feature flag (e.g., "DIGEST_V2")
        user_id: Optional user identifier for consistent targeting
        default: Default value if flag not found

    Returns:
        True if feature is enabled, False otherwise

    Side Effects:
        - Initializes FeatureFlags singleton on first call
        - Logs flag check if DEBUG mode enabled
    """
    return get_feature_flags().is_enabled(flag_name, user_id, default)
