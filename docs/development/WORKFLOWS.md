# ShopQ Workflows & Commands

Development workflows, iteration patterns, and quick command reference.

## Quick Commands

```bash
# Start backend
uvicorn shopq.api:app --reload

# Run tests
npm run test:e2e                    # E2E tests
pytest -v                           # Backend tests

# Debug digest
./scripts/watch-and-debug.sh        # Automated watch mode
./scripts/validate-digest.sh        # Single validation
```

---

## Table of Contents

- [Development Iteration Workflow](#development-iteration-workflow)
- [CLI Commands Reference](#cli-commands-reference)
- [Common Tasks](#common-tasks)

---

## Development Iteration Workflow

### Claude Code + Playwright Iteration Loop

**The Loop:**

```
┌─────────────────────────────────────────────────────────┐
│  1. Run Playwright Test                                 │
│     • Remove labels, clear data, reload Gmail           │
│     • Wait for digest generation                        │
│     • Capture screenshots, HTML, logs                   │
│     • Validate backend + visual output                  │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  2. Analyze Results                                      │
│     • Extract issues from report.json                   │
│     • Categorize: Critical, Visual, Warnings            │
│     • Generate detailed bug report                      │
│     • Include file paths, line numbers, examples        │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  3. Claude Code Fixes Bugs                               │
│     • Read bug report + test artifacts                  │
│     • Examine source files                              │
│     • Apply fixes (code, prompts, config)               │
│     • Report what was fixed                             │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  4. Validate & Repeat                                    │
│     • Re-run test with fixes applied                    │
│     • Check if issues resolved                          │
│     • If not all passed → Loop back to step 1           │
│     • If all passed 2x in a row → Success!              │
└─────────────────────────────────────────────────────────┘
```

### Iterative Testing Workflow

Run test cycles and apply fixes:

```bash
# Run automated digest test
./scripts/test-digest-quality.sh

# Watch mode for continuous testing
./scripts/watch-and-debug.sh

# Validate single digest
./scripts/validate-digest.sh
```

**Manual Iteration Process**:
1. Run test (e.g., `./scripts/test-digest-quality.sh`)
2. Review test output and screenshots
3. Apply fixes to identified issues
4. Re-run test to verify
5. Repeat until all tests pass

### Available Test Scripts

**`./scripts/test-digest-quality.sh`**
- Purpose: Run digest quality tests
- Output: Test results and validation report
- Best for: Verifying digest generation quality

**`./scripts/watch-and-debug.sh`**
- Purpose: Automated watch mode for digest debugging
- Output: Continuous monitoring and validation
- Best for: Real-time debugging during development

**`./scripts/validate-digest.sh`**
- Purpose: Single digest validation
- Output: Quick validation report
- Best for: Spot-checking digest output

**`./scripts/claude-iterate-digest.sh`**
- Purpose: Iterative digest improvement with Claude
- Output: Multiple iterations with analysis
- Best for: Improving digest quality over multiple cycles

### Example Session

```bash
# Run initial test
./scripts/test-digest-quality.sh

# Review output, identify issues
# - Missing timestamps
# - Coverage gap

# Apply fixes manually
# - Fix logger.js to log emailTimestamp
# - Fix api.py to extract emailTimestamp
# - Reload Chrome extension

# Re-run test
./scripts/test-digest-quality.sh

# Review improvements
# Identifies: Age markers missing (timestamps now fixed!)

# Apply fixes
# - Fix timeline_synthesizer.py age threshold

# Re-run test after fixes
./scripts/test-digest-quality.sh

# 🎉 All tests passed!
```

### Tips for Development

**Debugging Issues:**
1. Review test output and logs carefully
2. Check screenshots and visual output
3. Prioritize critical issues first
4. Understand root causes before fixing

**Applying Fixes:**
1. Read the source file - understand context before editing
2. Make targeted changes - don't refactor unnecessarily
3. Verify your fix - re-read the code after editing
4. Test incrementally - fix one issue, test, move to next

**Validating Fixes:**

After applying fixes:

1. **If you modified extension code**:
   - Extension must be reloaded in Chrome
   - Extension data may need to be cleared
   - Gmail must be refreshed

2. **If you modified backend code**:
   - Backend auto-reloads (uvicorn --reload)
   - No manual restart needed

3. **Re-run the test**:
   ```bash
   ./scripts/test-digest-quality.sh
   ```

4. **Verify fixes**:
   - Check test output for improvements
   - Look for any new issues introduced
   - Continue until all tests pass

---

## CLI Commands Reference

### Development Workflow

**Start Backend:**
```bash
# Development (auto-reload)
uvicorn shopq.api:app --reload

# With specific host/port
uvicorn shopq.api:app --host 0.0.0.0 --port 8000 --reload

# Production mode
uvicorn shopq.api:app --host 0.0.0.0 --port 8000
```

**Load Chrome Extension:**
```bash
# Open Chrome extensions page
open -a "Google Chrome" "chrome://extensions/"

# Then manually:
# 1. Enable "Developer mode" (top-right toggle)
# 2. Click "Load unpacked"
# 3. Select: /Users/justinkoufopoulos/Projects/mailq-prototype/extension/
```

**Health Check:**
```bash
# Test backend is running
curl http://localhost:8000/health

# Test with pretty output
curl http://localhost:8000/health | python3 -m json.tool

# Check backend version/info
curl http://localhost:8000/ | python3 -m json.tool
```

### Testing

**Backend Tests:**
```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Specific test file
pytest shopq/tests/test_classifier.py

# Specific test function
pytest shopq/tests/test_classifier.py::test_classify_email

# Run with coverage
pytest --cov=mailq --cov-report=html

# Stop on first failure
pytest -x
```

**E2E Tests:**
```bash
# All tests
npm run test:e2e

# Watch mode (headed)
npm run test:e2e:headed

# Debug mode
npm run test:e2e:debug

# Interactive UI
npm run test:e2e:ui

# View report
npm run test:report
```

### Database Commands

**Inspect Central Database:**
```bash
# Open database
sqlite3 shopq/data/shopq.db

# Count rules
sqlite3 shopq/data/shopq.db "SELECT COUNT(*) FROM rules;"

# View recent rules (last 10)
sqlite3 shopq/data/shopq.db "SELECT sender, type, domains, confidence FROM rules ORDER BY created_at DESC LIMIT 10;"

# Find rule for specific sender
sqlite3 shopq/data/shopq.db "SELECT * FROM rules WHERE sender LIKE '%amazon%';"

# View high-confidence rules
sqlite3 shopq/data/shopq.db "SELECT * FROM rules WHERE confidence > 0.90;"

# Export all rules to CSV
sqlite3 -header -csv shopq/data/shopq.db "SELECT * FROM rules;" > rules_export.csv
```

**Inspect Classification Logs:**
```bash
# Count classification logs
sqlite3 shopq/data/shopq.db "SELECT COUNT(*) FROM classification_logs;"

# View recent classifications
sqlite3 shopq/data/shopq.db "SELECT timestamp, sender, type, confidence FROM classification_logs ORDER BY timestamp DESC LIMIT 10;"

# View classifications by type
sqlite3 shopq/data/shopq.db "SELECT type, COUNT(*) as count FROM classification_logs GROUP BY type ORDER BY count DESC;"

# View low-confidence classifications
sqlite3 shopq/data/shopq.db "SELECT * FROM classification_logs WHERE confidence < 0.70 ORDER BY timestamp DESC LIMIT 20;"

# Export logs to CSV
sqlite3 -header -csv shopq/data/shopq.db "SELECT * FROM classification_logs;" > classification_logs.csv
```

### Git & Deployment

**Commit Changes:**
```bash
# Add changes
git add .

# Commit with message
git commit -m "Your message

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>"

# Push
git push
```

**Deploy:**
```bash
# Deploy to Cloud Run
./deploy.sh

# View deployment logs
gcloud run services logs read shopq-api --limit=50

# Check service status
gcloud run services describe shopq-api
```

### API Endpoints

**Configuration:**
```bash
# View confidence thresholds
curl http://localhost:8000/api/config/confidence

# View feature gates
curl http://localhost:8000/api/features

# Toggle feature
curl -X POST http://localhost:8000/api/features/test_mode/enable
curl -X POST http://localhost:8000/api/features/test_mode/disable

# Check test mode
curl http://localhost:8000/api/test/mode
```

**Debug Endpoints:**
```bash
# Featured selection
curl http://localhost:8000/api/debug/featured-selection

# Category summary
curl http://localhost:8000/api/debug/category-summary

# Label counts
curl "http://localhost:8000/api/debug/label-counts?labels=ShopQ-Uncategorized,ShopQ-Notifications"

# Missed featured
curl "http://localhost:8000/api/debug/missed-featured?k=20"

# Digest snapshot
curl http://localhost:8000/api/debug/digest-snapshot
```

**Confidence Stats:**
```bash
# Get stats for last 7 days
curl "http://localhost:8000/api/confidence/stats?days=7"

# Get low-confidence emails
curl "http://localhost:8000/api/confidence/low?limit=100"

# Get confidence trend
curl "http://localhost:8000/api/confidence/trend?days=30"
```

---

## Common Tasks

### Edit Prompts

**Classifier prompt:**
```bash
nano shopq/prompts/classifier_prompt.txt
# Changes load automatically on next classification
```

**Verifier prompt:**
```bash
nano shopq/prompts/verifier_prompt.txt
# Changes load automatically on next verification
```

### Clear Caches

**Extension cache:**
```javascript
// In Gmail console (F12)
await chrome.storage.local.clear();
indexedDB.deleteDatabase('ShopQLogger');
location.reload();
```

**Backend cache:**
```bash
# Rules cache clears automatically
# Classification cache expires after 24 hours
```

### View Logs

**Backend logs:**
```bash
# Tail logs
tail -f /tmp/mailq-backend.log

# Search for errors
grep -i error /tmp/mailq-backend.log

# Search for timestamps
grep "📅" /tmp/mailq-backend.log
```

**Extension logs:**
```javascript
// In Gmail console (F12)
// Look for emojis: 🔍 🏷️ ✅ ❌ 💾
```

### Regenerate Code Graph

```bash
./code-graph/scripts/quick_regen.sh
```

### Check Service Health

**Local:**
```bash
curl http://localhost:8000/health
```

**Production (Cloud Run):**
```bash
curl https://shopq-api-XXXXX-uc.a.run.app/health
```

---

## Related Documentation

- [TESTING.md](TESTING.md) - Testing procedures
- [DEBUGGING.md](DEBUGGING.md) - Debugging tools
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration options
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [QUICKSTART.md](../QUICKSTART.md) - Getting started

---

**Last Updated**: 2025-11-01
