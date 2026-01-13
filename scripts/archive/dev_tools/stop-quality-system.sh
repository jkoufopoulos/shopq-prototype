#!/bin/bash
# Stop MailQ Quality Monitor

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_PID_FILE="$SCRIPT_DIR/quality-monitor/.monitor.pid"

echo "🛑 Stopping MailQ Quality Monitor"
echo "=================================="
echo ""

# Stop monitor daemon
if [ -f "$MONITOR_PID_FILE" ]; then
  MONITOR_PID=$(cat "$MONITOR_PID_FILE")

  if ps -p "$MONITOR_PID" > /dev/null 2>&1; then
    echo "Stopping quality monitor daemon (PID: $MONITOR_PID)..."
    kill "$MONITOR_PID"
    sleep 1

    # Force kill if still running
    if ps -p "$MONITOR_PID" > /dev/null 2>&1; then
      echo "  Force killing..."
      kill -9 "$MONITOR_PID"
    fi

    rm "$MONITOR_PID_FILE"
    echo "✅ Monitor daemon stopped"
  else
    echo "ℹ️  Monitor daemon not running (PID $MONITOR_PID not found)"
    rm "$MONITOR_PID_FILE"
  fi
else
  echo "ℹ️  Quality monitor is not running"
fi

echo ""
echo "To restart: ./scripts/start-quality-system.sh"
