# MailQ Quickstart Guide

Get MailQ running in 5 minutes.

## Prerequisites

- Python 3.11+
- Node.js 18+ (for extension tests)
- Chrome browser
- Google Cloud account (for Vertex AI)

## Setup

### 1. Clone and Install

```bash
git clone <repo-url>
cd mailq-prototype

# Backend dependencies
pip install -r requirements.txt

# Extension dependencies (optional, for tests)
cd extension && npm install && cd ..
```

###  2. Configure Environment

```bash
cp .env.example .env
nano .env
```

**Required variables**:
```bash
GOOGLE_API_KEY=AIzaSy...              # Your Vertex AI API key
GOOGLE_CLOUD_PROJECT=mailq-467118     # Your GCP project ID
GEMINI_MODEL=gemini-2.0-flash         # Model to use
```

**Optional variables**:
```bash
API_PORT=8000                         # API server port
USE_RULES_ENGINE=true                 # Enable rule-based classification
USE_AI_CLASSIFIER=true                # Enable LLM classification

# Quality Monitoring (optional - for automated quality analysis)
ANTHROPIC_API_KEY=sk-ant-...          # Claude API for quality analysis
GITHUB_TOKEN=ghp_...                  # For creating quality issues
MIN_EMAILS_FOR_ANALYSIS=25            # Trigger analysis threshold
```

### 3. Initialize Databases

```bash
# Databases are created automatically on first run
# Located in mailq/data/
```

## Running

### Backend API Server

```bash
# Development (auto-reload)
uvicorn mailq.api:app --host 0.0.0.0 --port 8000 --reload

# Production
uvicorn mailq.api:app --host 0.0.0.0 --port 8000
```

**Test it works**:
```bash
curl http://localhost:8000/health
# → {"status": "healthy"}
```

### Chrome Extension

1. **Open Chrome Extensions**: `chrome://extensions/`
2. **Enable Developer Mode**: Toggle in top-right
3. **Load Extension**:
   - Click "Load unpacked"
   - Select `mailq-prototype/extension/` directory
4. **Pin Extension**: Click puzzle icon, pin MailQ

**Test it works**:
1. Open Gmail
2. Click MailQ extension icon
3. Check console for logs (F12 → Console)

## Common Tasks

### Run Tests

```bash
# Backend tests (pytest)
pytest                       # All tests
pytest -v                    # Verbose
pytest -m unit               # Unit tests only
pytest mailq/tests/test_classifier.py  # Specific file

# Extension tests (vitest)
cd extension && npm test
```

### View Logs

```bash
# Backend logs
tail -f /tmp/mailq.log      # If configured

# Extension logs
# Chrome DevTools → Console (F12)
# Filter by "MailQ" or "🏷️" "🔍" emojis
```

### Edit Prompts

```bash
# Classifier prompt (LLM #1)
nano mailq/prompts/classifier_prompt.txt

# Verifier prompt (LLM #2)
nano mailq/prompts/verifier_prompt.txt

# Changes load automatically on next classification
```

### Debug Classification

Enable verbose logging:

```bash
# In extension/config.js, set:
DEBUG_MODE: true

# Reload extension
```

Check classification output:
```bash
# Extension console shows:
# 🔍 Phase 6: Calling verifier...
# ✅ Verifier response: confirm
# 💾 Label cache hit: MailQ-Finance
```

### Analyze Classification Results

Complete workflow to export and analyze your classification batches.

#### Step 1: Export from Chrome

**Before you can analyze**, you need to export the classifications:

1. **Open Gmail** in Chrome
2. **Open Chrome DevTools** - Press F12 (or Cmd+Option+I on Mac)
3. **Go to Console tab** - Click "Console" in the DevTools tabs
4. **Run the export command:**

```javascript
logger.downloadExport();
```

This downloads a file like `mailq-classifications-2025-10-25.jsonl` to your Downloads folder.

**Optional: Check stats first**
```javascript
// See how many classifications you have
logger.getStats().then(stats => console.log(stats));
// → Shows: total, byType, byDecider, lowConfidence, verifierCorrections

// Export last N classifications only
logger.getClassifications().then(async (all) => {
  const recent = all.slice(-50);  // Last 50
  const jsonl = recent.map(c => JSON.stringify(c)).join('\n');
  const blob = new Blob([jsonl], { type: 'application/x-ndjson' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'recent-50.jsonl';
  a.click();
});
```

#### Step 2: Analyze with Python

**Once you have the file downloaded**, run the analyzer:

