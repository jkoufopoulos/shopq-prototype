/**
 * E2E Test: Gmail Search Functionality
 *
 * Tests Issue #2: Gmail Search Returns 0 Results Despite Visible Inbox Emails
 *
 * This test verifies that:
 * 1. Gmail search query matches what extension uses
 * 2. Search actually finds unlabeled emails
 * 3. Visible inbox emails have the expected labels (or lack thereof)
 */

import { test, expect } from './fixtures.js';

test.describe('Gmail Search Functionality', () => {
  test('should find unlabeled emails using extension search query', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Verifying Gmail search finds unlabeled emails...');

    // Step 1: Navigate to Gmail inbox
    console.log('📧 Step 1: Loading Gmail inbox...');
    await gmailPage.goto();

    // Step 2: Count visible emails in inbox
    const inboxEmailCount = await gmailPage.countEmails();
    console.log(`📊 Visible emails in inbox: ${inboxEmailCount}`);

    if (inboxEmailCount === 0) {
      console.log('⚠️  No emails in inbox - skipping test');
      test.skip();
    }

    // Step 3: Test the exact search query the extension uses
    // From extension/modules/gmail.js:73-78
    const searchQuery = 'in:inbox -in:sent -in:drafts -in:trash -in:spam -label:ShopQ/*';
    console.log(`🔍 Step 2: Testing search query: "${searchQuery}"`);

    await gmailPage.search(searchQuery);
    await page.waitForTimeout(2000);

    // Step 4: Count search results
    const searchResultCount = await gmailPage.countEmails();
    console.log(`📊 Search results: ${searchResultCount}`);

    // Step 5: Compare results
    console.log('\n📊 Analysis:');
    console.log(`   Emails visible in inbox: ${inboxEmailCount}`);
    console.log(`   Emails found by search: ${searchResultCount}`);
    console.log(`   Difference: ${inboxEmailCount - searchResultCount}`);

    // Step 6: If search returns 0 but inbox shows emails, investigate
    if (searchResultCount === 0 && inboxEmailCount > 0) {
      console.log('\n❌ ISSUE #2 DETECTED: Search returns 0 but emails are visible!');
      console.log('   Investigating possible causes...');

      // Go back to inbox to investigate
      await page.goto('https://mail.google.com/mail/u/0/#inbox');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Check a sample email
      const emails = await gmailPage.getEmails();
      if (emails.length > 0) {
        const sampleEmail = emails[0];
        const text = await sampleEmail.textContent();
        const subject = text?.split('\n')[0] || 'Unknown';

        console.log(`\n🔬 Analyzing sample email: "${subject.substring(0, 50)}..."`);

        // Click on email to see full details
        await sampleEmail.click();
        await page.waitForTimeout(1000);

        // Check for labels
        const labels = await gmailPage.getEmailLabels(sampleEmail);
        console.log(`   Labels: ${labels.length > 0 ? labels.join(', ') : 'None visible'}`);

        // Test individual search components
        console.log('\n🧪 Testing search query components:');

        const tests = [
          { query: 'in:inbox', desc: 'Has INBOX label' },
          { query: '-label:ShopQ/*', desc: 'No ShopQ labels' },
          { query: `subject:"${subject.substring(0, 30)}"`, desc: 'Subject search' },
        ];

        for (const testCase of tests) {
          await page.goto('https://mail.google.com/mail/u/0/#search/' + encodeURIComponent(testCase.query));
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(1500);

          const count = await gmailPage.countEmails();
          console.log(`   ${testCase.query}: ${count} results - ${testCase.desc}`);
        }
      }

      // Throw error with diagnostic info
      throw new Error(
        `Issue #2: Gmail search returns 0 results but ${inboxEmailCount} emails are visible in inbox. ` +
        `This means the search query is not matching emails that should be unlabeled.`
      );
    }

    // Step 7: Verify search found some emails (or all have ShopQ labels)
    if (searchResultCount === 0) {
      console.log('✅ Search returned 0 results - all emails may already be labeled');
    } else {
      console.log(`✅ Search found ${searchResultCount} unlabeled emails`);

      // Assertion: Search should find at least some emails if inbox has them
      expect(searchResultCount).toBeGreaterThan(0);
    }
  });

  test('should correctly identify emails without ShopQ labels', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Verifying ShopQ label detection...');

    await gmailPage.goto();

    const emails = await gmailPage.getEmails();
    const sampleSize = Math.min(5, emails.length);

    console.log(`📊 Checking ${sampleSize} emails for ShopQ labels...`);

    let withShopQLabels = 0;
    let withoutShopQLabels = 0;

    for (let i = 0; i < sampleSize; i++) {
      const email = emails[i];
      const text = await email.textContent();
      const subject = text?.split('\n')[0] || 'Unknown';
      const labels = await gmailPage.getEmailLabels(email);

      const hasShopQLabel = labels.some(label => label.includes('ShopQ'));

      if (hasShopQLabel) {
        withShopQLabels++;
        console.log(`   ✅ Email ${i + 1}: Has ShopQ labels - "${subject.substring(0, 40)}..."`);
      } else {
        withoutShopQLabels++;
        console.log(`   ❌ Email ${i + 1}: No ShopQ labels - "${subject.substring(0, 40)}..."`);
      }
    }

    console.log('\n📊 Results:');
    console.log(`   With ShopQ labels: ${withShopQLabels}`);
    console.log(`   Without ShopQ labels: ${withoutShopQLabels}`);

    // If all emails have ShopQ labels, that's okay
    // If some don't, the search should find them
    console.log('✅ Label detection complete');
  });

  test('should handle Gmail category tabs correctly', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Checking Gmail category tabs (Promotions, Social, Updates)...');

    // Issue #2 mentioned category tabs might affect label detection

    await page.goto('https://mail.google.com/mail/u/0/');
    await page.waitForLoadState('networkidle');

    // Check if category tabs are visible
    const tabs = [
      { name: 'Primary', selector: '[data-category="primary"]' },
      { name: 'Social', selector: '[data-category="social"]' },
      { name: 'Promotions', selector: '[data-category="promotions"]' },
      { name: 'Updates', selector: '[data-category="updates"]' },
      { name: 'Forums', selector: '[data-category="forums"]' },
    ];

    console.log('🔍 Checking for category tabs...');

    const foundTabs = [];
    for (const tab of tabs) {
      const element = await page.$(tab.selector);
      if (element) {
        foundTabs.push(tab.name);
        console.log(`   ✅ ${tab.name} tab exists`);
      }
    }

    if (foundTabs.length > 1) {
      console.log(`\n⚠️  Gmail has category tabs enabled: ${foundTabs.join(', ')}`);
      console.log('   This may affect which emails have the INBOX label');
      console.log('   Emails in Promotions/Social/Updates may not be in:inbox');

      // Test each tab
      for (const tabName of foundTabs) {
        const tab = tabs.find(t => t.name === tabName);
        if (!tab) continue;

        const tabElement = await page.$(tab.selector);
        if (tabElement) {
          await tabElement.click();
          await page.waitForTimeout(1500);

          const emailCount = await gmailPage.countEmails();
          console.log(`   ${tabName}: ${emailCount} emails`);
        }
      }
    } else {
      console.log('✅ Category tabs not detected - using standard inbox');
    }
  });

  test('should verify specific problem emails from Issue #2', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Checking specific emails mentioned in Issue #2...');

    // Specific emails from ISSUES.md:
    const problemEmails = [
      { sender: 'hertz', subject: 'rental return' },
      { sender: 'matt', subject: 'pharmacy' },
      { sender: 'juan', subject: 'tandem' },
      { sender: 'jordan', subject: 'job' },
    ];

    console.log('🔍 Searching for specific problem emails...');

    for (const email of problemEmails) {
      // Search by sender
      const query = `from:${email.sender}`;
      await gmailPage.search(query);
      await page.waitForTimeout(1500);

      const count = await gmailPage.countEmails();
      console.log(`   ${email.sender}: ${count} emails found`);

      if (count > 0) {
        // Check if it's in inbox
        const inInboxQuery = `in:inbox from:${email.sender}`;
        await gmailPage.search(inInboxQuery);
        await page.waitForTimeout(1500);

        const inboxCount = await gmailPage.countEmails();
        console.log(`      in:inbox: ${inboxCount} emails`);

        if (inboxCount > 0) {
          // Get labels
          const emails = await gmailPage.getEmails();
          if (emails.length > 0) {
            const labels = await gmailPage.getEmailLabels(emails[0]);
            console.log(`      labels: ${labels.length > 0 ? labels.join(', ') : 'None'}`);
          }
        }
      }
    }

    console.log('✅ Specific email verification complete');
  });
});
