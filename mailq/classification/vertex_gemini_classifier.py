"""Vertex AI Gemini - Multi-dimensional email classifier"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import vertexai
from dotenv import load_dotenv
from pydantic import ValidationError
from vertexai.generative_models import GenerativeModel

from mailq.concepts.feedback import FeedbackManager
from mailq.infrastructure.circuitbreaker import InvalidJSONCircuitBreaker
from mailq.llm.prompts import get_classifier_prompt
from mailq.llm.prompts.classifier_examples import STATIC_FEWSHOT_EXAMPLES
from mailq.observability.logging import get_logger
from mailq.observability.telemetry import log_event
from mailq.storage.classification import ClassificationContract
from mailq.utils.versioning import MODEL_NAME, MODEL_VERSION, PROMPT_VERSION

load_dotenv()
logger = get_logger(__name__)

# HIGH FIX: Import fallback to prevent pipeline breakage if structured logging fails
try:
    from mailq.observability.structured import EventType
    from mailq.observability.structured import get_logger as get_structured_logger

    s_logger = get_structured_logger()  # Structured logger for high-signal events
except Exception as e:
    # Fallback: NoOp logger that silently ignores structured log calls
    class NoOpLogger:
        def log_event(self, *args: object, **kwargs: object) -> None:
            pass

        def llm_call_error(self, *args: object, **kwargs: object) -> None:
            pass

        def llm_rate_limited(self, *args: object, **kwargs: object) -> None:
            pass

    s_logger = NoOpLogger()  # type: ignore[assignment]
    logger.warning(f"Structured logging disabled due to import error: {e}")


def sanitize_user_input(text: str, max_length: int = 500) -> str:
    """
    Sanitize user-controlled input to prevent LLM prompt injection attacks.

    Args:
        text: User input (email subject, snippet, from field)
        max_length: Maximum allowed length

    Returns:
        Sanitized text safe for LLM prompt inclusion

    Security measures:
    - Removes prompt injection markers (ignore, disregard, system, assistant)
    - Escapes template markers
    - Truncates to maximum length
    - Logs suspicious patterns for monitoring

    Side Effects:
        None (pure function)
    """
    if not text:
        return ""

    original_text = text

    # Remove common prompt injection patterns
    injection_patterns = [
        (
            r"(?i)(ignore|disregard|forget).*(previous|prior|above).*(instruction|directive|command|prompt)",
            "[REDACTED]",
        ),
        (r"(?i)system\s*:", ""),
        (r"(?i)assistant\s*:", ""),
        (r"(?i)you\s+are\s+now", "[REDACTED]"),
        (r"(?i)new\s+instructions?:", "[REDACTED]"),
    ]

    for pattern, replacement in injection_patterns:
        if re.search(pattern, text):
            logger.warning(
                "Potential prompt injection detected and sanitized: pattern=%s, original_length=%d",
                pattern[:50],
                len(text),
            )
            text = re.sub(pattern, replacement, text)

    # Escape template markers (prevent format string attacks)
    text = text.replace("{", "{{").replace("}", "}}")

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]
        logger.debug(
            "Truncated user input from %d to %d characters", len(original_text), max_length
        )

    return text


class VertexGeminiClassifier:
    def __init__(self, category_manager=None):
        self.category_manager = category_manager
        self.feedback_manager = FeedbackManager()  # NEW
        self.verbose = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

        # Vertex AI configuration from environment variables
        project_id = os.getenv("VERTEX_AI_PROJECT_ID", "mailq-467118")
        location = os.getenv("VERTEX_AI_LOCATION", "us-central1")

        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-2.0-flash")
        logger.info("Vertex Gemini 2.0 classifier initialized (multi-dimensional)")
        self.circuit_breaker = InvalidJSONCircuitBreaker()

        # Cache few-shot examples at init to avoid DB queries on every classify() call
        self._cached_fewshot_examples = self._build_fewshot_examples()
        logger.info("Few-shot examples cached at init")

    def _build_fewshot_examples(self) -> str:
        """Build few-shot examples from static + learned patterns

        Side Effects:
            - Reads from learned_patterns table in mailq.db (via feedback_manager)
        """

        # Start with static examples (imported from classifier_examples.py)
        examples = STATIC_FEWSHOT_EXAMPLES

        # Add learned examples from user feedback
        learned = self.feedback_manager.get_fewshot_examples(limit=5)

        if learned:
            examples += "\n\n--- LEARNED FROM YOUR CORRECTIONS ---\n\n"

            for i, ex in enumerate(learned, start=17):  # Start at 17 (after 16 static examples)
                examples += f"""Example {i} - Learned Pattern (seen {ex["support_count"]}x):