```bash
# Auto-find most recent file (recommended - no need to know the filename!)
python3 experiments/analysis/analyze_classifications.py --latest

# Generate markdown report
python3 experiments/analysis/analyze_classifications.py --latest --output report.md

# Or specify exact file
python3 experiments/analysis/analyze_classifications.py ~/Downloads/mailq-classifications-2025-10-25.jsonl --output report.md

# View the report
open report.md  # or: cat report.md
```

**What the analyzer checks:**
- ❌ Domain/type conflicts (e.g., promotions with domain labels)
- 📊 Low confidence classifications (<0.85)
- 🔄 Verifier corrections and rejection rate
- 🔀 Sender inconsistencies (same sender, different types)
- 📈 Summary statistics (type distribution, avg confidence, costs)

**Common issue:** If you see `FileNotFoundError`, you haven't exported from Chrome yet. Go back to Step 1.

#### Quick Database Queries (SQLite)

For quick checks without exporting:

```bash
# Classification summary
sqlite3 mailq/data/mailq.db "
  SELECT type, COUNT(*) as count, AVG(confidence) as avg_conf
  FROM classification_logs
  GROUP BY type
  ORDER BY count DESC;"

# Find low-confidence classifications
sqlite3 mailq/data/mailq.db "
  SELECT sender, subject, type, confidence
  FROM classification_logs
  WHERE confidence < 0.85
  ORDER BY timestamp DESC LIMIT 10;"

# Cost analysis
sqlite3 mailq/data/mailq.db "
  SELECT decider, COUNT(*) as count,
         ROUND(COUNT(*) * 0.0001, 4) as est_cost_usd
  FROM classification_logs
  GROUP BY decider;"
```

For comprehensive analysis commands, see [COMMANDS.md](COMMANDS.md) → Analysis section.

### Auto-Organize for Continuous Inbox Zero

MailQ can automatically organize your inbox at regular intervals using Chrome's Alarms API, keeping you at inbox zero without manual intervention.

#### How It Works

- **FREE**: Chrome alarms run in background, no server costs
- **Periodic checks**: Every 5, 10, 15, 30, or 60 minutes
- **Budget-aware**: Respects daily cost limits
- **Smart notifications**: Alerts when inbox reaches zero
- **Persistent**: Survives browser restarts

#### Enable Auto-Organize

1. **Click MailQ extension icon** in Chrome toolbar
2. **Settings popup opens** with auto-organize controls
3. **Check "Enable auto-organize"**
4. **Select check interval** (default: 15 minutes)
5. **Check "Notify when inbox reaches zero"** (optional)
6. **Click "Save Settings"**

You'll see a confirmation notification that auto-organize is enabled.

#### Manual Organization

You can also manually trigger organization from the settings popup:

1. **Click MailQ extension icon**
2. **Click "Organize Inbox Now"** button
3. Wait for processing to complete

The button will show:
- `✨ Already at zero!` if inbox is empty
- `✅ Processed N!` if emails were organized

#### View Auto-Organize Status

The settings popup shows current status:
- **Auto-organize: Enabled** (green) - automatic processing is active
- **Auto-organize: Disabled** (red) - manual mode only

Check extension console for detailed logs:
```javascript
// Look for these log messages:
⏰ Alarm triggered: mailq-auto-organize
🚀 Running automatic inbox organization...
📬 Found 5 unlabeled emails to process
✅ Auto-organize complete: 5 emails processed, 0 remaining
```

#### Cost Tracking

Auto-organize respects the same budget limits as manual organization:
- **Daily cap**: $0.50
- **Typical cost**: ~$0.0001 per email (only if not in rules cache)
- **Budget exceeded**: Auto-organize skips until next day

Check budget in extension console:
```javascript
showStats()  // In background service worker console
```

#### Troubleshooting Auto-Organize

**Alarm not triggering?**
- Check Chrome is running (alarms only fire when Chrome is open)
- Check settings: Click icon → verify "Enable auto-organize" is checked
- View alarm status in extension console:
  ```javascript
  chrome.alarms.getAll().then(console.log)
  ```

**Not processing emails?**
- Check budget limit: `showStats()` in console
- Check API health: `curl http://localhost:8000/health`
- View detailed logs: Open extension console (F12 in service worker)

**Disable auto-organize**
1. Click MailQ extension icon
2. Uncheck "Enable auto-organize"
3. Click "Save Settings"

The alarm will be cleared and automatic processing will stop.

#### Technical Details

