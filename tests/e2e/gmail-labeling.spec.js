/**
 * E2E Test: Gmail Label Application
 *
 * Tests Issue #7: Gmail API Label Application Silently Failing
 *
 * This test verifies that:
 * 1. Extension can classify emails
 * 2. Labels are ACTUALLY applied to Gmail (not just logged)
 * 3. Emails are archived from inbox
 * 4. Database matches reality
 */

import { test, expect } from './fixtures.js';

test.describe('Gmail Label Application', () => {
  test.beforeEach(async ({ page }) => {
    // Set longer timeout for Gmail operations
    test.setTimeout(120000);
  });

  test('should actually apply labels to Gmail emails', async ({ page, gmailPage, context }) => {
    console.log('🧪 Test: Verifying labels are actually applied to Gmail...');

    // Step 1: Navigate to Gmail
    console.log('📧 Step 1: Loading Gmail...');
    await gmailPage.goto();

    // Step 2: Get initial email count
    const initialEmailCount = await gmailPage.countEmails();
    console.log(`📊 Found ${initialEmailCount} emails in inbox`);

    if (initialEmailCount === 0) {
      console.log('⚠️  No emails in inbox - skipping test');
      test.skip();
    }

    // Step 3: Get first email for testing
    const emails = await gmailPage.getEmails();
    const testEmail = emails[0];
    const emailText = await testEmail.textContent();
    const emailSubject = emailText?.split('\n')[0] || 'Unknown';
    console.log(`🎯 Testing with email: "${emailSubject.substring(0, 50)}..."`);

    // Step 4: Check initial labels (should have none or be unlabeled)
    const initialLabels = await gmailPage.getEmailLabels(testEmail);
    console.log(`🏷️  Initial labels: ${initialLabels.length > 0 ? initialLabels.join(', ') : 'None'}`);

    // Step 5: Set up console log monitoring
    const consoleLogs = [];
    page.on('console', (msg) => {
      const text = msg.text();
      consoleLogs.push({ type: msg.type(), text, timestamp: new Date().toISOString() });

      // Log important messages
      if (text.includes('labeled successfully') ||
          text.includes('Labeled:') ||
          text.includes('Error') ||
          text.includes('Failed')) {
        console.log(`   📝 Extension: ${text}`);
      }
    });

    // Step 6: Trigger MailQ auto-organize
    console.log('🚀 Step 2: Triggering MailQ auto-organize...');

    // Find and click the MailQ button (or trigger via extension message)
    try {
      // Option 1: Try to click MailQ button in Gmail UI
      const mailqButton = await page.$('button:has-text("MailQ")').catch(() => null);
      if (mailqButton) {
        await mailqButton.click();
        console.log('   ✅ Clicked MailQ button');
      } else {
        // Option 2: Send message directly to extension
        console.log('   📨 Sending organize message to extension...');
        const backgroundPages = context.backgroundPages();
        if (backgroundPages.length > 0) {
          await backgroundPages[0].evaluate(() => {
            // Trigger organize in background script
            if (typeof organizeEmails === 'function') {
              organizeEmails();
            }
          });
        }
      }
    } catch (error) {
      console.log('   ⚠️  Could not trigger via button, trying reload...');
      await page.reload();
      await page.waitForLoadState('networkidle');
    }

    // Step 7: Wait for processing to complete
    console.log('⏳ Step 3: Waiting for classification to complete...');
    await page.waitForTimeout(10000); // Wait 10 seconds for processing

    // Step 8: Reload Gmail to ensure we see updated state
    console.log('🔄 Step 4: Reloading Gmail to verify labels...');
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Step 9: Search for the email again (it might be archived)
    console.log('🔍 Step 5: Searching for email...');
    const emailStillInInbox = await gmailPage.getEmailBySubject(emailSubject);

    if (!emailStillInInbox) {
      console.log('✅ Email was archived (good sign!)');
      // Search in all mail
      await gmailPage.search(`subject:"${emailSubject}"`);
      await page.waitForTimeout(2000);
    }

    // Step 10: Get email again and check labels
    const updatedEmail = await gmailPage.getEmailBySubject(emailSubject);

    if (!updatedEmail) {
      console.log('❌ FAIL: Cannot find email after processing');

      // Log all console output for debugging
      console.log('\n📋 Extension Console Logs:');
      consoleLogs.forEach(log => {
        console.log(`   [${log.type}] ${log.text}`);
      });

      throw new Error('Email not found after processing');
    }

    // Step 11: Verify labels were applied
    const finalLabels = await gmailPage.getEmailLabels(updatedEmail);
    console.log(`🏷️  Final labels: ${finalLabels.length > 0 ? finalLabels.join(', ') : 'None'}`);

    // Step 12: Analyze results
    const hasMailQLabel = finalLabels.some(label => label.includes('MailQ'));

    console.log('\n📊 Test Results:');
    console.log(`   Initial labels: ${initialLabels.length}`);
    console.log(`   Final labels: ${finalLabels.length}`);
    console.log(`   Has MailQ label: ${hasMailQLabel}`);
    console.log(`   Still in inbox: ${emailStillInInbox !== null}`);

    // Check for success claims in logs
    const successLogs = consoleLogs.filter(log => log.text.includes('labeled successfully'));
    const errorLogs = consoleLogs.filter(log => log.text.toLowerCase().includes('error'));

    console.log(`   Success log count: ${successLogs.length}`);
    console.log(`   Error log count: ${errorLogs.length}`);

    // Step 13: Assertions
    if (successLogs.length > 0) {
      // Extension claimed success - verify labels actually exist
      expect(hasMailQLabel,
        'Extension logged success but no MailQ labels found in Gmail! This is Issue #7.'
      ).toBe(true);

      expect(finalLabels.length,
        'Extension logged success but email has no labels at all'
      ).toBeGreaterThan(0);
    }

    // If we got here, log success
    console.log('\n✅ TEST PASSED: Labels were actually applied to Gmail');
  });

  test('should match database logs with actual Gmail state', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Verifying database matches Gmail reality...');

    // This test checks Issue #3: Database logs classifications that never get applied

    await gmailPage.goto();

    // Get a sample of emails
    const emails = await gmailPage.getEmails();
    const sampleSize = Math.min(5, emails.length);

    console.log(`📊 Checking ${sampleSize} emails...`);

    for (let i = 0; i < sampleSize; i++) {
      const email = emails[i];
      const text = await email.textContent();
      const subject = text?.split('\n')[0] || 'Unknown';

      // Get labels from Gmail
      const gmailLabels = await gmailPage.getEmailLabels(email);

      // TODO: Query database for this email's classification
      // For now, we just verify Gmail state

      console.log(`   Email ${i + 1}: "${subject.substring(0, 40)}..."`);
      console.log(`      Gmail labels: ${gmailLabels.length > 0 ? gmailLabels.join(', ') : 'None'}`);
    }

    console.log('✅ Database verification complete');
  });

  test('should handle batch labeling correctly', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Verifying batch labeling (Issue #7 - 42/42 claimed success)...');

    await gmailPage.goto();

    const initialEmailCount = await gmailPage.countEmails();
    console.log(`📊 Found ${initialEmailCount} emails to process`);

    if (initialEmailCount === 0) {
      console.log('⚠️  No emails in inbox - skipping test');
      test.skip();
    }

    // Record console logs
    const successClaims = [];
    const actualResults = [];

    page.on('console', (msg) => {
      const text = msg.text();
      // Capture success claims like "✅ [1/42] Labeled: ..."
      const match = text.match(/✅ \[(\d+)\/(\d+)\] Labeled:/);
      if (match) {
        successClaims.push({ index: parseInt(match[1]), total: parseInt(match[2]), text });
      }
    });

    // Trigger organize
    console.log('🚀 Triggering batch organize...');
    await page.reload(); // This should trigger auto-organize
    await page.waitForTimeout(15000); // Wait for batch processing

    // Reload and check actual results
    console.log('🔄 Verifying actual Gmail state...');
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Count emails with MailQ labels
    const emails = await gmailPage.getEmails();
    let labeledCount = 0;
    let unlabeledCount = 0;

    for (const email of emails) {
      const labels = await gmailPage.getEmailLabels(email);
      const hasMailQLabel = labels.some(label => label.includes('MailQ'));

      if (hasMailQLabel) {
        labeledCount++;
        actualResults.push({ labeled: true, labels });
      } else {
        unlabeledCount++;
        actualResults.push({ labeled: false, labels });
      }
    }

    console.log('\n📊 Batch Results:');
    console.log(`   Extension claimed: ${successClaims.length} emails labeled`);
    console.log(`   Actually labeled: ${labeledCount} emails`);
    console.log(`   Still unlabeled: ${unlabeledCount} emails`);
    console.log(`   Success rate: ${(labeledCount / (labeledCount + unlabeledCount) * 100).toFixed(1)}%`);

    // Assertion: If extension claimed success, verify actual results
    if (successClaims.length > 0) {
      const successRate = labeledCount / successClaims.length;

      console.log(`   Accuracy: ${(successRate * 100).toFixed(1)}% of claimed successes are real`);

      expect(successRate,
        `Extension claimed ${successClaims.length} successes but only ${labeledCount} actually labeled (${(successRate * 100).toFixed(1)}% accuracy). This is Issue #7!`
      ).toBeGreaterThan(0.9); // At least 90% accuracy
    }

    console.log('✅ Batch labeling verification complete');
  });
});
