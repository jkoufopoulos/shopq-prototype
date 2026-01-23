"""
Gemini Model Manager - Singleton for shared model instance.

CODE-011: Provides a shared Gemini model instance to avoid duplicate
initialization in classifier and extractor, reducing memory usage.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from shopq.infrastructure.settings import GEMINI_LOCATION, GEMINI_MODEL, GOOGLE_CLOUD_PROJECT
from shopq.observability.logging import get_logger

if TYPE_CHECKING:
    from vertexai.generative_models import GenerativeModel

logger = get_logger(__name__)


class GeminiInitializationError(RuntimeError):
    """Raised when Gemini model cannot be initialized."""


@lru_cache(maxsize=1)
def get_gemini_model() -> "GenerativeModel":
    """
    Get or create shared Gemini model instance.

    CODE-011: Uses @lru_cache for thread-safe singleton pattern.
    Both ReturnabilityClassifier and ReturnFieldExtractor share this instance.

    Returns:
        GenerativeModel: Shared Vertex AI Gemini model

    Raises:
        GeminiInitializationError: If model cannot be initialized

    Side Effects:
        - Initializes Vertex AI SDK on first call
        - Creates GenerativeModel instance
        - Logs initialization info
    """
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        project = GOOGLE_CLOUD_PROJECT or os.getenv("GOOGLE_CLOUD_PROJECT")
        location = GEMINI_LOCATION or "us-central1"

        if not project:
            raise GeminiInitializationError("GOOGLE_CLOUD_PROJECT not set")

        vertexai.init(project=project, location=location)
        model = GenerativeModel(GEMINI_MODEL)

        logger.info(
            "Initialized shared Gemini model: project=%s, location=%s, model=%s",
            project,
            location,
            GEMINI_MODEL,
        )

        return model

    except ImportError as e:
        logger.error("Vertex AI SDK not installed: %s", e)
        raise GeminiInitializationError(f"Vertex AI SDK not installed: {e}") from e
    except Exception as e:
        logger.error("Failed to initialize Gemini model: %s", e)
        raise GeminiInitializationError(f"Failed to initialize Gemini: {e}") from e


def clear_model_cache() -> None:
    """
    Clear the cached model instance.

    Useful for testing or when reconfiguration is needed.
    """
    get_gemini_model.cache_clear()
    logger.info("Cleared Gemini model cache")