Auto-organize uses:
- **Chrome Alarms API**: Reliable background timers
- **Silent processing**: `organizeInboxSilently()` without user interaction
- **Chrome Storage**: Settings persist across browser sessions
- **Gmail API**: Same endpoints as manual organization

Settings stored in `chrome.storage.sync`:
```javascript
{
  enabled: true,           // Auto-organize on/off
  intervalMinutes: 15,     // Check frequency
  notifyOnZero: true       // Show inbox zero notification
}
```

Alarm configuration:
```javascript
{
  name: 'mailq-auto-organize',
  periodInMinutes: 15,     // Configurable interval
  delayInMinutes: 1        // First check in 1 minute
}
```

### Generate Email Digests

MailQ can generate glanceable email summaries following the specification in `mailq_digest_email_template.v2.yaml`.

#### Quick Start: Generate a Digest

```bash
# Generate today's digest (plaintext)
python3 mailq/cli_digest.py generate --period today

# Generate and save as HTML
python3 mailq/cli_digest.py generate --period today --format html --output digest.html

# Generate and email immediately
python3 mailq/cli_digest.py generate --period today --email your-email@example.com
```

#### Configure SMTP (for email delivery)

Add to your `.env` file:

```bash
# SMTP Configuration (Gmail example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password      # Use App Password, not main password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME=MailQ
```

**For Gmail:**
1. Enable 2-factor authentication
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use app password in `SMTP_PASSWORD`

**Test SMTP:**
```bash
python3 mailq/cli_digest.py test-smtp --email your-email@example.com
```

#### Schedule Automated Digests

```bash
# Daily digest at 8:00 AM
python3 mailq/cli_digest.py schedule --email your-email@example.com --time 08:00 --daily

# Weekly digest on Monday at 9:00 AM
python3 mailq/cli_digest.py schedule --email your-email@example.com --time 09:00 --weekly --day monday

# Both daily and weekly
python3 mailq/cli_digest.py schedule --email your-email@example.com --time 08:00 --daily --weekly
```

Press Ctrl+C to stop the scheduler.

**Run scheduler as background service** (Linux/Mac):

```bash
# Using nohup
nohup python3 mailq/cli_digest.py schedule --email your@email.com --time 08:00 --daily > digest.log 2>&1 &

# Using systemd (create /etc/systemd/system/mailq-digest.service)
[Unit]
Description=MailQ Digest Scheduler
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/mailq-prototype
ExecStart=/usr/bin/python3 mailq/cli_digest.py schedule --email your@email.com --time 08:00 --daily
Restart=always

[Install]
WantedBy=multi-user.target
```

#### View Digest Statistics

```bash
# Show email counts and breakdown
python3 mailq/cli_digest.py stats --period today

# List emails in digest database
python3 mailq/cli_digest.py list --period today --limit 20
```

#### API Endpoints

```bash
# Generate digest via API
curl -X POST http://localhost:8000/api/digest/generate \
  -H "Content-Type: application/json" \
  -d '{"period": "today", "format": "html"}' | python3 -m json.tool

# Preview digest in browser
open http://localhost:8000/api/digest/preview/today?format=html

# Get stats only
curl http://localhost:8000/api/digest/stats/today | python3 -m json.tool
```

#### Digest Sections

Generated digests include:

- **Header** - Period label + calm tagline
- **Opener** - Top topic + skip confidence reassurance
- **What Mattered** (3-6 items) - Priority emails with context
- **If You Do One Thing** (1-3 items) - Urgent actions
- **FYIs You Can Skim** (up to 6) - Informational updates
- **Hidden Value** - Receipts, perks, travel updates
- **Footer** - Sync time + preferences

For complete documentation, see [DIGEST_FEATURE.md](DIGEST_FEATURE.md).

### Monitor Classification Quality

MailQ includes an automated quality monitoring system that analyzes digest sessions and creates GitHub issues for classification problems.

#### Quick Start

```bash
# Start the quality monitoring system
./scripts/start-quality-system.sh

# Check status
./scripts/quality-system-status.sh

# Stop system
./scripts/stop-quality-system.sh
```

#### How It Works

The quality system:
- **Polls every 30 minutes** for new digest sessions
- **Analyzes when ≥25 emails** are processed across sessions
- **Uses Claude AI** to identify systematic classification issues
- **Creates GitHub issues** automatically for high/medium severity problems

#### Configuration

Add to your `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...      # For Claude analysis
GITHUB_TOKEN=ghp_...              # For creating issues
MIN_EMAILS_FOR_ANALYSIS=25        # Analysis trigger threshold
```

#### View Quality Issues

