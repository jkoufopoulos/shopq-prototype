#!/bin/bash

# Comprehensive Digest Validation
# Cross-references classified emails vs digest output

set -e

echo "🔍 Digest Validation Test"
echo "========================="
echo ""

# Check backend
if ! curl -s http://localhost:8000/ > /dev/null 2>&1; then
  echo "❌ Backend not running"
  echo "   Start: uvicorn mailq.api:app --reload --port 8000"
  exit 1
fi

# Set Chrome profile
export CHROME_USER_DATA="$HOME/Library/Application Support/Google/Chrome"

echo "▶️  Running validation test..."
echo ""

# Run test
npx playwright test tests/e2e/digest-validation.spec.js \
  --reporter=list \
  2>&1 | tee /tmp/validation-test.log

# Find latest report
LATEST=$(ls -td test-results/validation-* 2>/dev/null | head -1)

if [ -n "$LATEST" ]; then
  echo ""
  echo "📊 VALIDATION REPORT"
  echo "===================="
  echo ""

  # Show Claude analysis
  if [ -f "$LATEST/CLAUDE_ANALYSIS.md" ]; then
    cat "$LATEST/CLAUDE_ANALYSIS.md"
  fi

  echo ""
  echo "📁 Full report: $LATEST"
  echo ""
  echo "Commands:"
  echo "  View summary: cat $LATEST/summary.md"
  echo "  View screenshots: open $LATEST/*.png"
  echo "  View digest: cat $LATEST/digest-text.txt"
  echo "  View data: jq . $LATEST/report.json"
  echo ""
fi
