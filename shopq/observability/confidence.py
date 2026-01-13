"""
Centralized Confidence Thresholds Configuration

All confidence-related thresholds for the ShopQ classification system.
Changes here propagate across backend and (via API) to frontend.

IMPORTANT: All thresholds are loaded from config/shopq_policy.yaml.
This module provides constants for backward compatibility but YAML is the source of truth.

🎯 Design Philosophy:
- Conservative classification: Prefer "Uncategorized" over incorrect labels
- High confidence required for automatic labeling
- Lower thresholds for learning (building rules over time)
- Verifier catches edge cases missed by initial classification
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from shopq.observability.logging import get_logger

logger = get_logger(__name__)


def _load_policy_config() -> dict[str, Any]:
    """
    Load configuration from shopq_policy.yaml.

    Side Effects:
        - Reads config/shopq_policy.yaml file from filesystem

    Returns:
        Dict with classification and verifier config sections
    """
    # Try multiple paths to find config file
    possible_paths = [
        Path(__file__).parent.parent.parent / "config" / "shopq_policy.yaml",
        Path(__file__).parent.parent / "config" / "shopq_policy.yaml",
        Path("config/shopq_policy.yaml"),
    ]

    for config_path in possible_paths:
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
                logger.debug("Loaded confidence config from %s", config_path)
                return config

    logger.warning("shopq_policy.yaml not found, using hardcoded defaults")
    return {}


# Load config once at module import time
_POLICY_CONFIG = _load_policy_config()
_CLASSIFICATION_CONFIG = _POLICY_CONFIG.get("classification", {})
_VERIFIER_CONFIG = _POLICY_CONFIG.get("verifier", {})

# ============================================================================
# CLASSIFICATION GATES (API Response Filtering)
# ============================================================================

# Type confidence threshold (lowered to enable verifier-first strategy)
# If type_conf < this value → Mark as "Uncategorized"
# Strategy: Lower gate (0.70) + verify almost everything (0.50-0.94) = higher accuracy
TYPE_CONFIDENCE_MIN = _CLASSIFICATION_CONFIG.get("min_type_conf", 0.70)

# Individual label confidence threshold
# If label_conf < this value → Filter out that label
LABEL_CONFIDENCE_MIN = _CLASSIFICATION_CONFIG.get("min_label_conf", 0.70)

# ============================================================================
# MAPPER THRESHOLDS (Semantic → Gmail Label Filtering)
# ============================================================================

# NOTE: These should match CLASSIFICATION_GATES above for consistency
TYPE_GATE = _CLASSIFICATION_CONFIG.get("type_gate", 0.70)
DOMAIN_GATE = _CLASSIFICATION_CONFIG.get("domain_gate", 0.70)
ATTENTION_GATE = _CLASSIFICATION_CONFIG.get("attention_gate", 0.70)

# ============================================================================
# LEARNING THRESHOLDS (Rules Engine)
# ============================================================================

# Minimum confidence to learn from LLM classification
# Low enough to build patterns, high enough to avoid noise
LEARNING_MIN_CONFIDENCE = _CLASSIFICATION_CONFIG.get("learning_min_confidence", 0.70)

# Confidence assigned to user-corrected rules (highest trust)
USER_CORRECTION_CONFIDENCE = _CLASSIFICATION_CONFIG.get("user_correction_confidence", 0.95)

# Confidence for rules created from consistent LLM classifications
LLM_RULE_CONFIDENCE = _CLASSIFICATION_CONFIG.get("llm_rule_confidence", 0.85)

# ============================================================================
# LLM CLASSIFIER INTERNAL THRESHOLDS
# ============================================================================

# Domain confidence boost thresholds (vertex_gemini_classifier.py)
DOMAIN_MIN_THRESHOLD = _CLASSIFICATION_CONFIG.get("domain_min_threshold", 0.60)
DOMAIN_BOOST_VALUE = _CLASSIFICATION_CONFIG.get("domain_boost_value", 0.70)

# ============================================================================
# VERIFIER THRESHOLDS (Verify-First Strategy)
# ============================================================================

# Confidence range that triggers verifier (WIDENED for verify-first strategy)
VERIFIER_LOW_CONFIDENCE = _VERIFIER_CONFIG.get("trigger_conf_min", 0.50)
VERIFIER_HIGH_CONFIDENCE = _VERIFIER_CONFIG.get("trigger_conf_max", 0.94)
# Strategy: Only skip verifier for 0.95+ confidence (detectors only)
# Triggers verifier if: VERIFIER_LOW_CONFIDENCE <= conf <= VERIFIER_HIGH_CONFIDENCE

# Minimum confidence delta to accept verifier correction
VERIFIER_CORRECTION_DELTA = 0.15

# ============================================================================
# DETECTOR CONFIDENCE VALUES (Frontend Rules)
# ============================================================================

# Detectors are high-precision patterns, always high confidence
DETECTOR_CONFIDENCE = {
    "otp": {
        "type_conf": 0.98,
        "attention_conf": 0.99,
        "domain_conf": 0.80,
        "relationship_conf": 0.70,
    },
    "receipt": {
        "type_conf": 0.92,
        "attention_conf": 0.90,
        "domain_conf": 0.85,
        "relationship_conf": 0.70,
    },
    "transaction": {
        "type_conf": 0.94,
        "attention_conf_default": 0.85,
        "attention_conf_amount": 0.95,
        "attention_conf_decline": 0.88,
        "domain_conf": 0.75,
        "relationship_conf": 0.70,
    },
    "bank_notification": {
        "type_conf": 0.96,
        "attention_conf": 0.94,
        "domain_conf": 0.92,
        "relationship_conf": 0.70,
    },
    "password_reset": {
        "type_conf": 0.93,
        "attention_conf": 0.88,
        "domain_conf": 0.75,
        "relationship_conf": 0.70,
    },
}

# ============================================================================
# DIGEST FILTERING
# ============================================================================

# Minimum confidence for "high confidence" digest section
DIGEST_HIGH_CONFIDENCE = 0.85

# ============================================================================
# LOGGING/TELEMETRY
# ============================================================================

# Threshold for flagging "low confidence" in logs
LOGGING_LOW_CONFIDENCE = 0.85

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_all_thresholds() -> dict[str, Any]:
    """
    Get all thresholds as a dictionary (for API exposure)

    Returns:
        Dict of all confidence thresholds
    """
    return {
        "classification": {
            "type_min": TYPE_CONFIDENCE_MIN,
            "label_min": LABEL_CONFIDENCE_MIN,
        },
        "mapper": {
            "type_gate": TYPE_GATE,
            "domain_gate": DOMAIN_GATE,
            "attention_gate": ATTENTION_GATE,
        },
        "learning": {
            "min_confidence": LEARNING_MIN_CONFIDENCE,
            "user_correction": USER_CORRECTION_CONFIDENCE,
            "llm_rule": LLM_RULE_CONFIDENCE,
        },
        "llm": {"domain_min": DOMAIN_MIN_THRESHOLD, "domain_boost": DOMAIN_BOOST_VALUE},
        "verifier": {
            "low_conf": VERIFIER_LOW_CONFIDENCE,
            "high_conf": VERIFIER_HIGH_CONFIDENCE,
            "correction_delta": VERIFIER_CORRECTION_DELTA,
        },
        "detectors": DETECTOR_CONFIDENCE,
        "digest": {"high_confidence": DIGEST_HIGH_CONFIDENCE},
        "logging": {"low_confidence": LOGGING_LOW_CONFIDENCE},
    }


def validate_thresholds() -> bool:
    """
    Validate that all thresholds are consistent and within valid ranges

    Raises:
        ValueError: If thresholds are inconsistent
        Side Effects:
            Modifies local data structures
    """
    errors = []

    # TYPE_GATE should match TYPE_CONFIDENCE_MIN for consistency
    if TYPE_GATE != TYPE_CONFIDENCE_MIN:
        errors.append(
            f"TYPE_GATE ({TYPE_GATE}) should match TYPE_CONFIDENCE_MIN ({TYPE_CONFIDENCE_MIN})"
        )

    # All thresholds should be between 0 and 1
    all_values = [
        TYPE_CONFIDENCE_MIN,
        LABEL_CONFIDENCE_MIN,
        TYPE_GATE,
        DOMAIN_GATE,
        ATTENTION_GATE,
        LEARNING_MIN_CONFIDENCE,
        USER_CORRECTION_CONFIDENCE,
        DOMAIN_MIN_THRESHOLD,
        DOMAIN_BOOST_VALUE,
        VERIFIER_LOW_CONFIDENCE,
        VERIFIER_HIGH_CONFIDENCE,
        VERIFIER_CORRECTION_DELTA,
    ]

    for val in all_values:
        if not (0.0 <= val <= 1.0):
            errors.append(f"Threshold {val} is outside valid range [0.0, 1.0]")

    # Verifier range should make sense
    if VERIFIER_LOW_CONFIDENCE >= VERIFIER_HIGH_CONFIDENCE:
        errors.append(
            f"VERIFIER_LOW_CONFIDENCE ({VERIFIER_LOW_CONFIDENCE}) "
            f"must be < VERIFIER_HIGH_CONFIDENCE ({VERIFIER_HIGH_CONFIDENCE})"
        )

    if errors:
        raise ValueError("Threshold validation failed:\n" + "\n".join(errors))

    return True


# Validate on import
try:
    validate_thresholds()
    logger.info("Confidence thresholds validated successfully")
except ValueError as e:
    logger.warning("Confidence threshold validation warning: %s", e)
