#!/bin/bash
# Auto-Fix Test Runner
# Runs tests, captures failures, and provides fix suggestions
# This is what Claude will use to iteratively fix issues

set -e

echo "🤖 ShopQ Auto-Fix Test Runner"
echo "=============================="
echo ""

# Ensure backend is running
if ! lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "🚀 Starting backend..."
    uvicorn shopq.api:app --reload --port 8000 > /tmp/mailq-backend.log 2>&1 &
    sleep 3
fi

# Set Chrome profile
export CHROME_USER_DATA="$HOME/Library/Application Support/Google/Chrome"

# Run tests and capture output
echo "🧪 Running tests..."
echo ""

# Create detailed test output
npx playwright test \
  --reporter=html \
  --reporter=json \
  --reporter=list \
  > /tmp/mailq-test-detailed.log 2>&1 || true

# Parse results
if [ -f test-results/results.json ]; then
    echo ""
    echo "📊 Test Results Analysis:"
    echo ""

    # Use Python to parse JSON results (if available)
    if command -v python3 &> /dev/null; then
        python3 - <<'EOF'
import json
import os

if os.path.exists('test-results/results.json'):
    with open('test-results/results.json', 'r') as f:
        results = json.load(f)

    total = len(results.get('suites', []))
    passed = sum(1 for s in results.get('suites', []) if s.get('status') == 'passed')
    failed = total - passed

    print(f"   Total Tests: {total}")
    print(f"   Passed: {passed} ✅")
    print(f"   Failed: {failed} ❌")
    print(f"   Pass Rate: {(passed/total*100):.1f}%")
    print("")

    if failed > 0:
        print("🔍 Failed Tests:")
        for suite in results.get('suites', []):
            if suite.get('status') != 'passed':
                print(f"   - {suite.get('title', 'Unknown')}")
        print("")
else:
    print("   No results file found")
EOF
    else
        echo "   (Install Python3 for detailed analysis)"
    fi
fi

# Show failure details
echo ""
echo "📋 Detailed Output:"
echo "   Full logs: /tmp/mailq-test-detailed.log"
echo "   HTML report: playwright-report/index.html"
echo ""

# Check if we should show failures
if grep -q "failed" /tmp/mailq-test-detailed.log; then
    echo "❌ Test Failures Detected:"
    echo ""
    grep -A 10 "Error:" /tmp/mailq-test-detailed.log | head -50 || true
fi

echo ""
echo "🔧 Ready for Claude to analyze and fix"
echo "   Run: open playwright-report/index.html (to view detailed report)"
