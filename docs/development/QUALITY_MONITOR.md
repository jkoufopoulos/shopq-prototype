# Quality Monitor - AI-Powered Classification Analysis

Continuous background monitoring of ShopQ classification quality with automated issue detection and GitHub integration.

## What It Does

The Quality Monitor runs 24/7 and:

1. **Checks for new digest sessions** every 30 minutes
2. **Accumulates data** until it has enough sessions to analyze (default: 5)
3. **Analyzes with Claude** to detect systematic issues
4. **Auto-creates GitHub issues** for high/medium severity problems
5. **Tracks analysis history** in local SQLite database

## Quick Start

### 1. Setup Environment

```bash
# Copy config template
cp .env.quality-monitor .env

# Edit with your keys
nano .env
```

Add:
```bash
ANTHROPIC_API_KEY=sk-ant-...     # Get from https://console.anthropic.com
GITHUB_TOKEN=ghp_...             # Get from https://github.com/settings/tokens (needs 'repo' scope)
```

### 2. Run Monitor

**Option A: Foreground (testing)**
```bash
./run-quality-monitor.sh --analyze-now    # One-time analysis
./run-quality-monitor.sh                  # Run daemon in foreground
```

**Option B: Docker (recommended)**
```bash
docker-compose -f docker-compose.quality-monitor.yml up -d
docker-compose -f docker-compose.quality-monitor.yml logs -f
```

**Option C: Systemd (Linux)**
```bash
sudo cp quality-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable quality-monitor
sudo systemctl start quality-monitor
sudo systemctl status quality-monitor
```

### 3. Check Logs

```bash
tail -f quality_monitor.log
```

## Architecture

### Complete Quality Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                   ShopQ Quality Pipeline                     │
└─────────────────────────────────────────────────────────────┘

  Digest Sessions (Cloud Run API)
           ↓
  ┌────────────────────────────┐
  │   Quality Monitor Daemon   │  ← Checks every 30 min
  │   quality_monitor.py       │
  └────────────────────────────┘
           ↓
  Fetch session details via API
  (/api/tracking/sessions)
           ↓
  ┌────────────────────────────┐
  │  Claude Analysis (Sonnet)  │  ← Identifies patterns
  │  Analyzes classifications  │
  └────────────────────────────┘
           ↓
  ┌────────────────────────────┐
  │  Quality Issues Database   │
  │  quality_monitor.db        │
  └────────────────────────────┘
           ↓
  ┌────────────────────────────┐
  │   GitHub Issue Creation    │  ← High/medium severity
  │   (automated)              │
  └────────────────────────────┘
```

### Components

1. **Quality Monitor Daemon** (`scripts/quality-monitor/quality_monitor.py`)
   - Polls API every 30 minutes
   - Accumulates sessions until threshold met
   - Triggers both Claude classification analysis AND digest format analysis

2. **Claude AI Analysis** (Sonnet 4.5)
   - Analyzes classification patterns
   - Identifies systematic issues
   - Provides evidence and root cause
   - Suggests concrete fixes

3. **Digest Format Analyzer** (`scripts/quality-monitor/digest_format_analyzer.py`)
   - Parses actual digest HTML structure
   - Compares against ideal format (4 sections with emojis)
   - Detects structure issues (numbered list vs sections)
   - Identifies noise in featured items (promotional, past events)
   - Python-based (no LLM required)

4. **SQLite Database** (`quality_monitor.db`)
   - Stores analyzed sessions
   - Tracks quality issues (both classification and format)
   - Maintains analysis history

5. **GitHub Integration**
   - Auto-creates issues for high/medium severity
   - Adds proper labels and formatting
   - Includes category (classification vs digest_format)
   - Links to specific email IDs

6. **Webhook Server** (Optional - `scripts/quality-monitor/webhook_server.py`)
   - Receives immediate notifications on digest generation
   - Triggers instant analysis
   - Faster feedback loop than 30-minute polling
   - Runs on port 9000 (configurable via QUALITY_WEBHOOK_PORT)

## How It Works

### Detection Flow

```
Every 30 minutes:
  ├─ Check /api/tracking/sessions for new data
  ├─ Wait until ≥5 new sessions accumulated
  ├─ Fetch detailed session reports (including digest HTML)
  │
  ├─ CLASSIFICATION ANALYSIS:
  │   ├─ Send to Claude API for analysis
  │   └─ Claude returns structured issues:
  │       {
  │         "severity": "high|medium|low",
  │         "category": "classification",
  │         "pattern": "Newsletters marked as critical",
  │         "evidence": "3/10 newsletters: X, Y, Z",
  │         "root_cause": "Pattern too broad",
  │         "suggested_fix": "Add unsubscribe link check"
  │       }
  │
  ├─ DIGEST FORMAT ANALYSIS:
  │   ├─ Parse digest HTML structure
  │   ├─ Extract sections/items
  │   └─ Return format issues:
  │       {
  │         "severity": "high|medium|low",
  │         "category": "digest_format",
  │         "pattern": "Missing categorized sections",
  │         "evidence": "Using numbered list instead of sections",
  │         "root_cause": "Digest generator not using sectioned format",
  │         "suggested_fix": "Update digest template to use 4 emoji sections"
  │       }
  │
  ├─ Combine all issues (classification + format)
  ├─ Store in quality_monitor.db
  ├─ Create GitHub issues (if high/medium severity)
  └─ Sleep 30 minutes
