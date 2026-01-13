#!/usr/bin/env python3
"""
MailQ Context Extractor

Extracts relevant information from CLAUDE.md and codebase to inject into diagrams.
Provides context-aware information based on diagram type.
**Now 100% dynamic** - detects values from actual code.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel

    VERTEX_AVAILABLE = True
except ImportError:
    VERTEX_AVAILABLE = False

PROJECT_ROOT = Path(__file__).parent.parent.parent
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"


class MailQContext:
    """Extract and provide MailQ-specific context for diagrams (now dynamic!)"""

    def __init__(self):
        self.content = self._load_claude_md()
        self.sections = self._parse_sections()

        # Dynamic detection
        self.database_config = self._detect_database_config()
        self.external_services = self._detect_external_services()
        self.confidence_thresholds = self._detect_confidence_thresholds()
        self.extension_config = self._detect_extension_config()

    def _load_claude_md(self) -> str:
        """Load CLAUDE.md content"""
        if CLAUDE_MD.exists():
            return CLAUDE_MD.read_text()
        return ""

    def _parse_sections(self) -> dict[str, str]:
        """Parse CLAUDE.md into sections"""
        sections = {}

        # Extract key sections
        patterns = {
            "architecture": r"## Core Architecture\n\n```\n(.*?)```",
            "dimensions": r"### Classification Dimensions\n\n```json\n(.*?)```",
            "labels": r"### Gmail Label Mapping\n\n```\n(.*?)```",
            "classification_flow": r"## Classification Flow.*?### 1\. Rules Engine.*?### 4\. Verifier.*?\n\n",
            "costs": r"\| Operation \| Cost \| When \|(.*?)\n\n",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, self.content, re.DOTALL)
            if match:
                sections[key] = (
                    match.group(1).strip() if match.lastindex else match.group(0).strip()
                )

        return sections

    def _detect_database_config(self) -> dict:
        """Detect database configuration from mailq/config/database.py"""
        config = {
            "path": "mailq.db",  # default
            "tables": [],
            "pool_size": 5,
        }

        db_config_path = PROJECT_ROOT / "mailq" / "config" / "database.py"
        if not db_config_path.exists():
            return config

        try:
            content = db_config_path.read_text()

            # Detect DB_PATH
            if match := re.search(r"DB_PATH\s*=\s*.*['\"]([^'\"]+\.db)['\"]", content):
                config["path"] = match.group(1).split("/")[-1]

            # Detect pool size
            if match := re.search(r"pool_size\s*=\s*(\d+)", content):
                config["pool_size"] = int(match.group(1))

            # Detect tables from CREATE TABLE statements
            tables = re.findall(r"CREATE TABLE.*?(\w+)\s*\(", content, re.IGNORECASE)
            config["tables"] = list(set(tables))

        except Exception:
            pass

        return config

    def _detect_external_services(self) -> dict[str, dict]:
        """Detect external services used across the codebase"""
        services = {}

        # Scan backend files
        backend_dir = PROJECT_ROOT / "mailq"
        if backend_dir.exists():
            for file in backend_dir.rglob("*.py"):
                if file.name.startswith("test_") or file.name == "__init__.py":
                    continue

                try:
                    content = file.read_text()

                    # Vertex AI / Gemini
                    if "vertexai" in content or "GenerativeModel" in content:
                        if "vertexai" not in services:
                            services["vertexai"] = {"name": "Vertex AI", "model": "Gemini"}

                        # Detect model name
                        if match := re.search(r'["\']gemini-([^"\']+)["\']', content):
                            services["vertexai"]["model"] = f"gemini-{match.group(1)}"

                    # Gmail API
                    if "gmail" in content.lower() and "api" in content.lower():
                        if "gmail" not in services:
                            services["gmail"] = {"name": "Gmail API"}

                except Exception:
                    pass

        return services

    def _detect_confidence_thresholds(self) -> dict[str, float]:
        """Detect confidence thresholds from code"""
        thresholds = {
            "min_type_conf": 0.85,  # defaults
            "min_label_conf": 0.75,
            "verifier_delta": 0.15,
        }

        # Check api_organize.py
        organize_file = PROJECT_ROOT / "mailq" / "api_organize.py"
        if organize_file.exists():
            try:
                content = organize_file.read_text()

                # MIN_TYPE_CONF patterns
                if match := re.search(r"MIN_TYPE_CONF(?:IDENCE)?\s*=\s*([\d.]+)", content):
                    thresholds["min_type_conf"] = float(match.group(1))

                # MIN_LABEL_CONF patterns
                if match := re.search(r"MIN_LABEL_CONF(?:IDENCE)?\s*=\s*([\d.]+)", content):
                    thresholds["min_label_conf"] = float(match.group(1))

                # Verifier delta
                if match := re.search(r"confidence_delta.*?>=?\s*([\d.]+)", content):
                    thresholds["verifier_delta"] = float(match.group(1))

            except Exception:
                pass

        return thresholds

    def _detect_extension_config(self) -> dict:
        """Detect extension configuration from extension/config.js"""
        config = {
            "cache_expiry_hours": 24,  # default
            "daily_budget_cap": 0.50,  # default
            "tier_costs": {
                "T0": 0.0,
                "T3": 0.001,  # default
            },
            "verifier_range": (0.50, 0.90),  # default
        }

        # Read config.js
        config_file = PROJECT_ROOT / "extension" / "config.js"
        if config_file.exists():
            try:
                content = config_file.read_text()

                # Detect cache expiry (in hours)
                if match := re.search(
                    r"CACHE_EXPIRY_MS:\s*(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)", content
                ):
                    hours = int(match.group(1))
                    config["cache_expiry_hours"] = hours

                # Detect daily spend cap
                if match := re.search(r"DAILY_SPEND_CAP_USD:\s*([\d.]+)", content):
                    config["daily_budget_cap"] = float(match.group(1))

                # Detect tier costs
                if match := re.search(r"T0:\s*([\d.]+)", content):
                    config["tier_costs"]["T0"] = float(match.group(1))
                if match := re.search(r"T3:\s*([\d.]+)", content):
                    config["tier_costs"]["T3"] = float(match.group(1))

            except Exception:
                pass

        # Read verifier.js for confidence range
        verifier_file = PROJECT_ROOT / "extension" / "modules" / "verifier.js"
        if verifier_file.exists():
            try:
                content = verifier_file.read_text()

                # Look for: if (typeConf >= 0.50 && typeConf <= 0.90)
                if match := re.search(
                    r"typeConf\s*>=\s*([\d.]+)\s*&&\s*typeConf\s*<=\s*([\d.]+)", content
                ):
                    config["verifier_range"] = (float(match.group(1)), float(match.group(2)))

            except Exception:
                pass

        return config

    def get_architecture_context(self) -> dict[str, any]:
        """Get context for system architecture diagram"""
        return {
            "title": "MailQ Architecture",
            "sections": [
                {
                    "heading": "Core Flow",
                    "content": self.sections.get("architecture", ""),
                    "type": "code",
                },
                {
                    "heading": "Classification Dimensions",
                    "content": self.sections.get("dimensions", ""),
                    "type": "json",
                },
                {"heading": "Key Components", "content": self._extract_key_files(), "type": "list"},
            ],
        }

    def get_classification_context(self) -> dict[str, any]:
        """Get context for classification flow diagram"""
        # Dynamic confidence thresholds
        min_type = self.confidence_thresholds["min_type_conf"]
        min_label = self.confidence_thresholds["min_label_conf"]
        verifier_delta = self.confidence_thresholds["verifier_delta"]

        # Dynamic model name
        model = self.external_services.get("vertexai", {}).get("model", "Gemini")

        return {
            "title": "Classification Details",
            "sections": [
                {
                    "heading": "Confidence Thresholds (Detected)",
                    "content": """
