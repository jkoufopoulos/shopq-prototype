# ShopQ Quality Monitor

**Automated quality analysis for ShopQ classifications and digest formatting**

## Simplified Workflow (Current)

1. **Run ShopQ** → Data saved to GCS automatically
2. **Run quality monitor** → Analyzes with Claude, creates GitHub issues
3. **Fix issues** → Improve classification rules and digest format

No webhooks, no daemons - just simple manual analysis when you want it.

## Quick Start

### Option 1: Manual Analysis (Recommended)

```bash
# After running ShopQ, analyze immediately:
cd scripts/quality-monitor
python3 quality_monitor.py --analyze-now --force
```

### Option 2: Daemon Mode (Optional)

```bash
# Start background daemon (polls GCS every 30 minutes)
./scripts/start-quality-system.sh

# Check status
./scripts/quality-system-status.sh

# Stop daemon
./scripts/stop-quality-system.sh
```

## Configuration

### Required Environment Variables

**IMPORTANT**: Set these environment variables before running the quality monitor:

```bash
# Required for Claude analysis
export ANTHROPIC_API_KEY=sk-ant-api03-...

# Required for creating GitHub issues
export GITHUB_TOKEN=ghp_...
```

**⚠️ SECURITY WARNING**: Never commit tokens to the repository. Always use environment variables.

To get a GitHub token:
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token with `repo` scope
3. Export it: `export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx`

### Optional Configuration

Edit `.env` in project root or set environment variables:

```bash
# Optional (defaults shown)
MIN_EMAILS_FOR_ANALYSIS=1
CHECK_INTERVAL_MINUTES=30
SHOPQ_API_URL=https://shopq-api-488078904670.us-central1.run.app
GITHUB_REPO=jkoufopoulos/mailq-prototype
```

## What It Analyzes

### Classification Issues
- Confidence scores (should be > 0.0)
- Missing fields (from_email, domains)
- Verifier trigger patterns
- Over/under-classification
- Entity extraction coverage

### Digest Format Issues
- Section structure (CRITICAL, COMING UP, etc.)
- Emoji usage (🔴, ⏰, 💡)
- Bullet formatting (• character)
- Email counts in headers
- Content categorization

## Output

Creates GitHub issues with:
- Problem description
- Affected session IDs
- Example data
- Suggested fixes
- `quality` label

---

## Legacy Documentation (Webhook-based System)

> **Note**: The webhook-based system has been simplified. See "Simplified Workflow" above for current usage.

### Old Components

### 1. Quality Monitor Daemon (`quality_monitor.py`)
- Polls GCS every 30 minutes for new sessions
- Triggers analysis when ≥1 new sessions found
- Uses Claude Sonnet 4.5 to identify patterns
- **NEW: LLM-based digest format analysis** - compares actual digest HTML against ideal structure
- Creates GitHub issues automatically

### 2. ~~Webhook Server~~ (Removed)
- ~~Previously listened on port 9000~~
- ~~Received immediate notifications from backend~~
- **Replaced by manual workflow** - no longer needed

### 3. Manual Pipeline (`../run-quality-pipeline.sh`)
- Run complete analysis on-demand
- Useful for testing or immediate results
- Same logic as daemon, just manual trigger

### 4. Digest Format Analyzer (NEW)
- **LLM-based analysis** (`analyze_digest_format_with_llm()`) - Uses Claude to intelligently compare digest against ideal format
- Detects structural issues (numbered list vs categorized sections)
- Identifies misclassification (promotional/past events in featured)
- Checks for missing sections (CRITICAL, TODAY, COMING UP, WORTH KNOWING)
- More sophisticated than pattern matching - understands context and categorization

## Architecture