```

### What the System Analyzes

#### Classification Analysis (Claude AI)

- **Misclassification patterns** - Types of emails consistently miscategorized
- **Over/under-triggering** - Critical/time-sensitive being over/under-used
- **Rule quality** - Pattern-matching rules too broad/narrow
- **Edge cases** - Emails falling through the cracks
- **Prompt weaknesses** - LLM classification improvements needed
- **Entity extraction gaps** - Important entities being missed

#### Digest Format Analysis (Python)

- **Structure issues** - Missing sections, using numbered list instead of categorized sections
- **Categorization issues** - Promotional/noise items in featured area, past events not filtered
- **Priority issues** - Critical items missing, routine items elevated
- **Template compliance** - Adherence to ideal format (🚨 CRITICAL, 📦 TODAY, 📅 COMING UP, 💼 WORTH KNOWING)

### Issue Severity

- **High** 🔴 - Affects >25% of a category, immediate action needed
- **Medium** 🟡 - Affects 10-25%, should fix soon
- **Low** ⚪ - Affects <10%, nice to have

### Example Issues Detected

#### Classification Issues

```
🔴 [HIGH] Newsletters marked as critical
Evidence: 7/20 newsletters classified as critical (35%)
Root Cause: Pattern "statement is ready" matches newsletter footers
Suggested Fix: Add sender domain check for known newsletters

🟡 [MEDIUM] Package delivery notifications marked routine
Evidence: 4/15 delivery notifications marked routine (27%)
Root Cause: "has been delivered" not in critical patterns
Suggested Fix: Add "has been delivered" to time_sensitive patterns
```

#### Digest Format Issues

```
🔴 [HIGH] Missing categorized sections (CRITICAL, TODAY, COMING UP, WORTH KNOWING)
Evidence: Digest uses numbered list format instead of categorized sections
Root Cause: Digest generator not using sectioned format template
Suggested Fix: Update digest generation to use categorized sections with emojis

🟡 [MEDIUM] Promotional/noise items featured in main digest
Evidence: Found 2 promotional items: "Time to vote", "Last chance feedback"
Root Cause: Importance classifier elevating promotional content
Suggested Fix: Add promotional keyword filters to importance classifier

🟡 [MEDIUM] Past/concluded events featured in digest
Evidence: Found 2 past events: "from yesterday", "has adjourned"
Root Cause: Time-decay filter not removing expired events
Suggested Fix: Strengthen Phase 1 time-decay filter to remove past dates
```

## Configuration

Edit `quality_monitor.py` constants:

```python
CHECK_INTERVAL_MINUTES = 30        # How often to check
MIN_SESSIONS_FOR_ANALYSIS = 5      # Min sessions before analyzing
ANALYSIS_WINDOW_HOURS = 24         # Analyze last N hours
```

Or set via environment:
```bash
export CHECK_INTERVAL_MINUTES=60
export MIN_SESSIONS_FOR_ANALYSIS=10
```

## Database Schema

### `quality_monitor.db`

**analyzed_sessions** - Tracks which sessions have been analyzed
```sql
session_id TEXT PRIMARY KEY
analyzed_at TEXT
num_threads INTEGER
num_issues INTEGER
```

**quality_issues** - Stores detected issues
```sql
id INTEGER PRIMARY KEY
created_at TEXT
severity TEXT (high|medium|low)
category TEXT (classification|digest_format)
pattern TEXT
evidence TEXT
root_cause TEXT
suggested_fix TEXT
github_issue_url TEXT
resolved BOOLEAN
```

Query examples:
```bash
# View all format issues
sqlite3 quality_monitor.db "SELECT * FROM quality_issues WHERE category='digest_format' ORDER BY created_at DESC"

# View all classification issues
sqlite3 quality_monitor.db "SELECT * FROM quality_issues WHERE category='classification' ORDER BY created_at DESC"

# Count issues by category
sqlite3 quality_monitor.db "SELECT category, COUNT(*) FROM quality_issues GROUP BY category"
```

## GitHub Integration

Issues are auto-created with:
- **Title**: `🔴 [Quality] Pattern description`
- **Body**: Evidence, root cause, suggested fix
- **Labels**: `quality`, `severity-{high|medium|low}`, `auto-generated`

Example: https://github.com/justinkoufopoulos/mailq-prototype/issues/123

## Monitoring the Monitor

```bash
# Check if running
ps aux | grep quality_monitor

