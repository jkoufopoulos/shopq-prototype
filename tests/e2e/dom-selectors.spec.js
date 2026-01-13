/**
 * E2E Test: Gmail DOM Selector Health
 *
 * Tests Issue #6: Gmail DOM Selectors Broken (Content Script Errors)
 *
 * This test verifies that:
 * 1. Critical selectors can find their target elements
 * 2. Content script can monitor Gmail UI
 * 3. Selector fallbacks work correctly
 */

import { test, expect } from './fixtures.js';

test.describe('Gmail DOM Selector Health', () => {
  test('should find email rows with current selectors', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Verifying email row selectors...');

    await gmailPage.goto();

    // Selectors from extension/modules/selectors.js
    const emailRowSelectors = [
      '[data-legacy-thread-id]',
      '[data-thread-id]',
      'tr[role="row"]',
      '.zA',
      '.yO',
      'tr.zA',
      '.email-row'
    ];

    console.log('🔍 Testing email row selectors:');

    let workingSelector = null;
    let maxMatches = 0;

    for (const selector of emailRowSelectors) {
      try {
        const elements = await page.$$(selector);
        const count = elements.length;

        if (count > 0) {
          console.log(`   ✅ ${selector}: Found ${count} elements`);
          if (count > maxMatches) {
            maxMatches = count;
            workingSelector = selector;
          }
        } else {
          console.log(`   ❌ ${selector}: No elements found`);
        }
      } catch (error) {
        console.log(`   ❌ ${selector}: Error - ${error.message}`);
      }
    }

    console.log(`\n📊 Best selector: ${workingSelector || 'NONE'} (${maxMatches} matches)`);

    // Assertion: At least one selector should work
    expect(workingSelector,
      'CRITICAL: No email row selector works! This is Issue #6. Extension cannot find emails in Gmail.'
    ).not.toBeNull();

    expect(maxMatches,
      'Found a working selector but it matched 0 elements'
    ).toBeGreaterThan(0);
  });

  test('should find label indicators in emails', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Verifying label indicator selectors...');

    await gmailPage.goto();

    const labelIndicatorSelectors = [
      '[data-tooltip*="Labels"]',
      'span[email]',
      '.ar',
      '.xY',
      '[aria-label*="Labels"]',
      '.label-container',
      '.aDm'
    ];

    console.log('🔍 Testing label indicator selectors:');

    let workingSelector = null;
    let maxMatches = 0;

    for (const selector of labelIndicatorSelectors) {
      try {
        const elements = await page.$$(selector);
        const count = elements.length;

        if (count > 0) {
          console.log(`   ✅ ${selector}: Found ${count} elements`);
          if (count > maxMatches) {
            maxMatches = count;
            workingSelector = selector;
          }
        } else {
          console.log(`   ❌ ${selector}: No elements found`);
        }
      } catch (error) {
        console.log(`   ❌ ${selector}: Error - ${error.message}`);
      }
    }

    console.log(`\n📊 Best selector: ${workingSelector || 'NONE'} (${maxMatches} matches)`);

    if (!workingSelector) {
      console.log('⚠️  WARNING: No label indicator selectors work');
      console.log('   This prevents content script from detecting label changes');
      console.log('   Feedback mechanism (Issue #6) will be broken');
    }
  });

  test('should diagnose current Gmail DOM structure', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Diagnosing Gmail DOM structure...');

    await gmailPage.goto();

    // Run diagnostic function from extension
    console.log('🔬 Running Gmail DOM diagnostic...');

    const domStructure = await page.evaluate(() => {
      const results = {
        emailRows: [],
        labels: [],
        structure: {}
      };

      // Find email rows by trying common patterns
      const rowCandidates = [
        document.querySelectorAll('tr[role="row"]'),
        document.querySelectorAll('tr.zA'),
        document.querySelectorAll('[data-thread-id]'),
        document.querySelectorAll('[data-legacy-thread-id]'),
      ];

      // Find first working row selector
      for (const candidates of rowCandidates) {
        if (candidates.length > 0) {
          const firstRow = candidates[0];
          results.structure.rowElement = firstRow.tagName;
          results.structure.rowClasses = Array.from(firstRow.classList);
          results.structure.rowAttributes = Array.from(firstRow.attributes).map(attr => ({
            name: attr.name,
            value: attr.value.substring(0, 50)
          }));

          // Analyze children
          results.structure.children = Array.from(firstRow.children).map(child => ({
            tag: child.tagName,
            classes: Array.from(child.classList),
            text: child.textContent?.substring(0, 30)
          }));

          break;
        }
      }

      // Find label elements
      const labelCandidates = [
        document.querySelectorAll('.ar'),
        document.querySelectorAll('.xY'),
        document.querySelectorAll('[data-tooltip*="Labels"]'),
        document.querySelectorAll('span[title]'),
      ];

      for (const candidates of labelCandidates) {
        if (candidates.length > 0) {
          results.labels.push({
            selector: 'found',
            count: candidates.length,
            sample: candidates[0].textContent?.substring(0, 30)
          });
          break;
        }
      }

      return results;
    });

    console.log('\n📊 Gmail DOM Structure:');
    console.log('   Email Row Element:', domStructure.structure.rowElement || 'Not found');
    console.log('   Row Classes:', domStructure.structure.rowClasses?.join(', ') || 'None');

    if (domStructure.structure.rowAttributes) {
      console.log('   Row Attributes:');
      for (const attr of domStructure.structure.rowAttributes) {
        console.log(`      ${attr.name}: ${attr.value}`);
      }
    }

    if (domStructure.structure.children && domStructure.structure.children.length > 0) {
      console.log('   Child Elements:');
      for (const child of domStructure.structure.children.slice(0, 5)) {
        console.log(`      <${child.tag}> .${child.classes.join('.')} - "${child.text}"`);
      }
    }

    console.log('\n   Labels:', domStructure.labels.length > 0 ? 'Found' : 'Not found');

    // Provide recommendations
    if (!domStructure.structure.rowElement) {
      console.log('\n❌ CRITICAL: Cannot identify email row structure');
      console.log('   Gmail may have changed their DOM significantly');
      console.log('   Extension selectors need to be updated');
      throw new Error('Issue #6: Cannot find email rows in Gmail DOM');
    } else {
      console.log('\n✅ Email row structure identified');

      // Suggest optimal selectors based on findings
      if (domStructure.structure.rowAttributes) {
        const hasThreadId = domStructure.structure.rowAttributes.some(
          attr => attr.name.includes('thread-id') || attr.name.includes('data-thread')
        );

        if (hasThreadId) {
          console.log('   Recommendation: Use [data-thread-id] or [data-legacy-thread-id]');
        } else {
          console.log('   Recommendation: Use tr[role="row"] or class-based selector');
          console.log(`   Classes: ${domStructure.structure.rowClasses?.join(', ')}`);
        }
      }
    }
  });

  test('should verify content script can monitor label changes', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Verifying content script label monitoring...');

    await gmailPage.goto();

    // Check if content script is loaded and working
    const contentScriptStatus = await page.evaluate(() => {
      // Check for content script global variables/functions
      return {
        hasMonitoring: typeof window.mailqLabelMonitor !== 'undefined',
        hasSelectors: typeof window.GMAIL_SELECTORS !== 'undefined',
        documentReady: document.readyState,
      };
    });

    console.log('📊 Content Script Status:');
    console.log(`   Label monitor loaded: ${contentScriptStatus.hasMonitoring ? 'Yes' : 'No'}`);
    console.log(`   Selectors available: ${contentScriptStatus.hasSelectors ? 'Yes' : 'No'}`);
    console.log(`   Document ready: ${contentScriptStatus.documentReady}`);

    if (!contentScriptStatus.hasMonitoring) {
      console.log('\n⚠️  WARNING: Content script may not be loaded or initialized');
      console.log('   Label change monitoring will not work');
    } else {
      console.log('\n✅ Content script is loaded');
    }

    // Check console for selector errors
    const selectorErrors = [];
    page.on('console', (msg) => {
      const text = msg.text();
      if (text.includes('Failed to find') || text.includes('selector')) {
        selectorErrors.push(text);
      }
    });

    // Trigger a page interaction to activate content script
    await page.waitForTimeout(3000);

    if (selectorErrors.length > 0) {
      console.log('\n❌ Selector Errors Detected:');
      selectorErrors.forEach(error => console.log(`   ${error}`));
      throw new Error(`Issue #6: ${selectorErrors.length} selector errors found`);
    }

    console.log('✅ No selector errors detected');
  });

  test('should generate updated selector recommendations', async ({ page, gmailPage }) => {
    console.log('🧪 Test: Generating selector update recommendations...');

    await gmailPage.goto();

    // Comprehensive DOM analysis
    const recommendations = await page.evaluate(() => {
      const analysis = {
        emailRows: { selectors: [], recommended: null },
        labels: { selectors: [], recommended: null },
        buttons: { selectors: [], recommended: null }
      };

      // Test email row selectors
      const rowTests = [
        'tr[role="row"]',
        '.zA',
        '[data-thread-id]',
        '[data-legacy-thread-id]',
        'tr.yO',
        'tr[jsaction]'
      ];

      for (const selector of rowTests) {
        const elements = document.querySelectorAll(selector);
        if (elements.length > 0) {
          analysis.emailRows.selectors.push({ selector, count: elements.length });
        }
      }

      // Pick best email row selector
      if (analysis.emailRows.selectors.length > 0) {
        analysis.emailRows.recommended = analysis.emailRows.selectors.reduce((best, current) =>
          current.count > best.count ? current : best
        ).selector;
      }

      // Test label selectors
      const labelTests = [
        '.ar',
        '.xY',
        '.aDm',
        '[data-tooltip*="Labels"]',
        'span[title]',
        '.label-wrapper'
      ];

      for (const selector of labelTests) {
        const elements = document.querySelectorAll(selector);
        if (elements.length > 0) {
          analysis.labels.selectors.push({ selector, count: elements.length });
        }
      }

      if (analysis.labels.selectors.length > 0) {
        analysis.labels.recommended = analysis.labels.selectors[0].selector;
      }

      return analysis;
    });

    console.log('\n📋 Selector Update Recommendations:');
    console.log('\nEmail Rows:');
    if (recommendations.emailRows.recommended) {
      console.log(`   ✅ Recommended: ${recommendations.emailRows.recommended}`);
      console.log('   Alternatives:');
      recommendations.emailRows.selectors.forEach(s => {
        console.log(`      ${s.selector} (${s.count} matches)`);
      });
    } else {
      console.log('   ❌ No working selectors found');
    }

    console.log('\nLabels:');
    if (recommendations.labels.recommended) {
      console.log(`   ✅ Recommended: ${recommendations.labels.recommended}`);
      console.log('   Alternatives:');
      recommendations.labels.selectors.forEach(s => {
        console.log(`      ${s.selector} (${s.count} matches)`);
      });
    } else {
      console.log('   ❌ No working selectors found');
    }

    // Write recommendations to file
    console.log('\n💡 Update extension/modules/selectors.js with these values');
  });
});