```
┌─────────────────────────────────────────────────┐
│           ShopQ Backend (Cloud Run)             │
│  - Classifies emails                            │
│  - Generates digests                            │
│  - Tracks sessions                              │
└──────────────┬──────────────────────────────────┘
               │
               │ HTTP API
               │ /api/tracking/sessions
               │
               ▼
┌─────────────────────────────────────────────────┐
│        Quality Monitor Daemon (Local)           │
│  - Polls every 30 minutes                       │
│  - Checks for new sessions                      │
│  - Waits for ≥25 emails                         │
└──────────────┬──────────────────────────────────┘
               │
               │ When threshold met
               │
               ▼
┌─────────────────────────────────────────────────┐
│         Claude API Analysis                     │
│  - Analyzes classification patterns             │
│  - Identifies systematic issues                 │
│  - Assigns severity (high/medium/low)           │
└──────────────┬──────────────────────────────────┘
               │
               │ Issues found
               │
               ▼
┌─────────────────────────────────────────────────┐
│         GitHub Issue Creation                   │
│  - Creates issues for high/medium               │
│  - Labels by severity                           │
│  - Includes evidence & suggested fix            │
└─────────────────────────────────────────────────┘
```

## Automatic Triggers

Analysis runs automatically when:

✅ **Email Volume**: ≥25 emails processed across new sessions
✅ **Digest Generated**: Backend sends webhook (if configured)
✅ **Time-Based**: Every 30 minutes daemon checks for updates

You don't need to do anything - just let it run!

## Configuration

Edit these constants in `quality_monitor.py`:

```python
CHECK_INTERVAL_MINUTES = 30        # Polling frequency
MIN_SESSIONS_FOR_ANALYSIS = 1      # Min sessions before analyzing
MIN_EMAILS_FOR_ANALYSIS = 25       # Min emails before analyzing
ANALYSIS_WINDOW_HOURS = 48         # Look back window
```

Environment variables:

```bash
ANTHROPIC_API_KEY        # Required: Claude API key
GITHUB_TOKEN             # Required: For creating issues
SHOPQ_API_URL            # Optional: Default is production URL
GITHUB_REPO              # Optional: Default is jkoufopoulos/mailq-prototype
QUALITY_WEBHOOK_PORT     # Optional: Default is 9000
MAX_LLM_CALLS_PER_DAY    # Optional: Default is 100 (~$1.50/day budget)
```

**Budget Controls (NEW)**:
- Daily LLM call limit prevents cost overruns
- Default: 100 calls/day (~$1.50 at current pricing)
- Tracked in `llm_usage_tracking` table
- View usage: `sqlite3 quality_monitor.db "SELECT * FROM llm_usage_tracking"`

## Commands

```bash
# Start complete system (daemon + webhook)
./scripts/start-quality-system.sh

# Check status
./scripts/quality-system-status.sh

# Stop system
./scripts/stop-quality-system.sh

# Run analysis manually (don't wait for daemon)
./scripts/run-quality-pipeline.sh

# View logs
tail -f quality_monitor.log
tail -f webhook.log
```

## Database Schema

All state is stored in `quality_monitor.db`:

```sql
-- Tracks which sessions have been analyzed
CREATE TABLE analyzed_sessions (
    session_id TEXT PRIMARY KEY,
    analyzed_at TEXT NOT NULL,
    num_threads INTEGER,
    num_issues INTEGER
);

-- Stores identified quality issues
CREATE TABLE quality_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    severity TEXT NOT NULL,           -- high, medium, low
    category TEXT NOT NULL DEFAULT 'classification',  -- classification, digest_format
    pattern TEXT NOT NULL,             -- Brief description
    evidence TEXT,                     -- Stats/examples
    root_cause TEXT,                   -- Why it's happening
    suggested_fix TEXT,                -- How to fix it
    github_issue_url TEXT,             -- Link to GitHub issue
    resolved BOOLEAN DEFAULT 0
);
```

Query examples:

