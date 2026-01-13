"""

from __future__ import annotations

Generate HTML visualization of codebase analysis with AI summaries
"""

import json
from pathlib import Path


def generate_detailed_html(analysis_path: Path, output_path: Path):
    """Generate detailed.html with AI summaries"""

    with open(analysis_path) as f:
        data = json.load(f)

    files = data.get("files", {})
    stats = data.get("statistics", {})
    dependencies = data.get("dependencies", {})

    # Group files by directory
    python_files = {k: v for k, v in files.items() if v.get("type") == "python"}
    js_files = {k: v for k, v in files.items() if v.get("type") == "javascript"}

    # Count files with AI summaries
    files_with_summaries = sum(1 for f in files.values() if f.get("ai_summary"))

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MailQ Codebase Analysis - Detailed View</title>
    <style>
        {_get_css()}
    </style>
</head>
<body>
    <header>
        <h1>📊 MailQ Codebase Analysis</h1>
        <nav>
            <a href="summary.html">Summary</a>
            <a href="detailed.html" class="active">Detailed</a>
            <a href="graph.html">Dependencies</a>
        </nav>
        <div class="meta">
            Generated: {datetime.now().strftime("%B %d, %Y at %H:%M")} |
            AI Summaries: {files_with_summaries}/{len(files)}
        </div>
    </header>

    <main>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats.get("total_files", 0)}</div>
                <div class="stat-label">Total Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get("python_files", 0)}</div>
                <div class="stat-label">Python Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get("js_files", 0)}</div>
                <div class="stat-label">JavaScript Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get("total_lines", 0):,}</div>
                <div class="stat-label">Lines of Code</div>
            </div>
        </div>

        <section class="file-section">
            <h2>🐍 Python Backend ({len(python_files)} files)</h2>
            {_render_python_files(python_files, dependencies)}
        </section>

        <section class="file-section">
            <h2>🌐 JavaScript Frontend ({len(js_files)} files)</h2>
            {_render_js_files(js_files, data.get("js_dependencies", {}))}
        </section>
    </main>

    <footer>
        <p>MailQ Codebase Analyzer • Powered by Gemini Flash •
        <a href="https://github.com/yourusername/mailq-prototype" target="_blank">GitHub</a></p>
    </footer>

    <script>
        // Add search/filter functionality
        document.addEventListener('DOMContentLoaded', () => {{
            console.log('📊 MailQ Codebase Viewer loaded');
        }});
    </script>
</body>
</html>
"""

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(html)

    print(f"✅ Generated: {output_path}")
    print(f"   Files with AI summaries: {files_with_summaries}/{len(files)}")


def _get_css() -> str:
    """CSS styles for the HTML page"""
    return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa;
            color: #2d3748;
            line-height: 1.6;
        }

        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        header h1 {
            font-size: 2rem;
            margin-bottom: 1rem;
        }

        nav {
            display: flex;
            gap: 1rem;
            margin-bottom: 0.5rem;
        }

        nav a {
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            transition: background 0.2s;
        }

        nav a:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        nav a.active {
            background: rgba(255, 255, 255, 0.3);
            font-weight: 600;
        }

        .meta {
            font-size: 0.9rem;
            opacity: 0.9;
        }

        main {
            max-width: 1400px;
            margin: 2rem auto;
            padding: 0 2rem;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }

        .stat-card {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }

        .stat-value {
            font-size: 2.5rem;
            font-weight: bold;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .stat-label {
            color: #718096;
            margin-top: 0.5rem;
            font-size: 0.9rem;
        }

        .file-section {
            margin-bottom: 3rem;
        }

        .file-section h2 {
            font-size: 1.8rem;
            margin-bottom: 1.5rem;
            color: #1a202c;
            border-bottom: 3px solid #667eea;
            padding-bottom: 0.5rem;
        }

        .file-card {
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            border-left: 4px solid #667eea;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .file-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }

        .file-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }

        .file-path {
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            font-size: 1rem;
            font-weight: 600;
            color: #2d3748;
        }

        .file-badge {
            background: #edf2f7;
            color: #4a5568;
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.85rem;
        }

        .ai-summary {
            background: linear-gradient(135deg, #f6e8ff 0%, #e9d5ff 100%);
            border-left: 4px solid #9f7aea;
            padding: 1rem;
            margin-bottom: 1rem;
            border-radius: 8px;
        }

        .ai-summary::before {
            content: "🤖 AI Summary";
            display: block;
            font-weight: 600;
            font-size: 0.85rem;
            color: #6b46c1;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .ai-summary p {
            color: #44337a;
            font-size: 0.95rem;
            line-height: 1.6;
        }

        .ai-relationships {
            background: linear-gradient(135deg, #e0f2fe 0%, #dbeafe 100%);
            border-left: 4px solid #3b82f6;
            padding: 1rem;
            margin-bottom: 1rem;
            border-radius: 8px;
        }

        .ai-relationships::before {
            content: "🔗 Relationships";
            display: block;
            font-weight: 600;
            font-size: 0.85rem;
            color: #1e40af;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .ai-relationships p {
            color: #1e3a8a;
            font-size: 0.95rem;
            line-height: 1.6;
        }

        .no-summary {
            background: #fed7d7;
            border-left-color: #fc8181;
        }

        .no-summary::before {
            content: "⚠️ No AI Summary";
            color: #c53030;
        }

        .no-summary p {
            color: #742a2a;
        }

        .file-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1rem;
        }

        .detail-section {
            background: #f7fafc;
            padding: 1rem;
            border-radius: 8px;
        }

        .detail-section h4 {
            color: #4a5568;
            font-size: 0.85rem;
            margin-bottom: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }

        .detail-section ul {
            list-style: none;
        }

        .detail-section li {
            color: #2d3748;
            padding: 0.4rem 0;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.85rem;
        }

        .detail-section li::before {
            content: "▸ ";
            color: #667eea;
            font-weight: bold;
            margin-right: 0.5rem;
        }

        .empty-section {
            color: #a0aec0;
            font-style: italic;
            font-size: 0.9rem;
        }

        footer {
            background: #2d3748;
            color: white;
            text-align: center;
            padding: 2rem;
            margin-top: 4rem;
        }

        footer a {
            color: #90cdf4;
            text-decoration: none;
        }

        footer a:hover {
            text-decoration: underline;
        }
    """


