/**
 * Manual Gmail Verification Test
 *
 * Run this in Gmail DevTools Console to verify:
 * 1. Labels are actually applied (not just logged)
 * 2. Extension claims vs reality match
 * 3. Batch labeling accuracy
 *
 * INSTRUCTIONS:
 * 1. Open Gmail in Chrome with ShopQ extension loaded
 * 2. Open DevTools (F12 or Cmd+Option+I)
 * 3. Go to Console tab
 * 4. Copy and paste this entire script
 * 5. Press Enter
 * 6. Wait for results
 */

(async function verifyShopQLabeling() {
  console.log('🧪 ShopQ Manual Verification Test');
  console.log('='.repeat(60));

  const results = {
    totalEmails: 0,
    withShopQLabels: 0,
    withoutShopQLabels: 0,
    claimedSuccesses: 0,
    actualSuccesses: 0,
    accuracy: 0,
    emails: []
  };

  // Step 1: Check if we're in Gmail
  if (!window.location.hostname.includes('mail.google.com')) {
    console.error('❌ This script must be run in Gmail');
    return;
  }

  console.log('✅ Running in Gmail');
  console.log('');

  // Step 2: Find all email rows
  console.log('📧 Step 1: Finding email rows...');

  const selectors = [
    'tr[role="row"]',
    '.zA',
    '[data-thread-id]',
    '[data-legacy-thread-id]'
  ];

  let emailRows = [];
  for (const selector of selectors) {
    emailRows = document.querySelectorAll(selector);
    if (emailRows.length > 0) {
      console.log(`   ✅ Found ${emailRows.length} emails using selector: ${selector}`);
      break;
    }
  }

  if (emailRows.length === 0) {
    console.error('❌ No email rows found. Possible Issue #6 (DOM selectors broken)');
    console.log('   Try these selectors manually:');
    selectors.forEach(s => console.log(`      document.querySelectorAll('${s}').length`));
    return;
  }

  results.totalEmails = emailRows.length;
  console.log('');

  // Step 3: Check each email for ShopQ labels
  console.log('🏷️  Step 2: Checking for ShopQ labels...');
  console.log('');

  for (let i = 0; i < Math.min(emailRows.length, 20); i++) {
    const row = emailRows[i];

    // Get email subject
    const subject = row.textContent?.split('\n').find(line => line.trim().length > 0) || 'Unknown';

    // Find labels in this row
    const labelSelectors = [
      '.ar',
      '.xY',
      '[data-tooltip*="Labels"]',
      'span[title]',
      '.aDm'
    ];

    let labels = [];
    for (const selector of labelSelectors) {
      const labelElements = row.querySelectorAll(selector);
      labelElements.forEach(el => {
        const text = el.textContent?.trim() || el.getAttribute('title')?.trim() || '';
        if (text && text.length > 0) {
          labels.push(text);
        }
      });
      if (labels.length > 0) break;
    }

    const hasShopQLabel = labels.some(label => label.includes('ShopQ'));

    if (hasShopQLabel) {
      results.withShopQLabels++;
      console.log(`   ✅ [${i + 1}] HAS ShopQ labels: "${subject.substring(0, 50)}..."`);
      console.log(`      Labels: ${labels.filter(l => l.includes('ShopQ')).join(', ')}`);
    } else {
      results.withoutShopQLabels++;
      console.log(`   ❌ [${i + 1}] NO ShopQ labels: "${subject.substring(0, 50)}..."`);
      if (labels.length > 0) {
        console.log(`      Other labels: ${labels.join(', ')}`);
      }
    }

    results.emails.push({
      subject: subject.substring(0, 60),
      hasShopQLabel,
      labels: labels.filter(l => l.includes('ShopQ'))
    });
  }

  console.log('');
  console.log('📊 Step 3: Analyzing extension logs...');

  // Note: We can't directly access past console logs, but we can check if there are recent ones
  console.log('   (Check your console history for messages like:)');
  console.log('   "✅ [X/Y] Labeled: ..." - these are claimed successes');
  console.log('   "📊 Results: X/Y labeled successfully" - claimed batch results');
  console.log('');

  // Step 4: Database check (if available)
  console.log('🗄️  Step 4: Checking extension database...');

  try {
    // Try to access extension's IndexedDB
    const dbs = await window.indexedDB.databases();
    const mailqDB = dbs.find(db => db.name.includes('mailq') || db.name.includes('ShopQ'));

    if (mailqDB) {
      console.log(`   ✅ Found ShopQ database: ${mailqDB.name}`);
      console.log('   (Database entries should match actual Gmail labels)');
    } else {
      console.log('   ⚠️  ShopQ database not found in this context');
    }
  } catch (error) {
    console.log('   ⚠️  Cannot access IndexedDB from this context');
  }

  console.log('');
  console.log('='.repeat(60));
  console.log('📊 FINAL RESULTS');
  console.log('='.repeat(60));
  console.log('');

  console.log(`Total emails checked: ${results.totalEmails}`);
  console.log(`With ShopQ labels: ${results.withShopQLabels}`);
  console.log(`Without ShopQ labels: ${results.withoutShopQLabels}`);
  console.log('');

  // Calculate percentages
  const labeledPercentage = (results.withShopQLabels / results.totalEmails * 100).toFixed(1);
  const unlabeledPercentage = (results.withoutShopQLabels / results.totalEmails * 100).toFixed(1);

  console.log(`Labeling rate: ${labeledPercentage}% labeled, ${unlabeledPercentage}% unlabeled`);
  console.log('');

  // Issue #7 detection
  if (results.withoutShopQLabels > 0) {
    console.log('⚠️  POTENTIAL ISSUE #7 DETECTED:');
    console.log(`   ${results.withoutShopQLabels} emails have NO ShopQ labels`);
    console.log('');
    console.log('   Check if extension logs claimed these were labeled:');
    console.log('   - Search console for "labeled successfully"');
    console.log('   - Compare claimed count vs actual count above');
    console.log('   - If logs say "42/42 success" but only a few have labels → Issue #7');
    console.log('');
  } else {
    console.log('✅ All checked emails have ShopQ labels');
    console.log('   (If extension is working correctly, this is good!)');
    console.log('');
  }

  // Recommendations
  console.log('🔍 NEXT STEPS:');
  console.log('');

  if (results.withoutShopQLabels > 0) {
    console.log('1. Click the ShopQ button to organize emails');
    console.log('2. Watch console for "✅ [X/Y] Labeled: ..." messages');
    console.log('3. After it finishes, run this script again');
    console.log('4. Compare: Did the count of labeled emails increase?');
    console.log('5. If logs say success but labels don\'t appear → Issue #7 confirmed');
  } else {
    console.log('1. Remove a ShopQ label from an email manually');
    console.log('2. Click ShopQ button to re-organize');
    console.log('3. Run this script again');
    console.log('4. Check if label was re-applied');
  }

  console.log('');
  console.log('='.repeat(60));

  // Store results globally for inspection
  window.mailqVerificationResults = results;
  console.log('💾 Results saved to: window.mailqVerificationResults');
  console.log('');

  return results;
})();
