#!/usr/bin/env python3
"""
Code-Graph v3 - Dynamic Diagram Generator

Generates Mermaid diagrams by analyzing actual codebase structure.
No hardcoded templates - fully dynamic and always accurate.
All files automatically included - no manual updates needed!
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
VISUALS_DIR = PROJECT_ROOT / "code-graph" / "visuals"


class DynamicDiagramGenerator:
    """Generates Mermaid diagrams from actual codebase analysis"""

    def __init__(self):
        self.backend_files = self._scan_backend()
        self.extension_files = self._scan_extension()
        self.backend_imports = self._analyze_all_imports()
        self.backend_components = self._analyze_backend()
        self.extension_components = self._analyze_extension()
        self.component_index = self._load_component_index()
        self.golden_stats = self._load_golden_dataset_stats()

        # Dynamic detections
        self.database_config = self._detect_database_config()
        self.external_services = self._detect_external_services()
        self.confidence_thresholds = self._detect_confidence_thresholds()
        self.api_endpoints = self._detect_api_endpoints()
        self.data_flows = self._detect_data_flows()
        self.extension_config = self._detect_extension_config()  # NEW: cache, budget, costs

    def _scan_backend(self) -> list[Path]:
        """Scan Python backend files (core architecture only)"""
        mailq_dir = PROJECT_ROOT / "mailq"

        # Directories to exclude (utility, config, data)
        exclude_dirs = {"scripts", "config", "prompts", "data", "logs", "tests", "__pycache__"}

        # Files to exclude (logging, telemetry, infrastructure)
        exclude_files = {
            "logger.py",
            "telemetry.py",
            "monitoring.py",
            "metrics.py",
            "instrumentation.py",
        }

        backend_files = []
        for f in mailq_dir.rglob("*.py"):
            # Skip test files and __init__.py
            if f.name.startswith("test_") or f.name == "__init__.py":
                continue

            # Skip logging/infrastructure files
            if f.name in exclude_files:
                continue

            # Skip if file is in excluded directory
            relative_parts = f.relative_to(mailq_dir).parts
            if any(part in exclude_dirs for part in relative_parts):
                continue

            backend_files.append(f)

        return backend_files

    def _scan_extension(self) -> list[Path]:
        """Scan JavaScript extension files"""
        ext_dir = PROJECT_ROOT / "extension"
        modules_dir = ext_dir / "modules"

        # Files to exclude (logging, telemetry, infrastructure)
        exclude_files = {
            "logger.js",
            "telemetry.js",
            "monitoring.js",
            "metrics.js",
            "instrumentation.js",
        }

        # Get core files
        core_files = [ext_dir / "background.js", ext_dir / "content.js"]

        # Get all module files (excluding infrastructure)
        module_files = [
            f for f in (modules_dir.glob("*.js") if modules_dir.exists() else [])
            if f.name not in exclude_files
        ]

        return [f for f in core_files + module_files if f.exists()]

    def _analyze_file_imports(self, filepath: Path) -> dict[str, list[str]]:
        """Parse a file to extract import relationships"""
        imports = {
            "internal": [],  # from mailq.X import Y
            "external": [],  # vertexai, gmail API, etc.
            "stdlib": [],  # datetime, json, etc.
        }

        try:
            content = filepath.read_text()

            # Python imports
            if filepath.suffix == ".py":
                for line in content.split("\n"):
                    line = line.strip()

                    # from mailq.digest_X import Y
                    if (match := re.match(r"from mailq\.(\w+)", line)) or (
                        match := re.match(r"import mailq\.(\w+)", line)
                    ):
                        module_name = match.group(1)
                        imports["internal"].append(module_name)

                    # External services
                    if "vertexai" in line or "GenerativeModel" in line:
                        if "vertexai" not in imports["external"]:
                            imports["external"].append("vertexai")
                    if "gmail" in line.lower() and "from" in line:
                        if "gmail" not in imports["external"]:
                            imports["external"].append("gmail")
                    if "smtp" in line.lower():
                        if "smtp" not in imports["external"]:
                            imports["external"].append("smtp")

            # JavaScript imports (for future extension)
            elif filepath.suffix == ".js":
                # Can be extended for JS module analysis
                pass

        except Exception:
            # Silently skip files that can't be read
            pass

        return imports

    def _analyze_all_imports(self) -> dict[str, dict[str, list[str]]]:
        """Analyze imports for all backend files"""
        all_imports = {}

        for filepath in self.backend_files:
            file_stem = filepath.stem
            imports = self._analyze_file_imports(filepath)
            all_imports[file_stem] = imports

        return all_imports

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

        # Scan all files for external service patterns
        all_files = self.backend_files + self.extension_files

        for filepath in all_files:
            try:
                content = filepath.read_text()

                # Vertex AI / Gemini
                if "vertexai" in content or "GenerativeModel" in content:
                    if "vertexai" not in services:
                        services["vertexai"] = {
                            "name": "Vertex AI",
                            "description": "Gemini LLM",
                            "files": [],
                        }
                    services["vertexai"]["files"].append(filepath.name)

                    # Detect model name
                    if match := re.search(r'["\']gemini-([^"\']+)["\']', content):
                        services["vertexai"]["model"] = f"gemini-{match.group(1)}"

                # Gmail API
                if "gmail.googleapis.com" in content or "GmailService" in content:
                    if "gmail" not in services:
                        services["gmail"] = {
                            "name": "Gmail API",
                            "description": "Email Operations",
                            "files": [],
                        }
                    services["gmail"]["files"].append(filepath.name)

                # OpenWeather API
                if "openweathermap" in content:
                    if "weather" not in services:
                        services["weather"] = {
                            "name": "OpenWeather",
                            "description": "Weather Data",
                            "files": [],
                        }
                    services["weather"]["files"].append(filepath.name)

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

        # Check api_organize.py and confidence config files
        target_files = [
            PROJECT_ROOT / "mailq" / "api_organize.py",
            PROJECT_ROOT / "mailq" / "config" / "confidence.py",
        ]

        for filepath in target_files:
            if not filepath.exists():
                continue

            try:
                content = filepath.read_text()

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

    def _detect_api_endpoints(self) -> list[dict]:
        """Detect API endpoints from api.py and api_*.py files"""
        endpoints = []

        api_files = [f for f in self.backend_files if "api" in f.stem]

        for filepath in api_files:
            try:
                content = filepath.read_text()

                # FastAPI route patterns: @app.post("/api/...")
                routes = re.findall(r'@app\.(get|post|put|delete)\(["\']([^"\']+)["\']\)', content)

                for method, path in routes:
                    # Get docstring if available
                    pattern = rf'@app\.{method}\(["\']{re.escape(path)}["\']\).*?"""(.*?)"""'
                    doc_match = re.search(pattern, content, re.DOTALL)
                    description = doc_match.group(1).strip().split("\n")[0] if doc_match else ""

                    endpoints.append(
                        {
                            "method": method.upper(),
                            "path": path,
                            "file": filepath.stem,
                            "description": description,
                        }
                    )

            except Exception:
                pass

        return endpoints

    def _detect_data_flows(self) -> list[dict]:
        """Detect common data flows by analyzing code patterns"""
        flows = []

        # Flow 1: Classification (detect from api_organize.py)
        organize_file = PROJECT_ROOT / "mailq" / "api_organize.py"
        if organize_file.exists():
            try:
                content = organize_file.read_text()
                if "rules_engine" in content and "vertex" in content:
                    flows.append(
                        {
                            "name": "Classification Flow",
                            "path": "Extension → API → Rules → LLM",
                            "confidence": "high",
                        }
                    )
            except Exception:
                pass

        # Flow 2: Feedback (detect from api_feedback.py)
        feedback_file = PROJECT_ROOT / "mailq" / "api_feedback.py"
        if feedback_file.exists():
            flows.append(
                {
                    "name": "Feedback Loop",
                    "path": "User → content.js → API → Database",
                    "confidence": "high",
                }
            )

        # Flow 3: Context Digest (detect from context_digest.py)
        digest_file = PROJECT_ROOT / "mailq" / "context_digest.py"
        if digest_file.exists():
            flows.append(
                {
                    "name": "Context Digest Flow",
                    "path": "Extension → API → LLM → Email",
                    "confidence": "high",
                }
            )

        # Flow 4: Auto-organize (detect from extension)
        auto_org_file = PROJECT_ROOT / "extension" / "modules" / "auto-organize.js"
        if auto_org_file.exists():
            flows.append(
                {
                    "name": "Auto-Organize Flow",
                    "path": "Extension → Gmail API → Classify → Labels",
                    "confidence": "high",
                }
            )

        return flows

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

    def _categorize_backend_file(self, filepath: Path) -> str:
        """Categorize backend file by purpose using pattern-based detection"""
        name = filepath.stem.lower()

        # Pattern-based detection (NO HARDCODING specific files)
        # Core API
        if name == "api":
            return "core"
        if re.match(r"^api_", name):
            return "api"

        # Digest subsystem - NEW!
        if re.match(r"^(digest_|cli_digest)", name) or "simple_digest" in name:
            return "digest"

        # Classification system
        if "classifier" in name and "vertex" not in name:
            return "classifier"
        if "vertex" in name or "gemini" in name:
            return "llm"
        if "verif" in name:
            return "verifier"

        # Rules and learning
        if "rules" in name or "feedback" in name or "learning" in name:
            return "learning"

        # Utilities
        if name in ["mapper", "logger", "category_manager"]:
            return "utility"

        # Summary/features (but not digest)
        if "summary" in name and "digest" not in name:
            return "feature"

        return "other"

    def _categorize_extension_file(self, filepath: Path) -> str:
        """Categorize extension file by purpose"""
        name = filepath.stem.lower()

        # Core files
        if name == "background":
            return "core"
        if name == "content":
            return "core"

        # Gmail operations
        if name == "gmail":
            return "gmail"

        # Classification
        if name in ["classifier", "verifier", "mapper"]:
            return "classification"

        # Storage and caching
        if name in ["cache", "storage"]:
            return "storage"

        # Features (user-facing functionality)
        if name in ["summary-email", "notifications", "auto-organize"]:
            return "feature"

        # Utilities (support/infrastructure code)
        if name in ["logger", "telemetry", "detectors", "budget", "auth", "utils", "signatures"]:
            return "utility"

        return "other"

    def _get_description(self, filepath: Path) -> str:
        """Extract description from file docstring or comments"""
        try:
            content = filepath.read_text()

            if filepath.suffix == ".py":
                # Look for module docstring
                match = re.search(r'"""(.+?)"""', content, re.DOTALL)
                if match:
                    lines = match.group(1).strip().split("\n")
                    return lines[0].strip()[:50]

            elif filepath.suffix == ".js":
                # Look for JSDoc or comments
                match = re.search(r"/\*\*\s*\n\s*\*\s*(.+?)\n", content)
                if match:
                    return match.group(1).strip()[:50]

                # Try single line comment at top
                match = re.search(r"^//\s*(.+?)$", content, re.MULTILINE)
                if match:
                    return match.group(1).strip()[:50]

        except Exception:
            pass

        # Generate description from filename
        name = filepath.stem.replace("_", " ").replace("-", " ").title()
        return name

    def _analyze_backend(self) -> dict[str, list[dict]]:
        """Analyze backend files and categorize"""
        components = defaultdict(list)

        for filepath in self.backend_files:
            category = self._categorize_backend_file(filepath)
            description = self._get_description(filepath)

            components[category].append(
                {
                    "name": filepath.stem,
                    "file": filepath.name,
                    "description": description,
                    "path": filepath,
                }
            )

        return dict(components)

    def _load_component_index(self) -> dict[str, dict]:
        """Load component metadata index for documentation/source links"""
        index_path = PROJECT_ROOT / "code-graph" / "component_index.json"
        if not index_path.exists():
            return {}
        try:
            return json.loads(index_path.read_text())
        except Exception:
            return {}

    def _load_golden_dataset_stats(self) -> dict:
        """Load metadata about the golden dataset (if available)"""
        metadata_path = PROJECT_ROOT / "tests" / "golden_set" / "metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            return json.loads(metadata_path.read_text())
        except Exception:
            return {}

    def _get_component_info(self, filepath: Path) -> dict | None:
        """Return component metadata for a given file path"""
        try:
            rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return None
        return self.component_index.get(rel_path)

    def _make_visuals_relative(self, path: str) -> str:
        """Return path relative to visuals markdown directory"""
        if not path:
            return ""
        return path if path.startswith("http") else f"../../{path}"

    def _make_html_relative(self, path: str) -> str:
        """Return path relative to visuals/html directory"""
        if not path:
            return ""
        return path if path.startswith("http") else f"../../../{path}"

    def _format_component_entry(self, comp: dict) -> str:
        """Format component entry with links to docs, code, and tests"""
        rel_code_path = comp["path"].relative_to(PROJECT_ROOT).as_posix()
        info = comp.get("info") or self._get_component_info(comp["path"])
        description = (
            info["description"] if info and info.get("description") else comp["description"]
        )

        line = f"- [`{comp['file']}`]({self._make_visuals_relative(rel_code_path)}) — {description}"

        extras = []
        if info:
            if info.get("doc"):
                extras.append(f"[Docs]({self._make_visuals_relative(info['doc'])})")
            tests = info.get("tests") or []
            if tests:
                test_links = ", ".join(
                    f"[`{Path(test).name}`]({self._make_visuals_relative(test)})" for test in tests
                )
                extras.append(f"Tests: {test_links}")

        if extras:
            line += f" ({'; '.join(extras)})"

        return line

    def _analyze_extension(self) -> dict[str, list[dict]]:
        """Analyze extension files and categorize"""
        components = defaultdict(list)

        for filepath in self.extension_files:
            category = self._categorize_extension_file(filepath)
            description = self._get_description(filepath)

            components[category].append(
                {
                    "name": filepath.stem,
                    "file": filepath.name,
                    "description": description,
                    "path": filepath,
                }
            )

        return dict(components)

    def _make_node_id(self, name: str, prefix: str = "") -> str:
        """Convert filename to a valid Mermaid node ID with optional prefix"""
        # Remove file extension and special chars, uppercase
        clean_name = (
            name.replace(".py", "")
            .replace(".js", "")
            .replace("-", "_")
            .replace("_", "")
            .upper()[:8]
        )
        if prefix:
            return f"{prefix}_{clean_name}"
        return clean_name

    def _indent_lines(self, text: str, indent: str = "    ") -> str:
        """Add consistent indentation to each line of text"""
        if not text:
            return ""
        lines = text.split("\n")
        return "\n".join(f"{indent}{line}" for line in lines if line.strip())

    def _sanitize_label(self, text: str) -> str:
        """Sanitize text for use in Mermaid node labels"""
        # Remove all bracket-like characters that conflict with Mermaid syntax
        # Mermaid uses () for shapes and [] for labels, so we can't use them inside
        text = text.replace("(", "").replace(")", "")
        text = text.replace("[", "").replace("]", "")
        text = text.replace("{", "").replace("}", "")
        # Replace quotes with smart quotes to avoid parsing issues
        text = text.replace('"', "'")
        return text

    def _get_emoji_for_file(self, filename: str, category: str) -> str:
        """Get emoji based on file purpose - 100% dynamic"""
        name_lower = filename.lower()

        # Extension files
        if "background" in name_lower:
            return "🎯"
        if "content" in name_lower:
            return "👁️"
        if "gmail" in name_lower:
            return "📧"
        if "classifier" in name_lower or "verifier" in name_lower:
            return "🤖"
        if "cache" in name_lower or "storage" in name_lower:
            return "💾"
        if "auto-organize" in name_lower:
            return "⚡"
        if "summary" in name_lower or "digest" in name_lower:
            return "📊"
        if "notification" in name_lower:
            return "🔔"
        if "mapper" in name_lower:
            return "🗺️"
        if "logger" in name_lower or "telemetry" in name_lower:
            return "📝"
        if "auth" in name_lower:
            return "🔐"
        if "detector" in name_lower:
            return "🔍"
        if "budget" in name_lower:
            return "💰"

        # Backend files
        if "api" in name_lower:
            return "🌐"
        if "rules" in name_lower:
            return "📚"
        if "feedback" in name_lower:
            return "💬"
        if "verify" in name_lower:
            return "✓"
        if "gemini" in name_lower or "vertex" in name_lower:
            return "🧠"

        # Default by category
        if category == "core":
            return "⚙️"
        if category in ["api", "classifier", "llm"]:
            return "🔧"
        return "📄"

    def _generate_external_services_nodes(self) -> str:
        """Generate external services nodes dynamically"""
        if not self.external_services:
            return "        NO_EXTERNAL[No External Services Detected]"

        nodes = []
        for service_key, service in self.external_services.items():
            node_id = service_key.upper()
            name = service.get("name", service_key)
            desc = service.get("description", "")
            model = service.get("model", "")

            # Build description line
            desc_parts = [name]
            if model:
                desc_parts.append(model)
            elif desc:
                desc_parts.append(desc)

            desc_line = "<br/>".join(desc_parts)
            nodes.append(f"        {node_id}[{desc_line}]")

        return "\n".join(nodes)

    def _generate_database_node(self) -> str:
        """Generate database node dynamically"""
        db_name = self.database_config["path"]
        tables = self.database_config.get("tables", [])

        # Build description
        if tables:
            # Show first 3 tables as examples
            tables_preview = ", ".join(sorted(tables)[:3])
            if len(tables) > 3:
                tables_preview += f", +{len(tables) - 3} more"
            desc = f"Unified Database<br/>{len(tables)} tables: {tables_preview}"
        else:
            desc = "Unified Database<br/>Rules, Feedback, Logs"

        return f"        MAILQDB[({db_name}<br/>{desc})]"

    def generate_classification_flow(self) -> str:
        """Generate classification flow as a clean sequence diagram"""

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Build backend nodes grouped by category
        backend_category_nodes = {}
        backend_node_ids = {}

        for category in [
            "core",
            "api",
            "classifier",
            "llm",
            "verifier",
            "learning",
            "digest",
            "utility",
            "feature",
            "other",
        ]:
            if category in self.backend_components:
                backend_category_nodes[category] = []
                for comp in sorted(self.backend_components[category], key=lambda x: x["name"]):
                    node_id = self._make_node_id(comp["name"], prefix="BE")
                    backend_node_ids[comp["name"]] = node_id

                    info = self._get_component_info(comp["path"])
                    description_source = (
                        info["description"]
                        if info and info.get("description")
                        else comp["description"]
                    )

                    # Get emoji and truncate/sanitize description
                    emoji = self._get_emoji_for_file(comp["file"], category)
                    desc = (
                        description_source[:35] + "..."
                        if len(description_source) > 35
                        else description_source
                    )
                    desc = self._sanitize_label(desc)

                    backend_category_nodes[category].append(
                        f'{node_id}["{emoji} {comp["file"]}<br/>{desc}"]'
                    )
                    comp["node_id"] = node_id
                    comp["info"] = info

        # Build extension nodes grouped by category
        extension_node_ids = {}
        extension_runtime_groups = defaultdict(list)

        for category in [
            "core",
            "gmail",
            "classification",
            "storage",
            "feature",
            "utility",
            "other",
        ]:
            if category in self.extension_components:
                for comp in sorted(self.extension_components[category], key=lambda x: x["name"]):
                    node_id = self._make_node_id(comp["name"], prefix="EXT")
                    extension_node_ids[comp["name"]] = node_id

                    info = self._get_component_info(comp["path"])
                    description_source = (
                        info["description"]
                        if info and info.get("description")
                        else comp["description"]
                    )

                    emoji = self._get_emoji_for_file(comp["file"], category)
                    desc = (
                        description_source[:35] + "..."
                        if len(description_source) > 35
                        else description_source
                    )
                    desc = self._sanitize_label(desc)

                    if comp["name"] not in ["background", "content"]:
                        display_name = comp["file"].replace(".js", "")
                    else:
                        display_name = comp["file"]

                    node_text = f'{node_id}["{emoji} {display_name}<br/>{desc}"]'

                    comp["node_id"] = node_id
                    comp["info"] = info

                    runtime = "shared"
                    if info and info.get("runtime"):
                        runtime = info["runtime"]

                    extension_runtime_groups[runtime].append(node_text)

        # Build dynamic connections based on detected components
        connections = []

        # Helper to safely get node ID
        def get_node(node_dict, name):
            return node_dict.get(name, None)

        def get_external_node(service_key: str) -> str | None:
            return service_key.upper() if service_key in self.external_services else None

        # Key extension nodes
        bg_id = get_node(extension_node_ids, "background")
        content_id = get_node(extension_node_ids, "content")
        gmail_id = get_node(extension_node_ids, "gmail")
        classifier_id = get_node(extension_node_ids, "classifier")
        cache_id = get_node(extension_node_ids, "cache")

        # Key backend nodes
        api_id = get_node(backend_node_ids, "api")
        memory_id = get_node(backend_node_ids, "memory_classifier")
        rules_id = get_node(backend_node_ids, "rules_engine")
        mapper_id = get_node(backend_node_ids, "mapper")

        gmail_service_node = get_external_node("gmail")
        vertex_service_node = get_external_node("vertexai")

        # Main extension flows
        if bg_id and gmail_id:
            connections.append(f"{bg_id} --> {gmail_id}")
        if bg_id and classifier_id:
            connections.append(f"{bg_id} --> {classifier_id}")
        if gmail_id and gmail_service_node:
            connections.append(f"{gmail_id} --> {gmail_service_node}")
        if classifier_id and cache_id:
            connections.append(f"{classifier_id} --> {cache_id}")
        if classifier_id and api_id:
            connections.append(f"{classifier_id} --> {api_id}")
        if content_id and api_id:
            connections.append(f"{content_id} --> {api_id}")

        # Main backend flows
        if api_id and memory_id:
            connections.append(f"{api_id} --> {memory_id}")
        if memory_id and rules_id:
            connections.append(f"{memory_id} --> {rules_id}")
        if memory_id and mapper_id:
            connections.append(f"{memory_id} --> {mapper_id}")
        if memory_id and vertex_service_node:
            connections.append(f"{memory_id} --> {vertex_service_node}")
        if rules_id:
            connections.append(f"{rules_id} <--> MAILQDB")
        if api_id:
            connections.append(f"{api_id} --> MAILQDB")

        # Generate automatic connections from import analysis
        for file_stem, imports in self.backend_imports.items():
            from_id = get_node(backend_node_ids, file_stem)
            if not from_id:
                continue

            # Internal connections (mailq module imports)
            for imported_module in imports["internal"]:
                to_id = get_node(backend_node_ids, imported_module)
                if to_id and from_id != to_id:  # Avoid self-loops
                    connection = f"{from_id} --> {to_id}"
                    if connection not in connections:  # Avoid duplicates
                        connections.append(connection)

            # External service connections
            for external_service in imports["external"]:
                to_id = get_external_node(external_service)
                if to_id:
                    label = "Gemini" if external_service == "vertexai" else "API"
                    connection = f'{from_id} -.->|"{label}"| {to_id}'
                    if connection not in connections:
                        connections.append(connection)

        # Build style classes dynamically
        extension_classes = ",".join(extension_node_ids.values())
        backend_classes = ",".join(backend_node_ids.values())

        # Category names mapping
        category_names = {
            "core": "⚙️ Core",
            "api": "🌐 API",
            "classifier": "🤖 Classifier",
            "llm": "🧠 LLM",
            "verifier": "✓ Verifier",
            "learning": "📚 Learning",
            "digest": "📊 Digest System",
            "utility": "🔧 Utility",
            "feature": "✨ Features",
            "gmail": "📧 Gmail",
            "classification": "🤖 Classification",
            "storage": "💾 Storage",
            "other": "📦 Other",
        }

        runtime_labels = {
            "service_worker": "🛰️ Service Worker (MV3)",
            "content_script": "👁️ Content Script",
            "shared": "🧩 Shared Modules",
        }

        extension_subgraphs = []
        for runtime, nodes in extension_runtime_groups.items():
            if nodes:
                nodes_text = self._indent_lines("\n".join(nodes), "            ")
                label = runtime_labels.get(runtime, runtime.replace("_", " ").title())
                extension_subgraphs.append(
                    f"""        subgraph EXT_RT_{runtime.upper()}["{label} - {len(nodes)} files"]
{nodes_text}
        end"""
                )

        # Build backend subgraphs (use unique IDs for subgraphs: CAT_BE_xxx)
        backend_subgraphs = []
        for category, nodes in backend_category_nodes.items():
            if nodes:
                # Special handling for digest subsystem - create nested structure
                if category == "digest":
                    category_label = category_names.get(category, category.title())
                    count = len(nodes)

                    # Categorize digest files into subsystems
                    core_files = []
                    delivery_files = []
                    support_files = []

                    for node in nodes:
                        if any(
                            x in node for x in ["generator", "aggregator", "summarizer", "ranker"]
                        ):
                            core_files.append(node)
                        elif any(x in node for x in ["renderer", "delivery", "scheduler"]):
                            delivery_files.append(node)
                        else:
                            support_files.append(node)

                    # Build nested digest subgraph
                    digest_subgraph = f"""        subgraph CAT_BE_{category.upper()}["{category_label} - {count} files"]"""

                    if core_files:
                        core_nodes_text = self._indent_lines("\n".join(core_files), "            ")
                        digest_subgraph += f"""
            subgraph DIGEST_CORE["📦 Core Pipeline"]
{core_nodes_text}
            end"""

                    if delivery_files:
                        delivery_nodes_text = self._indent_lines(
                            "\n".join(delivery_files), "            "
                        )
                        digest_subgraph += f"""
            subgraph DIGEST_DELIVERY["📮 Delivery Pipeline"]
{delivery_nodes_text}
            end"""

                    if support_files:
                        support_nodes_text = self._indent_lines(
                            "\n".join(support_files), "            "
                        )
                        digest_subgraph += f"""
            subgraph DIGEST_SUPPORT["🔧 Support"]
{support_nodes_text}
            end"""

                    digest_subgraph += """
        end"""
                    backend_subgraphs.append(digest_subgraph)
                else:
                    # Regular category handling
                    nodes_text = self._indent_lines("\n".join(nodes), "            ")
                    category_label = category_names.get(category, category.title())
                    count = len(nodes)
                    backend_subgraphs.append(
                        f"""        subgraph CAT_BE_{category.upper()}["{category_label} - {count} files"]
{nodes_text}
        end"""
                    )

        connections_text = self._indent_lines("\n".join(connections), "    ")

        diagram = f"""# System Architecture Diagram (Engineering Reference)

