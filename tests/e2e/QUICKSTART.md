# E2E Tests Quick Start

## TL;DR

```bash
# 1. Start backend
uvicorn mailq.api:app --reload

# 2. Run tests (in another terminal)
npm run test:e2e

# 3. View results
npm run test:report
```

## What These Tests Do

- ✅ Verify labels are **actually** applied to Gmail (not just logged)
- ✅ Catch "42/42 success" lies when only 2 actually worked
- ✅ Test Gmail search finds unlabeled emails
- ✅ Check DOM selectors still work after Gmail updates

## Your Situation

**Problem:**
- 530+ changes
- 7 critical issues
- Extension logs success but labels don't appear
- Should you deploy?

**Answer:** NO - not until tests pass

**Why:**
- Logs lie (Issue #7: claims success, no labels)
- Tests verify reality (actually checks Gmail)
- Green tests = safe to deploy

## Run One Test to Start

```bash
# Test the most critical issue first (Issue #7: label application)
npm run test:labeling
```

**If it passes:**
```
✓ should actually apply labels to Gmail emails
✓ should match database logs with actual Gmail state
✓ should handle batch labeling correctly

3 passed (25s)
```
→ Labels are working! Move to next test.

**If it fails:**
```
✗ should actually apply labels to Gmail emails
  Error: Extension logged success but no MailQ labels found!
```
→ Issue #7 confirmed. Fix label application before deploying.

## Fix → Test → Deploy Loop

1. **Run test:** `npm run test:labeling`
2. **See failure:** Check screenshot in `test-results/`
3. **Fix code:** Update extension label application logic
4. **Re-run test:** `npm run test:labeling`
5. **Repeat** until green
6. **Deploy:** Now it's safe

## Commands

```bash
# Run all tests
npm run test:e2e

# Run specific test suite
npm run test:labeling    # Issue #7: Label application
npm run test:search      # Issue #2: Gmail search
npm run test:selectors   # Issue #6: DOM selectors

# Debug mode (step through test)
npm run test:e2e:debug

# Watch browser (see what's happening)
npm run test:e2e:headed

# View HTML report
npm run test:report
```

## First Time Setup

```bash
# Already done (you have playwright installed)
# But if needed:
npm install
npx playwright install chrome
```

## Decision Tree

```
Should I deploy my 530 changes?
│
├─ Are tests green? ───YES──→ ✅ Deploy
│
└─ NO
   │
   └─ Fix failures first
      │
      ├─ test:labeling fails? ──→ Fix Issue #7 (label application)
      ├─ test:search fails? ────→ Fix Issue #2 (Gmail search)
      └─ test:selectors fails? ─→ Fix Issue #6 (DOM selectors)
```

## What Success Looks Like

```bash
$ npm run test:e2e

Running 12 tests using 1 worker

  ✓ gmail-labeling.spec.js:15:3 › should actually apply labels (18s)
  ✓ gmail-labeling.spec.js:42:3 › should match database logs (9s)
  ✓ gmail-labeling.spec.js:68:3 › should handle batch labeling (22s)
  ✓ gmail-search.spec.js:12:3 › should find unlabeled emails (6s)
  ✓ gmail-search.spec.js:45:3 › should identify emails without MailQ (4s)
  ✓ gmail-search.spec.js:78:3 › should handle category tabs (7s)
  ✓ gmail-search.spec.js:112:3 › should verify problem emails (8s)
  ✓ dom-selectors.spec.js:10:3 › should find email rows (3s)
  ✓ dom-selectors.spec.js:35:3 › should find label indicators (2s)
  ✓ dom-selectors.spec.js:60:3 › should diagnose DOM structure (4s)
  ✓ dom-selectors.spec.js:95:3 › should verify content script (5s)
  ✓ dom-selectors.spec.js:125:3 › should generate recommendations (3s)

  12 passed (91s)

To view the HTML report, run:
  npx playwright show-report
```

**This means:** All issues fixed, safe to deploy.

## What Failure Looks Like

```bash
$ npm run test:e2e

Running 12 tests using 1 worker

  ✓ gmail-search.spec.js (4 tests passed)
  ✓ dom-selectors.spec.js (5 tests passed)
  ✗ gmail-labeling.spec.js:15:3 › should actually apply labels (15s)

  9 passed, 1 failed (48s)

  1) gmail-labeling.spec.js › should actually apply labels
     Error: Extension logged success but no MailQ labels found in Gmail! This is Issue #7.

To view the HTML report, run:
  npx playwright show-report
```

**This means:** Issue #7 still broken, don't deploy yet.

## Next Step

**Run the first test now:**

```bash
# Make sure backend is running
uvicorn mailq.api:app --reload

# In another terminal, run the labeling test
npm run test:labeling
```

Then come back and tell me what happened - we'll fix any failures together.

---

See `TESTING_GUIDE.md` for full documentation.