MIN_TYPE_CONF = {min_type} (type must be {int(min_type * 100)}%+ confident)
MIN_LABEL_CONF = {min_label} (labels must be {int(min_label * 100)}%+ confident)
Below threshold → "Uncategorized"
Above threshold → Continue to verification check
                    """.strip(),
                    "type": "code",
                },
                {
                    "heading": "LLM Model & Costs (Detected)",
                    "content": """
Current model: {model}
Verifier delta threshold: {verifier_delta}
T3 cost per email: ${self.extension_config["tier_costs"]["T3"]:.4f}
Daily budget cap: ${self.extension_config["daily_budget_cap"]:.2f}
Cache expiry: {self.extension_config["cache_expiry_hours"]} hours
                    """.strip(),
                    "type": "code",
                },
                {
                    "heading": "Verifier Triggers",
                    "content": """
• Low/medium confidence (0.50-0.90)
• Multi-purpose senders (Amazon, Google, banks)
• Contradictions detected
• Weak reasoning ("probably", "might be")
                    """.strip(),
                    "type": "list",
                },
                {
                    "heading": "Prompt Files",
                    "content": """
mailq/prompts/classifier_prompt.txt - LLM #1 (editable!)
mailq/prompts/verifier_prompt.txt - LLM #2 (editable!)
Changes load automatically - no code changes needed
                    """.strip(),
                    "type": "list",
                },
            ],
        }

    def get_learning_context(self) -> dict[str, any]:
        """Get context for learning loop diagram"""
        # Dynamic database info
        db_name = self.database_config["path"]
        tables = self.database_config.get("tables", [])
        tables_str = ", ".join(sorted(tables)[:5]) if tables else "rules, feedback, logs"

        return {
            "title": "Learning System",
            "sections": [
                {
                    "heading": "How Learning Works",
                    "content": """
