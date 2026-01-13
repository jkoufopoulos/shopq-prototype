---
description: Show prioritized quality issues from GitHub created by automated analysis
---

Run AI quality analysis on your most recent organize session and show prioritized GitHub issues.

**Desired workflow:**
1. Click ShopQ icon (organize emails)
2. Type `/analyze-quality`
3. View prioritized list of issues from most recent run

**What happens:**
- Fetches latest session data (5-250 emails)
- Runs Claude AI analysis on classifications + digest
- Creates GitHub issues for bugs found
- Shows you prioritized list of what to fix

---

## Show Latest Quality Analysis Results

```bash
#!/bin/bash
set -e

# Load environment variables
source scripts/load-env.sh 2>/dev/null || source ./scripts/load-env.sh 2>/dev/null || true

echo "📊 ShopQ Quality Control Pipeline Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get latest session info
SHOPQ_API_URL="${SHOPQ_API_URL:-https://shopq-api-488078904670.us-central1.run.app}"
SESSION_DATA=$(curl -s "${SHOPQ_API_URL}/api/tracking/latest" 2>/dev/null)

if [ $? -eq 0 ]; then
  SESSION_ID=$(echo "$SESSION_DATA" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('session_id', 'unknown'))" 2>/dev/null)
  EMAIL_COUNT=$(echo "$SESSION_DATA" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('summary', {}).get('total_threads', 0))" 2>/dev/null)

  echo "✅ Latest session: $SESSION_ID ($EMAIL_COUNT emails)"
else
  echo "⚠️  Could not fetch latest session from API"
  SESSION_ID="unknown"
fi

echo ""

# Check if quality monitor daemon is running
if ps aux | grep -v grep | grep "quality_monitor.py --daemon" > /dev/null; then
  echo "✅ Quality monitor daemon: RUNNING"
else
  echo "❌ Quality monitor daemon: NOT RUNNING"
  echo "   Start with: ./scripts/start-quality-system.sh"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐛 OPEN QUALITY ISSUES (Prioritized)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get issues from GitHub using curl
# Read token directly from .env to avoid bash variable interpolation issues
GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' .env | cut -d'=' -f2 | tr -d ' \n\r')
export ISSUES_JSON=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/jkoufopoulos/mailq-prototype/issues?state=open&labels=quality&per_page=50&sort=created&direction=desc")

python3 << 'PYTHON_EOF'
import json
import sys
import os

# Get JSON from environment (passed via bash)
issues_json = os.environ.get('ISSUES_JSON', '[]')

try:
    issues = json.loads(issues_json)

    # Check if we got an error response
    if isinstance(issues, dict) and 'message' in issues:
        print(f"⚠️  GitHub API error: {issues['message']}")
        print("   Check GITHUB_TOKEN in .env file")
        sys.exit(1)

    if not isinstance(issues, list) or len(issues) == 0:
        print("✅ No open quality issues!")
        print("   Your classifications are looking good.")
        print("")
    else:
        print(f"📊 Found {len(issues)} open quality issue(s)")
        print("")

        # Parse and display issues
        for i, issue in enumerate(issues[:15], 1):
            title = issue['title']
            body = issue.get('body', '')
            url = issue['html_url']
            created = issue['created_at']

            # Extract severity from labels
            severity = 'medium'
            for label in issue.get('labels', []):
                label_name = label['name'].lower()
                if 'high' in label_name or 'critical' in label_name:
                    severity = 'high'
                    break
                elif 'low' in label_name:
                    severity = 'low'

            emoji = "🔴" if severity == "high" else "🟡" if severity == "medium" else "🔵"

            print(f"{i}. {emoji} [{severity.upper()}] {title}")

            # Extract evidence and fix from body if present
            if body:
                lines = body.split('\n')
                for j, line in enumerate(lines):
                    if 'Evidence:' in line or 'Example:' in line:
                        evidence = lines[j+1] if j+1 < len(lines) else ''
                        if evidence.strip():
                            evidence_short = evidence[:150] + "..." if len(evidence) > 150 else evidence
                            print(f"   Evidence: {evidence_short.strip()}")
                    if 'Suggested Fix:' in line or 'Fix:' in line:
                        fix = lines[j+1] if j+1 < len(lines) else ''
                        if fix.strip():
                            fix_short = fix[:150] + "..." if len(fix) > 150 else fix
                            print(f"   💡 Fix: {fix_short.strip()}")

            print(f"   🔗 {url}")
            print(f"   📅 Created: {created[:10]}")
            print("")

except json.JSONDecodeError as e:
    print(f"⚠️  Failed to parse GitHub response: {e}")
    print("   This may indicate an API issue")
    print("")
except Exception as e:
    print(f"⚠️  Error processing GitHub issues: {e}")
    print("")

PYTHON_EOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Quick Actions:"
echo "   • View all issues: https://github.com/jkoufopoulos/mailq-prototype/issues?q=is%3Aissue+label%3Aquality+is%3Aopen"
echo "   • Monitor logs:    tail -f scripts/quality-monitor/quality_monitor.log"
echo "   • System status:   ./scripts/quality-system-status.sh"
echo ""
```
