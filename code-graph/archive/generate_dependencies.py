"""Generate dependency graph visualization"""

from __future__ import annotations

import json
from pathlib import Path


def generate_dependencies_html(analysis_path: Path, output_path: Path):
    """Generate dependencies.html with Mermaid diagrams"""

    with open(analysis_path) as f:
        data = json.load(f)

    files = data.get("files", {})

    # Build Python dependency graph
    python_deps = []
    for path, info in files.items():
        if info.get("type") == "python":
            imports = info.get("internal_imports", [])
            for target in imports:
                python_deps.append((path, target))

    print(f"🐍 Found {len(python_deps)} Python dependencies")

    # Build JS dependency graph
    js_deps = []
    for path, info in files.items():
        if info.get("type") == "javascript":
            imports = info.get("internal_imports", [])
            for target in imports:
                js_deps.append((path, target))

    print(f"🌐 Found {len(js_deps)} JavaScript dependencies")

    # Generate HTML with the data we collected
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dependency Graphs - MailQ</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f7fa;
            color: #2d3748;
            line-height: 1.6;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        header h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}
        nav {{
            margin-top: 1rem;
        }}
        nav a {{
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            background: rgba(255,255,255,0.2);
            border-radius: 6px;
            transition: background 0.2s;
            margin-right: 0.5rem;
        }}
        nav a:hover {{
            background: rgba(255,255,255,0.3);
        }}
        main {{
            max-width: 1400px;
            margin: 2rem auto;
            padding: 0 2rem;
        }}
        section {{
            background: white;
            padding: 2rem;
            margin-bottom: 2rem;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        section h2 {{
            color: #1a202c;
            margin-bottom: 1rem;
            font-size: 1.5rem;
        }}
        .meta {{
            color: #718096;
            font-size: 0.95rem;
            margin-bottom: 1.5rem;
        }}
        .graph-container {{
            background: #f7fafc;
            padding: 2rem;
            border-radius: 8px;
            overflow-x: auto;
        }}
        .mermaid {{
            display: flex;
            justify-content: center;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: #f7fafc;
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            color: #718096;
            font-size: 0.9rem;
            margin-top: 0.25rem;
        }}
        .empty-state {{
            text-align: center;
            padding: 3rem;
            color: #718096;
        }}
    </style>
</head>
<body>
    <header>
        <h1>🔗 Dependency Graphs</h1>
        <p class="meta">Generated {datetime.now().strftime("%B %d, %Y at %H:%M")}</p>
        <nav>
            <a href="index.html">← Back to Dashboard</a>
            <a href="detailed.html">Detailed Analysis</a>
        </nav>
    </header>

    <main>
        <section>
            <p>These diagrams show which files depend on which. Arrows point from files that import to files being imported.</p>

            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{len(python_deps)}</div>
                    <div class="stat-label">Python Dependencies</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{len(js_deps)}</div>
                    <div class="stat-label">JavaScript Dependencies</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get("total_files", 0)}</div>
                    <div class="stat-label">Total Files</div>
                </div>
            </div>
        </section>

        <section>
            <h2>🐍 Python Dependencies</h2>
            <p class="meta">Shows how Python modules in mailq/, scripts/, experiments/ connect</p>
            <div class="graph-container">
                {_render_python_graph(python_deps)}
            </div>
        </section>

        <section>
            <h2>🌐 JavaScript Dependencies</h2>
            <p class="meta">Shows how browser extension modules connect</p>
            <div class="graph-container">
                {_render_js_graph(js_deps)}
            </div>
        </section>
    </main>

    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'default',
                securityLevel: 'loose',
                flowchart: {{
                    useMaxWidth: true,
                    htmlLabels: true,
                    curve: 'basis'
                }}
            }});

            mermaid.run();
            console.log('Mermaid initialized');
        }});
    </script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"✅ Generated: {output_path}")


def _render_python_graph(edges):
    """Render Python dependency graph"""
    if not edges:
        return """
                <div class="empty-state">
                    <p>No Python dependencies found</p>
                </div>
        """

    mermaid = '<div class="mermaid">\ngraph LR\n'

    for source, target in edges:
        source_id = _to_node_id(source)
        target_id = _to_node_id(target)
        source_label = _shorten_path(source)
        target_label = _shorten_path(target)

        mermaid += f'    {source_id}["{source_label}"] --> {target_id}["{target_label}"]\n'

    mermaid += "</div>"
    return mermaid


def _render_js_graph(edges):
    """Render JavaScript dependency graph"""
    if not edges:
        return """
                <div class="empty-state">
                    <p>No JavaScript dependencies found</p>
                </div>
        """

    mermaid = '<div class="mermaid">\ngraph LR\n'

    for source, target in edges:
        source_id = _to_node_id(source)
        target_id = _to_node_id(target)
        source_label = _shorten_path(source)
        target_label = _shorten_path(target)

        mermaid += f'    {source_id}["{source_label}"] --> {target_id}["{target_label}"]\n'

    mermaid += "</div>"
    return mermaid


def _to_node_id(path):
    """Convert file path to valid Mermaid node ID"""
    return path.replace("/", "_").replace(".", "_").replace("-", "_")


def _shorten_path(path):
    """Shorten path for readability"""
    path = path.replace("mailq/", "")
    path = path.replace("extension/", "")
    path = path.replace("code-graph/scripts/", "scripts/")

    if len(path) > 30:
        parts = path.split("/")
        if len(parts) > 1:
            return f"{parts[0]}/.../{parts[-1]}"

    return path


if __name__ == "__main__":
    root_dir = Path(__file__).parent.parent
    analysis = root_dir / "codebase_analysis_with_summaries.json"

    if not analysis.exists():
        analysis = root_dir / "codebase_analysis.json"

    output = root_dir / "docs" / "analysis" / "dependencies.html"
    generate_dependencies_html(analysis, output)
