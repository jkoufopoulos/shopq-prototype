#!/bin/bash
# Comprehensive E2E Test Runner for ShopQ
# Runs against YOUR real Gmail with YOUR real emails
#
# This script will:
# 1. Check Chrome is closed
# 2. Start the backend API
# 3. Run all E2E tests using your Chrome profile
# 4. Iterate on failures until everything passes

set -e  # Exit on error

echo "🧪 ShopQ Comprehensive E2E Test Suite"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=8000
CHROME_PROFILE="$HOME/Library/Application Support/Google/Chrome"
MAX_ITERATIONS=5

# Check if Chrome is running
if pgrep -x "Google Chrome" > /dev/null; then
    echo -e "${YELLOW}⚠️  Chrome is currently running${NC}"
    echo "   Please close Chrome to avoid profile lock issues"
    echo ""
    read -p "Press Enter after closing Chrome, or Ctrl+C to cancel... "
fi

# Check if backend is already running
if lsof -Pi :$BACKEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠️  Backend already running on port $BACKEND_PORT${NC}"
    echo "   Using existing backend instance"
    BACKEND_ALREADY_RUNNING=true
else
    echo "🚀 Starting backend API..."

    # Start backend in background
    uvicorn shopq.api:app --reload --port $BACKEND_PORT > /tmp/mailq-backend.log 2>&1 &
    BACKEND_PID=$!

    echo "   Backend PID: $BACKEND_PID"
    echo "   Waiting for backend to be ready..."

    # Wait for backend to be ready
    for i in {1..30}; do
        if curl -s http://localhost:$BACKEND_PORT/api/health > /dev/null 2>&1; then
            echo -e "${GREEN}   ✅ Backend is ready${NC}"
            break
        fi

        if [ $i -eq 30 ]; then
            echo -e "${RED}   ❌ Backend failed to start${NC}"
            echo "   Check logs: tail -f /tmp/mailq-backend.log"
            exit 1
        fi

        sleep 1
    done
fi

# Set Chrome profile for tests
export CHROME_USER_DATA="$CHROME_PROFILE"

echo ""
echo "📋 Test Configuration:"
echo "   Chrome Profile: $CHROME_USER_DATA"
echo "   Backend API: http://localhost:$BACKEND_PORT"
echo "   Max Iterations: $MAX_ITERATIONS"
echo ""

# Function to run tests
run_tests() {
    local iteration=$1

    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "🔄 Test Iteration $iteration of $MAX_ITERATIONS"
    echo "═══════════════════════════════════════════════════════"
    echo ""

    # Run Playwright tests
    if npx playwright test --reporter=list 2>&1 | tee /tmp/mailq-test-output.log; then
        echo ""
        echo -e "${GREEN}✅ All tests passed!${NC}"
        return 0
    else
        echo ""
        echo -e "${RED}❌ Some tests failed${NC}"
        return 1
    fi
}

# Function to analyze failures
analyze_failures() {
    echo ""
    echo "📊 Analyzing test failures..."

    # Extract failure information from test output
    if grep -q "expected" /tmp/mailq-test-output.log; then
        echo ""
        echo "🔍 Failure Details:"
        grep -A 5 "Error:" /tmp/mailq-test-output.log || true
        echo ""
    fi

    # Check backend logs for errors
    if [ -f /tmp/mailq-backend.log ]; then
        if grep -qi "error" /tmp/mailq-backend.log | tail -20; then
            echo ""
            echo "🔍 Backend Errors (last 20 lines):"
            grep -i "error" /tmp/mailq-backend.log | tail -20 || true
            echo ""
        fi
    fi
}

# Main test loop
iteration=1
while [ $iteration -le $MAX_ITERATIONS ]; do
    if run_tests $iteration; then
        # Tests passed!
        echo ""
        echo "═══════════════════════════════════════════════════════"
        echo -e "${GREEN}🎉 All tests passed successfully!${NC}"
        echo "═══════════════════════════════════════════════════════"

        # Cleanup
        if [ -z "$BACKEND_ALREADY_RUNNING" ] && [ ! -z "$BACKEND_PID" ]; then
            echo ""
            echo "🛑 Stopping backend..."
            kill $BACKEND_PID 2>/dev/null || true
        fi

        exit 0
    fi

    # Tests failed - analyze and continue
    analyze_failures

    if [ $iteration -eq $MAX_ITERATIONS ]; then
        echo ""
        echo "═══════════════════════════════════════════════════════"
        echo -e "${RED}❌ Tests still failing after $MAX_ITERATIONS iterations${NC}"
        echo "═══════════════════════════════════════════════════════"
        echo ""
        echo "📋 Next Steps:"
        echo "   1. Review test output: cat /tmp/mailq-test-output.log"
        echo "   2. Review backend logs: tail -f /tmp/mailq-backend.log"
        echo "   3. Check extension console in Chrome DevTools"
        echo "   4. Run specific test: npx playwright test <test-file>"
        echo ""

        # Cleanup
        if [ -z "$BACKEND_ALREADY_RUNNING" ] && [ ! -z "$BACKEND_PID" ]; then
            echo "🛑 Stopping backend..."
            kill $BACKEND_PID 2>/dev/null || true
        fi

        exit 1
    fi

    echo ""
    echo "🔧 Attempting to fix issues..."
    echo "   (In automated mode, Claude would analyze and fix here)"
    echo ""
    echo "Press Enter to retry tests, or Ctrl+C to cancel..."
    read

    iteration=$((iteration + 1))
done
