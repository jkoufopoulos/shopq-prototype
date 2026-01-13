#!/usr/bin/env python3
"""
Code-Graph v2 - HTML Diagram Generator

Generates interactive HTML versions of Mermaid diagrams.
Features: Zoom, pan, export, beautiful styling.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from diagram_types import DiagramStructure, ExecutionStep, DiagramSpec

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
VISUALS_DIR = PROJECT_ROOT / "code-graph" / "visuals"
HTML_DIR = VISUALS_DIR / "html"


def extract_mermaid_code(markdown_content: str) -> str:
    """Extract mermaid code block from markdown"""
    pattern = r"```mermaid\n(.*?)\n```"
    match = re.search(pattern, markdown_content, re.DOTALL)
    if match:
        return match.group(1)
    return ""


def extract_execution_steps(markdown_content: str) -> list[ExecutionStep]:
    """Extract numbered execution steps directly from sequence diagram for context drawer"""
    steps = []

    # Extract mermaid code
    mermaid_code = extract_mermaid_code(markdown_content)
    if not mermaid_code:
        return steps

    # Check if it's a sequence diagram with autonumber
    if "sequenceDiagram" not in mermaid_code or "autonumber" not in mermaid_code:
        return steps

    # Extract participant mappings first
    # participant User as 👤 User
    participant_pattern = r'participant\s+(\w+)\s+as\s+(.+?)(?=\n|$)'
    participants = {}
    for p_match in re.finditer(participant_pattern, mermaid_code):
        participants[p_match.group(1)] = p_match.group(2).strip()

    # Mermaid autonumber counts BOTH solid (->>) AND dashed (-->) arrows
    # Extract both types: Actor->>Actor and Actor-->>Actor
    # Match both ->> and -->>
    arrow_pattern = r'(\w+)(-{1,2})>>(\w+):\s*(.+?)(?=\n|$)'
    step_num = 1

    for match in re.finditer(arrow_pattern, mermaid_code):
        from_actor = match.group(1)
        arrow_type = match.group(2)  # Either '-' or '--'
        to_actor = match.group(3)
        description = match.group(4).strip()

        # Skip "Note over" lines and empty descriptions
        if not description or from_actor == "Note":
            continue

        # Clean up description (remove line breaks, multiple spaces)
        description = re.sub(r'\s+', ' ', description)

        # Get readable names
        from_name = participants.get(from_actor, from_actor)
        to_name = participants.get(to_actor, to_actor)

        # Build step title and description
        # Clean up participant names: remove emoji, HTML tags, file paths
        # Example: "📱 Extension<br/>background.js" → "Extension"

        def clean_participant_name(name):
            # Remove emoji (non-ASCII characters)
            name = ''.join(char for char in name if ord(char) < 128)

            # Remove HTML tags
            name = re.sub(r'<[^>]+>', ' ', name)

            # Split on common separators and take first meaningful word
            # "Extension background.js" → ["Extension", "background.js"]
            # "Cache cache.js" → ["Cache", "cache.js"]
            parts = name.strip().split()
            if parts:
                # Take first part and remove file extensions
                first = parts[0]
                # Remove .js, .py extensions
                first = re.sub(r'\.(js|py)$', '', first)
                return first
            return name.strip()

        from_clean = clean_participant_name(from_name) or from_actor
        to_clean = clean_participant_name(to_name) or to_actor

        # Generate plain language description
        plain_description = generate_plain_description(
            from_clean, to_clean, description, arrow_type, from_actor, to_actor
        )

        steps.append({
            "number": step_num,
            "title": f"{from_clean} → {to_clean}",
            "description": plain_description
        })

        step_num += 1

    return steps


def generate_plain_description(from_actor: str, to_actor: str, arrow_desc: str, arrow_type: str, from_id: str, to_id: str) -> str:
    """Generate plain language description for a sequence diagram step"""

    # Determine if this is a response (dashed arrow) or request (solid arrow)
    is_response = arrow_type == "--"

    # Check for self-calls (actor talking to itself)
    is_self_call = from_id == to_id

    # Capitalize first letter and clean up actor names for readability
    from_display = from_actor.strip()
    to_display = to_actor.strip()

    # Build contextual description
    if is_self_call:
        # Self-calls are internal processing - add proper verb conjugation
        desc_lower = arrow_desc.lower()

        # Add third-person singular verb form
        if desc_lower.startswith("fetch"):
            return f"{from_display} fetches unlabeled emails from the inbox."
        elif desc_lower.startswith("deduplicate"):
            return f"{from_display} reduces ~100 emails to ~30 unique senders to minimize API calls."
        elif desc_lower.startswith("expand"):
            return f"{from_display} applies the classification to all emails from the same sender."
        elif desc_lower.startswith("analyze"):
            return f"{from_display} analyzes the email subject and content snippet."
        else:
            # Generic self-call with proper grammar
            action = arrow_desc[0].upper() + arrow_desc[1:] if arrow_desc else "processes internally"
            return f"{from_display} {action}."

    elif is_response:
        # Dashed arrows are responses/returns
        if "return" in arrow_desc.lower():
            # Clean "return" from description if it's redundant
            cleaned = arrow_desc.replace("Return ", "").replace("return ", "")
            return f"{from_display} returns {cleaned.lower()}."
        else:
            return f"{from_display} responds with {arrow_desc.lower()}."

    else:
        # Solid arrows are actions/requests
        desc_lower = arrow_desc.lower()

        # Pattern-based descriptions with better grammar
        if "post" in desc_lower and "api" in desc_lower:
            return f"{from_display} sends a batch request to {to_display} for processing."
        elif "check" in desc_lower and "cache" in desc_lower:
            return f"{from_display} checks the cache to see if this sender was recently classified."
        elif "check" in desc_lower and ("rule" in desc_lower or "engine" in desc_lower):
            return f"{from_display} checks the rules engine for learned patterns that match this email."
        elif "apply labels" in desc_lower:
            return f"{from_display} applies the classification labels and archives the emails."
        elif "update cache" in desc_lower:
            return f"{from_display} updates the cache with results for 24-hour reuse."
        elif "deduplicate" in desc_lower:
            return f"{from_display} reduces ~100 emails to ~30 unique senders to minimize API calls."
        elif "expand" in desc_lower and "same-sender" in desc_lower:
            return f"{from_display} applies the classification to all emails from the same sender."
        elif "create" in desc_lower and "rule" in desc_lower:
            return f"{from_display} creates a new classification rule based on the user's correction."
        elif "classify" in desc_lower and "llm" in desc_lower:
            return f"{from_display} uses the LLM to classify emails when no rule matches."
        elif "analyze" in desc_lower:
            return f"{from_display} analyzes the email subject and content snippet."
        elif "map" in desc_lower and "label" in desc_lower:
            return f"{from_display} converts the classification into Gmail label names."
        elif "click" in desc_lower:
            return f"User clicks the ShopQ icon to trigger email organization."
        elif "change label" in desc_lower or "correct" in desc_lower:
            return f"User manually changes a label, providing feedback to improve classification."
        elif "feedback" in desc_lower:
            return f"{from_display} sends the user's correction to update the rules engine."
        elif "organized inbox" in desc_lower:
            return f"Gmail displays the newly organized inbox with labeled emails."
        else:
            # Generic fallback with better formatting
            action = arrow_desc[0].upper() + arrow_desc[1:] if arrow_desc else "Processes"
            return f"{from_display} → {to_display}: {action}."


def parse_diagram_structure(mermaid_code: str) -> DiagramStructure:
    """
    Parse mermaid diagram to extract categories and nodes dynamically.
    Returns structure for generating filters.
    """
    structure = {
        "categories": {},  # {category_id: {name, emoji, nodes: []}}
        "nodes": {},  # {node_id: category_id}
    }

    # Extract subgraphs (categories)
    subgraph_pattern = r'subgraph\s+(CAT_[A-Z_]+|DIGEST_[A-Z_]+)\["(.+?)"\]'
    for match in re.finditer(subgraph_pattern, mermaid_code):
        cat_id = match.group(1)
        cat_label = match.group(2)
        # Extract emoji and name
        emoji_match = re.match(r"([^\w\s]+)\s*(.+)", cat_label)
        if emoji_match:
            emoji = emoji_match.group(1).strip()
            name = emoji_match.group(2)
        else:
            emoji = "📦"
            name = cat_label

        structure["categories"][cat_id] = {"name": name, "emoji": emoji, "nodes": []}

    # Extract nodes and assign to categories
    current_category = None
    lines = mermaid_code.split("\n")

    for line in lines:
        # Track which category we're in
        if "subgraph CAT_" in line or "subgraph DIGEST_" in line:
            match = re.search(r"subgraph\s+(CAT_[A-Z_]+|DIGEST_[A-Z_]+)", line)
            if match:
                current_category = match.group(1)
        elif line.strip() == "end" and current_category:
            # Check if this is closing a CAT_ subgraph
            current_category = None
        # Extract node definitions (e.g., EXT_GMAIL["..."])
        elif current_category:
            node_match = re.match(r"\s*([A-Z_]+)\[", line)
            if node_match:
                node_id = node_match.group(1)
                structure["nodes"][node_id] = current_category
                if current_category in structure["categories"]:
                    structure["categories"][current_category]["nodes"].append(node_id)

    return structure


def generate_filter_ui(structure: DiagramStructure) -> str:
    """Generate HTML for dynamic filter buttons"""
    if not structure or not structure["categories"]:
        return ""

    # Group by Extension vs Backend
    ext_cats = {k: v for k, v in structure["categories"].items() if k.startswith("CAT_EXT")}
    be_cats = {k: v for k, v in structure["categories"].items() if k.startswith("CAT_BE")}

    html = """
    <div class="filter-controls">
        <div class="filter-section">
            <button class="filter-btn filter-btn-primary active" onclick="showAll(event)">
                🔍 Show All
            </button>
        </div>
        <div class="filter-section">
            <h4 class="filter-heading">📱 Extension</h4>
            <div class="filter-buttons">
    """

    for cat_id, cat_info in ext_cats.items():
        count = len(cat_info["nodes"])
        if count > 0:
            html += """
                <button class="filter-btn" onclick="filterCategory(event, '{cat_id}')">
                    {cat_info["emoji"]} {cat_info["name"]}
                </button>
            """

    html += """
            </div>
        </div>
        <div class="filter-section">
            <h4 class="filter-heading">🐍 Backend</h4>
            <div class="filter-buttons">
    """

    for cat_id, cat_info in be_cats.items():
        count = len(cat_info["nodes"])
        if count > 0:
            html += """
                <button class="filter-btn" onclick="filterCategory(event, '{cat_id}')">
                    {cat_info["emoji"]} {cat_info["name"]}
                </button>
            """

    html += """
            </div>
        </div>
    </div>
    """

    return html


def generate_filter_javascript(structure: DiagramStructure) -> str:
    """Generate JavaScript for filtering functionality"""
    if not structure or not structure["categories"]:
        return ""

    # Convert structure to JSON-like dict for JS

    categories_nodes = {
        cat_id: cat_info["nodes"] for cat_id, cat_info in structure["categories"].items()
    }

    js = """
        const categoryNodes = {json.dumps(categories_nodes)};

        let activeFilter = null;

        function showAll(event) {{
            if (event) event.preventDefault();
            activeFilter = null;
            const svg = document.querySelector('#diagram svg');
            if (!svg) return;

            // Show all nodes and clusters
            svg.querySelectorAll('g.node, g.cluster').forEach(node => {{
                node.style.opacity = '1';
                node.style.display = 'block';
            }});

            // Restore all edges to normal opacity
            svg.querySelectorAll('g.edgePath').forEach(edge => {{
                edge.style.opacity = '1';
                edge.style.display = 'block';
            }});
            svg.querySelectorAll('path').forEach(path => {{
                if (path.classList.contains('path') || path.parentElement.classList.contains('edgePath')) {{
                    path.style.opacity = '1';
                }}
            }});

            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            if (event && event.target) {{
                event.target.classList.add('active');
            }}
        }}

        function filterCategory(event, categoryId) {{
            if (event) event.preventDefault();
            activeFilter = categoryId;
            const svg = document.querySelector('#diagram svg');
            if (!svg) return;

            const nodesToShow = new Set(categoryNodes[categoryId] || []);

            // Filter nodes - Mermaid uses the node ID directly as the element ID
            svg.querySelectorAll('g.node').forEach(node => {{
                // Mermaid sets node.id to the node identifier from the diagram
                const nodeId = node.id;

                if (nodesToShow.has(nodeId)) {{
                    node.style.opacity = '1';
                    node.style.display = 'block';
                }} else {{
                    node.style.opacity = '0.15';
                    node.style.display = 'block';
                }}
            }});

            // Highlight the subgraph/cluster for this category
            svg.querySelectorAll('g.cluster').forEach(cluster => {{
                const clusterId = cluster.id;
                // Match both the category itself and nested subgraphs (like DIGEST_CORE)
                if (clusterId === categoryId ||
                    clusterId.includes(categoryId) ||
                    categoryId.includes(clusterId)) {{
                    cluster.style.opacity = '1';
                }} else {{
                    cluster.style.opacity = '0.15';
                }}
            }});

            // Dim edges but keep visible
            svg.querySelectorAll('g.edgePath').forEach(edge => {{
                edge.style.opacity = '0.1';
            }});
            svg.querySelectorAll('path').forEach(path => {{
                if (path.classList.contains('path') || path.parentElement.classList.contains('edgePath')) {{
                    path.style.opacity = '0.1';
                }}
            }});

            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            if (event && event.target) {{
                event.target.classList.add('active');
            }}
        }}

        // Setup after Mermaid renders
        function setupFiltering() {{
            console.log('🔍 Filter system ready with', Object.keys(categoryNodes).length, 'categories');
            console.log('📊 Categories:', Object.keys(categoryNodes));

            // Debug: Log actual SVG node IDs
            const svg = document.querySelector('#diagram svg');
            if (svg) {{
                const nodeIds = Array.from(svg.querySelectorAll('g.node')).map(n => n.id).filter(id => id);
                console.log('✅ Found', nodeIds.length, 'nodes in SVG');
                console.log('📋 Sample node IDs:', nodeIds.slice(0, 10));
            }}
        }}
    """

    return js


def generate_html_template(
    title: str,
    mermaid_code: str,
    description: str = "",
    markdown_file: str = "",
    execution_steps: list[ExecutionStep] | None = None,
) -> str:
    """Generate interactive HTML with Mermaid diagram and optional context drawer"""

    # Enable pan/zoom for larger diagrams that benefit from navigation
    enable_pan_zoom = title in [
        "System Storyboard",
        "Evidence Heat-Map",
        "Layer Map",
    ]

    # Enable context drawer for task-flow diagrams with execution steps
    enable_context_drawer = execution_steps is not None and len(execution_steps) > 0
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_title = title.replace(" ", "_")
    cursor_style = "cursor: grab;" if enable_pan_zoom else ""
    active_style = ".diagram-container:active { cursor: grabbing; }" if enable_pan_zoom else ""
    zoom_controls_html = (
        """<div class="zoom-controls">
            <button class="zoom-btn" onclick="zoomIn()" title="Zoom In">+</button>
            <button class="zoom-btn" onclick="zoomOut()" title="Zoom Out">−</button>
            <button class="zoom-btn" onclick="resetZoom()" title="Reset Zoom">⟲</button>
        </div>"""
        if enable_pan_zoom
        else ""
    )

    # Generate context drawer HTML
    context_drawer_html = ""
    context_drawer_js = ""
    if enable_context_drawer and execution_steps:
        steps_html = ""
        for step in execution_steps:
            steps_html += f"""
            <div class="step-item" data-step="{step['number']}" onclick="highlightStep({step['number']})">
                <span class="step-number">{step['number']}</span>
                <div class="step-content">
                    <div class="step-title">{step['title']}</div>
                    <div class="step-description">{step['description']}</div>
                </div>
            </div>"""

        steps_json = json.dumps(execution_steps)
        context_drawer_html = f"""
    <button class="drawer-toggle" onclick="toggleDrawer()" title="Show Step Guide">📖</button>
    <div class="context-drawer" id="contextDrawer">
        <div class="drawer-header">
            <h2>Step-by-Step Guide</h2>
            <p>Click any step to highlight it in the diagram</p>
        </div>
        {steps_html}
    </div>"""

        context_drawer_js = f"""
        // Context Drawer Functionality
        const executionSteps = {steps_json};
        let drawerOpen = false;

        function toggleDrawer() {{
            const drawer = document.getElementById('contextDrawer');
            const toggle = document.querySelector('.drawer-toggle');
            drawerOpen = !drawerOpen;

            if (drawerOpen) {{
                drawer.classList.add('open');
                toggle.classList.add('drawer-open');
                toggle.textContent = '✕';
            }} else {{
                drawer.classList.remove('open');
                toggle.classList.remove('drawer-open');
                toggle.textContent = '📖';
            }}
        }}

        function highlightStep(stepNumber) {{
            // Remove previous highlights
            document.querySelectorAll('.step-item').forEach(item => {{
                item.classList.remove('active');
            }});

            // Highlight selected step
            const stepItem = document.querySelector(`[data-step="${{stepNumber}}"]`);
            if (stepItem) {{
                stepItem.classList.add('active');
            }}

            // Try to highlight corresponding diagram elements (sequence numbers)
            const svg = document.querySelector('#diagram svg');
            if (svg) {{
                // Remove previous diagram highlights
                svg.querySelectorAll('.seq-highlight').forEach(el => {{
                    el.classList.remove('seq-highlight');
                }});

                // Find and highlight the sequence number in the diagram
                const seqNumbers = svg.querySelectorAll('text');
                seqNumbers.forEach(text => {{
                    if (text.textContent.trim() === String(stepNumber)) {{
                        const parent = text.closest('g');
                        if (parent) {{
                            parent.classList.add('seq-highlight');
                            // Scroll diagram to show this element
                            text.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}
                    }}
                }});
            }}
        }}

        // Add CSS for diagram highlights
        const style = document.createElement('style');
        style.textContent = `
            .seq-highlight {{
                filter: drop-shadow(0 0 8px rgba(102,126,234,0.8));
                animation: pulse 1.5s ease-in-out infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ filter: drop-shadow(0 0 8px rgba(102,126,234,0.8)); }}
                50% {{ filter: drop-shadow(0 0 16px rgba(102,126,234,1)); }}
            }}
        `;
        document.head.appendChild(style);
"""
    else:
        context_drawer_html = ""
        context_drawer_js = ""
    pan_zoom_call = "setupPanAndZoom();" if enable_pan_zoom else ""
    pan_zoom_block = (
        """// Setup pan and zoom
        function setupPanAndZoom() {
            const container = document.querySelector('.diagram-container');
            if (!container) return;

            // Mouse wheel zoom
            container.addEventListener('wheel', (e) => {
                e.preventDefault();
                const delta = e.deltaY > 0 ? -0.15 : 0.15;
                currentZoom = Math.max(0.3, Math.min(3.0, currentZoom + delta));
                applyTransform();
            }, { passive: false });

            // Pan with mouse drag
            container.addEventListener('mousedown', (e) => {
                isPanning = true;
                startX = e.clientX - panX;
                startY = e.clientY - panY;
                container.style.cursor = 'grabbing';
            });

            document.addEventListener('mousemove', (e) => {
                if (!isPanning) return;
                panX = e.clientX - startX;
                panY = e.clientY - startY;
                applyTransform();
            });

            document.addEventListener('mouseup', () => {
                isPanning = false;
                if (container) container.style.cursor = 'grab';
            });
        }

        function zoomIn() {
            currentZoom = Math.min(3.0, currentZoom + 0.3);
            applyTransform();
        }

        function zoomOut() {
            currentZoom = Math.max(0.3, currentZoom - 0.3);
            applyTransform();
        }

        function resetZoom() {
            currentZoom = 1;
            panX = 0;
            panY = 0;
            applyTransform();
        }

        function applyTransform() {
            const wrapper = document.querySelector('.diagram-wrapper');
            if (wrapper) {
                wrapper.style.transform = `translate(${panX}px, ${panY}px) scale(${currentZoom})`;
            }
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === '+' || e.key === '=') {
                e.preventDefault();
                zoomIn();
            } else if (e.key === '-') {
                e.preventDefault();
                zoomOut();
            } else if (e.key === '0') {
                e.preventDefault();
                resetZoom();
            }
        });"""
        if enable_pan_zoom
        else ""
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - ShopQ</title>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            securityLevel: 'loose',
            logLevel: 'debug',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }},
            state: {{
                useMaxWidth: true
            }},
            themeVariables: {{
                darkMode: true,
                background: '#1c1c1e',
                primaryColor: '#2c2c2e',
                primaryTextColor: '#ffffff',
                primaryBorderColor: '#0a84ff',
                lineColor: '#0a84ff',
                secondaryColor: '#3a3a3c',
                secondaryTextColor: '#000000',
                tertiaryColor: '#48484a',
                tertiaryTextColor: '#000000',
                mainBkg: '#2c2c2e',
                secondBkg: '#3a3a3c',
                mainContrastColor: '#ffffff',
                darkTextColor: '#ffffff',
                textColor: '#ffffff',
                labelTextColor: '#ffffff',
                loopTextColor: '#000000',
                noteBkgColor: '#fef3c7',
                noteTextColor: '#000000',
                noteBorderColor: '#f59e0b',
                activationBkgColor: '#0a84ff',
                activationBorderColor: '#0070e0',
                sequenceNumberColor: '#000000',
                actorBkg: '#2c2c2e',
                actorBorder: '#0a84ff',
                actorTextColor: '#ffffff',
                actorLineColor: '#0a84ff',
                signalColor: '#ffffff',
                signalTextColor: '#ffffff',
                labelBoxBkgColor: '#2c2c2e',
                labelBoxBorderColor: '#0a84ff',
                labelColor: '#ffffff',
                edgeLabelBackground: '#1c1c1e',
                nodeBorder: '#0a84ff',
                clusterBkg: '#2c2c2e',
                clusterBorder: '#0a84ff',
                defaultLinkColor: '#0a84ff',
                titleColor: '#ffffff',
                nodeTextColor: '#ffffff',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
                fontSize: '16px'
            }}
        }});

        // Add error logging
        window.addEventListener('error', (e) => {{
            console.error('Error:', e.message);
        }});
    </script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
            background: #000000;
            min-height: 100vh;
            padding: 20px;
            color: #f5f5f7;
        }}

        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}

        .header {{
            background: #1c1c1e;
            border-radius: 18px;
            padding: 24px 32px;
            margin-bottom: 20px;
            border: 1px solid #2c2c2e;
        }}

        .header h1 {{
            color: #ffffff;
            font-size: 28px;
            margin-bottom: 8px;
        }}

        .header p {{
            color: #a1a1a6;
            font-size: 14px;
            margin-bottom: 16px;
        }}

        .controls {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}

        .btn {{
            padding: 8px 16px;
            border: 1px solid #2c2c2e;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-block;
        }}

        .btn-primary {{
            background: #0a84ff;
            color: #ffffff;
            border-color: #0a84ff;
        }}

        .btn-primary:hover {{
            background: #0070e0;
            border-color: #0070e0;
            transform: translateY(-1px);
        }}

        .btn-secondary {{
            background: #2c2c2e;
            color: #f5f5f7;
            border-color: #3a3a3c;
        }}

        .btn-secondary:hover {{
            background: #3a3a3c;
            border-color: #48484a;
        }}

        .diagram-container {{
            background: #1c1c1e;
            border-radius: 18px;
            padding: 40px;
            border: 1px solid #2c2c2e;
            overflow: auto;
            position: relative;
            {cursor_style}
        }}

        /* Mermaid diagram text improvements */
        #diagram text {{
            font-weight: 700 !important;
            font-size: 15px !important;
        }}

        /* Enhance readability */
        #diagram .nodeLabel,
        #diagram .cluster-label,
        #diagram .subgraph-label {{
            font-weight: 700 !important;
            stroke: none !important;
        }}

        #diagram tspan {{
            font-weight: 700 !important;
        }}

        /* Subgraph/cluster titles */
        #diagram g.cluster text {{
            font-weight: 700 !important;
            font-size: 16px !important;
        }}

        /* Edge labels need white text on dark background */
        #diagram .edgeLabel {{
            background-color: #1c1c1e !important;
        }}

        #diagram .edgeLabel tspan {{
            fill: #ffffff !important;
        }}

        {active_style}

        .diagram-wrapper {{
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 400px;
            transform-origin: center center;
        }}

        #diagram {{
            width: 100%;
            min-height: 400px;
            user-select: none;
        }}

        .footer {{
            text-align: center;
            color: #a1a1a6;
            margin-top: 20px;
            padding: 16px;
            font-size: 14px;
        }}

        .footer a {{
            color: #0a84ff;
            text-decoration: none;
        }}

        .footer a:hover {{
            text-decoration: underline;
        }}

        /* Zoom controls */
        .zoom-controls {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: #1c1c1e;
            border: 1px solid #2c2c2e;
            border-radius: 12px;
            padding: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .zoom-btn {{
            width: 40px;
            height: 40px;
            border: 1px solid #3a3a3c;
            background: #2c2c2e;
            color: #f5f5f7;
            border-radius: 8px;
            font-size: 20px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .zoom-btn:hover {{
            background: #3a3a3c;
            border-color: #48484a;
        }}

        /* Loading state */
        .loading {{
            text-align: center;
            color: #a1a1a6;
            padding: 40px;
        }}

        /* Info panel */
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            .header, .controls, .zoom-controls, .footer, .context-drawer {{
                display: none;
            }}
            .diagram-container {{
                box-shadow: none;
            }}
        }}

        /* Context Drawer Styles */
        .context-drawer {{
            position: fixed;
            right: 0;
            top: 0;
            bottom: 0;
            width: 380px;
            background: #1c1c1e;
            border-left: 1px solid #2c2c2e;
            box-shadow: -4px 0 16px rgba(0,0,0,0.5);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            z-index: 1000;
            overflow-y: auto;
        }}

        .context-drawer.open {{
            transform: translateX(0);
        }}

        .drawer-header {{
            background: #2c2c2e;
            border-bottom: 1px solid #3a3a3c;
            color: #ffffff;
            padding: 20px;
            position: sticky;
            top: 0;
            z-index: 10;
        }}

        .drawer-header h2 {{
            font-size: 18px;
            margin-bottom: 8px;
            color: #ffffff;
        }}

        .drawer-header p {{
            font-size: 13px;
            color: #a1a1a6;
        }}

        .drawer-toggle {{
            position: fixed;
            right: 20px;
            bottom: 80px;
            background: #0a84ff;
            color: white;
            border: 1px solid #0a84ff;
            border-radius: 50%;
            width: 56px;
            height: 56px;
            font-size: 24px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(10,132,255,0.4);
            transition: all 0.3s ease;
            z-index: 999;
        }}

        .drawer-toggle:hover {{
            background: #0070e0;
            border-color: #0070e0;
            transform: scale(1.1);
        }}

        .drawer-toggle.drawer-open {{
            right: 400px;
        }}

        .step-item {{
            padding: 20px;
            border-bottom: 1px solid #2c2c2e;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .step-item:hover {{
            background: #2c2c2e;
        }}

        .step-item.active {{
            background: #0a1929;
            border-left: 4px solid #0a84ff;
        }}

        .step-number {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            background: #0a84ff;
            color: white;
            border-radius: 50%;
            font-weight: 600;
            font-size: 14px;
            margin-right: 12px;
        }}

        .step-item.active .step-number {{
            background: #0070e0;
            box-shadow: 0 0 0 4px rgba(10,132,255,0.2);
        }}

        .step-content {{
            display: inline-block;
            vertical-align: top;
            width: calc(100% - 50px);
        }}

        .step-title {{
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 6px;
            font-size: 15px;
        }}

        .step-description {{
            color: #a1a1a6;
            font-size: 13px;
            line-height: 1.5;
        }}

    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>{description}</p>
            <p style="color: #86868b; font-size: 12px;">Auto-generated: {generated_at}</p>

            <div class="controls">
                <button class="btn btn-primary" onclick="exportDiagram()">
                    📥 Export SVG
                </button>
                <button class="btn btn-primary" onclick="exportPNG()">
                    📸 Export PNG
                </button>
                <button class="btn btn-secondary" onclick="window.print()">
                    🖨️ Print
                </button>
                <a href="index.html" class="btn btn-secondary">
                    ← All Diagrams
                </a>
                <a href="../{markdown_file}" class="btn btn-secondary" target="_blank">
                    📄 View Markdown
                </a>
            </div>
        </div>

        <div class="diagram-container">
            <div class="diagram-wrapper">
                <div class="loading">Loading diagram...</div>
                <pre class="mermaid" id="diagram">
{mermaid_code}
                </pre>
            </div>
        </div>

        {zoom_controls_html}
    </div>

    <!-- Context Drawer -->
    {context_drawer_html}

    <div class="footer">
        <p>ShopQ Code-Graph v2 | <a href="../../QUICKSTART.md">Documentation</a></p>
    </div>

    <script>
        {
        '''let currentZoom = 1;
        let panX = 0;
        let panY = 0;
        let isPanning = false;
        let startX = 0;
        let startY = 0;'''
        if enable_pan_zoom
        else ""
    }

        // Wait for Mermaid to render
        setTimeout(() => {{
            document.querySelector('.loading').style.display = 'none';
            const svg = document.querySelector('#diagram svg');
            if (svg) {{
                svg.style.transition = 'none'; // Remove transition for smooth dragging
            }}
            {pan_zoom_call}
        }}, 1000);

        {pan_zoom_block}

        {context_drawer_js}

        function exportDiagram() {{
            const svg = document.querySelector('#diagram svg');
            if (!svg) return;

            const svgData = new XMLSerializer().serializeToString(svg);
            const blob = new Blob([svgData], {{ type: 'image/svg+xml' }});
            const url = URL.createObjectURL(blob);

            const link = document.createElement('a');
            link.href = url;
            link.download = '{safe_title}.svg';
            link.click();

            URL.revokeObjectURL(url);
        }}

        function exportPNG() {{
            const svg = document.querySelector('#diagram svg');
            if (!svg) return;

            const svgData = new XMLSerializer().serializeToString(svg);
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const img = new Image();

            img.onload = function() {{
                canvas.width = img.width * 2;
                canvas.height = img.height * 2;
                ctx.fillStyle = 'white';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                canvas.toBlob(function(blob) {{
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = '{safe_title}.png';
                    link.click();
                    URL.revokeObjectURL(url);
                }});
            }};

            img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
        }}

        // Removed annoying node click functionality that dimmed the graph

    </script>
</body>
</html>"""

    return html


