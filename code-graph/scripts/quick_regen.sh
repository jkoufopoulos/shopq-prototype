#!/bin/bash
# Quick Diagram Regeneration Script
# Regenerates Mermaid diagrams from codebase analysis

set -euo pipefail  # Exit on error, undefined variables, pipe failures

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "🎨 Regenerating code-graph diagrams..."
echo ""

# ============================================================================
# STEP 1: Generate Markdown Diagrams
# ============================================================================

echo "📊 Step 1: Generating Mermaid markdown diagrams..."
python3 code-graph/scripts/generate_diagrams.py || {
    echo "❌ ERROR: Diagram generation failed"
    exit 1
}

# Validate expected markdown files exist
EXPECTED_MD_FILES=(
    "code-graph/visuals/SYSTEM_STORYBOARD.md"
    "code-graph/visuals/CLASSIFICATION_FLOW.md"
    "code-graph/visuals/EVIDENCE_HEATMAP.md"
)

for file in "${EXPECTED_MD_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "❌ ERROR: Expected markdown file not created: $file"
        echo "   Did generate_diagrams.py fail silently?"
        exit 1
    fi
done

echo "✅ Step 1 complete: Markdown diagrams generated"
echo ""

# ============================================================================
# STEP 2: Generate HTML from Markdown
# ============================================================================

echo "📊 Step 2: Converting markdown to interactive HTML..."
python3 code-graph/scripts/generate_diagram_html.py || {
    echo "❌ ERROR: HTML generation failed"
    exit 1
}

# Validate expected HTML files exist
EXPECTED_HTML_FILES=(
    "code-graph/visuals/html/index.html"
    "code-graph/visuals/html/system_storyboard.html"
)

for file in "${EXPECTED_HTML_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "❌ ERROR: Expected HTML file not created: $file"
        echo "   Did generate_diagram_html.py fail silently?"
        exit 1
    fi
done

echo "✅ Step 2 complete: HTML diagrams generated"
echo ""

# ============================================================================
# STEP 3: Generate Evidence Heat-Map
# ============================================================================

echo "📊 Step 3: Generating evidence heat-map..."
python3 code-graph/scripts/generate_evidence_html.py || {
    echo "❌ ERROR: Evidence heat-map generation failed"
    exit 1
}

# Validate evidence heatmap exists
if [[ ! -f "code-graph/visuals/html/evidence_heatmap.html" ]]; then
    echo "❌ ERROR: Evidence heatmap not created"
    exit 1
fi

echo "✅ Step 3 complete: Evidence heat-map generated"
echo ""

echo ""
echo "✨ Diagrams updated successfully!"
echo ""
echo "📍 View diagrams:"
echo "   Markdown:"
echo "   - code-graph/visuals/SYSTEM_DIAGRAM.md"
echo "   - code-graph/visuals/CLASSIFICATION_FLOW.md"
echo ""
echo "   Interactive HTML:"
echo "   - code-graph/visuals/html/index.html"
echo ""
echo "💡 Tip: These diagrams are auto-generated. Edit code, not diagrams."
