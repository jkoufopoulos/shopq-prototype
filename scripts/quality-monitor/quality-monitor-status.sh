#!/bin/bash
#
# Check Quality Monitor status
#

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Quality Monitor Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if daemon is running
DAEMON_PID=$(ps aux | grep 'quality_monitor.py --daemon' | grep -v grep | awk '{print $2}' | head -1)

if [ -n "$DAEMON_PID" ]; then
    echo "✅ Daemon Status: RUNNING (PID: $DAEMON_PID)"

    # Get process start time
    START_TIME=$(ps -p $DAEMON_PID -o lstart= 2>/dev/null || echo "Unknown")
    echo "   Started: $START_TIME"
else
    echo "❌ Daemon Status: NOT RUNNING"
    echo ""
    echo "To start: ./run-quality-monitor.sh &"
    exit 1
fi

echo ""

# Check log file
if [ -f quality_monitor.log ]; then
    LOG_SIZE=$(du -h quality_monitor.log | awk '{print $1}')
    LAST_LOG=$(tail -1 quality_monitor.log 2>/dev/null || echo "No logs yet")

    echo "📝 Log File: quality_monitor.log ($LOG_SIZE)"
    echo "   Last entry: $LAST_LOG"
else
    echo "⚠️  No log file found"
fi

echo ""

# Check database
if [ -f quality_monitor.db ]; then
    echo "💾 Database: quality_monitor.db"

    # Get stats
    NUM_SESSIONS=$(sqlite3 quality_monitor.db "SELECT COUNT(*) FROM analyzed_sessions" 2>/dev/null || echo "0")
    NUM_ISSUES=$(sqlite3 quality_monitor.db "SELECT COUNT(*) FROM quality_issues" 2>/dev/null || echo "0")
    NUM_UNRESOLVED=$(sqlite3 quality_monitor.db "SELECT COUNT(*) FROM quality_issues WHERE NOT resolved" 2>/dev/null || echo "0")

    echo "   Sessions analyzed: $NUM_SESSIONS"
    echo "   Issues detected: $NUM_ISSUES"
    echo "   Unresolved issues: $NUM_UNRESOLVED"
else
    echo "💾 Database: Not created yet (will be created on first analysis)"
fi

echo ""

# Show next check time
if [ -n "$DAEMON_PID" ]; then
    echo "⏰ Next Check: Within 30 minutes"
    echo "   (Daemon checks every 30 minutes for new sessions)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 Commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  tail -f quality_monitor.log              # Watch logs in real-time"
echo "  ./view-quality-issues.sh                 # View detected issues"
echo "  ./view-quality-issues.sh --stats         # View statistics"
echo "  kill $DAEMON_PID                         # Stop daemon"
echo "  ./run-quality-monitor.sh --analyze-now   # Force analysis now"
echo ""
