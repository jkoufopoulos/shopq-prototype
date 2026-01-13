"""

from __future__ import annotations

Generate human-readable documentation from codebase analysis
"""

import json
from pathlib import Path


def generate_analysis_md(analysis_path: Path, output_path: Path):
    """Generate CODEBASE_ANALYSIS.md with AI summaries"""

    with open(analysis_path) as f:
        data = json.load(f)

    files = data.get("files", {})
    deps = data.get("dependencies", {})
    js_deps = data.get("js_dependencies", {})
    stats = data.get("statistics", {})

    # Group files by type
    python_files = {k: v for k, v in files.items() if v.get("type") == "python"}
    js_files = {k: v for k, v in files.items() if v.get("type") == "javascript"}

    md = """# CODEBASE_ANALYSIS.md

# 📊 MailQ Codebase Analysis

**Generated:** {datetime.now().strftime("%B %d, %Y at %H:%M")}

---

## 📈 Statistics at a Glance

| Metric | Value |
|--------|-------|
| Total Files | {stats.get("total_files", 0)} |
| Python Files | {stats.get("python_files", 0)} |
| JavaScript Files | {stats.get("js_files", 0)} |
| Total Lines of Code | {stats.get("total_lines", 0):,} |
| Total Classes | {stats.get("total_classes", 0)} |
| Total Functions | {stats.get("total_functions", 0)} |

---

## 🐍 Python Backend Analysis

"""

    # Python files
    for path in sorted(python_files.keys()):
        info = python_files[path]

        md += f"\n### 📄 `{path}`\n\n"

        # AI Summary (NEW!)
        if "ai_summary" in info:
            md += f"**AI Summary:** {info['ai_summary']}\n\n"

        # Original docstring
        if info.get("docstring"):
            md += f"**Purpose:** {info['docstring'].split(chr(10))[0]}\n\n"

        # Classes
        if info.get("classes"):
            md += "**Classes:**\n"
            for cls in info["classes"]:
                md += f"- `{cls['name']}`"
                if cls.get("method_count", 0) > 0:
                    md += f" ({cls['method_count']} methods)"
                md += "\n"
            md += "\n"

        # Functions
        if info.get("functions"):
            md += "**Functions:**\n"
            for func in info["functions"][:10]:  # Limit to first 10
                md += f"- `{func['name']}()`\n"
            if len(info["functions"]) > 10:
                md += f"- *(+{len(info['functions']) - 10} more)*\n"
            md += "\n"

        # Dependencies
        if path in deps and deps[path]:
            md += "**Dependencies (internal):**\n"
            for dep in sorted(deps[path])[:5]:  # Top 5
                md += f"- `{dep}`\n"
            if len(deps[path]) > 5:
                md += f"- *(+{len(deps[path]) - 5} more)*\n"
            md += "\n"

        md += "---\n"

    md += "\n## 🌐 JavaScript Frontend Analysis\n\n"

    # JavaScript files
    for path in sorted(js_files.keys()):
        info = js_files[path]

        md += f"\n### 📄 `{path}`\n\n"

        # AI Summary (NEW!)
        if "ai_summary" in info:
            md += f"**AI Summary:** {info['ai_summary']}\n\n"

        # Original description
        if info.get("description"):
            md += f"**Purpose:** {info['description']}\n\n"

        # Characteristics
        md += "**Characteristics:**\n"
        md += f"- Lines of code: {info.get('lines', 0)}\n"
        md += f"- Uses ES6 modules: {'✅' if info.get('has_import') else '❌'}\n"
        md += f"- Contains async code: {'✅' if info.get('has_async') else '❌'}\n"
        md += f"- Makes HTTP requests: {'✅' if info.get('has_fetch') else '❌'}\n"
        md += "\n"

        # Dependencies
        if path in js_deps and js_deps[path]:
            md += "**Imports:**\n"
            for dep in sorted(js_deps[path])[:5]:
                md += f"- `{dep}`\n"
            if len(js_deps[path]) > 5:
                md += f"- *(+{len(js_deps[path]) - 5} more)*\n"
            md += "\n"

        md += "---\n"

    # Dependency graph
    md += "\n## 🔗 Dependency Graph\n\n"
    md += "**File dependencies (who imports whom):**\n\n"
    md += "```\n"

    def print_deps(path, visited=None, indent=0):
        if visited is None:
            visited = set()

        if path in visited:
            return ""

        visited.add(path)

        # Simplify path for display
        simple_path = path.replace("mailq/", "").replace(".py", "").replace("/__init__", "")

        output = "  " * indent + simple_path + "\n"

        if path in deps:
            for dep in sorted(deps[path])[:3]:  # Limit depth
                output += print_deps(dep, visited, indent + 1)

        return output

    # Show orchestrators first
    orchestrators = stats.get("orchestrators", [])
    for orch in orchestrators[:5]:
        md += print_deps(orch["path"])

    md += "```\n\n"

    # Key components
    md += "## 🎯 Key Components Summary\n\n"

    md += "**Orchestrator Files** (import many components):\n\n"
    for orch in orchestrators[:5]:
        md += f"- `{orch['path']}` - imports {orch['import_count']} internal modules\n"
    md += "\n"

    md += "**Core Classes** (with significant logic):\n\n"
    for cls in stats.get("core_classes", [])[:10]:
        md += f"- `{cls['class_name']}` in `{cls['path']}` - {cls['method_count']} methods\n"
    md += "\n"

    md += "---\n\n"
    md += "## 📝 Analysis Complete\n\n"
    md += "Use this report to understand:\n"
    md += "- File purposes and responsibilities (with AI summaries!)\n"
    md += "- Dependencies between components\n"
    md += "- Key classes and their methods\n"
    md += "- Entry points and orchestrators\n"

    # Write to file
    with open(output_path, "w") as f:
        f.write(md)

    print(f"✅ Generated: {output_path}")


if __name__ == "__main__":
    import sys

    # Check if we have summaries
    root_dir = Path(__file__).parent.parent
    analysis_with_summaries = root_dir / "codebase_analysis_with_summaries.json"
    analysis_basic = root_dir / "codebase_analysis.json"

    if analysis_with_summaries.exists():
        print("📄 Using analysis with AI summaries")
        input_file = analysis_with_summaries
    elif analysis_basic.exists():
        print("⚠️  Using basic analysis (no AI summaries)")
        print("   Run: python code-graph/scripts/ai_summarizer.py")
        input_file = analysis_basic
    else:
        print("❌ No analysis found. Run codebase_analyzer.py first")
        sys.exit(1)

    output_file = root_dir / "CODEBASE_ANALYSIS.md"

    generate_analysis_md(input_file, output_file)
