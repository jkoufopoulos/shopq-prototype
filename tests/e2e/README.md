# MailQ E2E Tests with Playwright

End-to-end tests for MailQ Chrome extension using Playwright.

## Purpose

These tests verify that the MailQ extension actually works with real Gmail, catching issues that unit tests and logs might miss.

### What These Tests Catch

**Issue #7: Gmail API Label Application Silently Failing**
- ✅ Verifies labels are ACTUALLY applied to Gmail (not just logged)
- ✅ Detects when extension claims success but labels don't appear
- ✅ Checks batch labeling accuracy (e.g., "42/42 labeled" vs reality)

**Issue #2: Gmail Search Returns 0 Results**
- ✅ Tests the exact search query extension uses
- ✅ Identifies why visible emails aren't found
- ✅ Checks Gmail category tabs (Promotions, Social, etc.)

**Issue #6: DOM Selectors Broken**
- ✅ Verifies extension can find email rows in Gmail
- ✅ Tests label indicators and content script monitoring
- ✅ Generates updated selector recommendations when Gmail changes

## Setup

### 1. Install Dependencies

```bash
npm install
npx playwright install chrome
```

### 2. Configure Gmail Test Account (Optional)

For full E2E tests with Gmail login, set environment variables:

```bash
# Create .env.test file
cp tests/e2e/.env.example tests/e2e/.env

# Edit with your test Gmail credentials
GMAIL_TEST_EMAIL=your-test-email@gmail.com
GMAIL_TEST_PASSWORD=your-app-password
```