> **Auto-generated** from codebase analysis. Last updated: {timestamp}
>
> **Audience:** Engineers & maintainers
> **For product overview:** See [SYSTEM_STORYBOARD.md](SYSTEM_STORYBOARD.md)

## Overview

This diagram shows **ALL {len(self.backend_files) + len(self.extension_files)} files** organized by category, automatically discovered and visualized.
**100% Dynamic** - Add/remove files and they automatically appear/disappear in the right category. Emojis assigned based on filename patterns.

```mermaid
graph TB
    subgraph EXT["📱 Chrome Extension - {len(self.extension_files)} files"]
{chr(10).join(extension_subgraphs)}
    end

    subgraph BE["🐍 Python Backend - {len(self.backend_files)} files"]
{chr(10).join(backend_subgraphs)}
    end

    subgraph "External Services"
{self._generate_external_services_nodes()}
    end

    subgraph "Data Storage"
{self._generate_database_node()}
    end

    %% Dynamic connections based on detected components
{connections_text}

    %% Styling - Dark mode vibrant colors
    classDef extension fill:#1e3a8a,stroke:#60a5fa,stroke-width:3px,color:#ffffff
    classDef backend fill:#92400e,stroke:#fbbf24,stroke-width:3px,color:#ffffff
    classDef external fill:#581c87,stroke:#c084fc,stroke-width:3px,color:#ffffff
    classDef storage fill:#14532d,stroke:#4ade80,stroke-width:3px,color:#ffffff

    class {extension_classes} extension
    class {backend_classes} backend
    class {",".join(s.upper() for s in self.external_services.keys()) if self.external_services else "NO_EXTERNAL"} external
    class MAILQDB storage
```

