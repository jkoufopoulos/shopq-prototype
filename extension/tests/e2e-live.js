/**
 * MailQ E2E Live Test
 *
 * Connects to an existing Chrome instance via CDP (Chrome DevTools Protocol)
 * to test the MailQ extension on a real Gmail account.
 *
 * Prerequisites:
 * 1. Launch Chrome with debugging port:
 *    Mac: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
 *    Windows: start chrome.exe --remote-debugging-port=9222
 *
 * 2. Log into Gmail in that Chrome instance
 *
 * 3. Find your extension ID:
 *    - Go to chrome://extensions
 *    - Enable "Developer mode" (top right toggle)
 *    - Find "MailQ" and copy the ID (long string like "abcdefghijklmnop...")
 *
 * 4. Set the MAILQ_EXTENSION_ID environment variable or edit this file
 *
 * Usage:
 *   MAILQ_EXTENSION_ID=your_extension_id node tests/e2e-live.js
 */

const { chromium } = require('playwright');

// Configuration
const CDP_ENDPOINT = 'http://localhost:9222';
const EXTENSION_ID = process.env.MAILQ_EXTENSION_ID || 'YOUR_EXTENSION_ID_HERE';
const GMAIL_URL = 'https://mail.google.com/mail/u/0/#inbox';

// Test settings
const MAX_ROWS_TO_CHECK = 20;
const WAIT_AFTER_CLASSIFY_MS = 5000;

