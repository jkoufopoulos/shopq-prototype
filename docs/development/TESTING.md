# ShopQ Testing Guide

Complete guide to testing ShopQ classification, digest generation, and Gmail integration.

## Quick Start

```bash
# 1. Ensure backend is running
uvicorn shopq.api:app --reload

# 2. Install dependencies
pip install -r requirements.txt
npm install

# 3. Run smoke tests (extension + backend)
npm run test

# 4. (Optional) Provide real pytest if available
#    - Place wheels in vendor/ or install via pip when network allows
#    - Fallback runner will engage automatically when pytest is missing

# 5. Run all Playwright suites
npm run test:e2e

# 6. View Playwright report
npm run test:report
```

---

## Table of Contents

- [Why Testing Matters](#why-testing-matters)
- [E2E Testing with Playwright](#e2e-testing-with-playwright)
- [Visual Digest Testing](#visual-digest-testing)
- [Manual Testing](#manual-testing)
- [Test-Driven Debugging](#test-driven-debugging)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

---

## Why Testing Matters

**DON'T DEPLOY without green tests.**

The extension can log success while labels don't actually appear in Gmail. Tests verify actual functionality:

- ✅ Labels **actually applied** to Gmail (not just logged)
- ✅ Emails are **correctly classified**
- ✅ Database logs **match Gmail reality**
- ✅ Digest generation **works end-to-end**
- ✅ Visual output **meets quality standards**

---

## E2E Testing with Playwright

### Test Suites

#### 1. Classification Accuracy Test

Tests the extension against your real Gmail account.

**What it verifies:**
- Finds unlabeled emails
- Triggers classification
- Verifies >50% success rate
- Labels actually appear in Gmail UI
- Quality checks (newsletters, receipts, action items)

**Run it:**
```bash
./scripts/test-with-my-gmail.sh
```

**Or with backend startup:**
```bash
./scripts/run-full-e2e-tests.sh
```

**What success looks like:**
```
✓ should classify emails with >50% accuracy (30s)
✓ should correctly classify newsletters (5s)
✓ should correctly classify receipts (5s)
✓ should detect misclassifications (8s)
```

#### 2. Gmail Labeling Test

**What it tests:**
- Labels are ACTUALLY applied to Gmail (not just logged)
- Batch labeling accuracy (42/42 claimed vs reality)
- Database matches Gmail state

**Run it:**
```bash
npm run test:labeling
```

**What failure looks like:**
```
✗ should actually apply labels to Gmail emails
  Error: Extension logged success but no ShopQ labels found in Gmail!
```

#### 3. Gmail Search Test

**What it tests:**
- Gmail search finds unlabeled emails
- Search query matches extension's query
- Category tabs (Promotions, Social) don't break search

**Run it:**
```bash
npm run test:search
```

#### 4. DOM Selector Test

**What it tests:**
- Extension can find email rows in Gmail
- Label indicators work
- Content script can monitor changes

**Run it:**
```bash
npm run test:selectors
```

**What failure looks like:**
```
✗ should find email rows with current selectors
  Error: CRITICAL: No email row selector works!
```

### Running Tests

**All tests:**
```bash
npm run test:e2e
```

**Watch mode (headed):**
```bash
npm run test:e2e:headed
```

See the browser and extension in action.

**Debug mode:**
```bash
npm run test:e2e:debug
```

Opens Playwright Inspector - step through test line by line.

**Interactive UI:**
```bash
npm run test:e2e:ui
```

Visual test runner with time-travel debugging.

### Setup Requirements

**Prerequisites:**
1. Close Chrome: `pkill -x "Google Chrome"`
2. Start backend: `uvicorn shopq.api:app --reload --port 8000`
3. Chrome profile at: `~/Library/Application Support/Google/Chrome`

**Change Chrome profile:**
```bash
export CHROME_USER_DATA="/path/to/profile"
```

**Change timeouts:**
```javascript
// playwright.config.js
timeout: 120 * 1000, // 2 minutes per test

// In specific tests
test.setTimeout(180000); // 3 minutes
```

### Test Artifacts

After tests run:
```
test-results/
├── classification-accuracy/
│   ├── test-failed-1.png       # Screenshot at failure
│   ├── video.webm              # Video of entire test
│   └── trace.zip               # Step-by-step trace
└── results.json                # JSON results for CI
```

**View HTML report:**
```bash
npm run test:report
# or
open playwright-report/index.html
```

---

## Visual Digest Testing

### What We Test

Comprehensive visual verification of digest generation:

- **Screenshots** at each step (Gmail loaded, digest opened, errors)
- **HTML snapshots** of digest content
- **Backend tracking data** (entities, coverage, timestamps)
- **Quality checks** (age markers, email coverage, entity links)

### Run Visual Tests

**Single test:**
```bash
./scripts/test-digest-quality.sh
```

**Automated iteration with Claude:**
```bash
./scripts/claude-iterate-digest.sh 1 10  # Up to 10 iterations
```

### What Gets Captured

**Screenshots:**
1. `01-gmail-loaded.png` - Gmail interface after loading
2. `02-digest-opened.png` - Digest email opened in Gmail
3. `ERROR.png` - State when error occurred (if failed)

**Content Files:**
1. `digest-content.txt` - Plain text version
2. `digest-content.html` - HTML with formatting and entity links
3. `tracking-data.json` - Backend session data, entity extraction

**Reports:**
1. `report.json` - Structured test results with all assertions
2. `summary.md` - Human-readable pass/fail summary
3. `ANALYSIS_FOR_SHOPQ_REFERENCE.md` - Claude-specific root cause analysis

### Expectations Checked

#### 1. Temporal Awareness

**Check:** Age markers like "[5 days old]" appear in digest

**Expected:**
```
[5 days old] Engineering Manager opportunity at Capsule (1)
[3 days old] Your Leesa order is on the way (2)
```

**Failure indicators:**
- `temporalAwarenessPresent: false`
- `ageMarkersFound: []`

**Debug steps:**
1. Check extension logs timestamp field
2. Verify backend receives timestamp
3. Check entity timestamp parsing
4. Verify age marker generation in timeline

#### 2. Email Coverage

**Check:** All emails represented in digest

**Expected:**
```
featured + orphaned + noise = total_threads
```

**Failure indicators:**
- `allEmailsRepresented: false`
- `missingEmails: [...]`

**Debug steps:**
1. Check entity extraction success rate
2. Verify timeline selection logic
3. Confirm noise summary inclusion

### File Locations

```
test-results/
├── claude-iterations/
│   ├── iter-1/
│   │   ├── ANALYSIS_FOR_SHOPQ_REFERENCE.md    ← Claude reads this
│   │   ├── 01-gmail-loaded.png
│   │   ├── 02-digest-opened.png
│   │   ├── digest-content.txt
│   │   ├── digest-content.html
│   │   ├── tracking-data.json
│   │   ├── report.json
│   │   └── summary.md
│   └── iter-N/
└── digest-{timestamp}/               ← Latest test run
```

### Example Iteration

```
Iteration 1:
  Run tests → ❌ Temporal Awareness: false
  Analysis: emailTimestamp not in logged data
  Fix: Add emailTimestamp to logger.js

Iteration 2:
  Run tests → ❌ Still failing
  Analysis: Backend not receiving timestamp
  Fix: Update API to extract emailTimestamp field

Iteration 3:
  Run tests → ❌ Still failing
  Analysis: Old cached data doesn't have field
  Fix: Clear IndexedDB in test setup

Iteration 4:
  Run tests → ✅ All passing!
```

---

## Manual Testing

### Manual Test Checklist

After automated tests pass, manually verify:

- [ ] Click ShopQ button/auto-organize triggers
- [ ] Labels appear in Gmail UI (not just logs)
- [ ] Emails are archived from inbox
- [ ] Multiple emails processed correctly (not just 1)
- [ ] Database logs match Gmail reality
- [ ] Remove label → re-organize works
- [ ] Extension survives page reload
- [ ] No console errors in DevTools

### Manual Test Procedure

#### Step 1: Load Extension

```bash
cd /Users/justinkoufopoulos/Projects/mailq-prototype
# In Chrome: chrome://extensions/
# Enable Developer mode
# Click "Load unpacked"
# Select the extension/ directory
```

#### Step 2: Test Normal Operation

1. Open Gmail in a new tab
2. Ensure inbox has unlabeled emails
3. Click ShopQ extension icon
4. Verify emails are organized successfully
5. Check console for any errors

#### Step 3: Test Label Reuse

1. Note which labels were created (e.g., ShopQ-Finance)
2. Delete emails from organized folders
3. Move them back to inbox, remove all ShopQ-* labels
4. Click ShopQ extension icon again
5. Verify it reuses existing labels without 409 errors

#### Step 4: Monitor Console Output

1. Look for proper error stringification
2. Verify 409 handling messages if duplicate labels attempted
3. Confirm no uncaught exceptions

---

## Test-Driven Debugging

### The Workflow

```
1. Run Tests
   └─> npm run test:e2e

2. Identify Failures
   └─> npm run test:report
   └─> Review screenshots, videos, logs

3. Fix the Issue
   └─> Based on test failure, fix code

4. Re-run Test
   └─> npm run test:labeling  (just the failed test)

5. Verify Fix
   └─> npm run test:e2e  (all tests)

6. Deploy
   └─> git commit && git push && ./deploy.sh
```

### Interpreting Failures

#### Issue #7: Labels Not Applied

**Symptom:**
```
Extension logged success but no ShopQ labels found in Gmail!
Expected: true
Received: false
```

**What's wrong:**
- Extension calls Gmail API to apply labels
- API returns success (200 OK)
- But labels don't actually appear in Gmail
- Could be: permissions, rate limiting, stale label IDs, race condition

**Fix:**
1. Check Gmail API permissions (extension/manifest.json)
2. Verify label IDs are correct (not stale)
3. Add retry logic for label application
4. Verify API response actually applied labels

#### Issue #2: Search Returns 0

**Symptom:**
```
Gmail search returns 0 results but 10 emails are visible in inbox.
```

**What's wrong:**
- Emails visible in inbox UI
- But search `in:inbox -label:ShopQ/*` finds nothing
- Likely: emails in category tabs (Promotions, Social) don't have INBOX label

**Fix:**
1. Update search query to include category tabs
2. Or: search in:Primary/Promotions/Social separately
3. Or: use different approach (list API instead of search)

#### Issue #6: Selectors Broken

**Symptom:**
```
CRITICAL: No email row selector works!
```

**What's wrong:**
- Gmail changed their DOM structure
- Extension's selectors are outdated
- Content script can't find emails

**Fix:**
1. Run diagnostic test: `npm run test:selectors`
2. Check console output for recommendations
3. Update `extension/modules/selectors.js` with new selectors
4. Re-run tests to verify

### Claude's Automated Fix Loop

**For Claude Code to use:**

```bash
while tests_failing:
    1. Run: ./scripts/auto-fix-tests.sh
    2. Parse: test-results/results.json
    3. Analyze: What failed and why?
    4. Fix:
       - Low confidence? Edit prompts
       - Wrong labels? Adjust rules
       - API errors? Fix backend
       - Extension bugs? Fix extension code
    5. Repeat until all ✅
```

**What Claude can access:**
- ✅ Test pass/fail status
- ✅ Error messages and stack traces
- ✅ Console logs from extension
- ✅ Backend API logs
- ✅ Screenshots of failures
- ✅ Number/percentage of emails classified
- ✅ Which labels were applied

**What Claude cannot access:**
- ❌ Your actual email content (unless logged by tests)
- ❌ Your Gmail UI directly
- ❌ Your Google credentials

---

## CI/CD Integration

Add to `.github/workflows/test.yml`:

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        run: |
          npm install
          npx playwright install chrome

      - name: Start backend
        run: |
          pip install -r requirements.txt
          uvicorn shopq.api:app &
          sleep 5

      - name: Run E2E tests
        run: npm run test:e2e

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: playwright-report/

      - name: Upload test videos
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: test-videos
          path: test-results/**/*.webm
```

---

## Troubleshooting

### Tests Won't Run

**Check:**
- Backend running? `curl http://localhost:8000/api/health`
- Playwright installed? `npx playwright install chrome`
- Extension directory exists? `ls extension/manifest.json`

### Tests Timeout

**Fix:**
- Increase timeout in `playwright.config.js`
- Check internet connection (Gmail needs to load)
- Use headed mode to see what's stuck: `npm run test:e2e:headed`

### Extension Not Loading

**Fix:**
- Check `extension/manifest.json` is valid JSON
- Check no syntax errors: `node -c extension/background.js`
- Verify path in `playwright.config.js` points to `./extension`

### Gmail Login Fails

**Fix:**
- Set up `.env` file with test credentials
- Use App Password, not regular password
- Enable "Less secure app access" for test account

### "Chrome profile is locked"

**Cause:** Chrome is still running

**Fix:**
```bash
pkill -x "Google Chrome"
sleep 2
```

### "Backend not running"

**Cause:** Tests need API at localhost:8000

**Fix:**
```bash
uvicorn shopq.api:app --reload --port 8000
```

### "No unlabeled emails found"

**Cause:** All emails already labeled

**Fix:**
- Remove ShopQ labels from some emails manually
- Or send yourself new test emails

### Screenshots Missing

**Cause:** Screenshot directory not created

**Fix:**
```javascript
fs.mkdirSync(debugDir, { recursive: true });
```

### Backend Data Unavailable

**Cause:** Backend not running

**Fix:**
```bash
uvicorn shopq.api:app --reload --port 8000
```

---

## Best Practices

1. **Run tests before every deploy**
2. **Don't trust console logs** - logs can lie, tests don't
3. **Fix tests immediately** - failing tests indicate broken functionality
4. **Add tests for new features** - prevent regressions
5. **Use headed mode for debugging** - see what's actually happening
6. **Keep tests fast** - optimize selectors, reduce waits
7. **Clean up after tests** - reset Gmail to known state
8. **Start fresh** - clear cache/IndexedDB before testing
9. **Check one thing at a time** - focus on single issue per iteration
10. **Trust structured data** - JSON reports are faster than screenshots

---

## Test Files Reference

```
tests/
├── e2e/
│   ├── classification-accuracy.spec.js  # Real Gmail classification tests
│   ├── digest-quality.spec.js           # Visual digest tests
│   ├── fixtures.js                      # Chrome profile support
│   ├── gmail-labeling.spec.js           # Label application tests
│   ├── gmail-search.spec.js             # Search tests
│   ├── dom-selectors.spec.js            # DOM health checks
│   └── global-setup.js                  # Backend check
├── config/
│   ├── playwright.config.js             # Playwright configuration
│   └── package.json                     # Test dependencies
└── test-results/                        # Generated test artifacts
```

**Test runner scripts:**
```
scripts/
├── test-with-my-gmail.sh         # Simple test runner
├── run-full-e2e-tests.sh         # Advanced with backend startup
├── test-digest-quality.sh        # Visual digest test
├── claude-iterate-digest.sh      # Automated iteration
└── auto-fix-tests.sh             # For Claude's automated fixing
```

---

## Next Steps

1. ✅ Run tests: `npm run test:e2e`
2. 📊 Check results: `npm run test:report`
3. 🔧 Fix failures (see "Interpreting Failures" above)
4. ✅ Re-run until all green
5. 🚀 Deploy with confidence

---

**Remember:** Tests are your safety net. Green tests = safe to deploy.