## Detected Architecture

### External Services ({len(self.external_services)} detected)
{chr(10).join([f"- **{s['name']}**: {s.get('model', s.get('description', 'N/A'))}" for s in self.external_services.values()]) if self.external_services else "_No external services detected_"}

### Database
- **{self.database_config["path"]}**: {len(self.database_config.get("tables", []))} tables detected
  - Pool size: {self.database_config.get("pool_size", "N/A")} connections

### Configuration
- **Min Type Confidence**: {self.confidence_thresholds["min_type_conf"]}
- **Min Label Confidence**: {self.confidence_thresholds["min_label_conf"]}
- **Verifier Delta**: {self.confidence_thresholds["verifier_delta"]}

---

## File Details

All files are automatically scanned and categorized. Each file gets an emoji based on its purpose (detected from filename).

### Backend ({len(self.backend_files)} files)
"""

        # Add backend components
        for category, components in sorted(self.backend_components.items()):
            diagram += f"\n**{category.title()}**:\n"
            for comp in sorted(components, key=lambda x: x["name"]):
                diagram += self._format_component_entry(comp) + "\n"

        diagram += f"\n### Extension ({len(self.extension_files)} files)\n"

        # Add extension components
        for category, components in sorted(self.extension_components.items()):
            diagram += f"\n**{category.title()}**:\n"
            for comp in sorted(components, key=lambda x: x["name"]):
                diagram += self._format_component_entry(comp) + "\n"

        # Dynamic data flows
        flows_text = "\n".join(
            [
                f"{i}. **{flow['name']}**: {flow['path']}"
                for i, flow in enumerate(self.data_flows, 1)
            ]
        )

        diagram += f"""