```bash
# Check system status
./scripts/quality-system-status.sh

# View issues in GitHub (if gh CLI installed)
gh issue list --label quality

# Or open in browser
open https://github.com/your-repo/issues?q=label%3Aquality
```

For complete documentation, see [docs/QUALITY_CONTROL_PIPELINE.md](docs/QUALITY_CONTROL_PIPELINE.md).

### Analyze Dead Code

Identify potentially unused scripts, Python files, and functions:

```bash
# Full analysis (scripts, Python, JavaScript)
./scripts/analyze-dead-code.sh

# Just scripts
./scripts/analyze-dead-code.sh --scripts

# Just Python files
./scripts/analyze-dead-code.sh --python

# Review the report
cat dead-code-report.md
```

**What it checks:**
- Scripts not referenced in documentation
- Python files with no imports
- Functions/classes with no references
- Old test files (60+ days)
- JavaScript files not modified recently

**Automated:** Runs weekly via GitHub Actions, creates issues if dead code is found.

### Deploy to Production

```bash
# Google Cloud Run
./deploy.sh

# Verify deployment
curl https://mailq-api-<project-id>.run.app/health
```

## Troubleshooting

### Backend won't start

**Error**: `ModuleNotFoundError: No module named 'mailq'`
```bash
pip install -r requirements.txt
```

**Error**: `google.auth.exceptions.DefaultCredentialsError`
```bash
# Set up Google Cloud credentials
gcloud auth application-default login
```

### Extension not working

**No emails classified**:
1. Check API is running: `curl http://localhost:8000/health`
2. Check extension console for errors (F12)
3. Verify OAuth token: Extension → Details → Permissions

**409 Errors (Label conflicts)**:
- This is normal and handled automatically
- Extension caches labels to prevent duplicates
- Check console for `💾 Label cache hit` messages

**Classification incorrect**:
1. Check prompts: `mailq/prompts/*.txt`
2. Review confidence scores in console
3. Adjust thresholds in `mailq/api_organize.py`

### Classification Issues

**Low confidence scores**:
- Edit classifier prompt for clearer instructions
- Add more few-shot examples
- Check if detectors should handle this pattern

**Verifier rejecting too much**:
- Edit verifier prompt to be less strict
- Review rubrics in `mailq/prompts/verifier_prompt.txt`

**Wrong domain assignment**:
- Update domain priority rules in classifier prompt
- Add sender to rules database for future auto-classification

## Project Structure

```
mailq-prototype/
├── mailq/                    # Backend (Python/FastAPI)
│   ├── api.py                # Main API entry point
│   ├── vertex_gemini_classifier.py  # LLM classifier
│   ├── api_verify.py         # Verifier logic
│   ├── prompts/              # LLM prompts (editable!)
│   ├── data/                 # SQLite databases
│   └── tests/                # Backend tests
│
├── extension/                # Chrome extension
│   ├── manifest.json         # Extension config
│   ├── background.js         # Service worker (main)
│   ├── content.js            # Gmail page script
│   ├── modules/              # Core modules
│   │   ├── classifier.js     # API client
│   │   ├── gmail.js          # Gmail API ops
│   │   ├── mapper.js         # Label mapping
│   │   ├── cache.js          # Caching
│   │   └── verifier.js       # Verifier client
│   └── tests/                # Extension tests
│
└── docs/                     # Documentation
    ├── ARCHITECTURE.md       # System design
    ├── TESTING.md            # Test procedures
    └── PROMPT_IMPROVEMENTS.md  # Prompt history
```

## Next Steps

1. **Understand the architecture**: Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. **Improve prompts**: See [mailq/prompts/README.md](mailq/prompts/README.md)
3. **Run tests**: Check [docs/TESTING.md](docs/TESTING.md)
4. **Add features**: Review [PRD.md](PRD.md)

## Resources

- **Full Documentation**: [INDEX.md](INDEX.md)
- **AI Assistant Guide**: [MAILQ_REFERENCE.md](MAILQ_REFERENCE.md)
- **Development Guardrails**: [claude.md](claude.md)
- **Runtime Configuration**: [config/mailq_policy.yaml](config/mailq_policy.yaml)
- **Prompts Guide**: [mailq/prompts/README.md](mailq/prompts/README.md)
- **Testing Guide**: [docs/TESTING.md](docs/TESTING.md)
- **Quality Monitoring**: [docs/QUALITY_CONTROL_PIPELINE.md](docs/QUALITY_CONTROL_PIPELINE.md)

---

**Need help?** Check [INDEX.md](INDEX.md) → Find What You Need