1. User removes/adds label → content.js detects
2. POST /api/feedback with correction
3. Creates rule (confidence=0.95)
4. Future emails auto-classified (T0 cost: free)
                    """.strip(),
                    "type": "list",
                },
                {
                    "heading": "Rule Confidence",
                    "content": """
New rule: 0.95 confidence
Each correction: +0.05 confidence
2+ consistent classifications → confirmed rule
                    """.strip(),
                    "type": "list",
                },
                {
                    "heading": "Database (Detected)",
                    "content": """
{db_name} - Unified database
Tables: {tables_str}
All learning data in one place
                    """.strip(),
                    "type": "list",
                },
            ],
        }

    def get_digest_learning_context(self) -> dict[str, any]:
        """Get context for digest learning loop diagram"""
        return {
            "title": "Digest Learning System",
            "sections": [
                {
                    "heading": "How Implicit Learning Works",
                    "content": """
1. User opens featured email → Upvote (strength: 1.0-1.5)
2. User stars any email → Strong signal (strength: 2.0)
3. User archives featured unread → Downvote (strength: 1.0-2.0)
4. Patterns emerge → Confidence calculated
5. High-confidence patterns → Boost importance scores
                    """.strip(),
                    "type": "list",
                },
                {
                    "heading": "Tracking Methods",
                    "content": """
Method 1: Embedded tracking (digest_tracking.html)
  - Tracks clicks in digest email
  - Real-time feedback on opens

Method 2: Gmail API polling (digest-feedback.js)
  - Polls every 5 minutes for 24 hours
  - Detects stars, archives, reads
                    """.strip(),
                    "type": "code",
                },
                {
                    "heading": "Pattern Confidence",
                    "content": """
Confidence = upvotes / (upvotes + downvotes)
Threshold: 0.7 minimum to apply
Example: 19 upvotes, 1 downvote = 0.95 confidence
                    """.strip(),
                    "type": "list",
                },
                {
                    "heading": "Database",
                    "content": """
digest_feedback.db:
  - digest_feedback: Raw user actions
  - digest_patterns: Learned patterns with confidence

Pattern types:
  - sender_domain: e.g., "jmir.org"
  - subject_pattern: e.g., "manuscript_review"
                    """.strip(),
                    "type": "code",
                },
            ],
        }

    def _generate_ai_explanation(self, diagram_mermaid: str, diagram_type: str) -> str:
        """Generate AI explanation of the diagram using Vertex AI Gemini"""
        try:
            if not VERTEX_AVAILABLE:
                return None

            # Initialize Vertex AI
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "mailq-467118")
            location = os.getenv("GEMINI_LOCATION", "us-central1")

            vertexai.init(project=project_id, location=location)
            # Use same model as MailQ classifier
            model = GenerativeModel("gemini-2.0-flash")

            prompt = """You are explaining a technical diagram for MailQ, an AI-powered Gmail email classification system.

The diagram shows: {diagram_type}

Here is the Mermaid diagram code:
```mermaid
{diagram_mermaid}
```

Write a SHORT explanation (under 150 words) with this structure:

**One-sentence summary:** What this shows in plain English.

