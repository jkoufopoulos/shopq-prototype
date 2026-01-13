/**
 * Digest Validation Test - Cross-reference organized emails vs digest output
 *
 * Validates:
 * 1. All classified emails appear in digest (featured, orphaned, or noise)
 * 2. Entity numbers match correctly
 * 3. Weather enrichment works
 * 4. Noise summary has correct counts
 * 5. Visual output matches backend data
 */

import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

test.describe('Digest Validation - Classified vs Visual Output', () => {

  test('should accurately represent all classified emails in digest', async ({ page }) => {
    const sessionId = Date.now();
    const debugDir = path.join('test-results', `validation-${sessionId}`);
    fs.mkdirSync(debugDir, { recursive: true });

    const report = {
      sessionId,
      timestamp: new Date().toISOString(),
      phase1_classified: null,
      phase2_digest: null,
      phase3_crossReference: null,
      issues: [],
      screenshots: [],
      success: false
    };

    try {
      // ============================================================
      // PHASE 1: Capture what was classified/organized
      // ============================================================
      console.log('\n📋 PHASE 1: Capturing classified emails...');

      await page.goto('https://mail.google.com/mail/u/0/#inbox');
      await page.waitForTimeout(3000);

      await page.screenshot({
        path: path.join(debugDir, '01-inbox-before-organize.png'),
        fullPage: true
      });
      report.screenshots.push('01-inbox-before-organize.png');

      // Trigger organize (reload to run extension)
      console.log('⚙️  Triggering organize...');
      await page.reload();
      await page.waitForTimeout(10000); // Wait for classify to complete

      await page.screenshot({
        path: path.join(debugDir, '02-after-organize.png'),
        fullPage: true
      });
      report.screenshots.push('02-after-organize.png');

      // Get classification data from extension logger
      const classifiedEmails = await page.evaluate(async () => {
        // Access the logger database
        const db = await new Promise((resolve, reject) => {
          const request = indexedDB.open('MailQLogger', 1);
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        });

        const tx = db.transaction(['classifications'], 'readonly');
        const store = tx.objectStore('classifications');
        const all = await new Promise(resolve => {
          const req = store.getAll();
          req.onsuccess = () => resolve(req.result);
        });

        // Get recent classifications (last 15 minutes)
        const fifteenMinutesAgo = new Date(Date.now() - 15 * 60 * 1000).toISOString();
        const recent = all.filter(c => c.timestamp >= fifteenMinutesAgo);

        return recent.map(c => ({
          subject: c.subject,
          from: c.from,
          messageId: c.messageId,
          threadId: c.threadId,
          type: c.classification.type,
          domains: c.classification.domains,
          attention: c.classification.attention,
          emailTimestamp: c.emailTimestamp,
          hasEmailTimestamp: !!c.emailTimestamp
        }));
      });

      report.phase1_classified = {
        totalEmails: classifiedEmails.length,
        emails: classifiedEmails,
        hasTimestamps: classifiedEmails.filter(e => e.hasEmailTimestamp).length
      };

      console.log(`✅ Captured ${classifiedEmails.length} classified emails`);
      console.log(`   ${report.phase1_classified.hasTimestamps}/${classifiedEmails.length} have emailTimestamp`);

      fs.writeFileSync(
        path.join(debugDir, 'classified-emails.json'),
        JSON.stringify(classifiedEmails, null, 2)
      );

      // ============================================================
      // PHASE 2: Capture the digest email
      // ============================================================
      console.log('\n📧 PHASE 2: Capturing digest email...');

      // Wait for digest email to appear
      await page.waitForTimeout(5000);

      // Find and open digest
      const digestEmail = await page.locator('span:has-text("Your Inbox --")').first();
      await digestEmail.waitFor({ timeout: 20000 });
      await digestEmail.click();
      await page.waitForTimeout(3000);

      await page.screenshot({
        path: path.join(debugDir, '03-digest-opened.png'),
        fullPage: true
      });
      report.screenshots.push('03-digest-opened.png');

      // Extract digest content
      const digestText = await page.locator('[role="main"]').innerText();
      const digestHTML = await page.locator('[role="main"]').innerHTML();

      fs.writeFileSync(path.join(debugDir, 'digest-text.txt'), digestText);
      fs.writeFileSync(path.join(debugDir, 'digest-html.html'), digestHTML);

      // Parse digest components
      const digestData = {
        fullText: digestText,
        greeting: null,
        weather: null,
        featuredItems: [],
        noiseSection: null,
        entityReferences: []
      };

      // Extract weather
      const weatherMatch = digestText.match(/(cloudy|sunny|rainy|snowy|clear)\s+(\d+)°/i);
      if (weatherMatch) {
        digestData.weather = {
          condition: weatherMatch[1],
          temp: weatherMatch[2]
        };
      }

      // Extract entity numbers
      const numberPattern = /\((\d+)\)/g;
      let match;
      while ((match = numberPattern.exec(digestText)) !== null) {
        digestData.entityReferences.push(parseInt(match[1]));
      }

      // Extract noise section
      const noiseMatch = digestText.match(/(\d+)\s+notifications?\s+\((.*?)\)/i);
      if (noiseMatch) {
        digestData.noiseSection = {
          total: parseInt(noiseMatch[1]),
          breakdown: noiseMatch[2]
        };
      }

      report.phase2_digest = digestData;

      console.log(`✅ Digest captured`);
      console.log(`   Weather: ${digestData.weather ? 'YES' : 'NO'}`);
      console.log(`   Entity refs: ${digestData.entityReferences.join(', ')}`);
      console.log(`   Noise section: ${digestData.noiseSection ? 'YES' : 'NO'}`);

      // ============================================================
      // PHASE 3: Cross-reference with backend
      // ============================================================
      console.log('\n🔍 PHASE 3: Cross-referencing with backend...');

      // Get backend tracking data
      const backendResponse = await page.request.get('http://localhost:8000/api/tracking/session/latest');
      const backendData = await backendResponse.json();

      fs.writeFileSync(
        path.join(debugDir, 'backend-tracking.json'),
        JSON.stringify(backendData, null, 2)
      );

      const crossRef = {
        backend: {
          totalThreads: backendData.summary.total_threads,
          critical: backendData.summary.importance.critical,
          timeSensitive: backendData.summary.importance.time_sensitive,
          routine: backendData.summary.importance.routine,
          entitiesExtracted: backendData.summary.entities_extracted,
          featured: backendData.summary.digest_breakdown.featured,
          orphaned: backendData.summary.digest_breakdown.orphaned,
          noise: backendData.summary.digest_breakdown.noise
        },
        digest: {
          entityRefsCount: digestData.entityReferences.length,
          uniqueRefs: [...new Set(digestData.entityReferences)],
          noiseCount: digestData.noiseSection ? digestData.noiseSection.total : 0
        },
        mismatches: []
      };

      report.phase3_crossReference = crossRef;

      // ============================================================
      // VALIDATION: Check for issues
      // ============================================================
      console.log('\n✅ VALIDATION: Checking for issues...');

      // Issue 1: Entity count mismatch
      if (crossRef.digest.uniqueRefs.length !== crossRef.backend.featured) {
        const issue = {
          type: 'ENTITY_COUNT_MISMATCH',
          severity: 'ERROR',
          expected: crossRef.backend.featured,
          actual: crossRef.digest.uniqueRefs.length,
          message: `Digest shows ${crossRef.digest.uniqueRefs.length} entity refs but backend has ${crossRef.backend.featured} featured`,
          debugSteps: [
            'Check entity extraction success rate',
            'Verify timeline synthesis selection logic',
            'Check entity linking in card renderer'
          ]
        };
        report.issues.push(issue);
        console.log(`❌ ${issue.type}: ${issue.message}`);
      }

      // Issue 2: Noise count mismatch
      if (crossRef.digest.noiseCount !== crossRef.backend.noise) {
        const issue = {
          type: 'NOISE_COUNT_MISMATCH',
          severity: 'ERROR',
          expected: crossRef.backend.noise,
          actual: crossRef.digest.noiseCount,
          message: `Digest shows ${crossRef.digest.noiseCount} noise items but backend has ${crossRef.backend.noise}`,
          debugSteps: [
            'Check noise summary generation',
            'Verify routine email categorization',
            'Check narrative prompt noise section'
          ]
        };
        report.issues.push(issue);
        console.log(`❌ ${issue.type}: ${issue.message}`);
      }

      // Issue 3: Weather missing
      if (!digestData.weather) {
        const issue = {
          type: 'WEATHER_MISSING',
          severity: 'WARNING',
          message: 'No weather information found in digest',
          debugSteps: [
            'Check weather API response',
            'Verify location detection',
            'Check narrative prompt weather section'
          ]
        };
        report.issues.push(issue);
        console.log(`⚠️  ${issue.type}: ${issue.message}`);
      }

      // Issue 4: Missing temporal awareness
      const hasAgeMarkers = /\[\d+ days? old\]|\[email from \d+ days? ago\]/.test(digestText);
      if (!hasAgeMarkers && classifiedEmails.length > 0) {
        const issue = {
          type: 'TEMPORAL_AWARENESS_MISSING',
          severity: 'ERROR',
          message: 'No age markers found in digest despite having classified emails',
          debugSteps: [
            'Check if emailTimestamp is logged',
            'Verify backend receives timestamps',
            'Check entity timestamp parsing',
            'Verify age marker generation in timeline_synthesizer.py'
          ]
        };
        report.issues.push(issue);
        console.log(`❌ ${issue.type}: ${issue.message}`);
      }

      // Issue 5: Coverage gap
      const totalRepresented = crossRef.backend.featured + crossRef.backend.orphaned + crossRef.backend.noise;
      if (totalRepresented !== crossRef.backend.totalThreads) {
        const gap = crossRef.backend.totalThreads - totalRepresented;
        const issue = {
          type: 'COVERAGE_GAP',
          severity: 'ERROR',
          message: `${gap} emails not represented in digest`,
          missing: gap,
          debugSteps: [
            'Check timeline synthesis logic',
            'Verify importance classification',
            'Check entity extraction failures'
          ]
        };
        report.issues.push(issue);
        console.log(`❌ ${issue.type}: ${issue.message} (${gap} emails)`);
      }

      // Issue 6: Entity reference continuity
      const sortedRefs = [...crossRef.digest.uniqueRefs].sort((a, b) => a - b);
      for (let i = 0; i < sortedRefs.length; i++) {
        if (sortedRefs[i] !== i + 1) {
          const issue = {
            type: 'ENTITY_REF_GAP',
            severity: 'ERROR',
            message: `Entity references not continuous: expected ${i + 1}, found ${sortedRefs[i]}`,
            expected: Array.from({ length: sortedRefs.length }, (_, i) => i + 1),
            actual: sortedRefs,
            debugSteps: [
              'Check entity linking in card_renderer.py',
              'Verify featured entities ordering',
              'Check narrative prompt entity numbering'
            ]
          };
          report.issues.push(issue);
          console.log(`❌ ${issue.type}: ${issue.message}`);
          break;
        }
      }

      // ============================================================
      // GENERATE COMPREHENSIVE REPORT
      // ============================================================

      report.success = report.issues.filter(i => i.severity === 'ERROR').length === 0;

      const summary = `
# Digest Validation Report
**Session**: ${sessionId}
**Time**: ${report.timestamp}
**Status**: ${report.success ? '✅ PASSED' : '❌ FAILED'}

---

## Phase 1: Classified Emails
- **Total classified**: ${report.phase1_classified.totalEmails}
- **With timestamps**: ${report.phase1_classified.hasTimestamps}/${report.phase1_classified.totalEmails}

${report.phase1_classified.emails.slice(0, 5).map((e, i) => `
### Email ${i + 1}
- **Subject**: ${e.subject}
- **Type**: ${e.type}
- **Domains**: ${e.domains.join(', ')}
- **Attention**: ${e.attention}
- **Has timestamp**: ${e.hasEmailTimestamp ? '✅' : '❌'}
`).join('\n')}

---

## Phase 2: Digest Output
- **Weather**: ${digestData.weather ? `${digestData.weather.condition} ${digestData.weather.temp}°` : '❌ Missing'}
- **Entity refs**: ${digestData.entityReferences.join(', ')}
- **Noise section**: ${digestData.noiseSection ? `${digestData.noiseSection.total} (${digestData.noiseSection.breakdown})` : '❌ Missing'}

### Full Digest
\`\`\`
${digestData.fullText}
\`\`\`

---

## Phase 3: Cross-Reference

### Backend Data
| Metric | Count |
|--------|-------|
| Total Threads | ${crossRef.backend.totalThreads} |
| Critical | ${crossRef.backend.critical} |
| Time-Sensitive | ${crossRef.backend.timeSensitive} |
| Routine | ${crossRef.backend.routine} |
| Entities Extracted | ${crossRef.backend.entitiesExtracted} |
| **Featured** | **${crossRef.backend.featured}** |
| **Orphaned** | **${crossRef.backend.orphaned}** |
| **Noise** | **${crossRef.backend.noise}** |

### Digest Data
| Metric | Count |
|--------|-------|
| Entity References | ${crossRef.digest.uniqueRefs.length} |
| Unique Refs | ${crossRef.digest.uniqueRefs.join(', ')} |
| Noise Count | ${crossRef.digest.noiseCount} |

---

## Issues Found: ${report.issues.length}

${report.issues.map(issue => `
### ${issue.type} (${issue.severity})
**Message**: ${issue.message}

**Debug Steps**:
${issue.debugSteps.map(s => `- ${s}`).join('\n')}

${issue.expected ? `**Expected**: ${JSON.stringify(issue.expected)}` : ''}
${issue.actual ? `**Actual**: ${JSON.stringify(issue.actual)}` : ''}
`).join('\n---\n')}

---

## Screenshots
${report.screenshots.map(s => `- \`${s}\``).join('\n')}

---

## Files Generated
- \`classified-emails.json\` - All classified emails from extension
- \`backend-tracking.json\` - Backend tracking data
- \`digest-text.txt\` - Plain text digest
- \`digest-html.html\` - HTML digest
- \`report.json\` - Full structured report
- \`summary.md\` - This file

---

## Next Steps

${report.success ? `
✅ **All validations passed!** The digest accurately represents classified emails.
` : `
❌ **Validation failed.** Fix the issues above and re-run the test.

### For Claude Code:
1. Read this file: \`cat ${debugDir}/CLAUDE_ANALYSIS.md\`
2. View screenshots: \`open ${debugDir}/*.png\`
3. Check backend logs: \`tail -100 /tmp/mailq-backend.log\`
4. Make fixes based on issue debug steps
5. Re-run test: \`./test-digest-quality.sh\`
`}
      `;

      fs.writeFileSync(path.join(debugDir, 'summary.md'), summary);

      // Generate Claude-specific analysis
      const claudeAnalysis = `
# Claude Code Analysis - Digest Validation

## Quick Summary
- **Total Issues**: ${report.issues.length}
- **Errors**: ${report.issues.filter(i => i.severity === 'ERROR').length}
- **Warnings**: ${report.issues.filter(i => i.severity === 'WARNING').length}
- **Status**: ${report.success ? '✅ PASS' : '❌ FAIL'}

## What Was Tested
1. ✅ Classified ${report.phase1_classified.totalEmails} emails from inbox
2. ✅ Captured digest email output
3. ✅ Cross-referenced backend tracking data
4. ✅ Validated entity numbers, noise counts, weather, temporal awareness

## Issues Requiring Fixes

${report.issues.map((issue, i) => `
### Issue ${i + 1}: ${issue.type}
**Severity**: ${issue.severity}
**Message**: ${issue.message}

**Root Cause Analysis**:
${issue.type === 'ENTITY_COUNT_MISMATCH' ? `
The digest shows ${issue.actual} numbered references but backend says ${issue.expected} were featured.
This means either:
- Entity linking is broken (card_renderer.py)
- Timeline synthesis isn't selecting the right entities
- Entity extraction failed for some emails
` : ''}
${issue.type === 'TEMPORAL_AWARENESS_MISSING' ? `
No age markers like "[5 days old]" found in digest.
This means:
- emailTimestamp not being logged (check logger.js)
- Backend not receiving timestamps (check api.py)
- Entity extractor not parsing timestamps (check entity_extractor.py)
- Age markers not being generated (check timeline_synthesizer.py)
` : ''}
${issue.type === 'NOISE_COUNT_MISMATCH' ? `
Digest says ${issue.actual} noise items but backend says ${issue.expected}.
This means:
- Noise summary not being generated correctly
- categorize_routine() logic is wrong
- Narrative prompt isn't using noise data
` : ''}

**Files to Check**:
${issue.debugSteps.map(step => {
  if (step.includes('entity extraction')) return '- mailq/entity_extractor.py';
  if (step.includes('timeline')) return '- mailq/timeline_synthesizer.py';
  if (step.includes('noise')) return '- mailq/importance_classifier.py (categorize_routine)';
  if (step.includes('timestamp')) return '- extension/modules/logger.js\n- mailq/api.py\n- mailq/entity_extractor.py';
  if (step.includes('weather')) return '- mailq/weather_enrichment.py\n- mailq/narrative_generator.py';
  if (step.includes('narrative')) return '- mailq/prompts/narrative_prompt_v2_grouped.txt';
  return '';
}).filter(f => f).join('\n')}

**Recommended Fix**:
${issue.debugSteps[0]}
`).join('\n---\n')}

## Evidence Files
- **Screenshots**: ${report.screenshots.join(', ')}
- **Classified emails**: classified-emails.json
- **Backend data**: backend-tracking.json
- **Digest content**: digest-text.txt, digest-html.html

## How to Fix

1. **Read the summary**: \`cat ${debugDir}/summary.md\`
2. **View screenshots**: \`open ${debugDir}/*.png\`
3. **Check specific issue**: Read root cause analysis above
4. **Make targeted fix**: Edit the files listed
5. **Re-run test**: \`./test-digest-quality.sh\`
6. **Verify**: Check that issue is resolved

## Example Fix Workflow

\`\`\`bash
# 1. Read this file
cat ${debugDir}/CLAUDE_ANALYSIS.md

# 2. View evidence
open ${debugDir}/03-digest-opened.png
cat ${debugDir}/digest-text.txt
jq . ${debugDir}/backend-tracking.json

# 3. Make fix (example: timestamp issue)
# Edit extension/modules/logger.js to add emailTimestamp
# Edit mailq/api.py to extract emailTimestamp

# 4. Restart backend
pkill -f uvicorn
uvicorn mailq.api:app --reload --port 8000 &

# 5. Re-test
./test-digest-quality.sh
\`\`\`
      `;

      fs.writeFileSync(path.join(debugDir, 'CLAUDE_ANALYSIS.md'), claudeAnalysis);

      // Save full report
      fs.writeFileSync(
        path.join(debugDir, 'report.json'),
        JSON.stringify(report, null, 2)
      );

      console.log('\n' + '='.repeat(80));
      console.log('📊 DIGEST VALIDATION COMPLETE');
      console.log('='.repeat(80));
      console.log(summary);
      console.log('='.repeat(80));
      console.log(`\n📁 Report: ${debugDir}`);
      console.log('='.repeat(80) + '\n');

      // Assertions
      expect(report.issues.filter(i => i.severity === 'ERROR').length).toBe(0);

    } catch (error) {
      report.issues.push({
        type: 'TEST_EXECUTION_ERROR',
        severity: 'ERROR',
        message: error.message,
        stack: error.stack
      });

      await page.screenshot({
        path: path.join(debugDir, 'ERROR.png'),
        fullPage: true
      });

      fs.writeFileSync(
        path.join(debugDir, 'report.json'),
        JSON.stringify(report, null, 2)
      );

      throw error;
    }
  });
});
