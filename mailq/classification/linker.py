"""

from __future__ import annotations

Span-Aware Entity Linker

Accurately detects and links entity spans in AI-generated text, handling:
- Case-insensitive matching
- Punctuation tolerance
- Multi-token entities
- Overlap resolution
- Fuzzy matching for paraphrases

Replaces naive substring matching with token-based span detection.
"""

import html
import re
from dataclasses import dataclass
from typing import Any

from mailq.observability.logging import get_logger

try:
    from rapidfuzz import fuzz

    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    from difflib import SequenceMatcher

    RAPIDFUZZ_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class Entity:
    """Entity to be linked in text"""

    name: str
    normalized_name: str
    url: str
    entity_type: str = "generic"
    priority: int = 0  # Higher priority wins in overlaps


@dataclass
class Span:
    """Detected entity span in text"""

    start_idx: int
    end_idx: int
    entity_name: str
    url: str
    confidence: float
    match_text: str
    entity_type: str = "generic"
    priority: int = 0

    def overlaps_with(self, other: "Span") -> bool:
        """Check if this span overlaps with another

        Side Effects:
            None (pure function - boolean comparison only)
        """
        return not (self.end_idx <= other.start_idx or self.start_idx >= other.end_idx)

    def length(self) -> int:
        """Get span length

        Side Effects:
            None (pure function - arithmetic only)
        """
        return self.end_idx - self.start_idx


