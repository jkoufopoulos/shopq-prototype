"""
Pytest configuration for GDS tests

Provides fixtures and configuration shared across all test files
"""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def gds_path():
    """Return path to Golden Dataset CSV"""
    return Path(__file__).parent / "golden_set" / "gds-1.0.csv"


@pytest.fixture(scope="session")
def skip_if_db_unavailable():
    """
    Skip tests if database is unavailable (e.g., during migration)

    This allows GDS tests to run even when DB is being migrated
    """
    try:
        from mailq.infrastructure.database import get_db_connection

        # Try to connect
        conn = get_db_connection()
        conn.close()

        # DB is available
        return False

    except Exception as e:
        # DB is unavailable - skip DB-dependent tests
        pytest.skip(f"Database unavailable (migration in progress?): {e}")


@pytest.fixture(scope="session")
def classifier_without_rules():
    """
    Initialize classifier without rules engine (for testing during DB migration)

    This allows testing type mapper + LLM even when rules DB is unavailable
    """
    try:
        from mailq.classification.memory_classifier import MemoryClassifier

        # Try to initialize normally first
        try:
            return MemoryClassifier()
        except Exception as db_error:
            # If DB fails, try to create a minimal classifier
            # that skips rules engine
            print(f"\n⚠️  RulesEngine unavailable: {db_error}")
            print("   Running tests with type mapper + LLM only")

            # Create a mock classifier that skips rules
            from mailq.classification.type_mapper import get_type_mapper
            from mailq.classification.vertex_gemini_classifier import VertexGeminiClassifier

            class MinimalClassifier:
                """Classifier without rules engine (for testing during migration)"""

                def __init__(self):
                    self.type_mapper = get_type_mapper()
                    self.llm_classifier = VertexGeminiClassifier()

                def classify(
                    self,
                    subject,
                    snippet,
                    from_field,
                    user_id="default",  # noqa: ARG002
                    user_prefs=None,  # noqa: ARG002
                ):
                    """Classify using type mapper + LLM only (no rules)"""
                    # Try type mapper first
                    type_hint = self.type_mapper.get_deterministic_type(
                        from_field, subject, snippet
                    )

                    if type_hint:
                        # Type mapper matched
                        result = self.llm_classifier.classify(subject, snippet, from_field)
                        result["type"] = type_hint["type"]
                        result["type_conf"] = type_hint["confidence"]
                        result["decider"] = "type_mapper"
                        return result
                    # Fall through to LLM
                    return self.llm_classifier.classify(subject, snippet, from_field)

            return MinimalClassifier()

    except ImportError as e:
        pytest.skip(f"Classifier modules not available: {e}")
