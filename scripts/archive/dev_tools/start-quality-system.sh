#!/bin/bash
# Start ShopQ Quality Monitor
# Manual quality analysis - run after ShopQ digest generation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MONITOR_PID_FILE="$SCRIPT_DIR/quality-monitor/.monitor.pid"
MONITOR_LOG="$SCRIPT_DIR/quality-monitor/quality_monitor.log"

# Configuration
CHECK_INTERVAL="${QUALITY_CHECK_INTERVAL:-30}"  # minutes

echo "🚀 Starting ShopQ Quality Monitor"
echo "=================================="
echo ""

# Load environment variables from .env
echo "Loading environment from .env..."
source "$SCRIPT_DIR/load-env.sh" 2>/dev/null || true
echo ""

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

# Check if already running
if [ -f "$MONITOR_PID_FILE" ]; then
  MONITOR_PID=$(cat "$MONITOR_PID_FILE")
  if ps -p "$MONITOR_PID" > /dev/null 2>&1; then
    echo "✅ Quality monitor daemon already running (PID: $MONITOR_PID)"
    echo ""
    echo "Commands:"
    echo "  • Status:  ./scripts/quality-system-status.sh"
    echo "  • Logs:    tail -f $MONITOR_LOG"
    echo "  • Stop:    ./scripts/stop-quality-system.sh"
    exit 0
  else
    echo "Removing stale monitor PID file..."
    rm "$MONITOR_PID_FILE"
  fi
fi

echo "Configuration:"
echo "  • Check interval:  $CHECK_INTERVAL minutes"
echo "  • Min emails:      1 (configured in .env)"
echo ""

# Start quality monitor daemon (polling)
echo "📊 Starting quality monitor daemon..."
cd "$PROJECT_ROOT"
nohup python3 "$SCRIPT_DIR/quality-monitor/quality_monitor.py" --daemon \
  > "$MONITOR_LOG" 2>&1 &

MONITOR_PID=$!
echo $MONITOR_PID > "$MONITOR_PID_FILE"
echo "   ✅ Started (PID: $MONITOR_PID)"
echo "   📄 Logs: $MONITOR_LOG"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Quality Monitor Running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "How it works:"
echo "  1. 🔄 Daemon polls GCS every $CHECK_INTERVAL minutes for new sessions"
echo "  2. 📊 Analysis runs when ≥1 new sessions found"
echo "  3. 🤖 Claude analyzes classifications and digest format"
echo "  4. 🐙 GitHub issues created for high/medium severity problems"
echo ""
echo "Manual Analysis:"
echo "  Run immediately after ShopQ digest generation:"
echo "  python3 scripts/quality-monitor/quality_monitor.py --analyze-now --force"
echo ""
echo "Commands:"
echo "  • Status:      ./scripts/quality-system-status.sh"
echo "  • View logs:   tail -f $MONITOR_LOG"
echo "  • Stop:        ./scripts/stop-quality-system.sh"
echo "  • Manual run:  ./scripts/run-quality-pipeline.sh"
echo ""