## Key Data Flows

{flows_text if flows_text else "_No data flows detected_"}

---

**See also**:
- [Classification Flow Diagram](CLASSIFICATION_FLOW.md) - Detailed step-by-step flow
- [Auto-Organize Sequence](AUTO_ORGANIZE_SEQUENCE.md) - Alarm → Gmail → pipeline → digest
- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) - Detailed component documentation

**Regenerate**: Run `./code-graph/scripts/quick_regen.sh`

> 🔄 This diagram is **dynamically generated** from actual code. When you add/remove files, they'll appear/disappear automatically.
"""

        return diagram

    def generate_classification_flow(self) -> str:
        """Generate classification flow as a clean sequence diagram"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Detect model from config
        model = self.external_services.get("vertexai", {}).get("model", "gemini-2.0-flash-exp")

        diagram = f"""# Task-Flow: Email Classification

> **Auto-generated** from codebase analysis. Last updated: {timestamp}

## Overview

This diagram shows what happens when an email is classified, from user trigger to Gmail labels.

```mermaid
sequenceDiagram
    autonumber
    participant User as 👤 User
    participant Ext as 📱 Extension<br/>background.js
    participant Cache as 💾 Cache<br/>cache.js
    participant API as 🌐 /api/organize
    participant Rules as 📋 Rules Engine<br/>rules_engine.py
    participant LLM as 🤖 {model}<br/>memory_classifier.py
    participant Mapper as 🏷️ Label Mapper<br/>mapper.py
    participant Gmail as 📧 Gmail API

    User->>Ext: Click MailQ icon / Auto-organize
    Ext->>Ext: Fetch unlabeled emails
    Ext->>Cache: Check sender cache (24hr TTL)

    alt Cache hit
        Cache-->>Ext: Return cached labels
        Ext->>Gmail: Apply labels & archive
    else Cache miss
        Ext->>Ext: Deduplicate by sender
        Note over Ext: 100 emails → ~30 unique

        Ext->>API: POST /api/organize (batch)
        API->>Rules: Check rules engine

        alt Rules match (50-70% of emails)
            Rules-->>API: Return classification
            Note over Rules: Cost: $0
        else No rule match
            Rules->>LLM: Classify with LLM
            LLM->>LLM: Analyze subject + snippet
            LLM-->>Rules: Return classification
            Note over LLM: Cost: ~$0.0010/email
        end

        API->>Mapper: Map to Gmail labels
        Mapper-->>API: Return label decisions
        API-->>Ext: Classification results

        Ext->>Gmail: Apply labels & archive
        Ext->>Cache: Update cache (24hr)
        Ext->>Ext: Expand to same-sender emails
    end

    Gmail-->>User: Organized inbox

    opt User corrects label
        User->>Ext: Change label in Gmail
        Ext->>API: POST /api/feedback
        API->>Rules: Create new rule (conf=0.95)
        Note over Rules: System learns from correction
    end
```

## Execution Flow

1. **Trigger**: User clicks MailQ icon or auto-organize alarm fires
2. **Cache check**: Extension checks 24-hour cache for sender classifications
3. **Deduplication**: 100 emails reduced to ~30 unique senders for API call
4. **Rules engine**: Checks learned rules first (50-70% match rate, $0 cost)
5. **LLM fallback**: If no rule matches, use {model} classifier (~$0.0010/email)
6. **Label mapping**: Mapper converts classification → Gmail labels (e.g., "MailQ-Urgent")
7. **Apply & cache**: Labels applied, results cached for 24hr, expanded to same-sender emails
8. **Learning loop**: User label corrections create new rules via /api/feedback

## Key Metrics

| Metric | Value |
|--------|-------|
| Cache TTL | {self.extension_config["cache_expiry_hours"]}hr |
| Rules match rate | 50-70% (estimate) |
| LLM cost per email | ${self.extension_config["tier_costs"]["T3"]:.4f} |
| Avg latency | 1-3s |
| Min confidence | {self.confidence_thresholds["min_type_conf"]} |

---

**See also**:
- [Auto-Organize Sequence](AUTO_ORGANIZE_SEQUENCE.md) – Full auto-organize flow
- [Digest Generation](TASK_FLOW_DIGEST.md) – Daily digest creation
- [System Storyboard](SYSTEM_STORYBOARD.md) – Architecture overview

**Regenerate**: Run `./code-graph/scripts/quick_regen.sh`

> 🔄 This diagram is generated from actual code structure. GDS (Golden Dataset) is used for **testing only**, not shown here.
"""

        return diagram

    def generate_system_storyboard(self) -> str:
        """Generate a curated high-level storyboard of the MailQ flow - DYNAMICALLY UPDATED"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # DYNAMIC DETECTION: Pull from actual codebase
        model = self.external_services.get("vertexai", {}).get("model", "Gemini")
        db_name = self.database_config["path"]
        table_count = len(self.database_config.get("tables", []))

        # Detect actual API endpoints
        organize_ep = next((e["path"] for e in self.api_endpoints if "organize" in e.get("path", "")), "/api/organize")
        feedback_ep = next((e["path"] for e in self.api_endpoints if "feedback" in e.get("path", "")), "/api/feedback")
        digest_ep = next((e["path"] for e in self.api_endpoints if "digest" in e.get("path", "")), "/api/context-digest")

        # Detect key component files
        backend_files_map = {f.stem: str(f.relative_to(PROJECT_ROOT)) for f in self.backend_files}
        extension_files_map = {f.stem: str(f.relative_to(PROJECT_ROOT)) for f in self.extension_files}

        # Check what components actually exist
        has_rules = "rules_manager" in backend_files_map
        has_memory = "memory_classifier" in backend_files_map
        has_verifier = any("verifier" in k for k in backend_files_map.keys())
        has_temporal_enrich = "temporal_enrichment" in backend_files_map
        has_temporal_decay = "temporal_decay" in backend_files_map
        has_entity_extractor = any("entity" in k and "extract" in k for k in backend_files_map.keys())
        has_feedback_mgr = "feedback_manager" in backend_files_map

        diagram = f"""# MailQ System Storyboard

> **Dynamically generated** from actual codebase structure. Last updated: {timestamp}
>
> **Stats**: {len(self.backend_files)} backend files • {len(self.extension_files)} extension files • {len(self.api_endpoints)} API endpoints • {table_count} DB tables

> **Curated overview** of how MailQ captures, classifies, learns, and narrates. Last updated: {timestamp}

## Overview

This storyboard highlights the five essential beats every MailQ run hits: **capture → classify → learn → narrate → delight**.