# View recent analysis
sqlite3 quality_monitor.db "SELECT * FROM quality_issues ORDER BY created_at DESC LIMIT 5"

# Check logs
tail -f quality_monitor.log

# Docker logs
docker logs -f mailq-quality-monitor
```

## Cost Estimate

- **Claude API**: ~$0.01 per analysis (every 5 sessions)
- **Frequency**: ~48 analyses/day (if running digest every 30min)
- **Monthly cost**: ~$15/month

Can adjust `MIN_SESSIONS_FOR_ANALYSIS` to reduce frequency.

## Troubleshooting

### No issues being created

```bash
# Check if sessions are being tracked
curl https://shopq-api-*.run.app/api/tracking/sessions

# Check state DB
sqlite3 quality_monitor.db "SELECT * FROM analyzed_sessions"

# Run manual analysis
./run-quality-monitor.sh --analyze-now
```

### GitHub issues not creating

```bash
# Test GitHub token
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# Check logs for errors
grep "GitHub" quality_monitor.log
```

### Claude API errors

```bash
# Test API key
export ANTHROPIC_API_KEY=sk-ant-...
python -c "import anthropic; print(anthropic.Anthropic().messages.create(model='claude-sonnet-4-5-20250929', max_tokens=10, messages=[{'role':'user','content':'test'}]))"
```

## Stopping the Monitor

```bash
# Docker
docker-compose -f docker-compose.quality-monitor.yml down

# Systemd
sudo systemctl stop quality-monitor

# Foreground (Ctrl+C)
```

## Testing Digest Format Analysis

Test the format analyzer with a sample digest:

```bash
cd scripts/quality-monitor

# Create test digest HTML file
cat > test_digest.html <<'EOF'
<html>
<body>
<h2>Your Inbox - Saturday, November 01 at 04:00 PM</h2>
1. Security alert
2. Time to vote, make every share count
3. Meeting from yesterday
<p>Plus, there are 65 routine notifications.</p>
</body>
</html>
EOF

# Run analyzer
python3 digest_format_analyzer.py test_digest.html

# Or use the Nov 1 test
python3 test_nov1_digest.py
```

Expected output:
```
Found 4 format issues:

1. [HIGH] Missing categorized sections (CRITICAL, TODAY, COMING UP, WORTH KNOWING)
2. [HIGH] Using numbered list instead of categorized sections
3. [MEDIUM] Promotional/noise items featured in main digest
4. [MEDIUM] Past/concluded events featured in digest
```

## Next Steps

1. **Run for a week** - Let it collect data and create issues
2. **Review issues** - Check if suggestions are actionable
3. **Tune thresholds** - Adjust severity thresholds if too noisy
4. **Implement fixes** - Apply suggested mitigations
5. **Mark resolved** - Update `quality_issues.resolved = 1`

## Advanced: Self-Healing

Future enhancement: Auto-apply low-risk fixes
```python
if issue['severity'] == 'low' and issue['type'] == 'add_rule':
    # Auto-add rule to database
    # Create PR for review
    pass
```

---

## Webhook Integration (Optional)

For **immediate analysis** instead of waiting for 30-minute polling, integrate webhook notifications into your backend.

### Backend Integration

Add to your digest generation endpoint (e.g., `shopq/api_digest.py`):

```python
import requests
import os

def notify_quality_monitor(session_id: str, email_count: int):
    """Notify quality monitor that a digest was generated"""
    webhook_url = os.getenv(
        "QUALITY_WEBHOOK_URL",
        "http://localhost:9000/webhook/digest-generated"
    )

    try:
        requests.post(
            webhook_url,
            json={
                "session_id": session_id,
                "email_count": email_count
            },
            timeout=2
        )
    except Exception as e:
        # Don't fail digest generation if webhook fails
        print(f"Quality webhook notification failed: {e}")

# Call after digest generation
notify_quality_monitor(session_id, len(processed_emails))
```

### Environment Variables

```bash
# Production
export QUALITY_WEBHOOK_URL=http://your-server:9000/webhook/digest-generated

# Local development
export QUALITY_WEBHOOK_URL=http://localhost:9000/webhook/digest-generated
```

### Testing Webhook

```bash
# 1. Start quality system (includes webhook server)
./scripts/start-quality-system.sh

# 2. Test webhook manually
curl -X POST http://localhost:9000/webhook/digest-generated \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test_20251106_120000", "email_count": 30}'

# 3. Check webhook logs
tail -f scripts/quality-monitor/webhook.log

# 4. Verify analysis was triggered
tail -f scripts/quality-monitor/quality_monitor.log
```

**Benefits**: Immediate analysis vs 30-minute polling delay, event-driven architecture, more efficient.

---

**Questions?** Check logs at `quality_monitor.log`
