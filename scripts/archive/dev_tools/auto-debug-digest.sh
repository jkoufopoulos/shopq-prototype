#!/bin/bash

# Automated Digest Debugging Loop
# Runs until digest passes all validations or max iterations reached

set -e

MAX_ITERATIONS=${1:-10}
ITERATION=1

echo "🤖 Automated Digest Debugging Loop"
echo "===================================="
echo "Max iterations: $MAX_ITERATIONS"
echo ""

# Create iterations directory
ITERATIONS_DIR="test-results/auto-debug"
mkdir -p "$ITERATIONS_DIR"

while [ $ITERATION -le $MAX_ITERATIONS ]; do
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🔄 ITERATION $ITERATION of $MAX_ITERATIONS"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  ITER_DIR="$ITERATIONS_DIR/iteration-$ITERATION"
  mkdir -p "$ITER_DIR"

  # ============================================================
  # PHASE 1: Capture current state
  # ============================================================
  echo "📊 Phase 1: Capturing current state..."

  # Get latest backend session
  LATEST_SESSION=$(ls -t exports/shopq_session_*.csv 2>/dev/null | head -1)

  if [ -z "$LATEST_SESSION" ]; then
    echo "❌ No session data found. Need to generate digest first."
    echo ""
    echo "Please:"
    echo "1. Reload extension: chrome://extensions → ShopQ → 🔄"
    echo "2. Clear data in Gmail console (F12):"
    echo "   indexedDB.deleteDatabase('ShopQLogger');"
    echo "   await chrome.storage.local.clear();"
    echo "   location.reload();"
    echo "3. Wait 10 seconds for digest to appear"
    echo "4. Re-run this script"
    exit 1
  fi

  # Copy session data
  cp "$LATEST_SESSION" "$ITER_DIR/session.csv"

  # Get latest digest email text
  echo "📧 Fetching latest digest email..."

  # Extract session ID from filename
  SESSION_ID=$(basename "$LATEST_SESSION" .csv | sed 's/shopq_session_//')

  # Try to get digest from backend
  DIGEST_TEXT=$(curl -s "http://localhost:8000/api/tracking/session/$SESSION_ID" 2>/dev/null | jq -r '.digest_text // empty' 2>/dev/null || echo "")

  if [ -z "$DIGEST_TEXT" ]; then
    echo "⚠️  Could not fetch digest text from backend, reading from CSV..."
    DIGEST_TEXT="See session.csv for data"
  fi

  echo "$DIGEST_TEXT" > "$ITER_DIR/digest.txt"

  # Copy backend logs
  tail -500 /tmp/mailq-backend.log > "$ITER_DIR/backend.log" 2>/dev/null || echo "No backend logs" > "$ITER_DIR/backend.log"

  echo "✅ Captured state for iteration $ITERATION"

  # ============================================================
  # PHASE 2: Analyze for issues
  # ============================================================
  echo ""
  echo "🔍 Phase 2: Analyzing for issues..."

  ISSUES=()
  FIXES=()

  # Parse CSV data
  TOTAL_EMAILS=$(tail -n +2 "$ITER_DIR/session.csv" | wc -l | tr -d ' ')
  FEATURED=$(tail -n +2 "$ITER_DIR/session.csv" | awk -F',' '$15==1' | wc -l | tr -d ' ')
  ORPHANED=$(tail -n +2 "$ITER_DIR/session.csv" | awk -F',' '$16==1' | wc -l | tr -d ' ')
  NOISE=$(tail -n +2 "$ITER_DIR/session.csv" | awk -F',' '$17==1' | wc -l | tr -d ' ')

  # Check if received_date looks like a timestamp (milliseconds) or ISO date
  SAMPLE_DATE=$(tail -n +2 "$ITER_DIR/session.csv" | head -1 | cut -d',' -f4)
  HAS_REAL_TIMESTAMPS=0

  if echo "$SAMPLE_DATE" | grep -q '^[0-9]\{13\}$'; then
    HAS_REAL_TIMESTAMPS=1
    echo "✅ Timestamps: Real email timestamps detected"
  else
    echo "❌ Timestamps: Using current time (not real email dates)"
    ISSUES+=("TIMESTAMP_MISSING")
    FIXES+=("Add emailTimestamp to logger.js and reload extension")
  fi

  # Check coverage
  REPRESENTED=$((FEATURED + ORPHANED + NOISE))
  if [ "$REPRESENTED" -ne "$TOTAL_EMAILS" ]; then
    echo "❌ Coverage: $REPRESENTED/$TOTAL_EMAILS emails represented (gap: $((TOTAL_EMAILS - REPRESENTED)))"
    ISSUES+=("COVERAGE_GAP")
    FIXES+=("Check timeline synthesis logic")
  else
    echo "✅ Coverage: All $TOTAL_EMAILS emails represented"
  fi

  # Check for age markers in digest
  if grep -q '\[.*days\? old\]' "$ITER_DIR/digest.txt" 2>/dev/null; then
    echo "✅ Temporal awareness: Age markers found"
  else
    echo "❌ Temporal awareness: No age markers in digest"
    ISSUES+=("NO_AGE_MARKERS")
    FIXES+=("Check _entity_to_text() adds age markers")
  fi

  # Check for weather
  if grep -qE '(cloudy|sunny|rainy|clear|snowy).*[0-9]+°' "$ITER_DIR/digest.txt" 2>/dev/null; then
    echo "✅ Weather: Present in digest"
  else
    echo "⚠️  Weather: Not found in digest"
    ISSUES+=("NO_WEATHER")
    FIXES+=("Check weather enrichment")
  fi

  # ============================================================
  # PHASE 3: Generate report
  # ============================================================
  echo ""
  echo "📝 Phase 3: Generating report..."

  REPORT_FILE="$ITER_DIR/ANALYSIS.md"

  cat > "$REPORT_FILE" << EOF
