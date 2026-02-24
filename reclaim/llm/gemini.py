"""
Gemini Model Manager - Singleton for shared model instance.

CODE-011: Provides a shared Gemini model instance to avoid duplicate
initialization in classifier and extractor, reducing memory usage.

Supports two backends:
  1. Vertex AI SDK (production, Cloud Run) — uses GOOGLE_CLOUD_PROJECT + service account
  2. google-generativeai (local dev) — uses GOOGLE_API_KEY
"""

from __future__ import annotations

import os
from functools import lru_cache

from reclaim.infrastructure.settings import GEMINI_LOCATION, GEMINI_MODEL, GOOGLE_CLOUD_PROJECT
from reclaim.observability.logging import get_logger

logger = get_logger(__name__)

# Track which backend is available so get_gemini_model_with_options can reuse it
_backend: str | None = None  # "vertexai" or "genai"


class GeminiInitializationError(RuntimeError):
    """Raised when Gemini model cannot be initialized."""


@lru_cache(maxsize=1)
def get_gemini_model():
    """
    Get or create shared Gemini model instance (no system instruction).

    CODE-011: Uses @lru_cache for thread-safe singleton pattern.
    Both ReturnabilityClassifier and ReturnFieldExtractor share this instance
    when no system instruction is needed.

    Tries Vertex AI SDK first (production). Falls back to google-generativeai
    with GOOGLE_API_KEY for local development.

    Returns:
        GenerativeModel: Shared Gemini model

    Raises:
        GeminiInitializationError: If model cannot be initialized
    """
    global _backend
    # Read env vars fresh (settings.py may have stale values if loaded before dotenv)
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or GOOGLE_CLOUD_PROJECT
    location = os.getenv("GEMINI_LOCATION", "") or GEMINI_LOCATION or "us-central1"

    # Try Vertex AI first (production / Cloud Run)
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        if not project:
            raise GeminiInitializationError("GOOGLE_CLOUD_PROJECT not set")

        vertexai.init(project=project, location=location)
        model = GenerativeModel(GEMINI_MODEL)
        _backend = "vertexai"

        logger.info(
            "Initialized Gemini model (Vertex AI): project=%s, location=%s, model=%s",
            project,
            location,
            GEMINI_MODEL,
        )

        return model

    except ImportError:
        logger.info("Vertex AI SDK not installed, trying google-generativeai fallback")

    # Fallback: google-generativeai with API key (local dev)
    try:
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise GeminiInitializationError(
                "Neither vertexai nor GOOGLE_API_KEY available. "
                "Install google-cloud-aiplatform or set GOOGLE_API_KEY."
            )

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        _backend = "genai"

        logger.info(
            "Initialized Gemini model (google-generativeai): model=%s",
            GEMINI_MODEL,
        )

        return model

    except ImportError as e:
        raise GeminiInitializationError(
            "No Gemini SDK available. Install google-cloud-aiplatform or google-generativeai."
        ) from e
    except Exception as e:
        logger.error("Failed to initialize Gemini model: %s", e)
        raise GeminiInitializationError(f"Failed to initialize Gemini: {e}") from e


def get_gemini_model_with_options(
    system_instruction: str | None = None,
) -> object:
    """Create a Gemini model instance with optional system instruction.

    System instructions are per-model-instance in the Gemini API, so when a
    system instruction is provided we create a fresh GenerativeModel. When
    no system instruction is needed, falls back to the cached singleton.

    Args:
        system_instruction: Optional system instruction for the model.

    Returns:
        GenerativeModel configured with the given options.
    """
    if system_instruction is None:
        return get_gemini_model()

    # Ensure the default model has been initialized (sets _backend)
    get_gemini_model()

    if _backend == "vertexai":
        from vertexai.generative_models import GenerativeModel

        return GenerativeModel(GEMINI_MODEL, system_instruction=system_instruction)
    else:
        import google.generativeai as genai

        return genai.GenerativeModel(GEMINI_MODEL, system_instruction=system_instruction)


def clear_model_cache() -> None:
    """
    Clear the cached model instance.

    Useful for testing or when reconfiguration is needed.
    """
    get_gemini_model.cache_clear()
    logger.info("Cleared Gemini model cache")
