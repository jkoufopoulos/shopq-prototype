"""

from __future__ import annotations

Narrative Verifier - Fact-check generated narratives

Prevents hallucinations by verifying:
1. All numbers appear in source emails
2. All dates appear in source emails
3. All names/merchants appear in source emails

If verification fails, flag for human review or regeneration.
"""

import re

from mailq.contracts.entities import DigestEntity
from mailq.observability.logging import get_logger

logger = get_logger(__name__)


class NarrativeVerifier:
    """Verify narrative facts against source emails"""

    def __init__(self):
        pass

    def extract_numbers(self, text: str) -> set[str]:
        """
        Extract all numbers from text (amounts, flight numbers, etc.).

        Side Effects: None (pure function - builds and returns set of strings)

        Args:
            text: Text to extract from

        Returns:
            Set of number strings
        """
        # Match: $145, $145.00, 345, 95°, etc.
        patterns = [
            r"\$\d+(?:,\d{3})*(?:\.\d{2})?",  # Money: $145, $1,234.56
            r"\b\d+(?:\.\d+)?°",  # Temperature: 95°
            r"\b[A-Z]{2,3}\s*\d{1,4}\b",  # Flight numbers: UA345, Flight 345
            r"\b\d{1,4}\b",  # General numbers
        ]

        numbers = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            numbers.update(matches)

        return numbers

    def extract_dates(self, text: str) -> set[str]:
        """
        Extract date-related phrases from text.

        Side Effects: None (pure function - builds and returns set of strings)

        Args:
            text: Text to extract from

        Returns:
            Set of date strings
        """
        date_patterns = [
            r"\b(?:tomorrow|today|tonight)\b",
            r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}\b",
            r"\bdue\s+(?:on\s+)?(\w+)",
            r"\bend[s]?\s+(\w+)",
        ]

        dates = set()
        text_lower = text.lower()

        for pattern in date_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            dates.update([m.lower() for m in matches])

        return dates

    def extract_names(self, text: str) -> set[str]:
        """
        Extract merchant names, airlines, services from text.

        Side Effects: None (pure function - builds and returns set of strings)

        Args:
            text: Text to extract from

        Returns:
            Set of name strings
        """
        # Common merchants, airlines, services
        known_entities = {
            "united",
            "delta",
            "american",
            "southwest",
            "alaska",
            "target",
            "amazon",
            "walmart",
            "costco",
            "bank of america",
            "chase",
            "wells fargo",
            "spotify",
            "netflix",
            "apple",
            "google",
            "uber",
            "lyft",
            "doordash",
            "instacart",
        }

        text_lower = text.lower()
        found_names = set()

        for entity in known_entities:
            if entity in text_lower:
                found_names.add(entity)

        return found_names

    def verify(self, digest_text: str, entities: list[DigestEntity]) -> tuple[bool, list[str]]:
        """
        Verify digest text against source entities.

        Side Effects: None (pure function - validates and returns tuple)

        Args:
            digest_text: Generated narrative text
            entities: Source entities

        Returns:
            (is_valid, error_messages) tuple
        """
        errors = []

        # Extract facts from digest
        digest_numbers = self.extract_numbers(digest_text)
        digest_dates = self.extract_dates(digest_text)
        digest_names = self.extract_names(digest_text)

        # Extract facts from sources
        source_texts = []
        for entity in entities:
            source_texts.append(entity.source_subject)
            source_texts.append(entity.source_snippet)

        combined_source = " ".join(source_texts)

        source_numbers = self.extract_numbers(combined_source)
        source_dates = self.extract_dates(combined_source)
        source_names = self.extract_names(combined_source)

        # Verify numbers
        for number in digest_numbers:
            # Extract just digits for comparison
            digest_digits = re.sub(r"[^\d]", "", number)

            # Check if these digits appear in any source number
            found = False
            for source_num in source_numbers:
                source_digits = re.sub(r"[^\d]", "", source_num)
                if digest_digits in source_digits or source_digits in digest_digits:
                    found = True
                    break

            if not found and len(digest_digits) > 0:
                errors.append(f"Number '{number}' not found in source emails")

        # Verify dates (more lenient - 'tomorrow', 'Friday' are generic)
        critical_dates = {d for d in digest_dates if len(d) > 5}  # Skip generic day names
        for date in critical_dates:
            if date not in source_dates and date not in combined_source.lower():
                errors.append(f"Date '{date}' not found in source emails")

        # Verify names
        for name in digest_names:
            if name not in source_names and name not in combined_source.lower():
                errors.append(f"Name '{name}' not found in source emails")

        is_valid = len(errors) == 0

        return (is_valid, errors)

    def verify_with_correction(
        self, digest_text: str, entities: list[DigestEntity]
    ) -> tuple[bool, list[str], str]:
        """
        Verify and attempt to suggest corrections if issues found.

        Args:
            digest_text: Generated narrative
            entities: Source entities

        Returns:
            (is_valid, errors, corrected_text) tuple
        """
        is_valid, errors = self.verify(digest_text, entities)

        if is_valid:
            return (True, [], digest_text)

        # For MVP, just return errors without correction
        # Future: Use LLM to regenerate with corrections
        corrected_text = digest_text  # No correction yet

        return (False, errors, corrected_text)


def verify_narrative(digest_text: str, entities: list[DigestEntity]) -> bool:
    """
    Convenience function to verify narrative.

    Args:
        digest_text: Generated narrative
        entities: Source entities

    Returns:
        True if valid, False otherwise
    """
    verifier = NarrativeVerifier()
    is_valid, errors = verifier.verify(digest_text, entities)

    if not is_valid:
        logger.warning("Verification failed:")
        for error in errors:
            logger.warning("   - %s", error)

    return is_valid