```bash
# View all high-severity issues
sqlite3 quality_monitor.db \
  "SELECT pattern FROM quality_issues WHERE severity='high'"

# View digest format issues
sqlite3 quality_monitor.db \
  "SELECT severity, pattern FROM quality_issues WHERE category='digest_format'"

# Count issues by category
sqlite3 quality_monitor.db \
  "SELECT category, COUNT(*) FROM quality_issues GROUP BY category"

# Check which sessions were analyzed
sqlite3 quality_monitor.db \
  "SELECT session_id, analyzed_at FROM analyzed_sessions ORDER BY analyzed_at DESC LIMIT 10"

# Count issues by severity
sqlite3 quality_monitor.db \
  "SELECT severity, COUNT(*) FROM quality_issues GROUP BY severity"
```

## Issue Severity Levels

| Severity | Criteria | Example |
|----------|----------|---------|
| 🔴 **High** | Affects >20% OR breaks core feature | "Financial statements all marked critical" |
| 🟡 **Medium** | Affects 10-20% OR degrades UX | "Shipments over-classified as time-sensitive" |
| ⚪ **Low** | Affects <10% OR minor issue | "Empty from_email field for tracking" |

High and medium severity issues are automatically created as GitHub issues.

## What Gets Analyzed?

The quality monitor performs two types of analysis:

### A. Classification Quality Analysis

Claude looks for:

#### 1. Misclassification Patterns
- Wrong importance level (routine → critical)
- Wrong type (receipt → promotion)
- Wrong timing (past events → time-sensitive)

#### 2. Over/Under-Triggering
- Too many criticals (>5% of emails)
- Too few time-sensitives (<5% of emails)
- Verifier never triggering (should be 10-20%)

#### 3. Rule Quality
- Patterns too broad (false positives)
- Patterns too narrow (false negatives)
- Missing context (e.g., "statement" without urgency check)

#### 4. System Health
- Confidence scores not populated
- Entity extraction rate too low
- Tracking fields not filled

#### 5. Prompt Weaknesses
- LLM inconsistencies
- Unclear instructions
- Missing examples for edge cases

### B. Digest Format Analysis (NEW - LLM-based)

Claude analyzes the actual digest HTML and compares it to the ideal format structure:

#### 1. Structure Issues
- ❌ Using numbered list (1. 2. 3.) instead of categorized sections
- ❌ Missing required sections (🚨 CRITICAL, 📦 TODAY, 📅 COMING UP, 💼 WORTH KNOWING)
- ❌ Missing "Everything else" separator (━━━━)

#### 2. Categorization Issues
- ❌ Promotional emails (vote, feedback, surveys) in main list instead of "Everything else"
- ❌ Past events (yesterday, concluded, adjourned) in main list instead of "Everything else"
- ❌ Deliveries not in TODAY section
- ❌ Appointments not in COMING UP section
- ❌ Bills/alerts not in CRITICAL section

#### 3. Priority Issues
- ❌ Routine notifications elevated to main sections
- ❌ Critical items (bills, security) missing from featured areas
- ❌ Incorrect relative importance (should be CRITICAL > TODAY > COMING UP > WORTH KNOWING)

**Example Issues Detected:**
- "Using numbered list instead of categorized sections" (HIGH)
- "Promotional emails featured in main list" (HIGH)
- "Past events featured instead of filtered to Everything else" (HIGH)
- "Security alerts not in CRITICAL section" (MEDIUM)
- "Appointments not grouped in COMING UP section" (MEDIUM)

## Example GitHub Issue

When a problem is detected, an issue like this is created:

```markdown
🔴 [Quality] Financial statement notifications misclassified as critical

## Issue Pattern
Financial statement notifications misclassified as critical

## Evidence
6/10 critical emails are statement notifications (eStatement, Vanguard
statement, Green Dot statement) using patterns like 'statement is ready',
'statement is available'

## Root Cause
Pattern matching on keywords like 'statement is available' and 'your bill'
without context - these are automated monthly notifications, not urgent
bills requiring immediate action

## Suggested Fix
Distinguish between bill/statement availability notifications (routine)
vs. bill due/overdue/payment failed (critical). Add pattern context:
'statement is available/ready' → routine, 'bill due/overdue/payment
failed' → critical

---
*Auto-generated by Quality Monitor*
*Severity: high*
*Created: 2025-11-06T03:46:32*
```

