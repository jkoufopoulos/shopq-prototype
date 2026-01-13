#!/bin/bash

# Claude Code Iteration Script
# Runs test, captures evidence, and provides structured feedback

set -e

ITERATION=${1:-1}
MAX_ITERATIONS=${2:-10}

echo "🤖 Claude Code Iteration Script"
echo "================================"
echo "Iteration: $ITERATION / $MAX_ITERATIONS"
echo ""

# Create iteration directory
ITERATION_DIR="test-results/claude-iterations/iter-$ITERATION"
mkdir -p "$ITERATION_DIR"

# Run the digest quality test
echo "▶️  Running digest quality test..."
./test-digest-quality.sh > "$ITERATION_DIR/test-output.log" 2>&1 || true

# Find latest digest report
LATEST_DIGEST=$(ls -td test-results/digest-* 2>/dev/null | head -1)

if [ -n "$LATEST_DIGEST" ]; then
  # Copy all evidence to iteration directory
  cp -r "$LATEST_DIGEST"/* "$ITERATION_DIR/"

  echo ""
  echo "📊 ITERATION $ITERATION RESULTS"
  echo "=============================="
  echo ""

  # Parse the report
  if [ -f "$ITERATION_DIR/report.json" ]; then
    TEMPORAL_AWARE=$(jq -r '.expectations.temporalAwarenessPresent' "$ITERATION_DIR/report.json")
    ALL_EMAILS=$(jq -r '.expectations.allEmailsRepresented' "$ITERATION_DIR/report.json")
    AGE_MARKERS=$(jq -r '.expectations.ageMarkersFound | length' "$ITERATION_DIR/report.json")
    MISSING_COUNT=$(jq -r '.expectations.missingEmails | length' "$ITERATION_DIR/report.json")

    echo "✅ Temporal Awareness: $TEMPORAL_AWARE"
    echo "✅ All Emails Represented: $ALL_EMAILS"
    echo "📅 Age Markers Found: $AGE_MARKERS"
    echo "❌ Missing Emails: $MISSING_COUNT"
    echo ""

    # Check if we're done
    if [ "$TEMPORAL_AWARE" = "true" ] && [ "$ALL_EMAILS" = "true" ]; then
      echo "🎉 SUCCESS! All tests passed!"
      echo ""
      echo "Final digest:"
      cat "$ITERATION_DIR/digest-content.txt"
      exit 0
    fi

    # Generate Claude-friendly analysis
    cat > "$ITERATION_DIR/ANALYSIS_FOR_CLAUDE.md" << EOF
# Iteration $ITERATION Analysis

## Test Results
- **Temporal Awareness**: $TEMPORAL_AWARE
- **All Emails Represented**: $ALL_EMAILS
- **Age Markers Found**: $AGE_MARKERS
- **Missing Emails**: $MISSING_COUNT

## Evidence Files
1. **Screenshots**:
   - \`01-gmail-loaded.png\` - Gmail interface loaded
   - \`02-digest-opened.png\` - Digest email opened
   - \`ERROR.png\` - Error state (if any)

2. **Content**:
   - \`digest-content.txt\` - Plain text digest
   - \`digest-content.html\` - HTML digest
   - \`tracking-data.json\` - Backend tracking data

3. **Reports**:
   - \`report.json\` - Full structured report
   - \`summary.md\` - Human-readable summary

## Current Digest
\`\`\`
$(cat "$ITERATION_DIR/digest-content.txt")
\`\`\`

## Issues Detected

### Missing Temporal Awareness
$(if [ "$TEMPORAL_AWARE" = "false" ]; then
  echo "❌ No age markers found in digest"
  echo ""
  echo "**Expected**: Emails should show age context like \"[5 days old]\""
  echo "**Actual**: All emails presented as if current"
  echo ""
  echo "**Debug Steps**:"
  echo "1. Check if \`emailTimestamp\` is in logged data"
  echo "2. Verify backend receives timestamps"
  echo "3. Check entity extractor timestamp parsing"
  echo "4. Verify timeline synthesizer age marker logic"
else
  echo "✅ Temporal awareness working"
fi)

### Missing Emails in Digest
$(if [ "$ALL_EMAILS" = "false" ]; then
  echo "❌ Some emails not represented in digest"
  echo ""
  jq -r '.expectations.missingEmails[] | "- \(.subject) (\(.importance), entity: \(.entity_extracted))"' "$ITERATION_DIR/report.json"
  echo ""
  echo "**Debug Steps**:"
  echo "1. Check why entities weren't extracted"
  echo "2. Verify timeline selection logic"
  echo "3. Check noise summary inclusion"
else
  echo "✅ All emails represented"
fi)

## Backend Logs
Check \`/tmp/mailq-backend.log\` for:
- Timestamp parsing errors
- Entity extraction failures
- Timeline synthesis decisions

## Recommended Fixes

### If Temporal Awareness Missing:
1. Verify extension logs timestamp: \`email.timestamp\` in \`logger.js\`
2. Verify backend receives it: Check API logs for "📅 Email timestamp"
3. Verify entity gets timestamp: Check \`entity_extractor.py\` parsing
4. Verify age markers added: Check \`timeline_synthesizer.py\` \`_entity_to_text()\`

### If Emails Missing:
1. Check entity extraction patterns in \`entity_extractor.py\`
2. Check timeline selection in \`timeline_synthesizer.py\`
3. Verify importance classification in \`importance_classifier.py\`

## Next Iteration
Run: \`./claude-iterate-digest.sh $((ITERATION + 1)) $MAX_ITERATIONS\`
EOF

    echo "📝 Analysis generated for Claude"
    echo ""
    cat "$ITERATION_DIR/ANALYSIS_FOR_CLAUDE.md"
    echo ""

    # Provide next steps
    if [ $ITERATION -lt $MAX_ITERATIONS ]; then
      echo ""
      echo "🔄 NEXT STEPS"
      echo "============"
      echo "1. Review: cat $ITERATION_DIR/ANALYSIS_FOR_CLAUDE.md"
      echo "2. View screenshots: open $ITERATION_DIR/*.png"
      echo "3. Check backend logs: tail -50 /tmp/mailq-backend.log"
      echo "4. Make fixes based on analysis"
      echo "5. Re-run: ./claude-iterate-digest.sh $((ITERATION + 1)) $MAX_ITERATIONS"
      echo ""
    else
      echo ""
      echo "❌ Max iterations ($MAX_ITERATIONS) reached without success"
      echo ""
    fi

  fi
else
  echo "❌ No digest report found"
  exit 1
fi
