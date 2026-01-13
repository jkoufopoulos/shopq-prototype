"""Generate summary.html (AI overview)"""

from __future__ import annotations

import json
from pathlib import Path


def generate_summary_html(analysis_path: Path, output_path: Path):
    """Generate summary.html with architecture overview"""

    with open(analysis_path) as f:
        data = json.load(f)

    stats = data.get("statistics", {})
    orchestrators = stats.get("orchestrators", [])[:5]

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MailQ Summary</title>
    <style>
        {_get_summary_css()}
    </style>
</head>
<body>
    <header>
        <h1>📝 MailQ Architecture Summary</h1>
        <nav>
            <a href="index.html">← Back to Dashboard</a>
        </nav>
    </header>

    <main>
        <section class="overview">
            <h2>What This System Does</h2>
            <p>
                MailQ is an AI-powered email classification system that automatically
                organizes Gmail messages into categories. It combines rule-based logic
                for common patterns with Gemini AI for complex emails.
            </p>
        </section>

        <section>
            <h2>How It Works</h2>
            <div class="architecture">
                <div class="arch-box">
                    <h3>1. Chrome Extension</h3>
                    <p>User clicks icon → Fetches unread emails from Gmail API</p>
                </div>
                <div class="arch-box">
                    <h3>2. Classification Pipeline</h3>
                    <p>Rules Engine (fast) → AI Classifier (complex cases)</p>
                </div>
                <div class="arch-box">
                    <h3>3. Apply Labels</h3>
                    <p>Multi-dimensional labels applied via Gmail API</p>
                </div>
            </div>
        </section>

        <section>
            <h2>Key Files to Know</h2>
            <div class="file-list">
"""

    # Add orchestrators
    for orch in orchestrators:
        path = orch["path"]
        file_info = data["files"].get(path, {})
        summary = file_info.get("ai_summary", orch.get("docstring", "No description"))

        html += """
                <div class="file-item">
                    <h3>{path}</h3>
                    <p>{summary}</p>
                    <p class="meta">{orch["import_count"]} dependencies</p>
                </div>
"""

    html += """
            </div>
        </section>

        <section>
            <h2>Where to Make Common Changes</h2>
            <ul class="changes-list">
                <li><strong>Add new email type:</strong> Edit <code>mailq/mapper.py</code> schema</li>
                <li><strong>Change AI model:</strong> Update <code>mailq/vertex_gemini_classifier.py</code></li>
                <li><strong>Modify label formats:</strong> Edit <code>mailq/mapper.py</code></li>
                <li><strong>Add classification domains:</strong> Update <code>mailq/config/sender_allowlist.py</code></li>
            </ul>
        </section>
    </main>

    <footer>
        <p>MailQ Codebase Analyzer</p>
    </footer>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"✅ Generated: {output_path}")


def _get_summary_css():
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f7fa;
            color: #2d3748;
            line-height: 1.6;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
        }
        header h1 { font-size: 2rem; margin-bottom: 1rem; }
        nav a {
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            background: rgba(255,255,255,0.2);
            border-radius: 6px;
        }
        main { max-width: 900px; margin: 2rem auto; padding: 0 2rem; }
        section {
            background: white;
            padding: 2rem;
            margin: 2rem 0;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h2 {
            color: #1a202c;
            border-bottom: 2px solid #edf2f7;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }
        .overview p { font-size: 1.1rem; color: #4a5568; }
        .architecture {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }
        .arch-box {
            background: #f7fafc;
            padding: 1.5rem;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .arch-box h3 { color: #2d3748; margin-bottom: 0.5rem; }
        .file-item {
            background: #f7fafc;
            padding: 1rem;
            margin: 1rem 0;
            border-radius: 8px;
            border-left: 4px solid #9f7aea;
        }
        .file-item h3 {
            font-family: 'SF Mono', Monaco, monospace;
            color: #2d3748;
            font-size: 1rem;
        }
        .file-item p { color: #4a5568; margin: 0.5rem 0; }
        .meta { color: #718096 !important; font-size: 0.9rem; }
        .changes-list {
            list-style: none;
        }
        .changes-list li {
            padding: 0.75rem;
            margin: 0.5rem 0;
            background: #f7fafc;
            border-radius: 6px;
        }
        code {
            background: #edf2f7;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.9rem;
        }
        footer {
            background: #2d3748;
            color: white;
            text-align: center;
            padding: 2rem;
            margin-top: 4rem;
        }
    """


def format_file_section(file_path: str, file_data: dict) -> str:
    """Format a file's information for markdown."""

    section = f"### 📄 `{file_path}`\n\n"

    # Parse AI summary (now has SUMMARY and RELATIONSHIPS)
    ai_summary = file_data.get("ai_summary", "No AI summary available")

    if "SUMMARY:" in ai_summary and "RELATIONSHIPS:" in ai_summary:
        parts = ai_summary.split("RELATIONSHIPS:")
        summary_part = parts[0].replace("SUMMARY:", "").strip()
        relationships_part = parts[1].strip() if len(parts) > 1 else ""

        section += f"**Summary:** {summary_part}\n\n"

        if relationships_part:
            section += f"**Relationships:** {relationships_part}\n\n"
    else:
        # Fallback for old format
        section += f"**AI Summary:** {ai_summary}\n\n"

    # Purpose
    if "purpose" in file_data:
        section += f"**Purpose:** {file_data['purpose']}\n\n"

    # Classes
    if "classes" in file_data and file_data["classes"]:
        section += "**Classes:**\n"
        for cls in file_data["classes"]:
            method_count = cls.get("method_count", 0)
            section += f"- `{cls['name']}` ({method_count} methods)\n"
        section += "\n"

    # Functions
    if "functions" in file_data and file_data["functions"]:
        section += "**Functions:**\n"
        for func in file_data["functions"][:10]:  # Limit to 10
            section += f"- `{func}()`\n"

        if len(file_data["functions"]) > 10:
            remaining = len(file_data["functions"]) - 10
            section += f"- *(+{remaining} more)*\n"
        section += "\n"

    # Dependencies
    deps = file_data.get("dependencies", {})
    internal = deps.get("internal", [])

    if internal:
        section += "**Dependencies (internal):**\n"
        for dep in internal[:5]:  # Show first 5
            section += f"- `{dep}`\n"

        if len(internal) > 5:
            remaining = len(internal) - 5
            section += f"- *(+{remaining} more)*\n"
        section += "\n"

    section += "---\n\n"
    return section


if __name__ == "__main__":
    root_dir = Path(__file__).parent.parent
    analysis = root_dir / "codebase_analysis_with_summaries.json"

    if not analysis.exists():
        analysis = root_dir / "codebase_analysis.json"

    output = root_dir / "docs" / "analysis" / "summary.html"
    generate_summary_html(analysis, output)