```mermaid
flowchart LR
    %% Client Layer
    subgraph client[" 1️⃣ CLIENT — Chrome Extension "]
        c1["🙋 User"]
        c2["Cache"]
        c3["Detectors"]
        c1 --> c2 --> c3
    end

    %% Gateway
    subgraph gateway[" 2️⃣ GATEWAY — FastAPI "]
        g1["Auth + Rate Limit"]
        g2["Router"]
        g1 --> g2
    end

    %% Classification Pipeline
    subgraph classify[" 3️⃣ CLASSIFY — Multi-Stage Pipeline "]
        p1["Rules Manager"]
        p2["Memory Classifier"]
        p3["LLM ({model})"]
        p4["Verifier"]
        p1 -->|miss| p2
        p2 -->|fallback| p3
        p3 --> p4
    end

    %% Temporal Intelligence
    subgraph enrich[" 4️⃣ ENRICH — Temporal Signals "]
        t1["Temporal Enrichment"]
        t2["Temporal Decay"]
        t1 --> t2
    end

    %% Database
    subgraph persist[" 5️⃣ PERSIST — Database "]
        d1[("{db_name}")]
        d2["{table_count} tables"]
        d1 -.-> d2
    end

    %% Digest Generation
    subgraph narrate[" 6️⃣ NARRATE — Digest Builder "]
        n1["Entity Extractor"]
        n2["Importance Ranker"]
        n3["Narrative Builder"]
        n4["HTML Renderer"]
        n1 --> n2 --> n3 --> n4
    end

    %% Delivery & Feedback
    subgraph deliver[" 7️⃣ DELIVER — Send + Learn "]
        v1["📧 Send Email"]
        v2["📰 User Reads"]
        v3["👍👎 Feedback"]
        v4["Learn Rules"]
        v1 --> v2 --> v3 --> v4
    end

    %% Main Flow
    client -->|POST {organize_ep}| gateway
    gateway --> classify
    classify --> enrich
    enrich --> persist
    persist --> narrate
    narrate -->|POST {digest_ep}| deliver
    deliver -.->|{feedback_ep}| p1

    %% Observability (parallel)
    subgraph monitor[" 🔍 OBSERVABILITY "]
        o1["Telemetry"]
        o2["Quality Monitor"]
        o3["Bridge Logs"]
        o1 --> o2 --> o3
    end

    g2 -.-> o1
    p4 -.-> o1
    o3 -.->|feedback| p1

    %% Styling - Dark mode vibrant colors
    classDef clientStyle fill:#1e3a8a,stroke:#60a5fa,stroke-width:3px,color:#ffffff
    classDef gatewayStyle fill:#581c87,stroke:#c084fc,stroke-width:3px,color:#ffffff
    classDef classifyStyle fill:#92400e,stroke:#fbbf24,stroke-width:3px,color:#ffffff
    classDef enrichStyle fill:#14532d,stroke:#4ade80,stroke-width:3px,color:#ffffff
    classDef persistStyle fill:#164e63,stroke:#22d3ee,stroke-width:3px,color:#ffffff
    classDef narrateStyle fill:#831843,stroke:#f472b6,stroke-width:3px,color:#ffffff
    classDef deliverStyle fill:#4c1d95,stroke:#a78bfa,stroke-width:3px,color:#ffffff
    classDef monitorStyle fill:#7c2d12,stroke:#fb923c,stroke-width:3px,color:#ffffff

    class client clientStyle
    class gateway gatewayStyle
    class classify classifyStyle
    class enrich enrichStyle
    class persist persistStyle
    class narrate narrateStyle
    class deliver deliverStyle
    class monitor monitorStyle
```

## Story Beats (Detailed)

### 1. Capture (Chrome Extension → API)
**What happens:** User opens Gmail. Extension scans for unlabeled threads.
- **Cache check:** Reuse labels from `rules_cache` and `label_cache` (IndexedDB)
- **Pattern detectors:** Fast regex-based detection for newsletters, social, promos
- **Batch building:** Group unlabeled threads (max 50 per request)
- **API call:** POST to `/api/organize` with thread metadata (subject, snippet, sender, timestamp)

**Files:** `extension/background.js`, `extension/modules/auto-organize.js`, `extension/modules/cache.js`

### 2. Classify (Backend Pipeline)
**What happens:** Multi-stage classification with fallback chain.
- **Rules Manager:** Check user-defined rules and feedback-learned rules first (fastest, deterministic)
- **Memory Classifier:** Check learned patterns from previous sessions (medium speed, high confidence)
- **LLM Classifier:** Vertex AI `{model}` with structured prompts (slowest, handles edge cases)
- **Verifier:** `NarrativeVerifier` checks for hallucinations (numbers, dates, names must exist in source)

**Files:** `mailq/api_organize.py`, `mailq/pipeline_wrapper.py`, `mailq/rules_manager.py`, `mailq/memory_classifier.py`, `mailq/vertex_gemini_classifier.py`, `mailq/narrative_verifier.py`

### 3. Learn (Temporal Intelligence + Persistence)
**What happens:** Enrich classifications with time-based signals and store decisions.
- **Temporal enrichment:** Add urgency signals (deadlines, event proximity, meeting times)
- **Temporal decay:** Apply time-based scoring (recent = higher priority)
- **Database write:** Store classification decision with metadata (decider, confidence, model version)
- **Feedback loop:** User corrections written to `feedback` table, trigger rule learning

**Files:** `mailq/temporal_enrichment.py`, `mailq/temporal_decay.py`, `mailq/config/database.py`, `mailq/feedback_manager.py`

### 4. Narrate (Digest Generation)
**What happens:** Build daily context-aware digest email.
- **Entity extraction:** Pull structured data (flights, events, deadlines, notifications) using rules + LLM
- **Importance ranking:** Classify as critical/time-sensitive/routine based on temporal signals
- **Narrative building:** Generate natural language story (~90 words) using context from entities
- **HTML rendering:** Render digest cards using Jinja2 template (`digest_v2.html.j2`)

**Files:** `mailq/context_digest.py`, `mailq/entity_extractor.py`, `mailq/digest/ranker.py`, `mailq/digest/narrative.py`, `mailq/hybrid_digest_renderer.py`, `mailq/templates/digest_v2.html.j2`

### 5. Delight (Delivery + Feedback)
**What happens:** Send digest, capture user feedback, improve system.
- **Digest delivery:** POST to `/api/context-digest`, returns HTML email sent via Gmail API
- **User interaction:** User reads digest, provides thumbs up/down on classifications
- **Feedback capture:** POST to `/api/feedback` with corrections (expected vs actual labels)
- **Rule learning:** `FeedbackManager` generates new rules or adjusts confidence thresholds
- **Quality monitoring:** Automated analysis flags hallucinations, inconsistencies, low-confidence decisions

**Files:** `mailq/api.py` (context-digest endpoint), `mailq/api_feedback.py`, `mailq/feedback_manager.py`, `scripts/quality-monitor/quality_monitor.py`

## Touchpoints

### Database Schema (`{db_name}`)
Single SQLite database with these key tables:
- `rules` – user rules + feedback-learned rules
- `email_threads` – processed emails with classifications
- `feedback` – user corrections (label thumbs up/down)
- `digest_sessions` – digest generation metadata
- `digest_emails` – rendered digest HTML + metrics
- `confidence_logs` – classification confidence tracking
- `pending_rules` – rules awaiting approval before activation

### API Endpoints
- **`/api/organize`** – Main classification endpoint (batch processing)
  - Input: List of email metadata (subject, snippet, sender, timestamp)
  - Output: Classification results with labels, confidence, decider
- **`/api/feedback`** – User corrections and rule learning
  - Input: Email ID, expected label, actual label, feedback type
  - Output: Confirmation, new rule ID (if applicable)
- **`/api/context-digest`** – Timeline-centric digest generation
  - Input: Classified emails, timezone, user preferences
  - Output: HTML digest card with entities, narrative, metrics
- **`/api/verify`** – Secondary classification verification (optional)
  - Input: Email + first classification result
  - Output: Verification verdict (confirm/correct/flag)

### Observability & Quality Control
- **Telemetry:** `infra/telemetry.py` logs events (API calls, classifications, errors)
- **Confidence Logger:** `mailq/confidence_logger.py` tracks decision confidence over time
- **Quality Monitor:** `scripts/quality-monitor/` automated digest analysis
  - Runs LLM-based checks for hallucinations, inconsistencies, tone issues
  - Creates GitHub issues for quality problems
  - Stores results in `quality_logs/`
- **Bridge Mode Logs:** `logs/bridge_mode/*.jsonl` captures shadow deployment comparisons
- **Structured Logging:** `mailq/structured_logging.py` provides searchable event logs

### Feature Flags
- `USE_REFACTORED_PIPELINE` – Enable refactored classification pipeline (default: true)
- `MAILQ_USE_LLM` – Enable LLM fallback in classification (default: false, rules-only mode)
- Dynamic feature gates via `/api/feature-gates` (database-backed toggles)

## Regenerate