From: {ex["from_field"]}
Subject: {ex["subject"]}
Snippet: {ex["snippet"]}
{{
  "type": "{ex["type"]}",
  "type_conf": 0.95,
  "importance": "{ex.get("importance", "routine")}",
  "importance_conf": 0.90,
  "attention": "{ex.get("attention", "none")}",
  "attention_conf": 0.90,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}

"""

        return examples

    def classify(
        self,
        subject: str,
        snippet: str,
        from_field: str,
        email_id: str | None = None,
        normalized_input_digest: str | None = None,
    ) -> dict[str, Any]:
        """Classify using multi-dimensional schema with dynamic few-shot examples"""

        if self.circuit_breaker.is_tripped():
            log_event(
                "classification.llm.circuit_breaker",
                reason="invalid_json_rate",
                rate=self.circuit_breaker.invalid_rate(),
            )
            s_logger.log_event(
                EventType.LLM_FALLBACK_INVOKED,
                email_id=email_id,
                reason="circuit_breaker_tripped",
                invalid_rate=round(self.circuit_breaker.invalid_rate(), 2),
            )
            return self._fallback_result(from_field)

        # Use cached few-shot examples (built at init) for performance
        prompt = get_classifier_prompt(
            fewshot_examples=self._cached_fewshot_examples,
            from_field=sanitize_user_input(from_field, max_length=200),
            subject=sanitize_user_input(subject, max_length=500),
            snippet=sanitize_user_input(snippet, max_length=300),
        )

        attempt = 0
        prompt_suffix = ""
        while attempt < 2:
            attempt += 1
            try:
                response_text = self._call_model(prompt + prompt_suffix, max_tokens=500)
                # Parse JSON inside try block so JSONDecodeError triggers retry
                result = self._extract_json(response_text)
            except json.JSONDecodeError as exc:
                self.circuit_breaker.record(False)
                log_event(
                    "classification.llm.json_error",
                    error=str(exc),
                    attempt=attempt,
                    model=MODEL_NAME,
                )
                s_logger.log_event(
                    EventType.LLM_CALL_ERROR,
                    email_id=email_id,
                    error="JSONDecodeError",
                    attempt=attempt,
                    subject=subject,
                )
                if self.verbose:
                    logger.debug("Raw response (JSON error) attempt %s", attempt)
                if attempt == 1:
                    prompt_suffix = "\nReturn only the JSON object matching the schema."
                    continue
                s_logger.log_event(
                    EventType.LLM_FALLBACK_INVOKED,
                    email_id=email_id,
                    reason="json_decode_error_after_retries",
                )
                return self._fallback_result(from_field)
            contract_payload = {
                **result,
                "message_id": email_id or "unknown",
                "confidence": result.get("type_conf", 0.5),  # Use type_conf as confidence
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "prompt_version": PROMPT_VERSION,
                "normalized_input_digest": normalized_input_digest,
            }
            # Add defaults for importance if not in LLM response
            if "importance" not in contract_payload:
                contract_payload["importance"] = "routine"
            if "importance_conf" not in contract_payload:
                contract_payload["importance_conf"] = 0.5

            try:
                contract = ClassificationContract.model_validate(contract_payload)
            except ValidationError as exc:
                self.circuit_breaker.record(False)
                log_event(
                    "classification.llm.schema_error",
                    error=str(exc),
                    attempt=attempt,
                    model=MODEL_NAME,
                )
                s_logger.log_event(
                    EventType.LLM_CALL_ERROR,
                    email_id=email_id,
                    error="ValidationError",
                    attempt=attempt,
                    subject=subject,
                )
                if attempt == 1:
                    prompt_suffix = (
                        "\nReturn only the JSON object that strictly matches the schema."
                    )
                    continue
                s_logger.log_event(
                    EventType.LLM_FALLBACK_INVOKED,
                    email_id=email_id,
                    reason="schema_validation_error_after_retries",
                )
                return self._fallback_result(from_field)

            self.circuit_breaker.record(True)
            normalized_result = contract.model_dump()
            normalized_result["model_name"] = MODEL_NAME
            normalized_result["model_version"] = MODEL_VERSION
            normalized_result["prompt_version"] = PROMPT_VERSION
            normalized_result["normalized_input_digest"] = (
                normalized_input_digest or normalized_result.get("normalized_input_digest")
            )
            log_event(
                "classification.llm.success",
                model=MODEL_NAME,
                model_version=MODEL_VERSION,
                prompt_version=PROMPT_VERSION,
                normalized_input_digest=normalized_result["normalized_input_digest"],
            )
            # Structured logging: LLM success
            s_logger.log_event(
                EventType.LLM_CALL_OK,
                email_id=email_id,
                type=normalized_result["type"],
                type_conf=round(normalized_result.get("type_conf", 0), 2),
                attention=normalized_result.get("attention", "none"),
            )
            normalized_result["decider"] = normalized_result.get("decider", "gemini")
            normalized_result["reason"] = normalized_result.get(
                "reason", f"gemini_classification_{normalized_result['type']}"
            )
            normalized_result["from"] = from_field
            normalized_result["id"] = email_id
            return normalized_result

        return self._fallback_result(from_field)

    def _validate_and_normalize(self, result: dict, from_field: str) -> dict:
        """Validate schema and add missing fields.

        Classification uses: type, importance, attention only.
        domains/domain_conf removed from schema.
        """

        # Ensure all required fields exist
        if "type" not in result:
            result["type"] = "uncategorized"
        if "type_conf" not in result:
            result["type_conf"] = 0.5

        # Attention
        if "attention" not in result:
            result["attention"] = "none"
        if "attention_conf" not in result:
            result["attention_conf"] = 0.9

        # Relationship
        if "relationship" not in result:
            result["relationship"] = "from_unknown"
        if "relationship_conf" not in result:
            result["relationship_conf"] = 0.8

        # Propose rule - all values must be strings per ClassificationContract schema
        if "propose_rule" not in result or not isinstance(result["propose_rule"], dict):
            result["propose_rule"] = {
                "should_propose": "false",
                "pattern": from_field.lower(),
                "kind": "exact",
                "support_count": "0",
            }
        else:
            # Ensure all fields exist and are strings
            rule = result["propose_rule"]
            if "should_propose" not in rule:
                rule["should_propose"] = "false"
            elif isinstance(rule["should_propose"], bool):
                rule["should_propose"] = "true" if rule["should_propose"] else "false"
            if "pattern" not in rule:
                rule["pattern"] = from_field.lower()
            if "kind" not in rule:
                rule["kind"] = "exact"
            if "support_count" not in rule:
                rule["support_count"] = "1" if rule["should_propose"] == "true" else "0"
            elif isinstance(rule["support_count"], int):
                rule["support_count"] = str(rule["support_count"])

        # Add decider and reason if missing
        if "decider" not in result:
            result["decider"] = "gemini"
        if "reason" not in result:
            result["reason"] = f"gemini_classification_{result['type']}"

        return result

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from Gemini response with repair attempts.

        Handles common LLM JSON formatting issues:
        - Markdown code blocks
        - Missing commas between fields
        - Trailing commas
        """
        # Remove markdown code blocks
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error (attempting repair): %s", e)

            # Attempt 1: Find JSON object boundaries and extract
            # Note: Uses greedy match to handle nested JSON objects
            # ReDoS risk is mitigated by max_tokens=500 limit on LLM responses
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                json_text = match.group(0)
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

                # Attempt 2: Fix missing commas between fields
                repaired = re.sub(r'"\s*\n\s*"', '",\n"', json_text)
                repaired = re.sub(r"(\d+\.?\d*|true|false|null)\s*\n\s*\"", r'\1,\n"', repaired)
                repaired = re.sub(r'\}\s*\n\s*"', '},\n"', repaired)
                repaired = re.sub(r'\]\s*\n\s*"', '],\n"', repaired)

                try:
                    result = json.loads(repaired)
                    logger.info("JSON repair succeeded (missing commas fixed)")
                    return result
                except json.JSONDecodeError:
                    pass

                # Attempt 3: Remove trailing commas before } or ]
                repaired = re.sub(r",\s*([\}\]])", r"\1", repaired)
                try:
                    result = json.loads(repaired)
                    logger.info("JSON repair succeeded (trailing commas removed)")
                    return result
                except json.JSONDecodeError as repair_error:
                    logger.warning("JSON repair failed: %s", repair_error)

            raise

    def _validate_result(self, result: dict) -> bool:
        """Validate result matches schema.

        Classification uses: type, importance, attention only.
        """
        required_fields = [
            "type",
            "type_conf",
            "attention",
            "attention_conf",
            "relationship",
            "relationship_conf",
            "decider",
            "reason",
            "propose_rule",
        ]

        for field in required_fields:
            if field not in result:
                logger.warning("Missing field in result: %s", field)
                return False

        # Validate confidence scores are 0-1
        conf_fields = ["type_conf", "attention_conf", "relationship_conf"]
        for field in conf_fields:
            conf_value = result.get(field, -1)
            if not isinstance(conf_value, int | float) or not (0 <= conf_value <= 1):
                logger.warning(
                    "Invalid confidence for %s: %s (must be 0.0-1.0)",
                    field,
                    conf_value,
                )
                return False

        # Validate enums
        valid_types = [
            "newsletter",
            "notification",
            "receipt",
            "event",
            "promotion",
            "message",
            "uncategorized",
        ]
        if result["type"] not in valid_types:
            logger.warning("Invalid type: %s", result["type"])
            return False

        return True

    def classify_with_custom_prompt(
        self, prompt: str, temperature: float = 0.1, max_tokens: int = 300
    ) -> dict[str, Any]:
        """
        Classify using a custom prompt (for verifier, etc.)

        Args:
            prompt: Raw prompt string (bypasses few-shot construction)
            temperature: LLM temperature (default 0.1 for conservative)
            max_tokens: Max output tokens (default 300 for shorter responses)

        Returns:
            Parsed JSON response from LLM
        """
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "top_p": 0.8,
                    "max_output_tokens": max_tokens,
                },
            )

            result_text = response.text.strip()

            # Extract JSON from markdown if present
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            return json.loads(result_text)

        except json.JSONDecodeError as e:
            logger.warning("Verifier JSON parse error: %s", e)
            return self._fallback_result("custom_prompt")

    def _call_model(
        self, prompt: str, *, max_tokens: int = 500, max_retries: int = 3, timeout_seconds: int = 30
    ) -> str:
        """Call Vertex AI model with retry logic for transient failures.

        Side Effects:
            Makes HTTP request to Vertex AI API.

        Args:
            prompt: The prompt to send to the model
            max_tokens: Maximum output tokens
            max_retries: Number of retry attempts
            timeout_seconds: Request timeout in seconds (default 30s)
        """
        import concurrent.futures
        import time

        last_error = None
        for attempt in range(max_retries):
            try:
                # Use ThreadPoolExecutor with timeout to prevent hanging
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self.model.generate_content,
                        prompt,
                        generation_config={
                            "temperature": 0.2,
                            "top_p": 0.8,
                            "max_output_tokens": max_tokens,
                        },
                    )
                    try:
                        response = future.result(timeout=timeout_seconds)
                    except concurrent.futures.TimeoutError:
                        logger.error(
                            "Vertex AI call timed out after %ds (attempt %d/%d)",
                            timeout_seconds,
                            attempt + 1,
                            max_retries,
                        )
                        raise TimeoutError(
                            f"Vertex AI call timed out after {timeout_seconds}s"
                        ) from None

                result_text = response.text.strip()
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                return result_text

            except json.JSONDecodeError as e:
                # Don't retry JSON errors - those need circuit breaker
                logger.warning("Verifier JSON parse error: %s", e)
                if self.verbose:
                    logger.debug("Raw response: %s", response.text[:200])
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                    logger.warning(
                        "Vertex AI call failed (attempt %d/%d): %s. Retrying in %ds...",
                        attempt + 1,
                        max_retries,
                        e,
                        wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Vertex AI call failed after %d attempts: %s", max_retries, e)
                    raise last_error from e

        # Should never reach here, but satisfy type checker
        raise RuntimeError("Unexpected exit from retry loop")

    def _fallback_result(self, from_field: str) -> dict:
        """Return safe fallback when classification fails.

        Side Effects:
            Logs warning when fallback is used.
        """
        logger.warning("Using fallback result for: %s", from_field[:50])
        return {
            "type": "uncategorized",  # Valid EmailType for unknown classifications
            "type_conf": 0.5,
            "importance": "routine",  # Safe default importance
            "importance_conf": 0.5,
            "confidence": 0.3,  # Low confidence indicates fallback
            "attention": "none",
            "attention_conf": 0.5,
            "client_label": "everything-else",  # Required for GDS corrections
            "relationship": "from_unknown",
            "relationship_conf": 0.7,
            "decider": "gemini_fallback",  # Indicates fallback was used
            "reason": "failed_to_classify",
            "propose_rule": {
                "should_propose": "false",  # String to match ClassificationContract schema
                "pattern": from_field.lower() if from_field else "",
                "kind": "exact",
                "support_count": "0",  # String to match ClassificationContract schema
            },
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "prompt_version": PROMPT_VERSION,
        }
