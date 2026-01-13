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
        if info.get("type") == "python" and info.get("internal_imports"):
            for target in info["internal_imports"]:
                python_deps.append((path, target))

    # Build JS dependency graph
    js_deps = []
    for path, info in files.items():
        if info.get("type") == "javascript" and info.get("internal_imports"):
            for target in info["internal_imports"]:
                js_deps.append((path, target))

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Dependency Graph - ShopQ</title>
    <link rel="stylesheet" href="../assets/css/analysis.css">
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
</head>
<body>
    <header>
        <h1>🔗 Dependency Graphs</h1>
        <nav>
            <a href="index.html">← Back to Dashboard</a>
        </nav>
    </header>

    <main>
        <section>
            <p>These diagrams show which files depend on which. Arrows point from files that import to files being imported.</p>
        </section>

        <section>
            <h2>🐍 Python Dependencies</h2>
            <p class="meta">Shows how Python modules in shopq/, scripts/, experiments/ connect</p>
            <div class="graph-container">
                <div class="mermaid">
graph TD
{_render_mermaid_graph(python_deps)}
                </div>
            </div>
        </section>

        <section>
            <h2>🌐 JavaScript Dependencies</h2>
            <p class="meta">Shows how browser extension modules connect</p>
            <div class="graph-container">
                <div class="mermaid">
graph TD
{_render_mermaid_graph(js_deps)}
                </div>
            </div>
        </section>
    </main>

    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"✅ Generated: {output_path}")


def _render_mermaid_graph(edges):
    """Convert edges to Mermaid syntax"""
    if not edges:
        return "    No dependencies found"

    lines = []

    # Convert file paths to valid Mermaid node IDs
    def to_node_id(path):
        return path.replace("/", "_").replace(".", "_").replace("-", "_")

    for source, target in edges:
        source_id = to_node_id(source)
        target_id = to_node_id(target)

        # Shorten labels for readability
        source_label = source.replace("shopq/", "").replace("extension/", "")
        target_label = target.replace("shopq/", "").replace("extension/", "")

        lines.append(f"        {source_id}[{source_label}] --> {target_id}[{target_label}]")

    return "\n".join(lines)


if __name__ == "__main__":
    root_dir = Path(__file__).parent.parent
    analysis = root_dir / "codebase_analysis_with_summaries.json"

    if not analysis.exists():
        analysis = root_dir / "codebase_analysis.json"

    output = root_dir / "docs" / "analysis" / "dependencies.html"
    generate_dependencies_html(analysis, output)