async function main() {
  console.log('='.repeat(60));
  console.log('MailQ E2E Live Test');
  console.log('='.repeat(60));

  if (EXTENSION_ID === 'YOUR_EXTENSION_ID_HERE') {
    console.error('\n[ERROR] Please set your extension ID!');
    console.error('Option 1: MAILQ_EXTENSION_ID=xxx node tests/e2e-live.js');
    console.error('Option 2: Edit EXTENSION_ID in this file');
    console.error('\nTo find your extension ID:');
    console.error('1. Go to chrome://extensions');
    console.error('2. Enable "Developer mode" (top right)');
    console.error('3. Find MailQ and copy the ID');
    process.exit(1);
  }

  let browser;

  try {
    // Step 1: Connect to existing Chrome
    console.log('\n[1/5] Connecting to Chrome via CDP...');
    browser = await chromium.connectOverCDP(CDP_ENDPOINT);
    console.log('    Connected to Chrome');

    const contexts = browser.contexts();
    if (contexts.length === 0) {
      throw new Error('No browser contexts found. Is Chrome running with --remote-debugging-port=9222?');
    }

    const context = contexts[0];
    const pages = context.pages();
    console.log(`    Found ${pages.length} open tabs`);

    // Step 1.5: Reload the extension to pick up code changes
    console.log('\n[1.5/5] Reloading MailQ extension...');
    const extPage = await context.newPage();
    await extPage.goto('chrome://extensions', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await new Promise(r => setTimeout(r, 1000));

    // Enable developer mode if not already enabled
    const devModeEnabled = await extPage.evaluate(() => {
      const toggle = document.querySelector('extensions-manager')?.shadowRoot
        ?.querySelector('extensions-toolbar')?.shadowRoot
        ?.querySelector('#devMode');
      return toggle?.checked;
    });

    if (!devModeEnabled) {
      console.log('    Enabling developer mode...');
      await extPage.evaluate(() => {
        const toggle = document.querySelector('extensions-manager')?.shadowRoot
          ?.querySelector('extensions-toolbar')?.shadowRoot
          ?.querySelector('#devMode');
        if (toggle) toggle.click();
      });
      await new Promise(r => setTimeout(r, 500));
    }

    // Find and click reload button for MailQ
    const reloaded = await extPage.evaluate((extId) => {
      const manager = document.querySelector('extensions-manager');
      if (!manager?.shadowRoot) return false;

      const itemList = manager.shadowRoot.querySelector('extensions-item-list');
      if (!itemList?.shadowRoot) return false;

      const items = itemList.shadowRoot.querySelectorAll('extensions-item');
      for (const item of items) {
        if (item.id === extId) {
          const reloadBtn = item.shadowRoot?.querySelector('#reload-button') ||
                           item.shadowRoot?.querySelector('[id*="reload"]') ||
                           item.shadowRoot?.querySelector('cr-icon-button[title*="Reload"]');
          if (reloadBtn) {
            reloadBtn.click();
            return true;
          }
        }
      }
      return false;
    }, EXTENSION_ID);

    if (reloaded) {
      console.log('    Extension reloaded');
    } else {
      console.log('    [WARN] Could not auto-reload extension');
    }

    await extPage.close();
    console.log('    Waiting 3s for extension to reinitialize...');
    await new Promise(r => setTimeout(r, 3000));

    // Re-fetch pages after extension reload (old references may be stale)
    const freshPages = context.pages();
    console.log(`    Found ${freshPages.length} tabs after reload`);

    // Try to capture service worker logs (may fail if context was invalidated)
    const swLogs = [];
    try {
      const client = await context.newCDPSession(freshPages[0]);
      client.on('Runtime.consoleAPICalled', (event) => {
        const text = event.args.map(a => a.value || a.description || '').join(' ');
        if (text.includes('MailQ') || text.includes('organize') || text.includes('Organize') ||
            text.includes('📊') || text.includes('❌') || text.includes('📬') || text.includes('✅')) {
          swLogs.push(`[SW ${event.type}] ${text}`);
        }
      });
      await client.send('Runtime.enable');
      console.log('    Service worker logging enabled');
    } catch (err) {
      console.log('    [WARN] Could not capture service worker logs:', err.message);
    }

    // Step 2: Find or open Gmail tab
    console.log('\n[2/5] Finding Gmail tab...');
    let gmailPage = freshPages.find(p => p.url().includes('mail.google.com'));

    if (!gmailPage) {
      console.log('    Gmail not open, creating new tab...');
      gmailPage = await context.newPage();
      await gmailPage.goto(GMAIL_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    } else {
      console.log('    Found existing Gmail tab');
      const currentUrl = gmailPage.url();
      // Navigate to inbox list if viewing a specific email
      if (!currentUrl.endsWith('#inbox')) {
        console.log('    Navigating to inbox list view...');
        await gmailPage.goto(GMAIL_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
      } else {
        console.log('    Reloading inbox...');
        await gmailPage.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
      }
    }

    // Wait for Gmail to fully load (email rows)
    console.log('    Waiting for inbox to load...');
    console.log('    Current URL:', gmailPage.url());

    // Check if we need to log in
    const pageContent = await gmailPage.content();
    if (pageContent.includes('Sign in') || pageContent.includes('accounts.google.com')) {
      console.log('    [WARN] Gmail requires login. Please log in manually in the Chrome debug window.');
      console.log('    Waiting 30s for manual login...');
      await new Promise(r => setTimeout(r, 30000));
    }

    try {
      await gmailPage.waitForSelector('tr.zA', { timeout: 60000 });
      console.log('    Gmail inbox loaded');
    } catch (selectorErr) {
      console.log('    [DEBUG] Selector tr.zA not found. Checking alternative selectors...');
      const altSelectors = await gmailPage.evaluate(() => {
        return {
          tableRows: document.querySelectorAll('table tr').length,
          divRows: document.querySelectorAll('[role="row"]').length,
          mainContent: document.querySelector('[role="main"]')?.textContent?.substring(0, 200),
          bodyClasses: document.body.className
        };
      });
      console.log('    [DEBUG] Alternative selectors:', JSON.stringify(altSelectors));
      throw selectorErr;
    }

    // Step 3: Clear cache, run classification, verify
    console.log('\n[3/5] Running classification to populate type data...');

    const consoleLogs = [];
    gmailPage.on('console', msg => {
      const text = msg.text();
      if (text.includes('MailQ') || text.includes('InboxSDK') || text.includes('organize') || text.includes('classify') || msg.type() === 'error') {
        consoleLogs.push(`[${msg.type()}] ${text}`);
      }
    });

    gmailPage.on('pageerror', err => {
      consoleLogs.push(`[pageerror] ${err.message}`);
    });

    // Wait for content script to be ready
    await new Promise(r => setTimeout(r, 2000));

    // Check if OAuth is working
    console.log('    Checking OAuth authentication...');
    const authResult = await gmailPage.evaluate(() => {
      return new Promise(resolve => {
        window.postMessage({ type: 'MAILQ_TEST_CHECK_AUTH' }, '*');
        const handler = (event) => {
          if (event.data?.type === 'MAILQ_TEST_CHECK_AUTH_RESPONSE') {
            window.removeEventListener('message', handler);
            resolve(event.data);
          }
        };
        window.addEventListener('message', handler);
        setTimeout(() => resolve({ timeout: true }), 10000);
      });
    });
    console.log('    Auth result:', JSON.stringify(authResult));

    // Check existing cache first (from previous classifications)
    console.log('    Checking existing cache from previous classifications...');
    const existingCache = await gmailPage.evaluate(() => {
      return new Promise(resolve => {
        window.postMessage({ type: 'MAILQ_TEST_GET_CACHE_STATUS' }, '*');
        const handler = (event) => {
          if (event.data?.type === 'MAILQ_TEST_GET_CACHE_STATUS_RESPONSE') {
            window.removeEventListener('message', handler);
            resolve(event.data);
          }
        };
        window.addEventListener('message', handler);
        setTimeout(() => resolve({ count: 0, timeout: true }), 5000);
      });
    });
    console.log(`    Existing cache: ${existingCache.count} entries`);
    if (existingCache.sample && existingCache.sample.length > 0) {
      console.log('    Sample:', JSON.stringify(existingCache.sample, null, 2));
    }

    // If no existing cache, try to run classification
    if (existingCache.count === 0) {
      console.log('    No cached data. Triggering classification (may take 2+ minutes)...');
      const organizeResult = await gmailPage.evaluate(() => {
        return new Promise(resolve => {
          window.postMessage({ type: 'MAILQ_TEST_ORGANIZE' }, '*');
          const handler = (event) => {
            if (event.data?.type === 'MAILQ_TEST_ORGANIZE_RESPONSE') {
              window.removeEventListener('message', handler);
              resolve(event.data);
            }
          };
          window.addEventListener('message', handler);
          setTimeout(() => resolve({ timeout: true }), 180000);
        });
      });
      console.log('    Organize result:', JSON.stringify(organizeResult));

      if (organizeResult.response?.error) {
        console.log(`    [ERROR] ${organizeResult.response.error}`);
        if (organizeResult.response.error.includes('429')) {
          console.log('    Rate limited - wait a minute and retry');
        }
      }

      // No page reload - just wait for storage update and InboxSDK to re-render
      console.log('    Waiting for storage update and badge rendering...');
      await new Promise(r => setTimeout(r, 3000));
    } else {
      console.log('    Using existing cached classifications');
    }

    // Wait for InboxSDK to initialize
    console.log('    Waiting 10s for InboxSDK to initialize...');
    await new Promise(r => setTimeout(r, 10000));

    // Take screenshot for visual verification
    const screenshotPath = `${__dirname}/screenshot-${Date.now()}.png`;
    await gmailPage.screenshot({ path: screenshotPath, fullPage: false });
    console.log(`    Screenshot saved: ${screenshotPath}`);

    console.log('    Console logs from page:');
    consoleLogs.forEach(log => console.log(`      ${log}`));

    if (consoleLogs.length === 0) {
      console.log('      (no MailQ/InboxSDK logs captured)');
    }

    console.log('\n    Service worker logs:');
    if (swLogs.length > 0) {
      swLogs.forEach(log => console.log(`      ${log}`));
    } else {
      console.log('      (no service worker logs captured)');
    }

    // Step 4: Verify badge rendering
    console.log('\n[4/5] Verifying badge rendering...');

    // Check for InboxSDK elements in DOM
    const domStatus = await gmailPage.evaluate(() => {
      return {
        inboxsdkLabels: document.querySelectorAll('.inboxsdk__thread_row_label').length,
        mailqBadges: document.querySelectorAll('[class*="mailq-badge"]').length,
        mailqDimmed: document.querySelectorAll('.mailq-dimmed').length,
        mailqCritical: document.querySelectorAll('.mailq-critical-row').length
      };
    });

    console.log('    DOM status:', JSON.stringify(domStatus));

    // Get all email rows
    const results = await gmailPage.evaluate((maxRows) => {
      const rows = document.querySelectorAll('tr.zA');
      const data = [];

      for (let i = 0; i < Math.min(rows.length, maxRows); i++) {
        const row = rows[i];

        // Get subject (multiple possible selectors)
        const subjectEl = row.querySelector('.bog, .bqe, [data-thread-id] span');
        const subject = subjectEl?.textContent?.trim() || '[No subject]';

        // Get sender
        const senderEl = row.querySelector('.yW span[email], .bA4 span, .yP');
        const sender = senderEl?.textContent?.trim() || senderEl?.getAttribute('email') || '[Unknown]';

        // Check for MailQ badges (InboxSDK labels)
        const badges = [];
        const labelEls = row.querySelectorAll('.inboxsdk__thread_row_label, [class*="mailq-badge"]');
        labelEls.forEach(el => {
          const text = el.textContent?.trim();
          if (text) badges.push(text);
        });

        // Check for critical styling
        const isCritical = row.classList.contains('mailq-critical-row') ||
                          row.querySelector('.mailq-badge-critical') !== null;

        // Check for dimming
        const isDimmed = row.classList.contains('mailq-dimmed');

        // Check for native MailQ labels (should be hidden)
        const nativeLabels = [];
        row.querySelectorAll('.ar, [data-tooltip]').forEach(el => {
          const text = el.textContent?.trim();
          if (text && text.includes('MailQ')) {
            nativeLabels.push(text);
          }
        });

        data.push({
          subject: subject.substring(0, 60),
          sender: sender.substring(0, 30),
          badges,
          isCritical,
          isDimmed,
          nativeLabels,
          hasBadge: badges.length > 0
        });
      }

      return data;
    }, MAX_ROWS_TO_CHECK);

    // Step 5: Report results
    console.log('\n[5/5] Results:');
    console.log('='.repeat(60));

    let withBadge = 0;
    let withoutBadge = 0;
    let critical = 0;
    let dimmed = 0;
    let nativeVisible = 0;

    results.forEach((row, i) => {
      const badgeStr = row.badges.length > 0 ? `[${row.badges.join(', ')}]` : '[NO BADGE]';
      const flags = [];
      if (row.isCritical) flags.push('CRITICAL');
      if (row.isDimmed) flags.push('DIMMED');
      if (row.nativeLabels.length > 0) flags.push(`NATIVE:${row.nativeLabels.join(',')}`);

      const flagStr = flags.length > 0 ? ` (${flags.join(', ')})` : '';

      console.log(`${String(i+1).padStart(2)}. ${row.hasBadge ? 'OK' : 'XX'} ${badgeStr.padEnd(20)} | ${row.sender.padEnd(25)} | ${row.subject}${flagStr}`);

      if (row.hasBadge) withBadge++;
      else withoutBadge++;
      if (row.isCritical) critical++;
      if (row.isDimmed) dimmed++;
      if (row.nativeLabels.length > 0) nativeVisible++;
    });

    console.log('='.repeat(60));
    console.log('\nSummary:');
    console.log(`  Total rows checked: ${results.length}`);
    console.log(`  With MailQ badge:   ${withBadge} (${Math.round(withBadge/results.length*100)}%)`);
    console.log(`  Without badge:      ${withoutBadge}`);
    console.log(`  Critical rows:      ${critical}`);
    console.log(`  Dimmed rows:        ${dimmed}`);
    console.log(`  Native labels visible: ${nativeVisible} ${nativeVisible > 0 ? '(CSS hiding may need work)' : '(good!)'}`);

    // Assertions
    const passRate = withBadge / results.length;
    if (passRate < 0.5 && results.length > 5) {
      console.log('\n[WARN] Less than 50% of emails have badges.');
      console.log('       Possible issues:');
      console.log('       - Classification not running');
      console.log('       - Label cache not populated');
      console.log('       - InboxSDK not loading');
    }

    if (nativeVisible > 0) {
      console.log('\n[WARN] Native MailQ labels are still visible.');
      console.log('       Check styles.css for label hiding CSS.');
    }

  } catch (error) {
    console.error('\n[ERROR]', error.message);

    if (error.message.includes('ECONNREFUSED')) {
      console.error('\nChrome is not running with debugging port.');
      console.error('Start Chrome with:');
      console.error('  Mac: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222');
      console.error('  Win: start chrome.exe --remote-debugging-port=9222');
    }

    process.exit(1);
  } finally {
    // Don't close the browser - it's the user's Chrome instance
    if (browser) {
      await browser.close();
    }
  }

  console.log('\nTest complete!');
}

main();