**Note:** Use a dedicated test account, not your personal Gmail. Create an [App Password](https://myaccount.google.com/apppasswords) for security.

### 3. Start Backend API

Tests expect the backend running on `localhost:8000`:

```bash
uvicorn mailq.api:app --reload
```

## Running Tests

### Run All Tests

```bash
npx playwright test
```

### Run Specific Test Suite

```bash
# Gmail labeling tests (Issue #7)
npx playwright test gmail-labeling

# Gmail search tests (Issue #2)
npx playwright test gmail-search

# DOM selector tests (Issue #6)
npx playwright test dom-selectors
```

### Run in Debug Mode

```bash
# Opens Playwright Inspector for step-by-step debugging
DEBUG=1 npx playwright test --debug

# Run with headed browser (see what's happening)
npx playwright test --headed
```

### Run Single Test

```bash
npx playwright test -g "should actually apply labels to Gmail"
```

## Test Structure

```
tests/e2e/
├── README.md                    # This file
├── fixtures.js                  # Reusable test utilities
├── global-setup.js              # Pre-test setup (check backend)
├── global-teardown.js           # Post-test cleanup
├── gmail-labeling.spec.js       # Tests Issue #7 (label application)
├── gmail-search.spec.js         # Tests Issue #2 (search functionality)
└── dom-selectors.spec.js        # Tests Issue #6 (DOM selectors)
```

## Test Helpers (Fixtures)

### `gmailPage` Fixture

Helper methods for interacting with Gmail:

```javascript
test('example', async ({ gmailPage }) => {
  // Navigate to Gmail
  await gmailPage.goto();

  // Get all emails
  const emails = await gmailPage.getEmails();

  // Find email by subject
  const email = await gmailPage.getEmailBySubject('Important Email');

  // Get labels for an email
  const labels = await gmailPage.getEmailLabels(email);

  // Search Gmail
  await gmailPage.search('in:inbox -label:MailQ/*');

  // Trigger MailQ auto-organize
  await gmailPage.triggerAutoOrganize();

  // Wait for extension processing
  await gmailPage.waitForExtensionProcessing();
});
```

### `extensionBackground` Fixture

Access extension background page:

```javascript
test('example', async ({ extensionBackground }) => {
  // Get background page
  const bg = await extensionBackground.getBackgroundPage();

  // Execute code in extension context
  const result = await extensionBackground.evaluate(() => {
    return window.extensionState;
  });

  // Get extension ID
  const id = await extensionBackground.getExtensionId();
});
```

## What Tests Do

### 1. Gmail Label Application Test (`gmail-labeling.spec.js`)

```javascript
✓ should actually apply labels to Gmail emails
  - Triggers MailQ auto-organize
  - Waits for processing
  - Reloads Gmail
  - VERIFIES labels actually appear (not just logs)
  - Catches Issue #7: logs say success but no labels

✓ should match database logs with actual Gmail state
  - Compares database classifications with Gmail reality
  - Catches Issue #3: database says labeled but Gmail disagrees

✓ should handle batch labeling correctly
  - Tests 42+ emails at once
  - Compares "42/42 success" claims vs actual results
  - Reports real success rate
```

### 2. Gmail Search Test (`gmail-search.spec.js`)

```javascript
✓ should find unlabeled emails using extension search query
  - Uses exact search: 'in:inbox -in:sent -label:MailQ/*'
  - Compares visible inbox vs search results
  - Catches Issue #2: 10 emails visible, 0 found

✓ should correctly identify emails without MailQ labels
  - Checks label detection logic
  - Ensures MailQ labels are recognized

✓ should handle Gmail category tabs correctly
  - Tests Primary, Promotions, Social, Updates tabs
  - Identifies if emails are in tabs vs inbox

✓ should verify specific problem emails from Issue #2
  - Tests Hertz, Matt, Juan, Jordan emails specifically
  - Reproduces exact issue scenarios
```

### 3. DOM Selector Test (`dom-selectors.spec.js`)

```javascript
✓ should find email rows with current selectors
  - Tests all selectors from selectors.js
  - Identifies which selectors work
  - Catches Issue #6: all selectors broken

✓ should find label indicators in emails
  - Tests label-related selectors
  - Ensures content script can detect labels

✓ should diagnose current Gmail DOM structure
  - Analyzes Gmail's actual DOM
  - Provides detailed structure report
  - Helps understand what changed

✓ should generate updated selector recommendations
  - Tests multiple selector candidates
  - Recommends best working selectors
  - Provides code to update selectors.js
```

## Viewing Test Results

### HTML Report

After tests run:

```bash
npx playwright show-report
```

Opens interactive HTML report with:
- Test pass/fail status
- Screenshots on failure
- Video recordings
- Detailed logs
- DOM snapshots

### CI/JSON Report

```bash
cat test-results/results.json
```

## Debugging Failed Tests

### 1. Check Screenshots

Failed tests automatically capture screenshots:

```
test-results/
  gmail-labeling-should-actually-apply-labels/
    test-failed-1.png
```

### 2. Watch Video

Tests record video on failure:

```
test-results/
  gmail-labeling-should-actually-apply-labels/
    video.webm
```

### 3. Check Traces

Playwright traces show step-by-step execution:

```bash
npx playwright show-trace test-results/.../trace.zip
```

### 4. Run with Console Logs

```bash
DEBUG=pw:api npx playwright test
```

## Common Issues

### "Extension background page not found"

The extension didn't load. Check:
- Extension is in `./extension` directory
- `manifest.json` exists
- No syntax errors in background.js

### "Gmail search box not found"

Gmail may not have loaded. Try:
- Increasing `page.waitForTimeout` values
- Checking internet connection
- Verifying Gmail didn't change their UI

### "Backend API not running"

Start the backend:

```bash
uvicorn mailq.api:app --reload
```

### Tests hang or timeout

Gmail can be slow. Increase timeout:

```javascript
test.setTimeout(180000); // 3 minutes
```

## Integration with CI/CD

Add to GitHub Actions:

```yaml
- name: Install Playwright
  run: |
    npm install
    npx playwright install chrome

- name: Start Backend
  run: uvicorn mailq.api:app &

- name: Run E2E Tests
  run: npx playwright test

- name: Upload Test Results
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: playwright-report
    path: playwright-report/
```

## Writing New Tests

Use the fixture helpers:

```javascript
import { test, expect } from './fixtures.js';

test.describe('My New Feature', () => {
  test('should do something', async ({ page, gmailPage }) => {
    // Navigate to Gmail
    await gmailPage.goto();

    // Interact with Gmail
    const emails = await gmailPage.getEmails();

    // Make assertions
    expect(emails.length).toBeGreaterThan(0);
  });
});
```

## Best Practices

1. **Test real user flows** - Don't just test APIs, test the full UI interaction
2. **Verify visual results** - Check that Gmail UI actually changes
3. **Don't trust logs** - Logs can lie (Issue #7), verify DOM state
4. **Use dedicated test account** - Don't test on your personal Gmail
5. **Keep tests independent** - Each test should clean up after itself
6. **Document failures** - When a test fails, it's catching a real bug

## Next Steps After Tests Pass

Once all tests are green:

1. ✅ Commit your 530+ changes
2. ✅ Deploy to production with confidence
3. ✅ Set up CI to run tests on every commit
4. ✅ Add new tests for new features

## Getting Help

- Playwright Docs: https://playwright.dev
- MailQ Issues: See `ISSUES_2025-10-30.md`
- Debugging Guide: https://playwright.dev/docs/debug

---

**Remember:** These tests are your safety net. They catch the issues your logs hide. Trust the tests, not the console output.
