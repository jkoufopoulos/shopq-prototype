"""

from __future__ import annotations

Prompt Management Module

Loads and manages LLM prompts from external text files.
This allows easy experimentation with different prompt versions without modifying code.
"""

import os
from pathlib import Path

# Get the prompts directory
PROMPTS_DIR = Path(__file__).parent

# Environment variable for A/B testing prompts
# Set SHOPQ_CLASSIFIER_PROMPT to use alternate prompt (e.g., "classifier_prompt_simplified")
CLASSIFIER_PROMPT_NAME = os.getenv("SHOPQ_CLASSIFIER_PROMPT", "classifier_prompt")


class PromptLoader:
    """Load and cache prompt templates from files"""

    def __init__(self):
        self._cache = {}

    def load_prompt(self, prompt_name: str) -> str:
        """
        Load a prompt template from file.

        Args:
            prompt_name: Name of the prompt file (without .txt extension)

        Returns:
            Prompt template string
        """
        if prompt_name not in self._cache:
            prompt_path = PROMPTS_DIR / f"{prompt_name}.txt"

            if not prompt_path.exists():
                raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

            with open(prompt_path, encoding="utf-8") as f:
                self._cache[prompt_name] = f.read()

        return self._cache[prompt_name]

    def get_classifier_prompt(self, **kwargs) -> str:
        """
        Get the classifier prompt with variables injected.

        Args:
            fewshot_examples: Few-shot examples string
            from_field: Email sender
            subject: Email subject
            snippet: Email snippet

        Returns:
            Formatted prompt string
        """
        template = self.load_prompt(CLASSIFIER_PROMPT_NAME)
        return template.format(**kwargs)

    def get_verifier_prompt(self, **kwargs) -> str:
        """
        Get the verifier prompt with variables injected.

        Args:
            from_field: Email sender
            subject: Email subject
            snippet: Email snippet
            type: First classification type
            type_conf: Type confidence
            importance: First classification importance (critical/time_sensitive/routine)
            importance_conf: Importance confidence
            attention: First classification attention
            attention_conf: Attention confidence
            domains: Domains string
            reason: First classification reason
            features_str: Features string
            contradictions_str: Contradictions string

        Returns:
            Formatted prompt string
        """
        template = self.load_prompt("verifier_prompt")
        return template.format(**kwargs)

    def reload(self) -> None:
        """Clear cache and reload prompts from disk"""
        self._cache.clear()


# Global instance
_loader = PromptLoader()


def get_classifier_prompt(**kwargs) -> str:
    """Get classifier prompt (convenience function)"""
    return _loader.get_classifier_prompt(**kwargs)


def get_verifier_prompt(**kwargs) -> str:
    """Get verifier prompt (convenience function)"""
    return _loader.get_verifier_prompt(**kwargs)


def reload_prompts() -> None:
    """Reload all prompts from disk (convenience function)"""
    _loader.reload()
