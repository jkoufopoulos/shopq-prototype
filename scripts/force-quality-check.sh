#!/bin/bash
# Force Quality Check - Run Full QC Pipeline Immediately
#
# This script forces analysis of ALL new sessions regardless of thresholds.
# Use this after clicking "Organize" in MailQ to immediately check quality.
#
# Usage:
#   ./scripts/force-quality-check.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "⚡ Force Quality Check"
echo "===================="
echo ""

# Load environment variables from .env
source "$SCRIPT_DIR/load-env.sh" 2>/dev/null || true

# Check prerequisites
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "❌ ANTHROPIC_API_KEY not set"
  echo "   Add to .env file or: export ANTHROPIC_API_KEY=your-key-here"
  exit 1
fi

if [ -z "$GITHUB_TOKEN" ]; then
  echo "⚠️  GITHUB_TOKEN not set - GitHub issues will not be created"
  echo "   Add to .env file or: export GITHUB_TOKEN=your-token-here"
  echo ""
fi

# Export environment for Python subprocess
export ANTHROPIC_API_KEY
export GITHUB_TOKEN
export MAILQ_API_URL="${MAILQ_API_URL:-https://mailq-api-488078904670.us-central1.run.app}"

cd "$PROJECT_ROOT"

echo "📊 Checking for new digest sessions..."
echo ""

# Run quality monitor with --force flag (skips volume checks)
python3 "$SCRIPT_DIR/quality-monitor/quality_monitor.py" --analyze-now --force

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Quality analysis failed"
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Force Quality Check Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show summary from database
DB_PATH="$SCRIPT_DIR/quality-monitor/quality_monitor.db"

echo "📋 Latest Issues Found:"
sqlite3 "$DB_PATH" "
  SELECT
    CASE severity
      WHEN 'high' THEN '🔴'
      WHEN 'medium' THEN '🟡'
      ELSE '⚪'
    END || ' [' || severity || '] ' ||
    SUBSTR(pattern, 1, 70) || CASE WHEN LENGTH(pattern) > 70 THEN '...' ELSE '' END
  FROM quality_issues
  ORDER BY created_at DESC
  LIMIT 10
" | awk '{print "  " $0}'

echo ""
echo "Commands:"
echo "  • View all issues:   ./scripts/view-quality-issues.sh"
echo "  • View on GitHub:    gh issue list --label quality"
echo "  • System status:     ./scripts/quality-system-status.sh"
echo ""
