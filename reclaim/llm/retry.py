"""Shared LLM call with retry logic.

Provides a single retry-decorated function for calling the Gemini model.
Both ReturnabilityClassifier (Stage 2) and ReturnFieldExtractor (Stage 3)
use this function. Each stage wraps it in its own try/except to implement
its specific final-failure policy (reject vs fallback).

CODE-003: Retries up to LLM_MAX_RETRIES times with exponential backoff.
CODE-004: Handles Vertex AI-specific exceptions (DeadlineExceeded, ServiceUnavailable).
"""

from __future__ import annotations

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from reclaim.config import LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS
from reclaim.llm.gemini import get_gemini_model
from reclaim.observability.logging import get_logger
from reclaim.observability.telemetry import counter

logger = get_logger(__name__)


@retry(
    stop=stop_after_attempt(LLM_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
    reraise=True,
)
def call_llm(prompt: str, counter_prefix: str = "llm") -> str:
    """Call LLM with retry and Vertex AI exception conversion.

    Args:
        prompt: The prompt to send to the model.
        counter_prefix: Telemetry counter prefix (e.g., "classifier", "extractor").

    Returns:
        The model's response text.

    Raises:
        TimeoutError: On deadline exceeded (retryable).
        ConnectionError: On service unavailable (retryable).
        Exception: On other errors (not retried, caller handles).
    """
    from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable

    model = get_gemini_model()

    try:
        response = model.generate_content(prompt)
        return response.text
    except DeadlineExceeded as e:
        counter(f"returns.{counter_prefix}.timeout")
        logger.warning("LLM call timed out after %ds", LLM_TIMEOUT_SECONDS)
        raise TimeoutError(f"LLM call timed out: {e}") from e
    except ServiceUnavailable as e:
        counter(f"returns.{counter_prefix}.service_unavailable")
        logger.warning("LLM service unavailable, will retry: %s", e)
        raise ConnectionError(f"LLM service unavailable: {e}") from e
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise
