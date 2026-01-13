# MailQ Quality Control Workflow

**Complete guide to running quality checks on email classification and digests**

## System Overview

The MailQ QC system has three modes of operation:

1. **Automatic Daemon** (Runs 24/7) - Polls every 30 minutes and analyzes when ≥25 emails processed
2. **Webhook Notifications** (Real-time) - Backend sends notification immediately after digest generation
3. **Manual Force-Run** (On-demand) - You trigger analysis of all new sessions regardless of thresholds

## Quick Start: One-Click Quality Check

After clicking "Organize" in the MailQ extension:

```bash
./scripts/force-quality-check.sh
```

This will:
- ✅ Analyze ALL new digest sessions (bypasses 25-email threshold)
- ✅ Run Claude AI on both classification quality AND digest format
- ✅ Create GitHub issues automatically for high/medium severity problems
- ✅ Show you the top 10 issues immediately

**Result**: Within 30-60 seconds you'll see:
- Classification issues (wrong importance levels, missing entities, etc.)
- Digest format issues (missing sections, miscategorized emails, etc.)
- Direct links to GitHub issues for each problem

## System Status

Check what's running:

```bash
./scripts/quality-system-status.sh
```

You'll see:
- Daemon status (should be ✅ RUNNING)
- Webhook status (should be ✅ RUNNING)
- Issues breakdown by severity
- Recent activity logs

## Complete Workflow

### 1. Generate a Digest (MailQ Extension)

1. Open Gmail in Chrome
2. Click the MailQ extension icon
3. Click "Organize" button
4. Wait for digest to be generated (~10-30 seconds)

**What happens behind the scenes:**
- Backend processes emails through classifier
- Digest HTML is generated
- Tracking session is stored in database
- Webhook notification sent to port 9000 (optional)

### 2. Run Quality Analysis

**Option A: Wait for automatic analysis** (30 min polling interval)
```bash
# Nothing to do - daemon will pick it up automatically
```

**Option B: Force immediate analysis** (recommended)
```bash
./scripts/force-quality-check.sh
```

**Option C: Run full pipeline with digest comparison** (detailed)
```bash
./scripts/run-quality-pipeline.sh
```

### 3. View Quality Issues

**In terminal:**
```bash
# Show all unresolved issues
./scripts/view-quality-issues.sh

# Show statistics
./scripts/view-quality-issues.sh --stats

# Show all issues (including resolved)
./scripts/view-quality-issues.sh --all
```

**On GitHub:**
```bash
# View in browser (if gh CLI installed)
gh issue list --label quality

# Or visit directly
open https://github.com/jkoufopoulos/mailq-prototype/issues?q=is%3Aissue+is%3Aopen+label%3Aquality
```

**In database:**
```bash
# Query raw data
sqlite3 scripts/quality-monitor/quality_monitor.db \
  "SELECT severity, pattern FROM quality_issues WHERE resolved = 0"
```

### 4. Fix Issues

For each high-severity issue:

1. **Read the issue details** (pattern, evidence, root cause, suggested fix)
2. **Make code changes** in the appropriate module:
   - Classification issues → `mailq/vertex_gemini_classifier.py`, rules, or prompts
   - Digest format issues → `mailq/narrative_generator.py` or templates
3. **Test locally** by running another digest
4. **Run QC again** to verify the fix worked
5. **Deploy to Cloud Run** once confirmed
6. **Mark issue as resolved** on GitHub

### 5. Monitor Improvements

After deploying fixes:

```bash
# Generate new digest with the MailQ extension
# Then run QC again
./scripts/force-quality-check.sh

# Compare issue counts before/after
./scripts/view-quality-issues.sh --stats
```

You should see:
- ✅ Previously identified issues no longer appear
- ✅ Issue counts decrease over time
- ✅ Digest quality improves

## Architecture

```
┌─────────────────────────────────────────────────┐
│         MailQ Chrome Extension                  │
│  User clicks "Organize" → sends emails to API   │
└──────────────┬──────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────┐
│          Backend API (Cloud Run)                │
│  - Classifies emails (Vertex Gemini)            │
│  - Generates digest (narrative_generator.py)    │
│  - Stores tracking session                      │
│  - Sends webhook → http://localhost:9000        │
└──────────────┬──────────────────────────────────┘
               │
               ├──────────────┐
               ▼              ▼
       [Daemon Polling]  [Webhook Listener]
       Every 30 min      Port 9000 (instant)
               │              │
               └──────┬───────┘
                      ▼
       ┌──────────────────────────────┐
       │  Quality Monitor             │
       │  - Fetches session data      │
       │  - Runs Claude AI analysis   │
       │    • Classification quality  │
       │    • Digest format analysis  │
       │  - Stores issues in DB       │
       └──────────────┬───────────────┘
                      ▼
       ┌──────────────────────────────┐
       │  GitHub Issue Creation       │
       │  - High/medium severity only │
       │  - Includes evidence + fix   │
       │  - Auto-labeled              │
       └──────────────────────────────┘
```

## Configuration

All settings are in `.env` file at project root:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...        # For Claude analysis
GITHUB_TOKEN=ghp_...                 # For creating issues

