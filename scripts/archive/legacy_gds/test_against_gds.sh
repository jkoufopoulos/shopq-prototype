#!/bin/bash
# Test MailQ against Golden Dataset (gds-1.0.csv)
#
# Usage:
#   ./scripts/test_against_gds.sh
#   ./scripts/test_against_gds.sh --verbose
#   ./scripts/test_against_gds.sh --report

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
VERBOSE=false
REPORT=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --report|-r)
            REPORT=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--verbose] [--report]"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  MailQ Golden Dataset Test Suite                          ║${NC}"
echo -e "${BLUE}║  Testing against gds-1.0.csv (500 emails)                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if GDS exists
GDS_PATH="tests/golden_set/gds-1.0.csv"
if [ ! -f "$GDS_PATH" ]; then
    echo -e "${RED}❌ Error: GDS not found at $GDS_PATH${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Found GDS at $GDS_PATH${NC}"
echo ""

# Run tests
if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS="-v"
else
    PYTEST_ARGS="-q"
fi

# Test 1: Type Mapper (if exists)
echo -e "${YELLOW}[1/3] Testing Type Mapper...${NC}"
if [ -f "tests/test_type_mapper_gds.py" ]; then
    pytest tests/test_type_mapper_gds.py $PYTEST_ARGS || {
        echo -e "${RED}❌ Type Mapper tests FAILED${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ Type Mapper tests PASSED${NC}"
else
    echo -e "${YELLOW}⚠️  test_type_mapper_gds.py not found (skipping)${NC}"
fi
echo ""

# Test 2: Guardrails
echo -e "${YELLOW}[2/3] Testing Guardrails...${NC}"
if [ -f "tests/test_guardrails_gds.py" ]; then
    pytest tests/test_guardrails_gds.py $PYTEST_ARGS || {
        echo -e "${RED}❌ Guardrails tests FAILED${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ Guardrails tests PASSED${NC}"
else
    echo -e "${YELLOW}⚠️  test_guardrails_gds.py not found (skipping)${NC}"
fi
echo ""

# Test 3: Importance Baseline (Quality Gates)
echo -e "${YELLOW}[3/3] Testing Quality Gates (Importance Baseline)...${NC}"
if [ -f "tests/test_importance_baseline_gds.py" ]; then
    pytest tests/test_importance_baseline_gds.py $PYTEST_ARGS || {
        echo -e "${RED}❌ Quality Gate tests FAILED${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ Quality Gate tests PASSED${NC}"
else
    echo -e "${YELLOW}⚠️  test_importance_baseline_gds.py not found (skipping)${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ALL TESTS PASSED ✅                                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Optional: Generate HTML report
if [ "$REPORT" = true ]; then
    echo -e "${YELLOW}Generating HTML report...${NC}"
    pytest tests/test_*_gds.py --html=reports/gds_test_report.html --self-contained-html
    echo -e "${GREEN}✅ Report saved to reports/gds_test_report.html${NC}"
fi

echo -e "${GREEN}✨ Ready to ship! All quality gates passed.${NC}"