# Iteration $ITERATION Analysis

## Summary
- **Total emails**: $TOTAL_EMAILS
- **Featured**: $FEATURED
- **Orphaned**: $ORPHANED
- **Noise**: $NOISE
- **Coverage**: $REPRESENTED/$TOTAL_EMAILS ($(echo "scale=1; $REPRESENTED * 100 / $TOTAL_EMAILS" | bc)%)
- **Real timestamps**: $([ $HAS_REAL_TIMESTAMPS -eq 1 ] && echo "✅ YES" || echo "❌ NO")

## Issues Found: ${#ISSUES[@]}

$(for i in "${!ISSUES[@]}"; do
  echo "### Issue $((i+1)): ${ISSUES[$i]}"
  echo "**Fix**: ${FIXES[$i]}"
  echo ""
done)

## Digest Content
\`\`\`
$(cat "$ITER_DIR/digest.txt")
\`\`\`

## Session Data
\`\`\`
$(head -5 "$ITER_DIR/session.csv" | column -t -s',')
\`\`\`

## Backend Logs (last 50 lines)
\`\`\`
$(tail -50 "$ITER_DIR/backend.log")
\`\`\`

---

## Next Steps

$(if [ ${#ISSUES[@]} -eq 0 ]; then
  echo "🎉 **ALL VALIDATIONS PASSED!**"
  echo ""
  echo "The digest is working correctly:"
  echo "- ✅ All emails represented"
  echo "- ✅ Real timestamps used"
  echo "- ✅ Age markers present"
  echo "- ✅ Weather enrichment working"
else
  echo "❌ **Issues detected - automated fixes needed**"
  echo ""
  echo "Claude will now apply fixes..."
fi)
EOF

  # Display report
  cat "$REPORT_FILE"

  # Save summary
  echo "$ITERATION,${#ISSUES[@]},$TOTAL_EMAILS,$FEATURED,$ORPHANED,$NOISE,$HAS_REAL_TIMESTAMPS" >> "$ITERATIONS_DIR/summary.csv"

  # ============================================================
  # PHASE 4: Check if done
  # ============================================================
  if [ ${#ISSUES[@]} -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 SUCCESS! All validations passed in iteration $ITERATION"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Final digest:"
    cat "$ITER_DIR/digest.txt"
    echo ""
    echo "📊 Iteration summary: $ITERATIONS_DIR/summary.csv"
    exit 0
  fi

  # ============================================================
  # PHASE 5: Apply automated fixes
  # ============================================================
  echo ""
  echo "🔧 Phase 5: Applying automated fixes..."

  CHANGES_MADE=0

  # Fix: Timestamp missing
  if [[ " ${ISSUES[@]} " =~ " TIMESTAMP_MISSING " ]]; then
    echo "🔧 Fixing: TIMESTAMP_MISSING"

    # Check if logger.js already has the fix
    if ! grep -q 'emailTimestamp:' extension/modules/logger.js; then
      echo "  → Adding emailTimestamp to logger.js"

      # Add emailTimestamp field to logger (after snippet line)
      sed -i.bak '/snippet: email.snippet/a\
      emailTimestamp: email.timestamp, // Gmail'\''s internalDate (milliseconds since epoch)' \
        extension/modules/logger.js

      CHANGES_MADE=1
      echo "  ✅ Updated logger.js"
    else
      echo "  ℹ️  logger.js already has emailTimestamp"
    fi

    # Check if api.py extracts emailTimestamp
    if ! grep -q "item.get('emailTimestamp'" shopq/api.py; then
      echo "  → Updating api.py to extract emailTimestamp"

      sed -i.bak "s/'timestamp': item.get('timestamp'/'timestamp': item.get('emailTimestamp'/g" shopq/api.py

      CHANGES_MADE=1
      echo "  ✅ Updated api.py"
    else
      echo "  ℹ️  api.py already extracts emailTimestamp"
    fi

    if [ $CHANGES_MADE -eq 1 ]; then
      echo ""
      echo "⚠️  CODE CHANGES MADE - Manual steps required:"
      echo "  1. Reload extension: chrome://extensions → ShopQ → 🔄"
      echo "  2. Clear data in Gmail console (F12):"
      echo "     indexedDB.deleteDatabase('ShopQLogger');"
      echo "     await chrome.storage.local.clear();"
      echo "     location.reload();"
      echo "  3. Wait 10 seconds for new digest"
      echo "  4. Re-run this script to continue"
      echo ""

      # Save state for resuming
      echo "$ITERATION" > "$ITERATIONS_DIR/last_iteration.txt"

      exit 2  # Exit code 2 = manual action required
    fi
  fi

  # Fix: No age markers (but have real timestamps)
  if [[ " ${ISSUES[@]} " =~ " NO_AGE_MARKERS " ]] && [ $HAS_REAL_TIMESTAMPS -eq 1 ]; then
    echo "🔧 Fixing: NO_AGE_MARKERS"

    # Check if _entity_to_text has age marker logic
    if ! grep -q 'age_days > 2' shopq/timeline_synthesizer.py; then
      echo "  → Age marker threshold might be too high"
      echo "  ℹ️  Current threshold: $(grep -A 2 'age_days >' shopq/timeline_synthesizer.py | head -1)"

      # Lower threshold from 7 to 2 days
      sed -i.bak 's/elif age_days > 7:/elif age_days > 2:/g' shopq/timeline_synthesizer.py

      CHANGES_MADE=1
      echo "  ✅ Lowered age marker threshold to 2 days"
    fi
  fi

  # If no automated fixes could be applied
  if [ $CHANGES_MADE -eq 0 ]; then
    echo "❌ No automated fixes available for these issues"
    echo ""
    echo "Manual intervention needed. Issues to fix:"
    for i in "${!ISSUES[@]}"; do
      echo "  $((i+1)). ${ISSUES[$i]}: ${FIXES[$i]}"
    done
    echo ""
    echo "Report saved to: $ITER_DIR/ANALYSIS.md"
    exit 1
  fi

  # ============================================================
  # PHASE 6: Prepare for next iteration
  # ============================================================
  echo ""
  echo "✅ Fixes applied for iteration $ITERATION"
  echo "⏭️  Moving to iteration $((ITERATION + 1))..."
  sleep 2

  ITERATION=$((ITERATION + 1))
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "❌ Max iterations ($MAX_ITERATIONS) reached without full success"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Last iteration: $((ITERATION - 1))"
echo "Review: $ITERATIONS_DIR/iteration-$((ITERATION - 1))/ANALYSIS.md"
echo ""
