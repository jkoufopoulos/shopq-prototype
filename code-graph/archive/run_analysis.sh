#!/bin/bash

set -e

echo "🔍 ShopQ Codebase Analysis Pipeline"
echo "===================================="
echo ""

# Get script directory (code-graph/scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CODE_GRAPH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "📍 Project root: $PROJECT_ROOT"
echo "📍 Code-graph dir: $CODE_GRAPH_DIR"

# Load environment variables from .env
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "🔐 Loading environment variables from .env"
    export $(cat "$PROJECT_ROOT/.env" | grep -v '^#' | xargs)
else
    echo "⚠️  Warning: .env file not found at $PROJECT_ROOT/.env"
fi

echo ""

# Step 1: Analyze codebase structure
echo "📊 Step 1/4: Analyzing codebase structure..."
cd "$PROJECT_ROOT"
python "$SCRIPT_DIR/codebase_analyzer.py" > "$CODE_GRAPH_DIR/codebase_analysis.json"
echo "   ✅ Generated: codebase_analysis.json"
echo ""

# Step 2: Add AI summaries with relationship context
echo "🤖 Step 2/4: Generating AI summaries (this may take a few minutes)..."
cd "$PROJECT_ROOT"
python "$SCRIPT_DIR/ai_summarizer.py"
echo "   ✅ Generated: codebase_analysis_with_summaries.json"
echo ""

# Step 3: Generate markdown documentation
echo "📝 Step 3/4: Generating markdown documentation..."
cd "$PROJECT_ROOT"
python "$SCRIPT_DIR/generate_docs.py"
echo "   ✅ Generated: CODEBASE_ANALYSIS.md"
echo ""

# Step 4: Generate HTML visualizations
echo "🌐 Step 4/4: Generating HTML documentation..."
cd "$PROJECT_ROOT"
python "$SCRIPT_DIR/generate_index.py"
python "$SCRIPT_DIR/generate_html.py"
python "$SCRIPT_DIR/generate_dependencies.py"  # ✅ ADD THIS
echo "   ✅ Generated: docs/analysis/index.html"
echo "   ✅ Generated: docs/analysis/detailed.html"
echo "   ✅ Generated: docs/analysis/dependencies.html"  # ✅ ADD THIS
echo ""

echo "✨ Analysis complete!"
echo ""
echo "📂 View results:"
echo "   Markdown: $CODE_GRAPH_DIR/CODEBASE_ANALYSIS.md"
echo "   HTML:     file://$CODE_GRAPH_DIR/docs/analysis/index.html"
echo ""
echo "💡 Open in browser:"
echo "   open $CODE_GRAPH_DIR/docs/analysis/index.html"
