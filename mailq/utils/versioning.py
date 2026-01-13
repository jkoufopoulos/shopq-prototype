"""
Model and Prompt Version Tracking

Central source of truth for model/prompt versions used in classification.
These versions MUST be logged with every classification to ensure:
- Reproducible baseline measurements
- Accurate A/B testing and shadow deployments
- Clear audit trail for debugging regressions

IMPORTANT: Changing these constants requires:
1. Update constants below
2. Add new row to VERSIONS.md at repo root
3. Run shadow period + golden set replay before deploying
4. Update baseline.md with new version results

See CONTRIBUTING.md for full version change workflow.
"""

from __future__ import annotations

# Model Configuration
# These should match the actual Gemini model being used in production
MODEL_NAME = "gemini-2.0-flash"
MODEL_VERSION = "2.0"

# Prompt Version
# Increment this whenever classifier prompts change in a way that could
# affect classification decisions (not just formatting/comments)
PROMPT_VERSION = "v1"

# Combined version string for logging
FULL_VERSION = f"{MODEL_NAME}/{MODEL_VERSION}/prompt-{PROMPT_VERSION}"


def get_version_metadata() -> dict[str, str]:
    """
    Get version metadata dict for logging.

    Returns:
        Dict with model_name, model_version, prompt_version fields
        matching ClassificationContract schema.
    """
    return {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "prompt_version": PROMPT_VERSION,
    }


def format_version_string() -> str:
    """
    Format version as human-readable string.

    Returns:
        Version string like "gemini-2.0-flash/2.0/prompt-v1"
    """
    return FULL_VERSION
