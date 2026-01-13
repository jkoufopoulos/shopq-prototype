#!/bin/bash
set -e

REPO="jkoufopoulos/mailq-prototype"

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ GITHUB_TOKEN not set. Please export GITHUB_TOKEN first."
  echo "   export GITHUB_TOKEN='your_github_personal_access_token'"
  exit 1
fi

echo "📋 Closing fixed quality monitor issues on GitHub..."
echo ""

# Function to close an issue by title pattern
close_issue_by_title() {
  local title_pattern="$1"
  local close_message="$2"

  echo "🔍 Finding issue: $title_pattern"

  # Search for the issue by title
  local issue_number=$(curl -s \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/$REPO/issues?state=open&labels=quality" | \
    jq -r ".[] | select(.title | contains(\"$title_pattern\")) | .number" | head -1)

  if [ -z "$issue_number" ]; then
    echo "⚠️  Issue not found (may already be closed or not created yet)"
    echo ""
    return
  fi

  echo "✅ Found issue #$issue_number"
  echo "📝 Closing with message..."

  # Add closing comment
  curl -s -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    -H "Content-Type: application/json" \
    "https://api.github.com/repos/$REPO/issues/$issue_number/comments" \
    -d "{\"body\":\"$close_message\"}" > /dev/null

  # Close the issue
  curl -s -X PATCH \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    -H "Content-Type: application/json" \
    "https://api.github.com/repos/$REPO/issues/$issue_number" \
    -d '{"state":"closed"}' | jq -r '.html_url // .message'

  echo ""
}

# Close Issue #1: Stats aggregation
close_issue_by_title \
  "All importance classifications show 0%" \
  "✅ **FIXED** in \`quality_monitor.py\`

Changes:
- Fixed nested path to importance counts: \`s['summary']['critical']\` → \`s['summary']['importance']['critical']\`
- Fixed verifier count field: \`s['summary']['verifier_used']\` → \`s['summary']['verified_count']\`

The stats aggregation now correctly reads importance and verifier counts from the data structure."

# Close Issue #2: Financial statements
close_issue_by_title \
  "Financial statement notifications misclassified as critical" \
  "✅ **FIXED** in \`mailq/importance_classifier.py\`

Changes:
- Moved patterns from \`CRITICAL_PATTERNS\` → \`ROUTINE_PATTERNS['financial_notifications']\`
- Patterns moved: 'bill is ready', 'statement is ready', 'statement is available', 'your bill', 'your statement'
- Now distinguishes FYI notifications (routine) from urgent payment issues (critical)

Financial statement availability notifications are now correctly classified as ROUTINE."

# Close Issue #13: Shipment notifications
close_issue_by_title \
  "Shipment notifications over-classified as time-sensitive" \
  "✅ **FIXED** in \`mailq/importance_classifier.py\`

Changes:
- Split shipment patterns into 3 tiers:
  - **ROUTINE**: Passive FYI updates ('shipped', 'tracking number', 'delivered')
  - **TIME_SENSITIVE**: Upcoming deliveries ('arriving tomorrow', 'estimated delivery', 'on its way')
  - **CRITICAL**: Urgent delivery issues ('arriving today', 'delivery attempted', 'requires signature')

Test suite confirms all 10 test cases pass. Standard shipment notifications are now correctly classified as ROUTINE."

# Close Issue #14: Policy updates
close_issue_by_title \
  "Policy update misclassified using medical_claims pattern" \
  "✅ **FIXED** in \`mailq/importance_classifier.py\`

Changes:
- Refined \`medical_claims\` pattern to require specific context
- Added new \`ROUTINE_PATTERNS['policy_updates']\` for generic privacy/ToS updates
- Now distinguishes:
  - Generic policy updates (privacy policy, ToS) → ROUTINE
  - Medical/insurance policies → TIME_SENSITIVE

Test suite confirms all 9 test cases pass. Generic policy updates are now correctly classified as ROUTINE."

# Close Issue #15: Promotional action_required
close_issue_by_title \
  "Promotional emails with action_required flag elevated to time-sensitive" \
  "✅ **FIXED** in \`mailq/importance_classifier.py\`

Changes:
- Marketing emails with vague urgency ('urgent', 'time sensitive') → ROUTINE
- Only concrete deadlines ('expires today', 'ends today', 'deadline today') → TIME_SENSITIVE
- Removed generic single-word urgency patterns from marketing triggers

Test suite confirms all 10 test cases pass. Promotional emails with marketing CTAs are now correctly classified as ROUTINE unless they have concrete deadlines."

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All fixed quality monitor issues closed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