## Backend Integration (Optional)

For instant analysis when digests are generated, add webhook notification to your backend:

```python
# In shopq/api_digest.py
import requests

def notify_quality_monitor(session_id: str, email_count: int):
    try:
        requests.post(
            "http://localhost:9000/webhook/digest-generated",
            json={"session_id": session_id, "email_count": email_count},
            timeout=2
        )
    except:
        pass  # Don't fail digest if webhook fails

# After generating digest
notify_quality_monitor(session_id, len(emails))
```

See [../docs/BACKEND_WEBHOOK_INTEGRATION.md](../docs/BACKEND_WEBHOOK_INTEGRATION.md) for details.

## Testing

```bash
# 1. Start system
./scripts/start-quality-system.sh

# 2. Test webhook manually
curl -X POST http://localhost:9000/webhook/digest-generated \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test_123", "email_count": 30}'

# 3. Check webhook was received
tail -f webhook.log

# 4. Verify analysis was triggered
tail -f quality_monitor.log

# 5. Check database
sqlite3 quality_monitor.db "SELECT * FROM quality_issues ORDER BY created_at DESC LIMIT 3"
```

## Troubleshooting

### Daemon won't start
```bash
# Check if already running
./scripts/quality-system-status.sh

# Check for stale PID files
rm .monitor.pid .webhook.pid

# Try starting again
./scripts/start-quality-system.sh
```

### No sessions found
```bash
# Verify API is reachable
curl https://shopq-api-488078904670.us-central1.run.app/api/tracking/sessions

# Check if backend is tracking sessions
# Open Chrome extension and process emails
```

### Analysis not triggering
```bash
# Check if threshold is met
# Need ≥1 session AND ≥25 emails

# Lower threshold for testing
# Edit MIN_EMAILS_FOR_ANALYSIS in quality_monitor.py

# Force manual analysis
python3 quality_monitor.py --analyze-now
```

### GitHub issues not created
```bash
# Check GITHUB_TOKEN is set
echo $GITHUB_TOKEN

# Test GitHub API access
gh auth status

# Check token has repo permissions
```

## Files

```
quality-monitor/
├── quality_monitor.py          # Main daemon
├── webhook_server.py           # Webhook listener
├── quality_monitor.db          # SQLite database
├── quality_monitor.log         # Daemon logs
├── webhook.log                 # Webhook logs
├── .monitor.pid                # Daemon PID (when running)
├── .webhook.pid                # Webhook PID (when running)
└── README.md                   # This file
```

## Monitoring

View live activity:

```bash
# Monitor daemon
tail -f quality_monitor.log

# Monitor webhooks
tail -f webhook.log

# Both at once
tail -f *.log
```

Check metrics:

```bash
# Overall status
./scripts/quality-system-status.sh

# Database stats
sqlite3 quality_monitor.db <<SQL
SELECT
  severity,
  COUNT(*) as total,
  SUM(CASE WHEN github_issue_url IS NOT NULL THEN 1 ELSE 0 END) as on_github
FROM quality_issues
GROUP BY severity;
SQL
```

## Maintenance

### Weekly Review
```bash
# Check new issues
gh issue list --label quality --label severity-high

# Prioritize and fix in code
# ... make changes ...

# Deploy
./deploy.sh

# System will verify improvements in next analysis
```

### Monthly Cleanup
```bash
# Close resolved issues
gh issue list --label quality --state open | grep "Fixed"
# Manually close or use gh CLI

# Archive old sessions (optional)
sqlite3 quality_monitor.db "DELETE FROM analyzed_sessions WHERE analyzed_at < date('now', '-30 days')"
```

## Support

- **Documentation**: See `../docs/QUALITY_CONTROL_PIPELINE.md`
- **Quick Start**: See `../QUICKSTART_QUALITY.md`
- **Backend Integration**: See `../docs/BACKEND_WEBHOOK_INTEGRATION.md`
- **Logs**: Check `quality_monitor.log` and `webhook.log`
- **Database**: Query `quality_monitor.db` for raw data
