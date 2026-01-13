#!/bin/bash
# Check ShopQ Quality Monitor Status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_PID_FILE="$SCRIPT_DIR/quality-monitor/.monitor.pid"
MONITOR_LOG="$SCRIPT_DIR/quality-monitor/quality_monitor.log"
DB_PATH="$SCRIPT_DIR/quality-monitor/quality_monitor.db"

echo "🔍 ShopQ Quality Monitor Status"
echo "================================"
echo ""

# Check daemon status
echo "Quality Monitor Daemon:"
if [ -f "$MONITOR_PID_FILE" ]; then
  MONITOR_PID=$(cat "$MONITOR_PID_FILE")
  if ps -p "$MONITOR_PID" > /dev/null 2>&1; then
    echo "  Status: ✅ RUNNING (PID: $MONITOR_PID)"
    START_TIME=$(ps -o lstart= -p "$MONITOR_PID")
    echo "  Started: $START_TIME"
  else
    echo "  Status: ❌ NOT RUNNING (stale PID)"
    rm "$MONITOR_PID_FILE"
  fi
else
  echo "  Status: ⚪ NOT RUNNING"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Database stats
if [ -f "$DB_PATH" ]; then
  echo "Quality Metrics:"
  echo ""

  echo "Issues by Severity:"
  sqlite3 "$DB_PATH" "
    SELECT
      severity,
      COUNT(*) as count,
      SUM(CASE WHEN github_issue_url IS NOT NULL THEN 1 ELSE 0 END) as on_github
    FROM quality_issues
    GROUP BY severity
    ORDER BY
      CASE severity
        WHEN 'high' THEN 1
        WHEN 'medium' THEN 2
        ELSE 3
      END
  " | awk -F'|' '{
    emoji = ($1 == "high" ? "🔴" : ($1 == "medium" ? "🟡" : "⚪"));
    printf "  %s %-10s: %2d total, %2d on GitHub\n", emoji, $1, $2, $3
  }'

  echo ""
  echo "Sessions Analyzed:"
  TOTAL=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM analyzed_sessions")
  echo "  Total: $TOTAL sessions"

  echo ""
  echo "Last Analysis:"
  LAST=$(sqlite3 "$DB_PATH" "SELECT analyzed_at FROM analyzed_sessions ORDER BY analyzed_at DESC LIMIT 1" 2>/dev/null || echo "Never")
  echo "  $LAST"

  echo ""
  echo "Recent Issues (Last 3):"
  sqlite3 "$DB_PATH" "
    SELECT
      severity,
      pattern,
      SUBSTR(created_at, 1, 16) as datetime
    FROM quality_issues
    ORDER BY created_at DESC
    LIMIT 3
  " | awk -F'|' '{
    emoji = ($1 == "high" ? "🔴" : ($1 == "medium" ? "🟡" : "⚪"));
    pattern = substr($2, 1, 50);
    if (length($2) > 50) pattern = pattern "...";
    printf "  %s [%s] %s\n      %s\n", emoji, $1, pattern, $3
  }'
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Recent activity
echo "Recent Activity (Last 5 log entries):"
echo ""

if [ -f "$MONITOR_LOG" ]; then
  tail -5 "$MONITOR_LOG" | sed 's/^/  /'
else
  echo "  No logs yet"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Commands:"
echo "  • View logs:          tail -f $MONITOR_LOG"
echo "  • Manual analysis:    python3 scripts/quality-monitor/quality_monitor.py --analyze-now --force"
echo "  • Stop daemon:        ./scripts/stop-quality-system.sh"
echo "  • View issues:        gh issue list --label quality"
echo ""