class SpanAwareEntityLinker:
    """
    Sophisticated entity linker that finds correct spans in text using
    token-based fuzzy matching.
    """

    def __init__(
        self,
        case_insensitive: bool = True,
        fuzzy_threshold: float = 0.9,
        allow_overlap: bool = False,
        fallback_mode: str = "append",
        window_size: int = 7,  # Token window for fuzzy search
    ):
        self.case_insensitive = case_insensitive
        self.fuzzy_threshold = fuzzy_threshold
        self.allow_overlap = allow_overlap
        self.fallback_mode = fallback_mode
        self.window_size = window_size

    def normalize_text(self, text: str) -> str:
        """
        Normalize text for matching: lowercase, collapse whitespace.
        Preserves punctuation for span boundary detection.

        Side Effects:
            None (pure function - string transformation only)
        """
        if self.case_insensitive:
            text = text.lower()
        # Collapse multiple spaces
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def tokenize(self, text: str) -> list[tuple[str, int, int]]:
        """
        Tokenize text into (token, start_idx, end_idx) tuples.
        Preserves original positions for accurate span extraction.

        Side Effects: None (pure function - builds and returns list of tuples)
        """
        tokens = []
        # Match word tokens (alphanumeric + internal punctuation like apostrophes)
        for match in re.finditer(r"\b[\w']+\b", text):
            tokens.append((match.group(), match.start(), match.end()))
        return tokens

    def fuzzy_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate fuzzy similarity between two strings.
        Returns value between 0.0 and 1.0.

        Side Effects:
            None (pure function - string comparison only)
        """
        if RAPIDFUZZ_AVAILABLE:
            return fuzz.ratio(str1, str2) / 100.0
        return SequenceMatcher(None, str1, str2).ratio()

    def find_entity_spans(self, text: str, entities: list[Entity]) -> list[Span]:
        """
        Find all entity spans in text using fuzzy token window search.

        Side Effects: None (pure function - builds and returns list of Span objects)

        Algorithm:
        1. Tokenize text and entity names
        2. For each entity, slide window across text tokens
        3. Find best matching window ≥ fuzzy_threshold
        4. Expand to exact character boundaries
        """
        original_text = text
        normalized_text = self.normalize_text(text)
        tokens = self.tokenize(normalized_text)

        if not tokens:
            return []

        spans = []

        for entity in entities:
            # Normalize entity name
            entity_norm = self.normalize_text(entity.normalized_name or entity.name)
            entity_tokens = entity_norm.split()

            if not entity_tokens:
                continue

            # Find best matching window
            best_match: dict[str, Any] | None = None
            best_score = 0.0

            # Try multiple window sizes around entity token length
            entity_token_count = len(entity_tokens)

            for window_len in range(
                entity_token_count, min(entity_token_count + 3, self.window_size + 1)
            ):
                for i in range(len(tokens)):
                    # Get window of tokens
                    window_end = min(i + window_len, len(tokens))

                    # Skip if window is too small
                    if window_end - i < entity_token_count:
                        continue

                    window_tokens = [t[0] for t in tokens[i:window_end]]
                    window_text = " ".join(window_tokens)

                    # Calculate similarity
                    similarity = self.fuzzy_similarity(entity_norm, window_text)

                    # Prefer exact-length matches
                    score_bonus = 0.05 if window_len == entity_token_count else 0.0
                    adjusted_score = similarity + score_bonus

                    if similarity >= self.fuzzy_threshold and adjusted_score > best_score:
                        best_score = adjusted_score
                        # Get character boundaries from original text
                        start_char = tokens[i][1]
                        end_char = tokens[window_end - 1][2]

                        # Expand to include full entity span in original text
                        # This handles punctuation and case correctly
                        match_text = original_text[start_char:end_char]

                        best_match = {
                            "start": start_char,
                            "end": end_char,
                            "text": match_text,
                            "score": similarity,  # Use raw similarity for confidence
                        }

            # Create span if found
            if best_match:
                # Refine boundaries: trim trailing/leading punctuation
                match_text = best_match["text"]
                start = best_match["start"]
                end = best_match["end"]

                # Trim leading punctuation/whitespace
                leading_trim = len(match_text) - len(match_text.lstrip(".,;:!?'\" "))
                start += leading_trim
                match_text = match_text[leading_trim:]

                # Trim trailing punctuation/whitespace (but preserve full entity)
                # Only trim if it's clearly not part of entity name
                trailing_trim = len(match_text) - len(match_text.rstrip(".,;:!?'\" "))
                end -= trailing_trim
                match_text = (
                    match_text[: len(match_text) - trailing_trim] if trailing_trim else match_text
                )

                span = Span(
                    start_idx=start,
                    end_idx=end,
                    entity_name=entity.name,
                    url=entity.url,
                    confidence=best_score,
                    match_text=match_text,
                    entity_type=entity.entity_type,
                    priority=entity.priority,
                )
                spans.append(span)

        return spans

    def resolve_overlaps(self, spans: list[Span]) -> list[Span]:
        """
        Resolve overlapping spans by keeping highest priority/longest/highest confidence.

        Side Effects: None (pure function - filters and returns list of Span objects)

        Priority rules:
        1. Higher priority entity
        2. Longer span
        3. Higher confidence
        """
        if self.allow_overlap:
            return spans

        if not spans:
            return []

        # Sort by start position
        spans = sorted(spans, key=lambda s: s.start_idx)

        resolved = []
        i = 0

        while i < len(spans):
            current = spans[i]
            overlapping = [current]

            # Find all spans that overlap with current
            j = i + 1
            while j < len(spans) and spans[j].start_idx < current.end_idx:
                overlapping.append(spans[j])
                j += 1

            # Choose best span from overlapping group
            if len(overlapping) > 1:
                # Sort by priority, then length, then confidence
                best = max(overlapping, key=lambda s: (s.priority, s.length(), s.confidence))
                resolved.append(best)
                # Skip to end of overlapping group
                i = j
            else:
                resolved.append(current)
                i += 1

        return resolved

    def inject_links(self, text: str, spans: list[Span]) -> str:
        """
        Inject HTML anchor tags into text at detected spans.

        Ensures:
        - No nested links
        - Balanced tags
        - Original text preserved outside links

        Side Effects:
            None (pure function - string manipulation only)
        """
        if not spans:
            return text

        # Sort spans by position (descending) so we can inject from end to start
        # This preserves earlier span indices
        sorted_spans = sorted(spans, key=lambda s: s.start_idx, reverse=True)

        result = text
        for span in sorted_spans:
            # Extract parts
            before = result[: span.start_idx]
            match = span.match_text
            after = result[span.end_idx :]

            # HTML-escape the match text (in case it contains < or >)
            match_escaped = html.escape(match)

            # Build link
            link = f'<a href="{html.escape(span.url)}">{match_escaped}</a>'

            # Reconstruct
            result = before + link + after

        return result

    def validate_html(self, text: str) -> bool:
        """
        Validate that HTML is well-formed (balanced anchor tags).

        Side Effects:
            None (pure function - validation logic only)
        """
        # Count opening and closing tags
        open_count = text.count("<a ")
        close_count = text.count("</a>")

        if open_count != close_count:
            return False

        # Check for nested anchors (not allowed in HTML)
        # Simple check: no <a inside another <a>
        depth = 0
        for match in re.finditer(r"<a\s|</a>", text):
            if match.group().startswith("<a"):
                depth += 1
                if depth > 1:
                    return False
            else:
                depth -= 1
                if depth < 0:
                    return False

        return depth == 0

    def append_fallbacks(self, text: str, entities: list[Entity], found_entities: list[str]) -> str:
        """
        Append fallback links for entities that weren't matched in text.

        Side Effects: None (pure function - builds and returns string)

        Format: " ({Entity Name} View Email →)"
        """
        if self.fallback_mode != "append":
            return text

        fallbacks = []
        found_set = set(found_entities)

        for entity in entities:
            if entity.name not in found_set:
                fallback = (
                    f' (<a href="{html.escape(entity.url)}">'
                    f"{html.escape(entity.name)} View Email →</a>)"
                )
                fallbacks.append(fallback)

        if fallbacks:
            return text + "".join(fallbacks)

        return text

    def link_entities(
        self, text: str, entities: list[Entity], enable_fallback: bool = True
    ) -> dict[str, Any]:
        """
        Main entry point: link all entities in text.

        Side Effects: None (pure function - builds and returns dict with linked text)

        Returns:
        {
            'html_text': str,
            'spans': list[Span],
            'fallback_links': list[dict],
            'html_valid': bool,
            'stats': dict
        }
        """
        # Find entity spans
        spans = self.find_entity_spans(text, entities)

        # Resolve overlaps
        resolved_spans = self.resolve_overlaps(spans)

        # Inject links
        html_text = self.inject_links(text, resolved_spans)

        # Validate HTML
        html_valid = self.validate_html(html_text)

        # If invalid, fall back to original text
        if not html_valid:
            logger.warning("HTML validation failed, reverting to original text")
            html_text = text
            resolved_spans = []

        # Collect found entities
        found_entities = [span.entity_name for span in resolved_spans]

        # Append fallbacks for unmatched entities
        fallback_links = []
        if enable_fallback:
            for entity in entities:
                if entity.name not in found_entities:
                    fallback_links.append(
                        {
                            "entity_name": entity.name,
                            "url": entity.url,
                            "reason": f"no span ≥{self.fuzzy_threshold} similarity",
                        }
                    )

            html_text = self.append_fallbacks(html_text, entities, found_entities)

        # Statistics
        stats = {
            "total_entities": len(entities),
            "matched_entities": len(resolved_spans),
            "fallback_entities": len(fallback_links),
            "overlaps_resolved": len(spans) - len(resolved_spans),
            "correct_span_rate": len(resolved_spans) / len(entities) if entities else 0.0,
            "fallback_usage_rate": len(fallback_links) / len(entities) if entities else 0.0,
        }

        return {
            "html_text": html_text,
            "spans": [
                {
                    "start_idx": s.start_idx,
                    "end_idx": s.end_idx,
                    "entity_name": s.entity_name,
                    "url": s.url,
                    "confidence": s.confidence,
                    "match_text": s.match_text,
                }
                for s in resolved_spans
            ],
            "fallback_links": fallback_links,
            "html_valid": html_valid,
            "stats": stats,
        }


# Convenience function
def link_entities_in_text(
    text: str,
    entities: list[dict],
    fuzzy_threshold: float = 0.9,
    enable_fallback: bool = False,
) -> str:
    """
    Convenience function to link entities in text.

    Args:
        text: Plain text
        entities: List of dicts with 'name', 'url' keys
        fuzzy_threshold: Minimum similarity for matching
        enable_fallback: Whether to append fallback links

    Returns:
        HTML text with linked entities

    Side Effects:
        None (pure function - wraps SpanAwareEntityLinker.link_entities)
    """
    # Convert dict entities to Entity objects
    entity_objects = [
        Entity(
            name=e.get("name", ""),
            normalized_name=e.get("normalized_name", e.get("name", "")),
            url=e.get("url", ""),
            entity_type=e.get("type", "generic"),
            priority=e.get("priority", 0),
        )
        for e in entities
        if e.get("name") and e.get("url")
    ]

    linker = SpanAwareEntityLinker(
        fuzzy_threshold=fuzzy_threshold,
        fallback_mode="append" if enable_fallback else "none",
    )

    result = linker.link_entities(text, entity_objects, enable_fallback=enable_fallback)
    return result["html_text"]
