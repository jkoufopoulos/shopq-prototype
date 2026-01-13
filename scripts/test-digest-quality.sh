#!/bin/bash

# Test Digest Quality with Visual Debugging
# Generates comprehensive reports for Claude Code to analyze

set -e

echo "🧪 Starting Digest Quality Test..."
echo ""

# Ensure backend is running
if ! curl -s http://localhost:8000/ > /dev/null 2>&1; then
  echo "❌ Backend not running at localhost:8000"
  echo "   Start it with: uvicorn mailq.api:app --reload --port 8000"
  exit 1
fi

# Set Chrome profile
export CHROME_USER_DATA="$HOME/Library/Application Support/Google/Chrome"

# Run test with detailed output
npx playwright test tests/e2e/digest-quality.spec.js \
  --reporter=list,json,html \
  --output=test-results/digest-debug \
  2>&1 | tee /tmp/digest-test.log

# Find latest report directory
LATEST_REPORT=$(ls -td test-results/digest-* 2>/dev/null | head -1)

if [ -n "$LATEST_REPORT" ]; then
  echo ""
  echo "📊 REPORT GENERATED"
  echo "=================="
  echo "Location: $LATEST_REPORT"
  echo ""

  # Show summary
  if [ -f "$LATEST_REPORT/summary.md" ]; then
    cat "$LATEST_REPORT/summary.md"
  fi

  echo ""
  echo "📁 Files generated:"
  ls -lh "$LATEST_REPORT"

  echo ""
  echo "🖼️  View screenshots:"
  echo "   open $LATEST_REPORT/*.png"
  echo ""
  echo "📄 View full report:"
  echo "   cat $LATEST_REPORT/report.json | jq ."
  echo ""
fi

# Open HTML report
if [ -f "playwright-report/index.html" ]; then
  echo "🌐 Opening HTML report..."
  open playwright-report/index.html
fi

echo ""
echo "✅ Test complete!"