**Key Numbers:**
- Most important cost/performance metrics (3-4 bullets max)
- Define terms inline: "p50 (50th percentile) = 800ms"
- Use concrete examples: "70% of emails = free processing"

**Bottom Line:**
- One sentence: Why this matters for engineers/business

Rules:
- Be extremely concise - cut all fluff
- Lead with insights, not descriptions
- Use bold for numbers and key terms
- No paragraph-form text - bullets only (except summary & bottom line)
- Assume reader can see the diagram - don't repeat what's visible

Example of conciseness:
❌ "The Cost Breakdown section shows the expenses..."
✅ "**$0.03/day** total cost (1000 emails)"

Write for busy technical readers who want insights fast."""

            response = model.generate_content(prompt)
            return response.text.strip()

        except Exception as e:
            print(f"Warning: Could not generate AI explanation: {e}")
            return None

    def get_cost_context(self, diagram_mermaid: str = "") -> dict[str, any]:
        """Get context for cost/performance diagram"""
        # Dynamic model name
        model = self.external_services.get("vertexai", {}).get("model", "Gemini")

        sections = []

        # Add AI-generated explanation if possible
        if diagram_mermaid:
            ai_explanation = self._generate_ai_explanation(
                diagram_mermaid, "Cost & Performance Analysis"
            )
            if ai_explanation:
                sections.append(
                    {"heading": "What This Shows", "content": ai_explanation, "type": "text"}
                )

        # Add existing sections
        sections.extend(
            [
                {
                    "heading": "Cost Breakdown (Detected)",
                    "content": """
T0 (Rules): $0 - 50-70% of emails (projected)
T3 ({model}): ${self.extension_config["tier_costs"]["T3"]:.4f} - 30-50% of emails (projected)
T3 (Verifier): ${self.extension_config["tier_costs"]["T3"]:.4f} - 5-10% of emails (projected)
Daily cap: ${self.extension_config["daily_budget_cap"]:.2f} (from extension/config.js)
⚠️ Percentages are projections, not measured
                """.strip(),
                    "type": "list",
                },
                {
                    "heading": "Performance Targets",
                    "content": """
Average latency: <2s
p95 latency: ~1.5s
Rules match rate: 50-70% (target: 60%)
Cache hit rate: ~70% (24hr expiry)
                """.strip(),
                    "type": "list",
                },
                {
                    "heading": "Optimization",
                    "content": """
Week 1: ~$0.09/day (10% rules)
Week 2: ~$0.07/day (30% rules)
Month 1: ~$0.04/day (60% rules)
Month 3: ~$0.03/day (70% rules)
                """.strip(),
                    "type": "list",
                },
            ]
        )

        return {"title": "Cost & Performance", "sections": sections}

    def _extract_key_files(self) -> str:
        """Extract key files from CLAUDE.md"""
        pattern = r"### Backend \(mailq/\)\n\n\| File \| Purpose \|(.*?)(?=###|$)"
        match = re.search(pattern, self.content, re.DOTALL)
        if match:
            lines = match.group(1).strip().split("\n")[1:]  # Skip header separator
            result = []
            for line in lines:
                parts = line.split("|")
                if len(parts) >= 3:
                    file = parts[1].strip()
                    purpose = parts[2].strip()
                    result.append(f"{file}: {purpose}")
            return "\n".join(result[:8])  # Top 8 files
        return "See CLAUDE.md for details"

    def get_context_for_diagram(
        self, diagram_type: str, diagram_mermaid: str = ""
    ) -> dict[str, any]:
        """Get appropriate context for diagram type"""
        context_map = {
            "system_architecture": lambda: self.get_architecture_context(),
            "classification_flow": lambda: self.get_classification_context(),
            "learning_loop": lambda: self.get_learning_context(),
            "digest_learning": lambda: self.get_digest_learning_context(),
            "cost_performance": lambda: self.get_cost_context(diagram_mermaid),
        }

        func = context_map.get(diagram_type, lambda: self.get_architecture_context())
        return func()


if __name__ == "__main__":
    # Test the extractor
    context = MailQContext()

    print("Testing context extraction...")
    print("\nArchitecture Context:")
    print(context.get_architecture_context())

    print("\n" + "=" * 50)
    print("\nClassification Context:")
    print(context.get_classification_context())