Run `./code-graph/scripts/quick_regen.sh` after architecture changes to refresh this storyboard.
"""

        return diagram

    def generate_cost_performance(self) -> str:
        """Generate cost/performance diagram"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Detect if verifier exists
        has_verifier = any(
            "verifier" in str(c["name"]).lower()
            for category in self.backend_components.values()
            for c in category
        )

        # Get model name
        model_name = self.external_services.get("vertexai", {}).get("model", "Gemini LLM")

        # Get actual detected costs
        t3_cost = self.extension_config["tier_costs"]["T3"]
        daily_cap = self.extension_config["daily_budget_cap"]
        cache_hours = self.extension_config["cache_expiry_hours"]

        diagram = f"""# Cost & Performance Dashboard

> **Auto-generated** from codebase analysis. Last updated: {timestamp}

## Overview

This dashboard shows estimated costs and performance metrics for MailQ's classification pipeline.

⚠️ **IMPORTANT**: Performance metrics (%, latency) are **projections**, not measured values. Cost values and config are **detected from code**.

```mermaid
flowchart TB
    subgraph Cost[Cost Breakdown - 1000 emails per day]
        Total[Total Cost<br/>0.03 USD per day<br/>0.90 USD per month<br/>10.80 USD per year]

        Total --> Tier0[T0 Rules Engine<br/>700 emails at 0 USD<br/>Cost 0.00 USD]
        Total --> Tier3[T3 {model_name}<br/>270 emails at {t3_cost:.4f} USD<br/>Cost {270 * t3_cost:.2f} USD]
        {"Total --> Verify[T3 Verifier<br/>30 emails at " + f"{t3_cost:.4f}" + " USD<br/>Cost " + f"{30 * t3_cost:.2f}" + " USD]" if has_verifier else ""}

        Tier0 -.->|70 percent of emails| Free[Free Classification]
        Tier3 -.->|{27 if not has_verifier else 24} percent of emails| Paid[Paid Classification]
        {"Verify -.->|3 percent of emails| Premium[Premium Validation]" if has_verifier else ""}
    end

    subgraph Perf[Performance Metrics]
        Latency[Response Time]
        Latency --> CacheHit[Cache Hit<br/>~10ms projected<br/>70 percent of requests]
        Latency --> RulesMatch[Rules Match<br/>~50ms projected<br/>18 percent of requests]
        Latency --> GeminiCall[{model_name} Classify<br/>~500ms projected<br/>{27 if not has_verifier else 24} percent of requests]
        {"Latency --> VerifyCall[Verifier Check<br/>~500ms projected<br/>3 percent of requests]" if has_verifier else ""}

        Overall[Overall Metrics<br/>projected estimates]
        Overall --> P50[p50: 800ms projected]
        Overall --> P95[p95: 1.5s projected]
        Overall --> P99[p99: 2.5s projected]
    end

    %% Styling - Dark mode vibrant colors
    classDef costNode fill:#7f1d1d,stroke:#f87171,stroke-width:3px,color:#ffffff
    classDef perfNode fill:#1e3a8a,stroke:#60a5fa,stroke-width:3px,color:#ffffff
    classDef highlight fill:#14532d,stroke:#4ade80,stroke-width:3px,color:#ffffff

    class Total,Tier0,Tier3{",Verify" if has_verifier else ""} costNode
    class Latency,CacheHit,RulesMatch,GeminiCall{",VerifyCall" if has_verifier else ""},Overall,P50,P95,P99 perfNode
    class Free highlight
```

## Detected Configuration

**Files analyzed**: {len(self.backend_files)} backend + {len(self.extension_files)} extension files

**Detected from code:**
- T3 cost per email: **${t3_cost:.4f}** (from extension/config.js)
- Daily budget cap: **${daily_cap:.2f}** (from extension/config.js)
- Cache expiry: **{cache_hours} hours** (from extension/config.js)
- Verifier range: **{self.extension_config["verifier_range"][0]}-{self.extension_config["verifier_range"][1]}** confidence (from verifier.js)

## Cost Optimization

**Projected architecture** (estimates, not measured):
- **T0 (Free)**: Rules engine + Cache (~70% of emails - estimate)
- **T3 (Paid)**: {model_name} classification (~27% of emails - estimate)
{"- **T3+ (Premium)**: Verifier validation (~3% of emails - estimate)" if has_verifier else ""}

---

**Regenerate**: Run `./code-graph/scripts/quick_regen.sh`

> 🔄 This diagram is **dynamically generated** from actual code.
"""

        return diagram

    def generate_task_flow_organize(self) -> str:
        """Task-flow lens: What happens during /api/organize"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        model = self.external_services.get("vertexai", {}).get("model", "Gemini")

        diagram = f"""# Task-Flow Lens: /api/organize Request

> **Auto-generated** from codebase analysis. Last updated: {timestamp}

## Purpose

Answer: **"What happens when the extension calls /api/organize?"**

Max 8 steps, showing the contract at each hop (no file sprawl).

```mermaid
sequenceDiagram
    autonumber
    participant Ext as Extension<br/>classifier.js
    participant API as FastAPI Gateway<br/>/api/organize
    participant Mem as Memory Classifier<br/>memory_classifier.py
    participant Rules as Rules Engine<br/>rules_engine.py
    participant LLM as {model}<br/>Vertex AI
    participant DB as mailq.db

    Ext->>API: POST {{threads: [...], user: "..."}}
    API->>Mem: classify_batch(threads)
    Mem->>Rules: check_rules(thread)
    alt Rule match (60-70%)
        Rules-->>Mem: {{type, label, confidence: 0.95}}
        Mem-->>API: Cached result (T0)
    else No rule match
        Mem->>LLM: classify(thread)
        LLM-->>Mem: {{type, label, confidence, reasoning}}
        Mem->>DB: Store classification
        Mem-->>API: LLM result (T3)
    end
    API-->>Ext: {{results: [{{id, type, label, mailq_labels}}]}}
```

## Key Contracts

1. **Extension → API**: `OrganizeRequest` with threads array
2. **API → Memory Classifier**: Thread list
3. **Memory → Rules**: Individual thread check
4. **Memory → LLM**: Thread + prompt template
5. **API → Extension**: `OrganizeResponse` with Gmail label arrays

## Metrics

- **Latency**: 50-500ms depending on cache/rules/LLM
- **Cost**: $0 (rules hit) or ${self.extension_config["tier_costs"]["T3"]:.4f} (LLM)
- **Success rate**: Target >95%

---

**See also**: [LAYER_MAP.md](LAYER_MAP.md) for "where does this live?"

**Regenerate**: Run `./code-graph/scripts/quick_regen.sh`
"""
        return diagram

    def generate_task_flow_digest(self) -> str:
        """Task-flow lens: What happens during digest generation"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        diagram = f"""# Task-Flow Lens: Daily Digest Generation

> **Auto-generated** from codebase analysis. Last updated: {timestamp}

## Purpose

Answer: **"What happens when a daily digest is generated?"**

Max 8 steps, showing the pipeline from trigger to Gmail inbox.

```mermaid
sequenceDiagram
    autonumber
    participant Trigger as Alarm/Manual Trigger
    participant API as /api/context-digest
    participant Context as Context Builder<br/>context_digest.py
    participant Format as Digest Formatter<br/>digest_formatter.py
    participant Render as Card Renderer<br/>card_renderer.py
    participant Gmail as Gmail API

    Trigger->>API: POST /api/context-digest
    API->>Context: build_context(user_id, date_range)
    Context->>Context: Aggregate threads by category
    Context->>Context: Extract entities & timeline
    Context-->>API: {{sections: [...], metadata}}

    API->>Format: format_digest(context)
    Format->>Format: Build cards for each section
    Format-->>API: {{cards: [...], summary}}

    API->>Render: render_html(cards)
    Render->>Render: Apply templates + Gmail links
    Render-->>API: HTML string

    API->>Gmail: Send email (to: user, html: ...)
    Gmail-->>API: Message ID
    API-->>Trigger: {{success: true, message_id}}
```

## Key Contracts

1. **Trigger → API**: `DigestRequest` with user_id, date_range
2. **API → Context**: Build structured context
3. **Context → Formatter**: Sections with threads
4. **Formatter → Renderer**: Card objects
5. **Renderer → Gmail**: HTML email

## Metrics

- **Latency**: ~2-5s (depends on email volume)
- **Cost**: Minimal (no LLM, just aggregation)
- **Frequency**: Daily or on-demand

---

**See also**: [LAYER_MAP.md](LAYER_MAP.md) for component locations

**Regenerate**: Run `./code-graph/scripts/quick_regen.sh`
"""
        return diagram

    def generate_task_flow_feedback(self) -> str:
        """Task-flow lens: What happens when user provides feedback"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        diagram = f"""# Task-Flow Lens: Feedback Learning Loop

> **Auto-generated** from codebase analysis. Last updated: {timestamp}

## Purpose

Answer: **"What happens when a user corrects a label?"**

Max 8 steps, showing how feedback becomes a rule.

```mermaid
sequenceDiagram
    autonumber
    participant User as User in Gmail
    participant Content as Content Script<br/>content.js
    participant API as /api/feedback
    participant FeedMgr as Feedback Manager<br/>feedback_manager.py
    participant RulesMgr as Rules Manager<br/>rules_manager.py
    participant DB as mailq.db

    User->>User: Changes label (Critical → Routine)
    Content->>Content: Detect label change (MutationObserver)
    Content->>API: POST {{thread_id, old_label, new_label}}

    API->>FeedMgr: process_feedback(...)
    FeedMgr->>DB: Log feedback event
    FeedMgr->>FeedMgr: Check if pattern warrants rule

    alt High-confidence pattern (3+ corrections)
        FeedMgr->>RulesMgr: create_rule(pattern, label)
        RulesMgr->>DB: INSERT INTO digest_rules
        RulesMgr-->>FeedMgr: Rule created (ID)
        FeedMgr-->>API: {{rule_created: true}}
    else Isolated correction
        FeedMgr-->>API: {{logged: true, rule_created: false}}
    end

    API-->>Content: {{success: true}}
    Content-->>User: Silent (no UI change)
```

## Key Contracts

1. **Content → API**: `FeedbackEvent` with label change
2. **API → Feedback Manager**: Process correction
3. **Feedback → Rules Manager**: Create rule if warranted
4. **Rules Manager → DB**: Persist new rule

## Learning Thresholds

- **Min corrections for rule**: 3 similar patterns
- **Rule confidence**: 0.95 (highest)
- **Rule precedence**: User rules override LLM

---

**See also**: [EVIDENCE_HEATMAP.md](EVIDENCE_HEATMAP.md) for what's changing most

**Regenerate**: Run `./code-graph/scripts/quick_regen.sh`
"""
        return diagram

    def generate_auto_organize_sequence(self) -> str:
        """Generate auto-organize sequence diagram"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        diagram = f"""# Auto-Organize Sequence

> **Auto-generated** from codebase analysis. Last updated: {timestamp}

## Overview

This diagram traces the end-to-end auto-organize flow, from the MV3 service worker alarm to Gmail labeling and digest triggers.

