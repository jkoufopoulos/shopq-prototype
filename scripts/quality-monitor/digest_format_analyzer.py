#!/usr/bin/env python3
"""
Digest Format Analyzer

Analyzes actual digest HTML output against ideal format structure and
identifies format/categorization issues.

Compares:
- Section presence (CRITICAL, TODAY, COMING UP, WORTH KNOWING)
- Item categorization (are items in the right sections?)
- Format structure (categorized sections vs numbered list)
- Noise filtering (promotional/past events in main list)
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class DigestFormatAnalyzer:
    """Analyzes digest format and structure"""

    # Expected sections in ideal format
    EXPECTED_SECTIONS = {
        "CRITICAL": "🚨",
        "TODAY": "📦",
        "COMING_UP": "📅",
        "WORTH_KNOWING": "💼",
        "EVERYTHING_ELSE": "━━━━",
    }

    # Keywords that indicate misclassification
    NOISE_KEYWORDS = [
        "vote",
        "feedback",
        "survey",
        "poll",
        "share",
        "promotion",
        "sale",
        "deal",
        "offer",
        "discount",
    ]

    PAST_EVENT_KEYWORDS = [
        "yesterday",
        "last week",
        "has ended",
        "concluded",
        "adjourned",
        "finished",
        "completed",
    ]

    def __init__(self):
        self.issues = []

    def analyze_digest_html(self, html_content: str, input_emails: list[dict]) -> list[dict]:
        """
        Analyze digest HTML and return list of format issues

        Args:
            html_content: Raw HTML of digest
            input_emails: List of input email dicts with classification info

        Returns:
            List of issue dicts with: severity, pattern, evidence, root_cause, suggested_fix
        """
        self.issues = []

        # Extract digest structure
        structure = self._parse_digest_structure(html_content)

        # Check for expected sections
        self._check_section_presence(structure)

        # Check if using numbered list vs sections
        self._check_format_type(structure)

        # Check item categorization
        self._check_item_categorization(structure, input_emails)

        # Check for noise in featured items
        self._check_noise_in_featured(structure)

        # Check for past events in featured
        self._check_past_events_in_featured(structure)

        # Check for duplicate sections
        self._check_duplicate_sections(html_content)

        return self.issues

    def _parse_digest_structure(self, html_content: str) -> dict:
        """
        Parse digest HTML to extract structure

        Returns dict with:
        - format_type: 'sections' or 'numbered_list'
        - sections: dict of section_name -> items
        - featured_items: list of items in main area
        """
        structure = {
            "format_type": "unknown",
            "sections": {},
            "featured_items": [],
            "everything_else_count": 0,
        }

        # Check if digest uses emoji sections
        has_critical = "🚨" in html_content or "CRITICAL" in html_content.upper()
        has_today = "📦" in html_content or "TODAY" in html_content.upper()
        has_coming_up = "📅" in html_content or "COMING UP" in html_content.upper()
        has_worth_knowing = "💼" in html_content or "WORTH KNOWING" in html_content.upper()

        if has_critical or has_today or has_coming_up or has_worth_knowing:
            structure["format_type"] = "sections"
            # Extract items per section
            structure["sections"] = self._extract_sections(html_content)
        else:
            structure["format_type"] = "numbered_list"
            # Extract numbered items
            structure["featured_items"] = self._extract_numbered_items(html_content)

        # Extract "everything else" count
        everything_else_match = re.search(r"Plus.*?(\d+)\s+routine", html_content, re.IGNORECASE)
        if everything_else_match:
            structure["everything_else_count"] = int(everything_else_match.group(1))

        return structure

    def _extract_sections(self, html_content: str) -> dict[str, list[str]]:
        """Extract items from each emoji section"""
        sections = {}

        # Extract CRITICAL section
        critical_match = re.search(
            r"🚨\s*CRITICAL.*?:(.*?)(?=📦|📅|💼|━━━|$)", html_content, re.DOTALL
        )
        if critical_match:
            sections["CRITICAL"] = self._extract_bullet_items(critical_match.group(1))

        # Extract TODAY section
        today_match = re.search(r"📦\s*TODAY.*?:(.*?)(?=🚨|📅|💼|━━━|$)", html_content, re.DOTALL)
        if today_match:
            sections["TODAY"] = self._extract_bullet_items(today_match.group(1))

        # Extract COMING UP section
        coming_match = re.search(
            r"📅\s*COMING UP.*?:(.*?)(?=🚨|📦|💼|━━━|$)", html_content, re.DOTALL
        )
        if coming_match:
            sections["COMING_UP"] = self._extract_bullet_items(coming_match.group(1))

        # Extract WORTH KNOWING section
        worth_match = re.search(
            r"💼\s*WORTH KNOWING.*?:(.*?)(?=🚨|📦|📅|━━━|$)", html_content, re.DOTALL
        )
        if worth_match:
            sections["WORTH_KNOWING"] = self._extract_bullet_items(worth_match.group(1))

        return sections

    def _extract_bullet_items(self, section_text: str) -> list[str]:
        """Extract bullet point items from section"""
        items = []
        for line in section_text.split("\n"):
            line = line.strip()
            if line.startswith("•") or line.startswith("-"):
                # Remove bullet and clean
                item = re.sub(r"^[•\-]\s*", "", line).strip()
                if item:
                    items.append(item)
        return items

    def _extract_numbered_items(self, html_content: str) -> list[str]:
        """Extract numbered list items (1. 2. 3. etc)"""
        items = []
        # Match patterns like "1. Security alert" or "2. AutoPay for Brooklinen"
        for match in re.finditer(r"^\s*\d+\.\s+(.+?)(?=\s*\d+\.|$)", html_content, re.MULTILINE):
            item = match.group(1).strip()
            if item:
                items.append(item)
        return items

    def _check_section_presence(self, structure: dict):
        """Check if all expected sections are present"""
        if structure["format_type"] == "numbered_list":
            self.issues.append(
                {
                    "severity": "high",
                    "category": "digest_format",
                    "pattern": (
                        "Missing categorized sections (CRITICAL, TODAY, COMING UP, WORTH KNOWING)"
                    ),
                    "evidence": (
                        "Digest uses numbered list format instead of categorized sections"
                    ),
                    "root_cause": "Digest generator not using sectioned format template",
                    "suggested_fix": (
                        "Update digest generation to use categorized sections with emojis "
                        "(🚨 CRITICAL, 📦 TODAY, 📅 COMING UP, 💼 WORTH KNOWING)"
                    ),
                }
            )
            return

        # Check each expected section
        missing_sections = []
        for section_name in ["CRITICAL", "TODAY", "COMING_UP", "WORTH_KNOWING"]:
            if section_name not in structure["sections"] or not structure["sections"][section_name]:
                missing_sections.append(section_name.replace("_", " "))

        if missing_sections:
            self.issues.append(
                {
                    "severity": "high",
                    "category": "digest_format",
                    "pattern": f"Missing required sections: {', '.join(missing_sections)}",
                    "evidence": f"Sections present: {', '.join(structure['sections'].keys())}",
                    "root_cause": "Not all importance categories represented in digest output",
                    "suggested_fix": (
                        "Ensure digest includes all 4 sections even if empty, or populate missing: "
                        f"{', '.join(missing_sections)}"
                    ),
                }
            )

    def _check_format_type(self, structure: dict):
        """Check if using ideal sectioned format"""
        if structure["format_type"] == "numbered_list":
            num_items = len(structure["featured_items"])
            self.issues.append(
                {
                    "severity": "high",
                    "category": "digest_format",
                    "pattern": "Using numbered list instead of categorized sections",
                    "evidence": (
                        f"Digest shows numbered list 1-{num_items} instead of emoji sections"
                    ),
                    "root_cause": "Digest template not using sectioned format",
                    "suggested_fix": (
                        "Update digest template to use 4 sections: 🚨 CRITICAL, 📦 TODAY, "
                        '📅 COMING UP, 💼 WORTH KNOWING with separator ━━━━ for "Everything else"'
                    ),
                }
            )

    def _check_item_categorization(self, structure: dict, input_emails: list[dict]):
        """Check if items are in correct sections based on classification"""
        # TODO: This requires mapping featured items back to input emails
        # For now, skip if we don't have classification data

    def _check_noise_in_featured(self, structure: dict):
        """Check if promotional/noise items are in featured area"""
        featured = []
        if structure["format_type"] == "numbered_list":
            featured = structure["featured_items"]
        else:
            # Collect all items from sections
            for items in structure["sections"].values():
                featured.extend(items)

        noise_items = []
        for item in featured:
            item_lower = item.lower()
            for keyword in self.NOISE_KEYWORDS:
                if keyword in item_lower:
                    noise_items.append(item)
                    break

        if noise_items:
            examples = noise_items[:3]  # Show up to 3 examples
            examples_str = ", ".join(f'#{i + 1} "{ex}"' for i, ex in enumerate(examples))
            self.issues.append(
                {
                    "severity": "medium",
                    "category": "digest_format",
                    "pattern": "Promotional/noise items featured in main digest",
                    "evidence": f"Found {len(noise_items)} promotional items: {examples_str}",
                    "root_cause": "Importance classifier elevating promotional content",
                    "suggested_fix": (
                        "Add promotional keyword filters to importance classifier or move "
                        'to "Everything else" section'
                    ),
                }
            )

    def _check_past_events_in_featured(self, structure: dict):
        """Check if past events are in featured area"""
        featured = []
        if structure["format_type"] == "numbered_list":
            featured = structure["featured_items"]
        else:
            for items in structure["sections"].values():
                featured.extend(items)

        past_items = []
        for item in featured:
            item_lower = item.lower()
            for keyword in self.PAST_EVENT_KEYWORDS:
                if keyword in item_lower:
                    past_items.append(item)
                    break

        if past_items:
            examples = past_items[:3]
            past_examples = ", ".join(f'"{ex}"' for ex in examples)
            self.issues.append(
                {
                    "severity": "medium",
                    "category": "digest_format",
                    "pattern": "Past/concluded events featured in digest",
                    "evidence": f"Found {len(past_items)} past events: {past_examples}",
                    "root_cause": "Time-decay filter not removing expired events",
                    "suggested_fix": (
                        "Strengthen Phase 1 time-decay filter to remove events with past dates "
                        'or "yesterday/concluded" keywords'
                    ),
                }
            )

    def _check_duplicate_sections(self, html_content: str):
        """
        Check if content appears multiple times (duplicate sections)

        Detects:
        - Presence of category-summaries div (should not exist)
        - Same items appearing both inline and in styled boxes
        """
        # Check for the category-summaries div that creates duplicates
        if 'class="category-summaries"' in html_content:
            # Try to count how many items are duplicated
            import re

            # Count items in main sections (inline format)
            inline_items = len(
                re.findall(r"<li[^>]*>.*?\([0-9]+\)</a></li>", html_content, re.DOTALL)
            )

            # Count items in category-summaries (styled boxes)
            category_section = re.search(
                r'<div class="category-summaries">(.*?)</div>\s*</div>\s*<div class="footer">',
                html_content,
                re.DOTALL,
            )
            styled_items = 0
            if category_section:
                styled_items = len(
                    re.findall(r'<li class="entity-item">', category_section.group(1))
                )

            self.issues.append(
                {
                    "severity": "high",
                    "category": "digest_format",
                    "pattern": "Duplicate content sections detected",
                    "evidence": (
                        f'Found <div class="category-summaries"> with {styled_items} styled items '
                        f"duplicating {inline_items} inline items. Same content appears twice "
                        "in different formats."
                    ),
                    "root_cause": (
                        "CardRenderer._build_sections_html() generates redundant styled sections "
                        "even though narrative already includes inline emoji sections"
                    ),
                    "suggested_fix": (
                        'In shopq/card_renderer.py line 267-268, set sections_html = "" to prevent '
                        "duplicate generation, OR add conditional check: only generate styled "
                        "sections if narrative lacks inline sections"
                    ),
                }
            )


def analyze_digest_file(digest_path: Path, input_emails_path: Path | None = None) -> list[dict]:
    """
    Analyze a digest HTML file and return format issues

    Args:
        digest_path: Path to actual_digest_*.html file
        input_emails_path: Optional path to input_emails_*.json

    Returns:
        List of issue dicts
    """
    # Read digest HTML
    with open(digest_path) as f:
        html_content = f.read()

    # Read input emails if provided
    input_emails = []
    if input_emails_path and input_emails_path.exists():
        with open(input_emails_path) as f:
            input_emails = json.load(f)

    # Analyze
    analyzer = DigestFormatAnalyzer()
    return analyzer.analyze_digest_html(html_content, input_emails)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python digest_format_analyzer.py <digest_html_file> [input_emails_json]")
        sys.exit(1)

    digest_file = Path(sys.argv[1])
    input_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    issues = analyze_digest_file(digest_file, input_file)

    print(f"\n Found {len(issues)} format issues:\n")
    for i, issue in enumerate(issues, 1):
        print(f"{i}. [{issue['severity'].upper()}] {issue['pattern']}")
        print(f"   Evidence: {issue['evidence']}")
        print(f"   Fix: {issue['suggested_fix']}\n")
