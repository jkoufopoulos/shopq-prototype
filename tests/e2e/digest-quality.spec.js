/**
 * Digest Quality Test with Visual Debugging
 *
 * Captures screenshots, HTML snapshots, and detailed logs for Claude to analyze
 */

const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('Digest Quality Analysis', () => {

  test('should generate digest with temporal awareness', async ({ page, gmailPage }) => {
    const sessionId = Date.now();
    const debugDir = path.join('test-results', `digest-${sessionId}`);

    // Create debug directory
    fs.mkdirSync(debugDir, { recursive: true });

    const report = {
      sessionId,
      timestamp: new Date().toISOString(),
      steps: [],
      errors: [],
      screenshots: [],
      expectations: {
        allEmailsRepresented: false,
        temporalAwarenessPresent: false,
        ageMarkersFound: [],
        missingEmails: []
      }
    };

    try {
      // Step 1: Navigate to Gmail
      report.steps.push({ step: 'navigate', status: 'started', time: Date.now() });
      await page.goto('https://mail.google.com/mail/u/0/#inbox');
      await page.waitForTimeout(3000);

      await page.screenshot({
        path: path.join(debugDir, '01-gmail-loaded.png'),
        fullPage: true
      });
      report.screenshots.push('01-gmail-loaded.png');
      report.steps[0].status = 'completed';

      // Step 2: Find the digest email
      report.steps.push({ step: 'find_digest', status: 'started', time: Date.now() });

      const digestEmail = await page.locator('span:has-text("Your Inbox --")').first();
      await digestEmail.waitFor({ timeout: 10000 });

      // Click to open
      await digestEmail.click();
      await page.waitForTimeout(2000);

      await page.screenshot({
        path: path.join(debugDir, '02-digest-opened.png'),
        fullPage: true
      });
      report.screenshots.push('02-digest-opened.png');
      report.steps[1].status = 'completed';

      // Step 3: Extract digest content
      report.steps.push({ step: 'extract_content', status: 'started', time: Date.now() });

      const digestContent = await page.locator('[role="main"]').innerText();

      // Save digest text
      fs.writeFileSync(
        path.join(debugDir, 'digest-content.txt'),
        digestContent
      );

      // Save digest HTML
      const digestHTML = await page.locator('[role="main"]').innerHTML();
      fs.writeFileSync(
        path.join(debugDir, 'digest-content.html'),
        digestHTML
      );

      report.digestContent = digestContent;
      report.steps[2].status = 'completed';

      // Step 4: Analyze for temporal awareness
      report.steps.push({ step: 'analyze_temporal', status: 'started', time: Date.now() });

      // Check for age markers
      const agePatterns = [
        /\[(\d+) days? old\]/gi,
        /\[email from (\d+) days? ago\]/gi,
        /(\d+) days? ago/gi,
        /from (\d+) days? ago/gi
      ];

      for (const pattern of agePatterns) {
        const matches = digestContent.matchAll(pattern);
        for (const match of matches) {
          report.expectations.ageMarkersFound.push({
            text: match[0],
            days: match[1]
          });
        }
      }

      report.expectations.temporalAwarenessPresent = report.expectations.ageMarkersFound.length > 0;
      report.steps[3].status = 'completed';

      // Step 5: Check email coverage (fetch backend tracking data)
      report.steps.push({ step: 'check_coverage', status: 'started', time: Date.now() });

      try {
        // Extract session ID from digest subject
        const subjectMatch = digestContent.match(/Friday, October 31 at (\d+:\d+)/);

        // Fetch latest session tracking data
        const backendResponse = await page.request.get('http://localhost:8000/api/tracking/session/latest');
        const trackingData = await backendResponse.json();

        fs.writeFileSync(
          path.join(debugDir, 'tracking-data.json'),
          JSON.stringify(trackingData, null, 2)
        );

        report.trackingData = trackingData;

        // Check coverage
        const summary = trackingData.summary;
        const totalEmails = summary.total_threads;
        const featured = summary.digest_breakdown.featured;
        const orphaned = summary.digest_breakdown.orphaned;
        const noise = summary.digest_breakdown.noise;

        report.expectations.allEmailsRepresented = (featured + orphaned + noise) === totalEmails;

        // Find missing emails
        if (!report.expectations.allEmailsRepresented) {
          trackingData.threads.forEach(thread => {
            if (!thread.in_featured && !thread.in_orphaned && !thread.in_noise) {
              report.expectations.missingEmails.push({
                subject: thread.subject,
                importance: thread.importance,
                entity_extracted: thread.entity_extracted
              });
            }
          });
        }

        report.steps[4].status = 'completed';
      } catch (error) {
        report.errors.push({
          step: 'check_coverage',
          error: error.message,
          stack: error.stack
        });
        report.steps[4].status = 'failed';
      }

      // Step 6: Visual comparison (capture entity references)
      report.steps.push({ step: 'capture_entities', status: 'started', time: Date.now() });

      const entityReferences = [];
      const numberPattern = /\((\d+)\)/g;
      let match;
      while ((match = numberPattern.exec(digestContent)) !== null) {
        entityReferences.push(parseInt(match[1]));
      }

      report.entityReferences = entityReferences;
      report.steps[5].status = 'completed';

      // Save comprehensive report
      fs.writeFileSync(
        path.join(debugDir, 'report.json'),
        JSON.stringify(report, null, 2)
      );

      // Generate human-readable summary
      const summary = `
# Digest Quality Report
**Session**: ${sessionId}
**Time**: ${report.timestamp}

## Screenshots
${report.screenshots.map(s => `- ${s}`).join('\n')}

## Temporal Awareness
- **Age markers found**: ${report.expectations.ageMarkersFound.length}
${report.expectations.ageMarkersFound.map(m => `  - "${m.text}" (${m.days} days)`).join('\n')}
- **Temporal awareness present**: ${report.expectations.temporalAwarenessPresent ? '✅ YES' : '❌ NO'}

## Email Coverage
- **All emails represented**: ${report.expectations.allEmailsRepresented ? '✅ YES' : '❌ NO'}
- **Missing emails**: ${report.expectations.missingEmails.length}
${report.expectations.missingEmails.map(e => `  - ${e.subject.substring(0, 60)} (${e.importance}, entity: ${e.entity_extracted})`).join('\n')}

## Entity References
${report.entityReferences.map(n => `- (${n})`).join(', ')}

## Digest Content
\`\`\`
${report.digestContent}
\`\`\`

## Errors
${report.errors.length > 0 ? report.errors.map(e => `- ${e.step}: ${e.error}`).join('\n') : 'None'}
      `;

      fs.writeFileSync(
        path.join(debugDir, 'summary.md'),
        summary
      );

      console.log('\n' + '='.repeat(80));
      console.log('📊 DIGEST QUALITY REPORT');
      console.log('='.repeat(80));
      console.log(summary);
      console.log('='.repeat(80));
      console.log(`\n📁 Full report saved to: ${debugDir}`);
      console.log('='.repeat(80) + '\n');

      // Assertions
      expect(report.expectations.temporalAwarenessPresent).toBe(true);
      expect(report.expectations.allEmailsRepresented).toBe(true);

    } catch (error) {
      report.errors.push({
        step: 'test_execution',
        error: error.message,
        stack: error.stack
      });

      // Save error report
      fs.writeFileSync(
        path.join(debugDir, 'report.json'),
        JSON.stringify(report, null, 2)
      );

      // Capture error screenshot
      await page.screenshot({
        path: path.join(debugDir, 'ERROR.png'),
        fullPage: true
      });

      throw error;
    }
  });
});
