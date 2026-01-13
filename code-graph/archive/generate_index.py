"""Generate index.html dashboard with relationship highlights"""

from __future__ import annotations

import json
from pathlib import Path


def generate_index_html(analysis_path: Path, output_path: Path):
    """Generate index.html landing page with relationship insights"""

    with open(analysis_path) as f:
        data = json.load(f)

    stats = data.get("statistics", {})
    files = data.get("files", {})
    dependencies = data.get("dependencies", {})

    # Count files with summaries
    files_with_summaries = sum(1 for f in files.values() if f.get("ai_summary"))
    total_files = len(files)

    # Find most connected files (orchestrators)
    orchestrators = stats.get("orchestrators", [])[:5]

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ShopQ Codebase Analysis</title>
    <style>
        {_get_index_css()}
    </style>
</head>
<body>
    <header>
        <h1>📊 ShopQ Codebase Analysis</h1>
        <p class="subtitle">Generated {datetime.now().strftime("%B %d, %Y at %H:%M")}</p>
    </header>

    <main>
        <div class="hero">
            <h2>Explore Your Codebase</h2>
            <p>AI-powered documentation with relationship insights</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats.get("total_files", 0)}</div>
                <div class="stat-label">Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get("total_lines", 0):,}</div>
                <div class="stat-label">Lines of Code</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get("total_classes", 0)}</div>
                <div class="stat-label">Classes</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{files_with_summaries}/{total_files}</div>
                <div class="stat-label">AI Summaries</div>
            </div>
        </div>

        <div class="nav-cards">
            <a href="summary.html" class="nav-card">
                <h3>📝 Overview</h3>
                <p>High-level summary with relationship highlights</p>
            </a>

            <a href="detailed.html" class="nav-card">
                <h3>🔍 Detailed Analysis</h3>
                <p>File-by-file breakdown with AI summaries</p>
            </a>

            <a href="dependencies.html" class="nav-card">
                <h3>🔗 Dependencies</h3>
                <p>Visual dependency graphs with Mermaid</p>
            </a>
        </div>

        <section class="insights">
            <h2>🎯 Key Insights</h2>

            <div class="insight-card">
                <h3>🔌 Most Connected Files</h3>
                <p>These files orchestrate multiple components:</p>
                <ul>
{_render_orchestrators(orchestrators, files)}
                </ul>
            </div>

            <div class="insight-card">
                <h3>📦 Project Structure</h3>
                <ul>
                    <li><strong>shopq/</strong> - Core Python backend ({stats.get("by_directory", {}).get("mailq", {}).get("files", 0)} files)</li>
                    <li><strong>extension/</strong> - Chrome extension ({stats.get("by_directory", {}).get("extension", {}).get("files", 0)} files)</li>
                    <li><strong>scripts/</strong> - Utility scripts ({stats.get("by_directory", {}).get("scripts", {}).get("files", 0)} files)</li>
                </ul>
            </div>
        </section>
    </main>

    <footer>
        <p>ShopQ Codebase Analyzer • Powered by Gemini Flash</p>
    </footer>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"✅ Generated: {output_path}")


def _render_orchestrators(orchestrators, files):
    """Render list of most connected files with their relationships"""
    html = ""
    for orch in orchestrators:
        path = orch["path"]
        import_count = orch["import_count"]

        # Get first sentence of AI summary (if exists)
        file_info = files.get(path, {})
        ai_summary = file_info.get("ai_summary", "")

        if "RELATIONSHIPS:" in ai_summary:
            # Extract the relationships part
            relationships = ai_summary.split("RELATIONSHIPS:")[1].strip()
            # Get first sentence
            first_sentence = relationships.split(".")[0] + "."
        else:
            first_sentence = f"Imports {import_count} internal modules."

        html += """
                    <li>
                        <code>{path}</code><br>
                        <small>{first_sentence}</small>
                    </li>
"""
    return html


def _get_index_css():
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
            padding: 3rem 2rem;
            text-align: center;
        }
        header h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
        .subtitle { opacity: 0.9; font-size: 1rem; }
        main { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        .hero {
            text-align: center;
            margin: 3rem 0;
        }
        .hero h2 {
            font-size: 2rem;
            color: #1a202c;
            margin-bottom: 0.5rem;
        }
        .hero p {
            color: #718096;
            font-size: 1.1rem;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin: 3rem 0;
        }
        .stat-card {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-value {
            font-size: 3rem;
            font-weight: bold;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stat-label {
            color: #718096;
            margin-top: 0.5rem;
        }
        .nav-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin: 3rem 0;
        }
        .nav-card {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-decoration: none;
            color: inherit;
            transition: transform 0.2s, box-shadow 0.2s;
            border-left: 4px solid #667eea;
        }
        .nav-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }
        .nav-card.disabled {
            opacity: 0.5;
            pointer-events: none;
        }
        .nav-card h3 {
            color: #1a202c;
            margin-bottom: 0.5rem;
        }
        .nav-card p {
            color: #718096;
        }
        .insights {
            margin: 3rem 0;
        }
        .insights h2 {
            margin-bottom: 1.5rem;
            color: #1a202c;
        }
        .insight-card {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .insight-card h3 {
            margin-bottom: 1rem;
            color: #2d3748;
        }
        .insight-card ul {
            list-style: none;
            padding-left: 0;
        }
        .insight-card li {
            padding: 0.75rem 0;
            border-bottom: 1px solid #edf2f7;
        }
        .insight-card li:last-child {
            border-bottom: none;
        }
        .insight-card code {
            background: #f7fafc;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.9rem;
            color: #667eea;
        }
        .insight-card small {
            display: block;
            color: #718096;
            margin-top: 0.25rem;
            font-size: 0.85rem;
        }
        footer {
            background: #2d3748;
            color: white;
            text-align: center;
            padding: 2rem;
            margin-top: 4rem;
        }
    """


if __name__ == "__main__":
    root_dir = Path(__file__).parent.parent
    analysis = root_dir / "codebase_analysis_with_summaries.json"

    if not analysis.exists():
        analysis = root_dir / "codebase_analysis.json"

    output = root_dir / "docs" / "analysis" / "index.html"
    generate_index_html(analysis, output)