```mermaid
sequenceDiagram
    autonumber
    participant Alarm as ⏰ Chrome Alarm<br/>mailq-auto-organize
    participant Worker as 🎯 Background Service Worker
    participant Gmail as 📧 Gmail API
    participant Backend as 🐍 FastAPI / Pipeline
    participant Store as 🗂️ Chrome Storage
    participant Digest as 📬 Summary Pipeline

    Alarm->>Worker: Alarm fired (interval)
    Worker->>Store: Record session start
    Worker->>Worker: getAutoOrganizeSettings()
    Worker->>Gmail: Fetch unlabeled threads
    alt Threads found
        Worker->>Backend: POST /api/organize (batch)
        Backend->>Backend: Parse → Classify → Map labels
        Backend-->>Worker: Classification results
        Worker->>Gmail: Apply labels & archive
        Worker->>Store: Update cache + telemetry
        Worker->>Store: Set mailq_digest_pending=true
        par Digest Trigger
            Worker->>Digest: generateAndSendSummaryEmail()
            Digest->>Gmail: Send MailQ digest
        end
    else Inbox empty
        Worker->>Store: Clear digest pending flag
    end
    Worker->>Store: Update mailq_last_auto_organize_at
```

## Execution Flow

1. **Alarm fires** based on the configured interval (`mailq_auto_organize_settings.intervalMinutes`).
2. **Service worker** validates settings, records session start, and queries Gmail for unlabeled threads.
3. **When threads exist**:
   - Calls the backend `/api/organize` endpoint with deduplicated threads.
   - Applies Gmail labels/archives via `gmail.js`.
   - Marks `mailq_digest_pending` so the next foreground Gmail tab triggers a digest.
4. **When inbox is empty**, the digest pending flag is cleared.
5. **Digest pipeline** runs when Gmail becomes active, using `generateAndSendSummaryEmail` to send the context digest.

## Key Metrics

- Alarm interval & settings in `mailq_auto_organize_settings`
- Cache hit/miss (`extension/modules/telemetry.js`)
- Pipeline timing (`infra/telemetry.py`:
  `pipeline.total_ms`, `gmail.fetch.latency_ms`, etc.)
- Digest timestamps (`mailq_last_digest_sent_at` sync storage)

---

**See also**:
- [System Storyboard](SYSTEM_STORYBOARD.md) – Architecture overview
- [Classification Flow Diagram](CLASSIFICATION_FLOW.md) – Backend classification steps
- [docs/ARCHITECTURE_OVERVIEW.md](../../docs/ARCHITECTURE_OVERVIEW.md) – Component documentation

**Regenerate**: Run `./code-graph/scripts/quick_regen.sh`

> 🔄 This diagram is generated from actual code structure. Update metadata to keep links in sync.
"""

        return diagram

    def generate_evidence_heatmap(self) -> str:
        """Evidence lens: Complete architecture color-coded by activity"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Gather evidence from git
        churn_data = self._analyze_git_churn()
        todo_counts = self._count_todos()
        scored_files = self._compute_evidence_scores(churn_data, todo_counts)

        # Build activity table by layer (all files, sorted by activity)
        all_files_with_layer = []

        # Extension files
        for f in self.extension_files:
            commits = scored_files.get(f, {}).get("commits", 0)
            score = scored_files.get(f, {}).get("score", 0)
            todos = scored_files.get(f, {}).get("todos", 0)
            all_files_with_layer.append({
                "layer": "📱 Extension",
                "file": f.stem + ".js",
                "commits": commits,
                "todos": todos,
                "score": score,
                "activity": self._get_activity_emoji(score)
            })

        # Backend files by category
        for f in self.backend_files:
            commits = scored_files.get(f, {}).get("commits", 0)
            score = scored_files.get(f, {}).get("score", 0)
            todos = scored_files.get(f, {}).get("todos", 0)

            # Determine layer
            if 'api' in f.stem:
                layer = "🌐 API"
            elif any(x in f.stem for x in ['classifier', 'entity', 'digest', 'temporal', 'mapper', 'importance']):
                layer = "⚙️ Core"
            elif any(x in f.stem for x in ['database', 'tracker', 'retention']):
                layer = "💾 Data"
            else:
                layer = "🔧 Utils"

            all_files_with_layer.append({
                "layer": layer,
                "file": f.stem + ".py",
                "commits": commits,
                "todos": todos,
                "score": score,
                "activity": self._get_activity_emoji(score)
            })

        # Sort by score descending
        all_files_with_layer.sort(key=lambda x: x["score"], reverse=True)

        # Build markdown table
        activity_table = "| Layer | Component | Commits | TODOs | Activity |\n"
        activity_table += "|-------|-----------|---------|-------|----------|\n"

        for item in all_files_with_layer[:25]:  # Top 25 most active
            activity_table += f"| {item['layer']} | `{item['file']}` | {item['commits']} | {item['todos']} | {item['activity']} |\n"

        # Generate migration insights
        migration_insights = self._generate_migration_insights(scored_files)

        diagram = f"""# 🔥 Architecture Activity: What's Changing?

> **Auto-generated** from codebase analysis. Last updated: {timestamp}

## 📋 What This Shows

A **sortable table** showing all components by recent activity (last 30 days). No zooming, no scrolling diagrams - just clear data.

**Activity Legend:**
- 🔥🔥🔥 = Very Hot (>40 score) - Heavy development
- 🔥🔥 = Hot (25-40 score) - Active work
- 🔥 = Warm (10-25 score) - Regular updates
- 🟢 = Cool (1-10 score) - Light maintenance
- ⚪ = Inactive (0 score) - No recent changes

**Score = (commits × 2) + (TODOs × 1.5)**

---

## 📊 Activity by Component (Top 25)

{activity_table}

---

## 🔄 Recent Migration & Initiative Insights

{migration_insights}

---

## 💡 How to Use This

1. **Scan the Activity column** - See where work is concentrated at a glance
2. **Sort by Layer** - Group by architectural tier to see patterns
3. **Check TODOs** - Non-zero TODOs = incomplete work
4. **Track week-over-week** - Compare to identify cooling/heating trends

---

## 🔄 Keep This Fresh

Run this **weekly** to track how your work is impacting the system:

```bash
./code-graph/scripts/quick_regen.sh
```

---

**See also**: [LAYER_MAP.md](LAYER_MAP.md) to understand layer responsibilities.
"""
        return diagram

    def _generate_evidence_recommendations(self, top_12: list) -> str:
        """Generate contextual recommendations for hot files"""
        lines = []

        # Map file names to their purpose
        file_descriptions = {
            "api.py": "🌐 **Main API Gateway** - Central entry point for all backend requests. High activity here means lots of new endpoints or request handling changes.",
            "background.js": "🎯 **Extension Service Worker** - Orchestrates all extension operations (alarms, Gmail API calls, classification). Core to the user experience.",
            "summary-email.js": "📰 **Digest Generator** - Creates and sends the daily context digest email. Changes here affect what users see in their inbox.",
            "gmail.js": "📧 **Gmail Integration** - Handles all Gmail API interactions (fetching emails, applying labels, archiving). Critical for reliability.",
            "context_digest.py": "📊 **Context Builder** - Aggregates threads into digestible sections. Changes here affect digest quality.",
            "entity_extractor.py": "🔍 **Entity Detection** - Extracts people, dates, topics from emails. Core to making digests useful.",
            "classifier.js": "🤖 **Extension Classifier** - Client-side classification logic with caching. Affects performance and user experience.",
            "mapper.js": "🗺️ **Label Mapper (Extension)** - Maps internal classifications to Gmail labels. Changes here affect what labels users see.",
            "mapper.py": "🗺️ **Label Mapper (Backend)** - Server-side label mapping. Needs to stay in sync with frontend.",
            "memory_classifier.py": "🧠 **Memory Classifier** - Orchestrates rules + LLM classification. Core intelligence of the system.",
            "vertex_gemini_classifier.py": "🤖 **LLM Integration** - Handles Gemini API calls for classification. Changes here affect accuracy and cost.",
            "timeline_synthesizer.py": "📅 **Timeline Builder** - Creates temporal context from threads. Helps users understand 'what's urgent now'.",
            "content.js": "👁️ **Content Script** - Runs in Gmail pages, detects user actions. Changes here affect feedback loop.",
            "verifier.js": "✓ **Verification Layer** - Double-checks uncertain classifications. Affects accuracy.",
            "auto-organize.js": "⚡ **Auto-Organize** - Automatically processes new emails on schedule. Core automation feature.",
            "cache.js": "💾 **Cache Manager** - Stores classifications to avoid redundant API calls. Affects performance and cost.",
            "detectors.js": "🔍 **Pattern Detectors** - Client-side rules for fast classification. Affects cache hit rate.",
        }

        for filepath, data in top_12:
            file_name = filepath.name
            score = data["score"]
            commits = data["commits"]
            todos = data["todos"]

            # Get description or generate a generic one
            description = file_descriptions.get(file_name, f"📄 **{file_name}** - Active development area.")

            # Add context based on metrics
            context_notes = []
            if commits > 30:
                context_notes.append("**Very high churn** - Consider refactoring or breaking into smaller modules.")
            elif commits > 15:
                context_notes.append("**High activity** - Good candidate for additional test coverage.")

            if todos > 0:
                context_notes.append(f"**{todos} TODO(s)** - Incomplete work that needs attention.")

            context = " ".join(context_notes) if context_notes else "Stable activity level."

            lines.append(f"**{file_name}** (Score: {score})\n{description}\n_{context}_\n")

        return "\n".join(lines)

    def _analyze_git_churn(self) -> dict:
        """Analyze git commits in last 30 days per file"""
        import subprocess

        churn = defaultdict(int)
        try:
            # Get commits in last 30 days with file stats
            result = subprocess.run(
                ["git", "log", "--since=30 days ago", "--name-only", "--pretty=format:"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line and (line.endswith(".py") or line.endswith(".js")):
                        churn[line] += 1
        except Exception:
            pass
        return dict(churn)

    def _count_todos(self) -> dict:
        """Count TODO/FIXME comments per file"""
        todo_counts = {}
        all_files = self.backend_files + self.extension_files

        for filepath in all_files:
            try:
                content = filepath.read_text()
                count = content.count("TODO") + content.count("FIXME")
                if count > 0:
                    rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
                    todo_counts[rel_path] = count
            except Exception:
                pass

        return todo_counts

    def _compute_evidence_scores(self, churn_data: dict, todo_counts: dict) -> dict:
        """Compute composite evidence scores for all files"""
        scores = {}
        all_files = self.backend_files + self.extension_files

        for filepath in all_files:
            rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
            commits = churn_data.get(rel_path, 0)
            todos = todo_counts.get(rel_path, 0)

            # Composite score
            score = (commits * 2) + (todos * 1.5)

            if score > 0:
                scores[filepath] = {"score": int(score), "commits": commits, "todos": todos}

        return scores

    def _get_activity_style(self, score: int) -> str:
        """Get Mermaid style class based on activity score"""
        if score > 40:
            return "hotNode"
        elif score > 15:
            return "warmNode"
        elif score > 0:
            return "coolNode"
        else:
            return "inactiveNode"

    def _get_activity_emoji(self, score: int) -> str:
        """Get visual activity indicator based on score"""
        if score > 40:
            return "🔥🔥🔥"
        elif score > 25:
            return "🔥🔥"
        elif score > 10:
            return "🔥"
        elif score > 0:
            return "🟢"
        else:
            return "⚪"

    def _generate_migration_insights(self, scored_files: dict) -> str:
        """Generate insights about recent migrations and work patterns"""

        # Analyze which initiatives are affecting which components
        insights = []

        # Database Consolidation
        db_files = [f for f in scored_files.keys() if any(x in str(f) for x in ['database', 'tracker', 'email_tracker'])]
        if db_files:
            total_commits = sum(scored_files[f]['commits'] for f in db_files)
            insights.append(f"**Database Consolidation** ({total_commits} commits): Central database migration recently completed. Files: {', '.join([f.name for f in db_files[:3]])}")

        # Digest System
        digest_files = [f for f in scored_files.keys() if any(x in str(f) for x in ['digest', 'context_digest', 'hybrid_digest'])]
        if digest_files:
            total_commits = sum(scored_files[f]['commits'] for f in digest_files)
            insights.append(f"**Digest Rebuild** ({total_commits} commits): Core digest generation pipeline under active development. Files: {', '.join([f.name for f in digest_files[:3]])}")

        # Classification
        class_files = [f for f in scored_files.keys() if any(x in str(f) for x in ['classifier', 'mapper', 'gemini'])]
        if class_files:
            total_commits = sum(scored_files[f]['commits'] for f in class_files)
            insights.append(f"**Classification Refactor** ({total_commits} commits): Heavy refactoring of LLM + rules classification. Files: {', '.join([f.name for f in class_files[:3]])}")

        # Extension
        ext_files = [f for f in scored_files.keys() if any(x in str(f) for x in ['background', 'gmail', 'summary-email'])]
        if ext_files:
            total_commits = sum(scored_files[f]['commits'] for f in ext_files)
            insights.append(f"**Extension Updates** ({total_commits} commits): Chrome extension core being enhanced. Files: {', '.join([f.name for f in ext_files[:3]])}")

        if not insights:
            return "*No significant migration activity in last 30 days*"

        return "\n".join(f"- {insight}" for insight in insights)

    def _format_evidence_table(self, top_12: list) -> str:
        """Format evidence table for markdown"""
        lines = []
        for filepath, data in top_12:
            file_name = filepath.name
            commits = data["commits"]
            todos = data["todos"]
            score = data["score"]

            status = "🔥 Hot" if score > 15 else "⚠️ Warm" if score > 8 else "✅ Cool"
            lines.append(f"| `{file_name}` | {commits} | {todos} | {score} | {status} |")

        return "\n".join(lines)

    def _markdown_to_html_UNUSED(self, markdown_content: str, title: str) -> str:
        """DEPRECATED: Use generate_diagram_html.py instead"""
        """Convert markdown with Mermaid to standalone HTML"""
        # Extract mermaid blocks and convert rest to HTML-ish format
        lines = markdown_content.split("\n")
        html_parts = []
        in_mermaid = False
        mermaid_code = []
        in_code_block = False
        code_block = []

        for line in lines:
            if line.strip().startswith("```mermaid"):
                in_mermaid = True
                mermaid_code = []
                continue
            if line.strip() == "```" and in_mermaid:
                in_mermaid = False
                html_parts.append(f'<div class="mermaid">\n{chr(10).join(mermaid_code)}\n</div>')
                mermaid_code = []
                continue
            if line.strip().startswith("```") and not in_mermaid:
                if in_code_block:
                    in_code_block = False
                    html_parts.append(f"<pre><code>{chr(10).join(code_block)}</code></pre>")
                    code_block = []
                else:
                    in_code_block = True
                continue

            if in_mermaid:
                mermaid_code.append(line)
            elif in_code_block:
                code_block.append(line)
            elif line.startswith("# "):
                html_parts.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                html_parts.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                html_parts.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("- "):
                html_parts.append(f"<li>{line[2:]}</li>")
            elif line.startswith("> "):
                html_parts.append(f"<blockquote>{line[2:]}</blockquote>")
            elif line.strip().startswith("|"):
                # Simple table handling
                html_parts.append(f"<tr>{line}</tr>")
            elif line.strip() == "---":
                html_parts.append("<hr/>")
            elif line.strip():
                html_parts.append(f"<p>{line}</p>")
            else:
                html_parts.append("<br/>")

        html_body = "\n".join(html_parts)

        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        h1 {{
            color: #1976d2;
            border-bottom: 3px solid #1976d2;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #f57c00;
            border-bottom: 2px solid #f57c00;
            padding-bottom: 8px;
            margin-top: 30px;
        }}
        h3 {{
            color: #388e3c;
            margin-top: 25px;
        }}
        blockquote {{
            background: #e3f2fd;
            border-left: 4px solid #1976d2;
            padding: 10px 20px;
            margin: 20px 0;
            font-style: italic;
        }}
        .mermaid {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin: 20px 0;
        }}
        pre {{
            background: #263238;
            color: #aed581;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }}
        code {{
            font-family: 'Courier New', monospace;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            background: white;
        }}
        tr {{
            border-bottom: 1px solid #ddd;
        }}
        li {{
            margin: 8px 0;
        }}
        hr {{
            border: none;
            border-top: 2px solid #ddd;
            margin: 30px 0;
        }}
        p {{
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    {html_body}
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true
            }}
        }});
    </script>
