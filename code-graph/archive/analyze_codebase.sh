#!/usr/bin/env bash
set -euo pipefail

# Change to project root (one level up from code-graph)
cd "$(dirname "$0")/../.."

echo "🔍 Analyzing MailQ Codebase..."
echo "Working directory: $(pwd)"
echo ""

# Step 1: Run Python analyzer
echo "▶ Step 1: Analyzing code structure..."
python3 code-graph/scripts/codebase_analyzer.py > code-graph/analysis_data.json

# Step 2: Generate reports
echo ""
echo "▶ Step 2: Generating HTML reports..."
python3 code-graph/scripts/report_generator.py

# Step 3: Generate AI summary (optional)
echo ""
echo "▶ Step 3: Generating AI summary..."
python3 <<'PYTHON_SUMMARY'
import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path.cwd()))

try:
    from mailq.vertex_gemini_classifier import VertexGeminiClassifier

    # Load analysis data
    with open('code-graph/analysis_data.json', 'r') as f:
        data = json.load(f)

    # Create prompt
    prompt = f"""You are a technical documentation expert. Analyze this codebase and create a summary for a product manager.

CODEBASE DATA:
```json
{json.dumps(data, indent=2)}
```

Provide:

1. **WHAT THIS SYSTEM DOES** (2-3 sentences, simple language)

2. **HOW IT WORKS** (architecture in plain English)
   - Main components and their roles
   - How data flows through the system

3. **KEY FILES TO KNOW** (top 5-7 most important)
   For each file:
   - Name
   - What it does (simple terms)
   - Why it matters

4. **WHERE TO MAKE COMMON CHANGES**
   - Adding a new email type
   - Changing the AI model
   - Modifying label formats
   - Adding new classification domains

Format in clean, readable HTML sections."""

    # Call Gemini
    classifier = VertexGeminiClassifier()
    response = classifier.model.generate_content(prompt)

    # Save as HTML fragment
    with open('code-graph/ai_summary.html', 'w') as f:
        f.write(response.text)

    print("✅ AI summary generated")

except Exception as e:
    print(f"⚠️  Could not generate AI summary: {e}")
    print("   (Continuing without AI summary)")

PYTHON_SUMMARY

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Analysis complete!"
echo ""
echo "🌐 Open the reports:"
echo "   open code-graph/docs/analysis/index.html"
echo ""
echo "Or view individual reports:"
echo "   open code-graph/docs/analysis/summary.html     # AI overview"
echo "   open code-graph/docs/analysis/detailed.html    # Technical details"
echo "   open code-graph/docs/analysis/dependencies.html # Dependency graph"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