def _render_python_files(files: dict, dependencies: dict) -> str:
    """Render Python files with AI summaries"""
    if not files:
        return "<p class='empty-section'>No Python files found.</p>"

    html = ""

    for path in sorted(files.keys()):
        info = files[path]

        # AI Summary section - NOW WITH RELATIONSHIPS
        ai_summary = info.get("ai_summary", "").strip()

        if "SUMMARY:" in ai_summary and "RELATIONSHIPS:" in ai_summary:
            # Parse the two sections
            parts = ai_summary.split("RELATIONSHIPS:")
            summary_part = parts[0].replace("SUMMARY:", "").strip()
            relationships_part = parts[1].strip() if len(parts) > 1 else ""

            # Render both sections
            html += """
            <div class="ai-summary">
                <p><strong>Summary:</strong> {summary_part}</p>
            </div>

            <div class="ai-relationships">
                <p><strong>Relationships:</strong> {relationships_part}</p>
            </div>
            """
        else:
            # Fallback for old format
            summary_class = "ai-summary" if ai_summary else "ai-summary no-summary"
            summary_text = (
                ai_summary
                if ai_summary
                else "AI summary not generated. Run ai_summarizer.py to add summaries."
            )

            html += """
            <div class="{summary_class}">
                <p>{summary_text}</p>
            </div>
            """

        # Build file card
        html += """
        <div class="file-card">
            <div class="file-header">
                <div class="file-path">{path}</div>
                <div class="file-badge">{info.get("lines", 0)} lines</div>
            </div>

            <div class="file-details">
        """

        # Classes
        classes = info.get("classes", [])
        if classes:
            html += """
                <div class="detail-section">
                    <h4>Classes</h4>
                    <ul>
            """
            for cls in classes[:8]:
                method_count = cls.get("method_count", 0)
                html += f"<li>{cls['name']} ({method_count} methods)</li>"
            if len(classes) > 8:
                html += f"<li class='empty-section'>+{len(classes) - 8} more...</li>"
            html += "</ul></div>"

        # Functions
        functions = info.get("functions", [])
        if functions:
            html += """
                <div class="detail-section">
                    <h4>Functions</h4>
                    <ul>
            """
            for func in functions[:8]:
                html += f"<li>{func['name']}()</li>"
            if len(functions) > 8:
                html += f"<li class='empty-section'>+{len(functions) - 8} more...</li>"
            html += "</ul></div>"

        # Dependencies
        file_deps = dependencies.get(path, [])
        if file_deps:
            html += """
                <div class="detail-section">
                    <h4>Dependencies</h4>
                    <ul>
            """
            for dep in sorted(file_deps)[:8]:
                # Shorten path for display
                short_dep = dep.replace("mailq/", "").replace(".py", "")
                html += f"<li>{short_dep}</li>"
            if len(file_deps) > 8:
                html += f"<li class='empty-section'>+{len(file_deps) - 8} more...</li>"
            html += "</ul></div>"

        html += """
            </div>
        </div>
        """

    return html


def _render_js_files(files: dict, dependencies: dict) -> str:
    """Render JavaScript files with AI summaries"""
    if not files:
        return "<p class='empty-section'>No JavaScript files found.</p>"

    html = ""

    for path in sorted(files.keys()):
        info = files[path]

        # AI Summary
        ai_summary = info.get("ai_summary", "").strip()
        summary_class = "ai-summary" if ai_summary else "ai-summary no-summary"
        summary_text = (
            ai_summary
            if ai_summary
            else "AI summary not generated. Run ai_summarizer.py to add summaries."
        )

        html += """
        <div class="file-card">
            <div class="file-header">
                <div class="file-path">{path}</div>
                <div class="file-badge">{info.get("lines", 0)} lines</div>
            </div>

            <div class="{summary_class}">
                <p>{summary_text}</p>
            </div>

            <div class="file-details">
        """

        # Characteristics
        html += """
            <div class="detail-section">
                <h4>Characteristics</h4>
                <ul>
        """
        html += f"<li>ES6 Modules: {'✅' if info.get('has_import') else '❌'}</li>"
        html += f"<li>Async/Await: {'✅' if info.get('has_async') else '❌'}</li>"
        html += f"<li>HTTP Requests: {'✅' if info.get('has_fetch') else '❌'}</li>"
        html += "</ul></div>"

        # Imports
        file_deps = dependencies.get(path, [])
        if file_deps:
            html += """
                <div class="detail-section">
                    <h4>Imports</h4>
                    <ul>
            """
            for imp in sorted(file_deps)[:8]:
                # Shorten path
                short_imp = imp.replace("extension/", "").replace(".js", "")
                html += f"<li>{short_imp}</li>"
            if len(file_deps) > 8:
                html += f"<li class='empty-section'>+{len(file_deps) - 8} more...</li>"
            html += "</ul></div>"

        html += """
            </div>
        </div>
        """

    return html


if __name__ == "__main__":
    import sys

    root_dir = Path(__file__).parent.parent

    # Check for analysis with summaries
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

    output_file = root_dir / "docs" / "analysis" / "detailed.html"

    generate_detailed_html(input_file, output_file)
