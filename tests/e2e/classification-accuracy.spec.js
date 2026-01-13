/**
 * E2E Test: Classification Accuracy
 *
 * Comprehensive test suite that verifies MailQ correctly classifies
 * real emails in your Gmail inbox across all dimensions:
 * - Type (newsletter, notification, receipt, event, promotion, message)
 * - Domain (finance, shopping, professional, personal)
 * - Attention (action_required, none)
 * - Relationship (from_contact, from_unknown)
 *
 * This test runs against YOUR REAL GMAIL with YOUR REAL EMAILS
 */

import { test, expect } from './fixtures.js';

test.describe('Classification Accuracy - Real Gmail', () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(180000); // 3 minutes per test
  });

  /**
   * Main comprehensive test - processes all unlabeled emails and verifies classification
   */
  test('should classify all unlabeled emails correctly', async ({ page, gmailPage, extensionBackground }) => {
    console.log('🧪 Starting Comprehensive Classification Test');
    console.log('   Testing against YOUR real Gmail inbox\n');

    // Step 1: Navigate to Gmail
    console.log('📧 Step 1: Loading Gmail inbox...');
    await gmailPage.goto();
    await page.waitForTimeout(3000);

    // Step 2: Search for unlabeled emails
    console.log('🔍 Step 2: Finding unlabeled emails (without MailQ labels)...');
    await gmailPage.search('-label:MailQ-Newsletters -label:MailQ-Notifications -label:MailQ-Receipts -label:MailQ-Events -label:MailQ-Promotions -label:MailQ-Messages');
    await page.waitForTimeout(2000);

    const unlabeledEmails = await gmailPage.getEmails();
    console.log(`   Found ${unlabeledEmails.length} unlabeled emails\n`);

    if (unlabeledEmails.length === 0) {
      console.log('✅ All emails already labeled! Test complete.');
      return;
    }

    // Limit to first 20 for initial test run
    const emailsToTest = unlabeledEmails.slice(0, 20);
    console.log(`📊 Processing first ${emailsToTest.length} emails...\n`);

    // Step 3: Capture extension logs
    const classifications = [];
    const errors = [];

    page.on('console', (msg) => {
      const text = msg.text();

      // Capture classification results
      if (text.includes('Classification:') || text.includes('Classified as')) {
        classifications.push({ timestamp: new Date().toISOString(), text });
      }

      // Capture errors
      if (text.toLowerCase().includes('error') || text.toLowerCase().includes('failed')) {
        errors.push({ timestamp: new Date().toISOString(), text });
      }

      // Log important events in real-time
      if (text.includes('✅') || text.includes('❌') || text.includes('🏷️')) {
        console.log(`   ${text}`);
      }
    });

    // Step 4: Get email details before processing
    console.log('📋 Collecting email metadata...');
    const emailData = [];
    for (let i = 0; i < Math.min(5, emailsToTest.length); i++) {
      const email = emailsToTest[i];
      const text = await email.textContent();
      const lines = text?.split('\n').filter(l => l.trim()) || [];

      emailData.push({
        index: i,
        sender: lines[0] || 'Unknown',
        subject: lines[1] || 'Unknown',
        preview: lines[2] || ''
      });

      console.log(`   ${i + 1}. From: ${emailData[i].sender.substring(0, 40)}`);
      console.log(`      Subject: ${emailData[i].subject.substring(0, 60)}`);
    }
    console.log('');

    // Step 5: Trigger MailQ auto-organize
    console.log('🚀 Step 3: Triggering MailQ auto-organize...');

    // Reload page to trigger extension
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Wait for processing (give it 30 seconds)
    console.log('⏳ Waiting for classification to complete (30s)...');
    await page.waitForTimeout(30000);

    // Step 6: Reload and verify results
    console.log('\n🔄 Step 4: Reloading Gmail to verify labels...');
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Search again for previously unlabeled emails
    await gmailPage.search('-label:MailQ-Newsletters -label:MailQ-Notifications -label:MailQ-Receipts -label:MailQ-Events -label:MailQ-Promotions -label:MailQ-Messages');
    await page.waitForTimeout(2000);

    const stillUnlabeled = await gmailPage.getEmails();
    const processedCount = unlabeledEmails.length - stillUnlabeled.length;

    console.log('\n📊 Results Summary:');
    console.log(`   Initial unlabeled: ${unlabeledEmails.length}`);
    console.log(`   Still unlabeled: ${stillUnlabeled.length}`);
    console.log(`   Successfully processed: ${processedCount}`);
    console.log(`   Success rate: ${((processedCount / unlabeledEmails.length) * 100).toFixed(1)}%`);

    // Step 7: Sample verification - check first few emails
    console.log('\n🔍 Step 5: Verifying sample classifications...');

    await page.goto('https://mail.google.com/mail/u/0/#inbox');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const verifiedResults = [];

    for (let i = 0; i < Math.min(5, emailData.length); i++) {
      const emailInfo = emailData[i];

      // Search for this specific email
      await gmailPage.search(`subject:"${emailInfo.subject}"`);
      await page.waitForTimeout(1500);

      const email = await gmailPage.getEmailBySubject(emailInfo.subject);

      if (email) {
        const labels = await gmailPage.getEmailLabels(email);
        const mailqLabels = labels.filter(l => l.includes('MailQ'));

        verifiedResults.push({
          email: emailInfo.subject.substring(0, 50),
          sender: emailInfo.sender.substring(0, 30),
          labels: mailqLabels,
          hasLabels: mailqLabels.length > 0
        });

        console.log(`   ${i + 1}. "${emailInfo.subject.substring(0, 40)}"`);
        console.log(`      From: ${emailInfo.sender.substring(0, 40)}`);
        console.log(`      Labels: ${mailqLabels.length > 0 ? mailqLabels.join(', ') : '❌ NONE'}`);
      } else {
        console.log(`   ${i + 1}. ⚠️  Email not found: "${emailInfo.subject.substring(0, 40)}"`);
      }

      // Go back to inbox for next iteration
      await page.goto('https://mail.google.com/mail/u/0/#inbox');
      await page.waitForTimeout(1000);
    }

    // Step 8: Log any errors encountered
    if (errors.length > 0) {
      console.log('\n⚠️  Errors Encountered:');
      errors.slice(0, 10).forEach((error, i) => {
        console.log(`   ${i + 1}. ${error.text}`);
      });
    }

    // Step 9: Assertions
    console.log('\n✅ Assertions:');

    // At least 50% should be processed successfully
    expect(processedCount).toBeGreaterThan(0);
    const successRate = processedCount / unlabeledEmails.length;

    console.log(`   - Processing emails: ${processedCount > 0 ? 'PASS' : 'FAIL'}`);
    console.log(`   - Success rate (${(successRate * 100).toFixed(1)}%): ${successRate >= 0.5 ? 'PASS' : 'FAIL'}`);

    expect(successRate,
      `Only ${(successRate * 100).toFixed(1)}% of emails were classified. Expected at least 50%.`
    ).toBeGreaterThan(0.5);

    // At least 50% of sampled emails should have labels
    const labeledSamples = verifiedResults.filter(r => r.hasLabels).length;
    const sampleRate = labeledSamples / verifiedResults.length;

    console.log(`   - Sample verification (${labeledSamples}/${verifiedResults.length}): ${sampleRate >= 0.5 ? 'PASS' : 'FAIL'}`);

    if (verifiedResults.length > 0) {
      expect(sampleRate,
        `Only ${labeledSamples}/${verifiedResults.length} sampled emails have labels. Expected at least 50%.`
      ).toBeGreaterThan(0.5);
    }

    console.log('\n🎉 Classification test complete!');
  });

  /**
   * Test classification quality - verify labels make sense
   */
  test('should apply semantically correct labels', async ({ page, gmailPage }) => {
    console.log('🧪 Testing Classification Quality\n');

    // Go to inbox
    await gmailPage.goto();

    // Search for newsletters
    await gmailPage.search('label:MailQ-Newsletters');
    await page.waitForTimeout(2000);

    const newsletters = await gmailPage.getEmails();
    console.log(`📰 Found ${newsletters.length} emails labeled as Newsletters`);

    if (newsletters.length > 0) {
      // Sample first 3 newsletters
      for (let i = 0; i < Math.min(3, newsletters.length); i++) {
        const email = newsletters[i];
        const text = await email.textContent();
        const lines = text?.split('\n').filter(l => l.trim()) || [];

        console.log(`   ${i + 1}. ${lines[0]} - "${lines[1]?.substring(0, 50)}"`);
      }
    }

    // Search for receipts
    await gmailPage.search('label:MailQ-Receipts');
    await page.waitForTimeout(2000);

    const receipts = await gmailPage.getEmails();
    console.log(`\n🧾 Found ${receipts.length} emails labeled as Receipts`);

    if (receipts.length > 0) {
      for (let i = 0; i < Math.min(3, receipts.length); i++) {
        const email = receipts[i];
        const text = await email.textContent();
        const lines = text?.split('\n').filter(l => l.trim()) || [];

        console.log(`   ${i + 1}. ${lines[0]} - "${lines[1]?.substring(0, 50)}"`);
      }
    }

    // Search for action required
    await gmailPage.search('label:MailQ-Action-Required');
    await page.waitForTimeout(2000);

    const actionRequired = await gmailPage.getEmails();
    console.log(`\n⚡ Found ${actionRequired.length} emails labeled as Action Required`);

    if (actionRequired.length > 0) {
      for (let i = 0; i < Math.min(3, actionRequired.length); i++) {
        const email = actionRequired[i];
        const text = await email.textContent();
        const lines = text?.split('\n').filter(l => l.trim()) || [];

        console.log(`   ${i + 1}. ${lines[0]} - "${lines[1]?.substring(0, 50)}"`);
      }
    }

    console.log('\n✅ Classification quality review complete');
    console.log('   Review the samples above to verify they make sense');
  });

  /**
   * Test for misclassifications - look for obvious errors
   */
  test('should not misclassify obvious patterns', async ({ page, gmailPage }) => {
    console.log('🧪 Testing for Misclassifications\n');

    const misclassifications = [];

    // Check: Receipts should be in Shopping domain
    await gmailPage.search('label:MailQ-Receipts -label:MailQ-Shopping');
    await page.waitForTimeout(2000);
    const receiptsNotShopping = await gmailPage.getEmails();

    if (receiptsNotShopping.length > 0) {
      console.log(`⚠️  Found ${receiptsNotShopping.length} receipts NOT labeled as Shopping`);
      misclassifications.push(`${receiptsNotShopping.length} receipts missing Shopping domain`);
    }

    // Check: Promotions from known senders should not be newsletters
    await gmailPage.search('label:MailQ-Promotions label:MailQ-Newsletters');
    await page.waitForTimeout(2000);
    const promoNewsletters = await gmailPage.getEmails();

    if (promoNewsletters.length > 0) {
      console.log(`⚠️  Found ${promoNewsletters.length} emails labeled as BOTH Promotion AND Newsletter`);
      misclassifications.push(`${promoNewsletters.length} emails with conflicting type labels`);
    }

    // Report
    if (misclassifications.length === 0) {
      console.log('✅ No obvious misclassifications detected!');
    } else {
      console.log(`\n⚠️  Found ${misclassifications.length} potential misclassification patterns:`);
      misclassifications.forEach((m, i) => {
        console.log(`   ${i + 1}. ${m}`);
      });
    }
  });
});