# Optional
MAILQ_API_URL=https://...            # Backend API endpoint
CHECK_INTERVAL_MINUTES=30            # Daemon polling frequency
MIN_EMAILS_FOR_ANALYSIS=25           # Threshold before analysis
MAX_LLM_CALLS_PER_DAY=100           # Budget limit (~$1.50/day)
```

## What Gets Analyzed

### A. Classification Quality

Claude examines:
1. **Misclassification patterns** - Wrong importance levels, types, or timing
2. **Over/under-triggering** - Too many criticals, too few time-sensitives
3. **Rule quality** - Patterns too broad/narrow, missing context
4. **System health** - Confidence scores, entity extraction rates
5. **Prompt weaknesses** - LLM inconsistencies, unclear instructions

### B. Digest Format Quality (LLM-based)

Claude compares actual digest HTML against ideal structure:

1. **Structure issues**
   - Missing sections (CRITICAL, TODAY, COMING UP, WORTH KNOWING)
   - Using numbered list instead of categorized sections
   - Missing "Everything else" separator

2. **Categorization issues**
   - Promotional emails featured instead of filtered
   - Past events in main list instead of "Everything else"
   - Deliveries not in TODAY
   - Appointments not in COMING UP

3. **Priority issues**
   - Routine notifications elevated to main sections
   - Critical items missing from featured areas

## Issue Severity Levels

| Severity | Criteria | GitHub? | Example |
|----------|----------|---------|---------|
| 🔴 **High** | Affects >20% OR breaks core feature | ✅ Yes | "Bills not in CRITICAL section" |
| 🟡 **Medium** | Affects 10-20% OR degrades UX | ✅ Yes | "Missing section count indicators" |
| ⚪ **Low** | Affects <10% OR minor issue | ❌ No | "Empty from_email field" |

## Troubleshooting

### "No new sessions to analyze"
**Solution**: Generate a digest first using the MailQ extension, then run QC.

### "ANTHROPIC_API_KEY not set"
**Solution**: Add to `.env` file:
```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
```

### "GITHUB_TOKEN not set - GitHub issues will not be created"
**Solution**: Add to `.env` file:
```bash
echo 'GITHUB_TOKEN=ghp_...' >> .env
```
Then restart the quality system:
```bash
./scripts/stop-quality-system.sh
./scripts/start-quality-system.sh
```

### "Daily LLM budget limit reached"
**Solution**: Wait until tomorrow OR increase limit:
```bash
echo 'MAX_LLM_CALLS_PER_DAY=200' >> .env  # ~$3/day
```

### Daemon not running
**Solution**: Start the quality system:
```bash
./scripts/start-quality-system.sh
```

### Issues found but not on GitHub
**Solution**: Check if GITHUB_TOKEN was loaded when daemon started. Restart:
```bash
./scripts/stop-quality-system.sh
./scripts/start-quality-system.sh
```

## Maintenance

### Daily
- ✅ No action needed - daemon runs automatically
- 🔔 Review GitHub notifications for new quality issues

### Weekly
```bash
# Check high-severity issues
./scripts/view-quality-issues.sh | grep "🔴"

# Prioritize and fix in code
# Deploy fixes
./deploy.sh

# Verify improvements
./scripts/force-quality-check.sh
```

### Monthly
```bash
# Close resolved issues on GitHub
# Archive old data (optional)
sqlite3 scripts/quality-monitor/quality_monitor.db \
  "DELETE FROM analyzed_sessions WHERE analyzed_at < date('now', '-90 days')"
```

## Files & Directories

```
scripts/
├── force-quality-check.sh           # ⚡ One-click QC (use this!)
├── start-quality-system.sh          # Start daemon + webhook
├── stop-quality-system.sh           # Stop daemon + webhook
├── quality-system-status.sh         # Check system status
├── run-quality-pipeline.sh          # Full pipeline with reports
├── view-quality-issues.sh           # View issues in terminal
└── quality-monitor/
    ├── quality_monitor.py           # Main daemon
    ├── webhook_server.py            # Webhook listener
    ├── quality_monitor.db           # Issues database
    ├── quality_monitor.log          # Daemon logs
    ├── webhook.log                  # Webhook logs
    └── prompts/
        └── digest_format_analysis.txt  # LLM prompt for digest analysis
```

## Cost Estimates

Based on Claude Sonnet 4.5 pricing:

| Activity | Cost per Run | Frequency | Monthly Cost |
|----------|--------------|-----------|--------------|
| Classification analysis | ~$0.01-0.02 | Per 25 emails | ~$3-6 |
| Digest format analysis | ~$0.01-0.03 | Per digest | ~$2-5 |
| **Total** | - | Automatic | **~$5-11/month** |

Budget controls:
- `MAX_LLM_CALLS_PER_DAY=100` limits to ~$1.50/day
- View usage: `sqlite3 quality_monitor.db "SELECT * FROM llm_usage_tracking"`

## Support

- **Documentation**: See `scripts/quality-monitor/README.md`
- **Logs**: `tail -f scripts/quality-monitor/*.log`
- **Database**: `sqlite3 scripts/quality-monitor/quality_monitor.db`
- **Issues**: https://github.com/jkoufopoulos/mailq-prototype/issues?q=label%3Aquality

---

**Last Updated**: November 6, 2025
**System Version**: v2 (LLM-based digest analysis)
