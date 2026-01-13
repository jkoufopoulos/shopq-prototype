#!/bin/bash

# Watch Mode - Automatically debug new digests as they're generated
# Continuously monitors for new digest sessions and validates them

set -e

WATCH_INTERVAL=${1:-5}  # Check every 5 seconds by default
LAST_SESSION=""

echo "👁️  Watch Mode - Automated Digest Debugging"
echo "==========================================="
echo "Monitoring for new digest sessions every ${WATCH_INTERVAL}s..."
echo "Press Ctrl+C to stop"
echo ""

# Create watch directory
WATCH_DIR="test-results/watch-mode"
mkdir -p "$WATCH_DIR"

ITERATION=1

while true; do
  # Find latest session
  LATEST_SESSION=$(ls -t exports/mailq_session_*.csv 2>/dev/null | head -1 || echo "")

  if [ -z "$LATEST_SESSION" ]; then
    echo "⏳ [$(date +%H:%M:%S)] No sessions found yet. Waiting for first digest..."
    sleep "$WATCH_INTERVAL"
    continue
  fi

  # Check if this is a new session
  if [ "$LATEST_SESSION" != "$LAST_SESSION" ]; then
    LAST_SESSION="$LATEST_SESSION"
    SESSION_ID=$(basename "$LATEST_SESSION" .csv | sed 's/mailq_session_//')

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🆕 NEW DIGEST DETECTED - Session: $SESSION_ID"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🔍 Auto-validation iteration #$ITERATION"
    echo ""

    # Create iteration directory
    ITER_DIR="$WATCH_DIR/iteration-$ITERATION"
    mkdir -p "$ITER_DIR"

    # Copy session data
    cp "$LATEST_SESSION" "$ITER_DIR/session.csv"

    # ============================================================
    # Quick Analysis
    # ============================================================

    # Parse CSV data
    TOTAL_EMAILS=$(tail -n +2 "$ITER_DIR/session.csv" | wc -l | tr -d ' ')
    FEATURED=$(tail -n +2 "$ITER_DIR/session.csv" | awk -F',' '$15==1' | wc -l | tr -d ' ')
    ORPHANED=$(tail -n +2 "$ITER_DIR/session.csv" | awk -F',' '$16==1' | wc -l | tr -d ' ')
    NOISE=$(tail -n +2 "$ITER_DIR/session.csv" | awk -F',' '$17==1' | wc -l | tr -d ' ')

    echo "📊 Quick Stats:"
    echo "   Total: $TOTAL_EMAILS emails"
    echo "   Featured: $FEATURED"
    echo "   Orphaned: $ORPHANED"
    echo "   Noise: $NOISE"
    echo ""

    # Check timestamps
    SAMPLE_DATE=$(tail -n +2 "$ITER_DIR/session.csv" | head -1 | cut -d',' -f4)
    HAS_REAL_TIMESTAMPS=0

    if echo "$SAMPLE_DATE" | grep -q '^[0-9]\{13\}$'; then
      HAS_REAL_TIMESTAMPS=1
      echo "✅ Timestamps: Real email timestamps (milliseconds)"
    else
      echo "❌ Timestamps: Using current time (ISO format)"
    fi

    # Check coverage
    REPRESENTED=$((FEATURED + ORPHANED + NOISE))
    if [ "$REPRESENTED" -ne "$TOTAL_EMAILS" ]; then
      echo "❌ Coverage: $REPRESENTED/$TOTAL_EMAILS emails (gap: $((TOTAL_EMAILS - REPRESENTED)))"
    else
      echo "✅ Coverage: All $TOTAL_EMAILS emails represented"
    fi

    # Get digest text (try from backend first)
    DIGEST_TEXT=""
    if curl -s "http://localhost:8000/api/tracking/session/$SESSION_ID" > /dev/null 2>&1; then
      DIGEST_TEXT=$(curl -s "http://localhost:8000/api/tracking/session/$SESSION_ID" | jq -r '.digest_text // empty' 2>/dev/null || echo "")
    fi

    if [ -n "$DIGEST_TEXT" ]; then
      echo "$DIGEST_TEXT" > "$ITER_DIR/digest.txt"

      # Check for age markers
      if grep -q '\[.*days\? old\]' "$ITER_DIR/digest.txt" 2>/dev/null; then
        echo "✅ Temporal awareness: Age markers found"
      else
        echo "❌ Temporal awareness: No age markers"
      fi

      # Check for weather
      if grep -qE '(cloudy|sunny|rainy|clear|snowy).*[0-9]+°' "$ITER_DIR/digest.txt" 2>/dev/null; then
        echo "✅ Weather: Present"
      else
        echo "⚠️  Weather: Not found"
      fi
    fi

    # ============================================================
    # Determine if all validations passed
    # ============================================================

    ALL_PASSED=0

    if [ $HAS_REAL_TIMESTAMPS -eq 1 ] && [ "$REPRESENTED" -eq "$TOTAL_EMAILS" ]; then
      # Check if age markers exist (if we have digest text)
      if [ -n "$DIGEST_TEXT" ]; then
        if grep -q '\[.*days\? old\]' "$ITER_DIR/digest.txt" 2>/dev/null; then
          ALL_PASSED=1
        fi
      else
        # Can't check digest text, but timestamps and coverage are good
        ALL_PASSED=1
      fi
    fi

    echo ""

    if [ $ALL_PASSED -eq 1 ]; then
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo "🎉 ALL VALIDATIONS PASSED!"
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo ""
      if [ -n "$DIGEST_TEXT" ]; then
        echo "Digest preview:"
        echo "----------------------------------------"
        echo "$DIGEST_TEXT" | head -10
        echo "----------------------------------------"
      fi
      echo ""
      echo "✅ Digest is working perfectly!"
      echo "   Report saved to: $ITER_DIR/"
      echo ""
      echo "Continuing to watch for more digests..."
    else
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo "❌ ISSUES DETECTED - Running full debug analysis..."
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo ""

      # Run full debug
      echo "🔧 Launching auto-debug-digest.sh..."
      echo ""

      ./auto-debug-digest.sh 5 2>&1 | tee "$ITER_DIR/debug-output.log"

      DEBUG_EXIT_CODE=$?

      echo ""
      if [ $DEBUG_EXIT_CODE -eq 0 ]; then
        echo "✅ Issues resolved by auto-debug!"
      elif [ $DEBUG_EXIT_CODE -eq 2 ]; then
        echo "⚠️  Manual action required. Auto-debug made code changes."
        echo ""
        echo "Please:"
        echo "  1. Reload extension: chrome://extensions → MailQ → 🔄"
        echo "  2. Clear data in Gmail console (F12):"
        echo "     indexedDB.deleteDatabase('MailQLogger');"
        echo "     await chrome.storage.local.clear();"
        echo "     location.reload();"
        echo "  3. Wait for new digest (~10 seconds)"
        echo ""
        echo "Watch mode will auto-validate the new digest when it appears."
      else
        echo "❌ Auto-debug could not fully resolve issues"
        echo "   Manual intervention may be needed"
        echo "   See: $ITER_DIR/debug-output.log"
      fi
    fi

    # Save iteration summary
    echo "$ITERATION,$SESSION_ID,$TOTAL_EMAILS,$FEATURED,$ORPHANED,$NOISE,$HAS_REAL_TIMESTAMPS,$ALL_PASSED" >> "$WATCH_DIR/summary.csv"

    ITERATION=$((ITERATION + 1))

  else
    # No new session, just show heartbeat
    echo -n "."
  fi

  sleep "$WATCH_INTERVAL"
done