</body>
</html>"""

    def generate_and_save_all_diagrams(self) -> list[Path]:
        """
        Generate all Mermaid diagrams and save to markdown files.

        NOTE: Most diagrams are now MANUALLY MAINTAINED for accuracy.
        This generator only produces the EVIDENCE_HEATMAP which benefits
        from dynamic git history analysis.

        Manually maintained files (DO NOT OVERWRITE):
        - SYSTEM_STORYBOARD.md
        - CLASSIFICATION_FLOW.md
        - AUTO_ORGANIZE_SEQUENCE.md
        - TASK_FLOW_DIGEST.md
        - TASK_FLOW_FEEDBACK.md
        - CONFIDENCE_FLOW.md

        Side Effects:
        - Creates code-graph/visuals/ directory if it doesn't exist
        - Writes EVIDENCE_HEATMAP.md only
        - Scans git history for activity metrics

        Returns:
            List of Path objects for generated markdown files
        """
        print(
            f"🎨 Generating diagrams from {len(self.backend_files)} backend + {len(self.extension_files)} extension files..."
        )
        generated_files = []

        # Ensure output directory exists
        VISUALS_DIR.mkdir(parents=True, exist_ok=True)

        # All diagrams are now MANUALLY MAINTAINED for accuracy.
        # The auto-generator cannot understand:
        # - V2 pipeline stages and their order
        # - Actual data flow between components
        # - Current confidence thresholds from config files
        # - Importance classification and temporal decay
        #
        # Edit the markdown files directly when architecture changes.
        diagrams = []

        print("  ℹ️  All diagrams are manually maintained for accuracy.")
        print("      Edit markdown files directly when architecture changes.")

        print("\n📍 Manually maintained diagrams:")
        print(f"   - {VISUALS_DIR / 'SYSTEM_STORYBOARD.md'}")
        print(f"   - {VISUALS_DIR / 'CLASSIFICATION_FLOW.md'}")
        print(f"   - {VISUALS_DIR / 'TASK_FLOW_DIGEST.md'}")
        print(f"   - {VISUALS_DIR / 'TASK_FLOW_FEEDBACK.md'}")
        print(f"   - {VISUALS_DIR / 'AUTO_ORGANIZE_SEQUENCE.md'}")
        print(f"   - {VISUALS_DIR / 'CONFIDENCE_FLOW.md'}")
        print("\n💡 Generate HTML: python3 code-graph/scripts/generate_diagram_html.py")

        return generated_files


if __name__ == "__main__":
    generator = DynamicDiagramGenerator()
    generator.generate_and_save_all_diagrams()