def generate_index_html(diagrams: list) -> str:
    """Generate index page for all diagrams"""

    # Group diagrams by category
    categories = {
        "start-here": {"title": "⭐ Start Here (PM & Product View)", "description": "Best overview diagrams for understanding the system at a glance", "diagrams": []},
        "task-flow": {"title": "🎯 Task-Flow Lens", "description": "What happens when X occurs? (≤8 steps, no file sprawl)", "diagrams": []},
        "analysis": {"title": "📊 Analysis Tools", "description": "Layer map, evidence tracking, and architectural insights", "diagrams": []},
    }

    # Categorize diagrams
    for diagram in diagrams:
        if diagram.get("file") == "system_storyboard.html":
            categories["start-here"]["diagrams"].append(diagram)
        elif diagram.get("category") == "task-flow":
            categories["task-flow"]["diagrams"].append(diagram)
        else:
            # Layer map, evidence heatmap, etc.
            categories["analysis"]["diagrams"].append(diagram)

    # Build category sections
    category_sections = []
    for cat_key in ["start-here", "task-flow", "analysis"]:
        cat_info = categories[cat_key]
        if not cat_info["diagrams"]:
            continue

        cards = "\n".join(
            f"""
            <a href="{diagram["file"]}" class="card">
                <div class="card-icon">{diagram["icon"]}</div>
                <h3>{diagram["title"]}</h3>
                <p>{diagram["description"]}</p>
                <span class="badge">{"100% Dynamic" if diagram["file"] == "evidence_heatmap.html" else "Engineering" if cat_key == "engineering" else "Interactive"}</span>
            </a>
            """.rstrip()
            for diagram in cat_info["diagrams"]
        )

        # Just add cards directly without section headers
        for card in cat_info["diagrams"]:
            cards_html = f"""
            <a href="{card["file"]}" class="card">
                <div class="card-icon">{card["icon"]}</div>
                <h3>{card["title"]}</h3>
                <p>{card["description"]}</p>
                <span class="badge">{card.get("category", "").replace("-", " ").title()}</span>
            </a>
            """
            category_sections.append(cards_html)

    diagram_count = len(diagrams)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ShopQ Code-Graph - Visual Documentation</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
            background: #000000;
            min-height: 100vh;
            padding: 0;
            margin: 0;
            color: #f5f5f7;
        }}

        .container {{
            max-width: 1280px;
            margin: 0 auto;
            padding: 60px 40px;
        }}

        .hero {{
            text-align: center;
            margin-bottom: 64px;
        }}

        .hero h1 {{
            font-size: 56px;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 12px;
            letter-spacing: -0.02em;
        }}

        .hero p {{
            font-size: 21px;
            color: #a1a1a6;
            font-weight: 400;
            line-height: 1.4;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 20px;
            margin-bottom: 48px;
        }}

        .card {{
            background: #1c1c1e;
            border-radius: 18px;
            padding: 40px 32px;
            text-decoration: none;
            color: inherit;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid #2c2c2e;
            position: relative;
            overflow: hidden;
        }}

        .card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, #636366 0%, #8e8e93 100%);
            opacity: 0;
            transition: opacity 0.3s;
        }}

        .card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 12px 32px rgba(255, 255, 255, 0.05);
            border-color: #3a3a3c;
            background: #2c2c2e;
        }}

        .card:hover::before {{
            opacity: 1;
        }}

        .card-icon {{
            font-size: 44px;
            margin-bottom: 20px;
        }}

        .card h3 {{
            font-size: 24px;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 12px;
            letter-spacing: -0.01em;
        }}

        .card p {{
            color: #a1a1a6;
            line-height: 1.5;
            font-size: 15px;
            margin-bottom: 16px;
        }}

        .badge {{
            display: inline-block;
            background: #2c2c2e;
            color: #f5f5f7;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .search-panel {{
            background: #1c1c1e;
            border-radius: 18px;
            padding: 32px;
            margin-bottom: 48px;
            border: 1px solid #2c2c2e;
        }}

        .search-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }}

        .search-header h2 {{
            color: #ffffff;
            font-size: 24px;
            font-weight: 600;
        }}

        .search-input {{
            width: 100%;
            padding: 14px 18px;
            border-radius: 12px;
            border: 1px solid #3a3a3c;
            background: #2c2c2e;
            color: #f5f5f7;
            font-size: 17px;
            margin-bottom: 20px;
            font-family: inherit;
            transition: border-color 0.2s;
        }}

        .search-input:focus {{
            outline: none;
            border-color: #636366;
            background: #3a3a3c;
        }}

        .search-input::placeholder {{
            color: #636366;
        }}

        .search-results {{
            max-height: 400px;
            overflow-y: auto;
        }}

        .search-item {{
            padding: 16px 20px;
            border-radius: 12px;
            background: #2c2c2e;
            margin-bottom: 12px;
            border: 1px solid transparent;
            transition: all 0.2s;
        }}

        .search-item:hover {{
            background: #3a3a3c;
            border-color: #48484a;
        }}

        .search-item-title {{
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 8px;
            font-size: 15px;
        }}

        .search-item-meta {{
            font-size: 13px;
            color: #a1a1a6;
            margin-bottom: 8px;
        }}

        .search-item-links {{
            font-size: 13px;
            margin-bottom: 6px;
        }}

        .search-item-links a {{
            color: #0a84ff;
            text-decoration: none;
        }}

        .search-item-links a:hover {{
            text-decoration: underline;
        }}

        .search-item-tests {{
            font-size: 12px;
            color: #8e8e93;
        }}

        @media (max-width: 768px) {{
            .hero h1 {{
                font-size: 36px;
            }}

            .search-panel {{
                padding: 20px;
            }}
        }}

        .category-title {{
            font-size: 32px;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 8px;
            letter-spacing: -0.01em;
        }}

        .category-description {{
            font-size: 17px;
            color: #a1a1a6;
            margin-bottom: 32px;
        }}

        .footer {{
            text-align: center;
            padding: 64px 32px;
            border-top: 1px solid #2c2c2e;
            margin-top: 80px;
        }}

        .footer p {{
            color: #a1a1a6;
            font-size: 14px;
            margin-bottom: 8px;
        }}

        .footer a {{
            color: #0a84ff;
            text-decoration: none;
            margin: 0 12px;
            font-size: 14px;
        }}

        .footer a:hover {{
            text-decoration: underline;
        }}

        .stats {{
            background: #1c1c1e;
            border-radius: 18px;
            padding: 32px;
            margin-bottom: 48px;
            border: 1px solid #2c2c2e;
            text-align: center;
        }}

        .stats h3 {{
            font-size: 21px;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 24px;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
        }}

        .stat-item {{
            background: #2c2c2e;
            padding: 20px;
            border-radius: 12px;
        }}

        .stat-number {{
            font-size: 36px;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 4px;
        }}

        .stat-label {{
            font-size: 13px;
            color: #a1a1a6;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .stat-label {{
            font-size: 14px;
            opacity: 0.8;
        }}

        .category-section {{
            margin-bottom: 60px;
        }}

        .category-title {{
            color: white;
            font-size: 32px;
            margin-bottom: 12px;
            text-align: center;
        }}

        .category-description {{
            color: rgba(255,255,255,0.9);
            font-size: 16px;
            text-align: center;
            margin-bottom: 32px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>ShopQ Code-Graph</h1>
            <p>Interactive Visual Documentation</p>
        </div>

        <div class="grid">
            {"".join(category_sections)}
        </div>

        <div class="footer">
            <p><strong>Auto-generated:</strong> {generated_at}</p>
            <p>
                <a href="../../INDEX.md">Documentation Index</a>
                <a href="../../docs/ARCHITECTURE.md">Architecture Docs</a>
                <a href="../../QUICKSTART.md">Quickstart Guide</a>
            </p>
            <p style="margin-top: 16px; opacity: 0.8;">
                ✨ Regenerate: <code>./code-graph/scripts/quick_regen.sh</code>
            </p>
        </div>
    </div>
</body>
</html>"""

    return html


def generate_and_save_all_diagrams() -> list[Path]:
    """
    Generate all HTML diagrams and save them to disk.

    Side Effects:
    - Creates code-graph/visuals/html/ directory if it doesn't exist
    - Writes 6+ HTML files (system_storyboard.html, classification_flow.html, etc.)
    - Writes index.html file
    - Overwrites existing HTML files without warning
    - Reads markdown files from code-graph/visuals/

    Returns:
        List of Path objects for generated HTML files
    """
    print("🎨 Generating interactive HTML diagrams...")
    generated_files = []

    # Ensure output directory exists
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize ShopQ context

    diagrams = [
        # Story Overview
        {
            "file": "system_storyboard.html",
            "markdown": "SYSTEM_STORYBOARD.md",
            "title": "System Storyboard",
            "description": "Narrative view of capture → classify → learn → digest beats",
            "icon": "🧭",
            "category": "story",
        },
        {
            "file": "classification_flow.html",
            "markdown": "CLASSIFICATION_FLOW.md",
            "title": "Task-Flow: Email Classification",
            "description": "What happens when an email is classified? (Rules → LLM → Verifier → Labels)",
            "icon": "🔄",
            "category": "task-flow",
        },
        {
            "file": "auto_organize_sequence.html",
            "markdown": "AUTO_ORGANIZE_SEQUENCE.md",
            "title": "Task-Flow: Auto-Organize",
            "description": "What happens when auto-organize runs? (Alarm → Fetch → Classify → Label → Digest)",
            "icon": "⚡",
            "category": "task-flow",
        },
        # REMOVED: cost_performance.html - 70% fake metrics
        # REMOVED: task_flow_organize.html - duplicate of classification_flow
        # Task-Flow Lens (Focused)
        {
            "file": "task_flow_digest.html",
            "markdown": "TASK_FLOW_DIGEST.md",
            "title": "Task-Flow: Digest Generation",
            "description": "What happens during daily digest generation? (≤8 steps)",
            "icon": "📰",
            "category": "task-flow",
        },
        {
            "file": "task_flow_feedback.html",
            "markdown": "TASK_FLOW_FEEDBACK.md",
            "title": "Task-Flow: Feedback Learning",
            "description": "What happens when user corrects a label? (≤8 steps)",
            "icon": "🔄",
            "category": "task-flow",
        },
        # Evidence Lens
        {
            "file": "evidence_heatmap.html",
            "markdown": "EVIDENCE_HEATMAP.md",
            "title": "Evidence Heat-Map",
            "description": "What's risky/hot right now? (top 12 by churn + TODOs + incidents)",
            "icon": "🔥",
            "category": "evidence",
        },
    ]

    for diagram in diagrams:
        print(f"  📊 {diagram['title']}...")

        # Read markdown file
        md_path = VISUALS_DIR / diagram["markdown"]
        if not md_path.exists():
            print(f"     ⚠️  Markdown file not found: {md_path}")
            continue

        markdown_content = md_path.read_text()
        mermaid_code = extract_mermaid_code(markdown_content)

        if not mermaid_code:
            print(f"     ⚠️  No Mermaid code found in {diagram['markdown']}")
            continue

        # Extract execution steps for task-flow diagrams
        execution_steps = None
        if diagram["category"] == "task-flow":
            execution_steps = extract_execution_steps(markdown_content)
            if execution_steps:
                print(f"     📖 Found {len(execution_steps)} execution steps")

        # Generate HTML
        html_content = generate_html_template(
            title=diagram["title"],
            mermaid_code=mermaid_code,
            description=diagram["description"],
            markdown_file=diagram["markdown"],
            execution_steps=execution_steps,
        )

        # Save HTML
        html_path = HTML_DIR / diagram["file"]
        html_path.write_text(html_content)
        generated_files.append(html_path)
        print(f"     ✅ Saved to html/{diagram['file']}")

    # Generate index page
    print("  📊 Index page...")
    index_html = generate_index_html(diagrams)
    index_path = HTML_DIR / "index.html"
    index_path.write_text(index_html)
    generated_files.append(index_path)
    print("     ✅ Saved to html/index.html")

    print("\n✨ Done! Open in browser:")
    print(f"   file://{HTML_DIR}/index.html")
    print("\n💡 Or run: open {HTML_DIR}/index.html")

    return generated_files


if __name__ == "__main__":
    generate_and_save_all_diagrams()
