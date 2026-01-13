/**
 * Email Classification Module
 */

/**
 * Print session summary at the end of classification
 * @param {Array} emails - All input emails
 * @param {Array} cached - Emails from cache
 * @param {Array} detected - Emails from detectors
 * @param {Array} llmResults - Emails classified by LLM
 * @param {number} verifierChecked - Number of verifications performed
 * @param {number} verifierFlips - Number of corrections made
 * @param {number} uniqueSendersCount - Total unique senders sent to LLM
 */
function printSessionSummary(emails, cached, detected, llmResults, verifierChecked, verifierFlips, uniqueSendersCount) {
  const allResults = [...cached, ...detected, ...llmResults];

  console.log('\n' + '═'.repeat(70));
  console.log('📊 SESSION CLASSIFICATION SUMMARY');
  console.log('═'.repeat(70));
  console.log(`   Total emails:     ${emails.length}`);
  console.log(`   ├─ From cache:    ${cached.length} (${((cached.length/emails.length)*100).toFixed(0)}%)`);
  console.log(`   ├─ From detectors: ${detected.length} (${((detected.length/emails.length)*100).toFixed(0)}%)`);
  console.log(`   └─ From LLM:      ${llmResults.length} (${((llmResults.length/emails.length)*100).toFixed(0)}%)`);
  console.log('');
  console.log(`   Verifier:         ${verifierFlips > 0 ? `${verifierFlips} corrections made` : 'No corrections needed'}`);
  console.log(`   └─ Checked:       ${verifierChecked}/${uniqueSendersCount || llmResults.length} (low/mid confidence only)`);
  console.log('');

  // Type breakdown for all results
  const allTypeBreakdown = {};
  for (const r of allResults) {
    const t = r.type || 'unknown';
    allTypeBreakdown[t] = (allTypeBreakdown[t] || 0) + 1;
  }
  const allTypeStr = Object.entries(allTypeBreakdown)
    .sort((a, b) => b[1] - a[1])
    .map(([t, n]) => `${t}: ${n}`)
    .join(', ');
  console.log(`   Types:            ${allTypeStr}`);
  console.log('');

  // Collect per-dimension confidence values
  const typeConfs = [];
  const attentionConfs = [];
  const importanceConfs = [];
  const minConfs = [];
  const lowConfEmails = [];  // Track emails with low confidence

  for (const r of allResults) {
    const typeConf = r.type_conf || 0;
    const attentionConf = r.attention_conf || 0;
    const importanceConf = r.importance_conf || 0;

    typeConfs.push(typeConf);
    if (attentionConf > 0) attentionConfs.push(attentionConf);
    if (importanceConf > 0) importanceConfs.push(importanceConf);

    const minConf = Math.min(typeConf, attentionConf || 1, importanceConf || 1);
    minConfs.push(minConf);

    // Track low confidence emails for detailed view
    if (minConf < 0.70) {
      const lowestDim = typeConf <= attentionConf && typeConf <= importanceConf ? 'type'
        : attentionConf <= importanceConf ? 'attention' : 'importance';
      const lowestVal = Math.min(typeConf, attentionConf || 1, importanceConf || 1);
      lowConfEmails.push({
        subject: r.subject || 'Unknown',
        dimension: lowestDim,
        value: lowestVal,
        type: r.type
      });
    }
  }

  // Helper to calc stats
  const calcStats = (arr) => {
    if (arr.length === 0) return { avg: 'N/A', min: 'N/A', max: 'N/A' };
    const avg = (arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(2);
    const min = Math.min(...arr).toFixed(2);
    const max = Math.max(...arr).toFixed(2);
    return { avg, min, max };
  };

  // Overall confidence (minimum across dimensions)
  const overall = calcStats(minConfs);
  console.log(`   Confidence (min): avg=${overall.avg}, min=${overall.min}, max=${overall.max}`);
  console.log('');

  // Per-dimension stats
  const typeStats = calcStats(typeConfs);
  const attentionStats = calcStats(attentionConfs);
  const importanceStats = calcStats(importanceConfs);

  console.log('   By Dimension:');
  console.log(`   ├─ Type:       avg=${typeStats.avg}, min=${typeStats.min}, max=${typeStats.max}`);
  console.log(`   ├─ Attention:  avg=${attentionStats.avg}, min=${attentionStats.min}, max=${attentionStats.max}`);
  console.log(`   └─ Importance: avg=${importanceStats.avg}, min=${importanceStats.min}, max=${importanceStats.max}`);
  console.log('');

  // Histogram distribution (finer buckets)
  const histogram = {
    '0.95-1.00': 0,
    '0.90-0.95': 0,
    '0.85-0.90': 0,
    '0.80-0.85': 0,
    '0.70-0.80': 0,
    '<0.70': 0
  };

  for (const conf of minConfs) {
    if (conf >= 0.95) histogram['0.95-1.00']++;
    else if (conf >= 0.90) histogram['0.90-0.95']++;
    else if (conf >= 0.85) histogram['0.85-0.90']++;
    else if (conf >= 0.80) histogram['0.80-0.85']++;
    else if (conf >= 0.70) histogram['0.70-0.80']++;
    else histogram['<0.70']++;
  }

  console.log('   Distribution:');
  const maxCount = Math.max(...Object.values(histogram));
  const barScale = maxCount > 0 ? 20 / maxCount : 1;

  for (const [range, count] of Object.entries(histogram)) {
    const pct = ((count / allResults.length) * 100).toFixed(0);
    const bar = '█'.repeat(Math.round(count * barScale));
    console.log(`   ${range.padEnd(9)}: ${bar.padEnd(20)} ${count} (${pct}%)`);
  }

  // Low confidence details
  if (lowConfEmails.length > 0) {
    console.log('');
    console.log(`   ⚠️  Low Confidence (${lowConfEmails.length}):`);
    // Sort by confidence ascending (lowest first)
    lowConfEmails.sort((a, b) => a.value - b.value);
    // Show up to 5
    lowConfEmails.slice(0, 5).forEach((e, i) => {
      const prefix = i === lowConfEmails.slice(0, 5).length - 1 ? '└─' : '├─';
      const subjectPreview = e.subject.length > 40 ? e.subject.substring(0, 40) + '...' : e.subject;
      console.log(`   ${prefix} "${subjectPreview}" (${e.dimension}: ${e.value.toFixed(2)})`);
    });
    if (lowConfEmails.length > 5) {
      console.log(`      ... and ${lowConfEmails.length - 5} more`);
    }
  }

  // Count action required
  const allActionRequired = allResults.filter(r => r.attention === 'action_required').length;
  if (allActionRequired > 0) {
    console.log('');
    console.log(`   ⚠️  Action Required: ${allActionRequired} emails`);
  }
  console.log('═'.repeat(70) + '\n');
}

/**
 * Classify multiple emails using the API
 */
async function classifyEmails(emails) {
  console.log('🤖 Classifying emails...');

  // Check cache first
  const { cached, uncached } = await checkCache(emails);

  const cacheHitRate = (cached.length / emails.length * 100).toFixed(1);
  console.log(`📊 Cache hit: ${cacheHitRate}%`);

  // Re-log cached classifications with fresh timestamps for digest generation
  if (cached.length > 0 && typeof logger !== 'undefined') {
    for (const cachedEmail of cached) {
      // Cached email has all properties flattened (email + classification merged)
      // Extract email properties
      const email = {
        id: cachedEmail.id,
        from: cachedEmail.from,
        subject: cachedEmail.subject,
        snippet: cachedEmail.snippet,
        threadId: cachedEmail.threadId
      };

      // Extract classification properties
      const classification = {
        type: cachedEmail.type,
        type_conf: cachedEmail.type_conf,
        attention: cachedEmail.attention,
        attention_conf: cachedEmail.attention_conf,
        importance: cachedEmail.importance,
        importance_conf: cachedEmail.importance_conf,
        client_label: cachedEmail.client_label,
        relationship: cachedEmail.relationship,
        relationship_conf: cachedEmail.relationship_conf,
        decider: 'cache',
        reason: cachedEmail.reason
      };

      logger.logClassification(email, classification, cachedEmail.labels, {
        decider: 'cache',
        reused: true
      }).catch(err => console.warn('Failed to re-log cached classification:', err));
    }
  }

  if (uncached.length === 0) {
    console.log('✅ All emails found in cache');
    return cached;
  }

  console.log(`🔄 Classifying ${uncached.length}/${emails.length} new emails`);

  // Phase 2: Run detectors first (high-precision, T0/T1 rules)
  const detected = [];
  const undetected = [];

  for (const email of uncached) {
    const detectorResult = runDetectors(email);

    if (detectorResult) {
      // Detector hit! Create full result with email metadata + labels
      const mappedLabels = mapToLabels(detectorResult, email);
      const detectedEmail = {
        ...detectorResult,
        id: email.id,
        threadId: email.threadId,
        from: email.from,
        subject: email.subject,
        snippet: email.snippet,
        labels: mappedLabels
      };

      detected.push(detectedEmail);

      // Log detector classification
      if (typeof logger !== 'undefined') {
        logger.logClassification(email, detectorResult, detectedEmail.labels, {
          detector: detectorResult.decider
        }).catch(err => console.warn('Failed to log detector result:', err));
      }
    } else {
      // No detector match - will need LLM classification
      undetected.push(email);
    }
  }

  console.log(`🎯 Phase 2: ${detected.length} detected by rules, ${undetected.length} need LLM`);

  // Early return if all emails were detected by rules (zero API cost!)
  if (undetected.length === 0) {
    console.log('✅ All uncached emails detected by Phase 2 rules - zero API calls!');

    // Update cache with detected results
    await updateCache(detected);

    // Combine cached + detected results
    const allResults = [...cached, ...detected];

    // Record telemetry for detector hits
    for (const result of detected) {
      await recordClassification(
        { id: result.id, from: result.from },
        result,
        0  // Detector hits are free (T0)
      );
      await recordCacheMiss();
    }

    // Record cache hits
    for (const cachedResult of cached) {
      await recordCacheHit();
    }

    // Print session summary at the end (early return path - no LLM calls)
    printSessionSummary(emails, cached, detected, [], 0, 0, 0);

    return allResults;
  }

  // Phase 1: Deduplicate undetected emails by (sender, subject_signature) to reduce API calls
  const uniqueSenders = deduplicateBySender(undetected);
  console.log(`🔍 Phase 1: Deduplicated to ${uniqueSenders.length} unique (sender, subject) combinations for LLM`);

  try {
    // Call API with deduplicated emails in batches to prevent timeouts
    const batchSize = CONFIG.BATCH_SIZE || 50;
    const CONCURRENT_BATCHES = 4;  // Process up to 4 batches in parallel
    const classifications = [];

    if (uniqueSenders.length > batchSize) {
      console.log(`📦 Processing in batches of ${batchSize} emails...`);

      // Split into batches
      const batches = [];
      for (let i = 0; i < uniqueSenders.length; i += batchSize) {
        batches.push(uniqueSenders.slice(i, i + batchSize));
      }

      // Process batches in parallel groups
      for (let i = 0; i < batches.length; i += CONCURRENT_BATCHES) {
        const parallelBatches = batches.slice(i, i + CONCURRENT_BATCHES);
        const batchNumbers = parallelBatches.map((_, idx) => i + idx + 1);

        console.log(`📦 Processing batches ${batchNumbers.join(', ')}/${batches.length} in parallel (${parallelBatches.reduce((sum, b) => sum + b.length, 0)} emails)`);

        // Process this group of batches concurrently
        const parallelResults = await Promise.all(
          parallelBatches.map(batch => callClassifierAPI(batch))
        );

        // Flatten results from all parallel batches
        parallelResults.forEach(batchResults => classifications.push(...batchResults));
      }

      console.log(`✅ Completed ${batches.length} batches (${CONCURRENT_BATCHES} concurrent), ${classifications.length} total classifications`);
    } else {
      // Small batch, process all at once
      const allResults = await callClassifierAPI(uniqueSenders);
      classifications.push(...allResults);
    }

    // Validate confidence thresholds (Fix 2: Extension-backend sync)
    if (typeof validateClassificationBatch === 'function') {
      const validation = await validateClassificationBatch(classifications);

      // Only warn if majority are below threshold (indicates configuration issue)
      const percentBelow = (validation.invalid / validation.total) * 100;
      if (percentBelow > 75) {
        console.warn(`⚠️ Most classifications (${percentBelow.toFixed(0)}%) have low confidence - backend thresholds may be misconfigured`);
      }
    }

    // Phase 6: Selective verification pass on suspicious classifications
    // Parallelize verifier calls for performance (like we do with classifier batches)
    const verifierInfoMap = new Map(); // Track verifier info for logging

    // Collect all emails that need verification
    const verificationsNeeded = [];
    for (let i = 0; i < uniqueSenders.length; i++) {
      const email = uniqueSenders[i];
      const classification = classifications[i];

      if (!classification) continue;

      // Check if this classification needs verification
      const verifyContext = shouldVerify(email, classification);

      if (verifyContext) {
        verificationsNeeded.push({ index: i, email, classification, verifyContext });
      }
    }

    // Run verifier calls in batches to avoid overwhelming browser connection limits
    // Chrome typically allows 6-8 connections per domain, so batch at 10 to be safe
    const VERIFIER_BATCH_SIZE = 10;
    const verifierResults = [];

    for (let i = 0; i < verificationsNeeded.length; i += VERIFIER_BATCH_SIZE) {
      const batch = verificationsNeeded.slice(i, i + VERIFIER_BATCH_SIZE);

      const batchResults = await Promise.all(
        batch.map(async ({ index, email, classification, verifyContext }) => {
          const verifierResult = await callVerifier(email, classification, verifyContext);
          return { index, email, classification, verifyContext, verifierResult };
        })
      );

      verifierResults.push(...batchResults);
    }

    // Process verifier results and apply corrections
    let verifierFlips = 0;
    for (const { index, email, classification, verifyContext, verifierResult } of verifierResults) {
      const dedupeKey = generateDedupeKey(email.from, email.subject);

      // Store verifier info for logging
      verifierInfoMap.set(dedupeKey, {
        triggered: true,
        triggers: verifyContext.reason,
        verdict: verifierResult?.verdict,
        why_bad: verifierResult?.why_bad,
        corrected: false // Will update if correction accepted
      });

      // Decide whether to accept correction
      if (verifierResult && shouldAcceptCorrection(verifierResult)) {
        const redactedFrom = redactForLog(email.from);
        console.log('🔄 Phase 6: Accepting verifier correction', {
          from: redactedFrom,
          before: `${classification.type}/${classification.attention}`,
          after: `${verifierResult.correction?.type || classification.type}/${verifierResult.correction?.attention || classification.attention}`,
          reason: redactForLog(verifierResult.why_bad || '')
        });

        // Merge correction with original classification (keeps original values for undefined fields)
        classifications[index] = {
          ...classification,  // Start with original classification
          ...verifierResult.correction,  // Override with correction fields
          decider: 'gemini_verifier',
          reason: `${verifierResult.correction?.reason || classification.reason} (verified: ${verifierResult.why_bad})`
        };

        verifierFlips++;

        // Update verifier info
        verifierInfoMap.get(dedupeKey).corrected = true;
      }
    }

    console.log(`🔍 Phase 6: Verified ${verificationsNeeded.length}/${uniqueSenders.length} classifications (${verifierFlips} corrected)`);

    // Log confidence distribution and type breakdown for LLM results
    const confBuckets = { high: 0, medium: 0, low: 0 };
    const typeBreakdown = {};
    const actionRequired = [];

    for (const c of classifications) {
      if (!c) continue;

      // Confidence buckets (using min of type_conf, attention_conf, importance_conf)
      const minConf = Math.min(
        c.type_conf || 0,
        c.attention_conf || 0,
        c.importance_conf || 0
      );
      if (minConf >= 0.80) confBuckets.high++;
      else if (minConf >= 0.60) confBuckets.medium++;
      else confBuckets.low++;

      // Type breakdown
      const t = c.type || 'unknown';
      typeBreakdown[t] = (typeBreakdown[t] || 0) + 1;

      // Track action_required for visibility
      if (c.attention === 'action_required') {
        actionRequired.push(c.type);
      }
    }

    const typeStr = Object.entries(typeBreakdown)
      .sort((a, b) => b[1] - a[1])
      .map(([t, n]) => `${t}:${n}`)
      .join(', ');

    console.log(`📊 LLM Results: ${typeStr}`);
    console.log(`📊 Confidence: ${confBuckets.high} high (≥0.80), ${confBuckets.medium} medium (0.60-0.80), ${confBuckets.low} low (<0.60)`);

    if (actionRequired.length > 0) {
      console.log(`⚠️ Action Required: ${actionRequired.length} emails (${actionRequired.join(', ')})`);
    }

    if (verificationsNeeded.length === 0 && confBuckets.high === classifications.length) {
      console.log(`   └─ Verifier skipped: all classifications high-confidence`);
    }

    // Phase 1: Build classification map using original email data
    // Note: API doesn't return subject field, so we map by index + preserve original data
    const classificationMap = new Map();
    uniqueSenders.forEach((email, index) => {
      const dedupeKey = generateDedupeKey(email.from, email.subject);
      const classification = classifications[index];

      if (classification) {
        classificationMap.set(dedupeKey, {
          ...classification,
          subject: email.subject  // Preserve original subject for cache
        });
      }
    });

    // Create full results for all undetected emails (those that needed LLM)
    const expandedResults = undetected.map(email => {
      const dedupeKey = generateDedupeKey(email.from, email.subject);
      const classification = classificationMap.get(dedupeKey);

      // Defensive check: classification should never be undefined
      if (!classification) {
        console.error('❌ Phase 1 BUG: No classification found for dedupe key', {
          key: redactForLog(dedupeKey),
          from: redactForLog(email.from),
          subject: redactForLog(email.subject),
          available: Array.from(classificationMap.keys()).map(redactForLog)
        });

        // Return a fallback result to prevent crash
        return {
          id: email.id,
          threadId: email.threadId,
          from: email.from,
          subject: email.subject,
          type: 'uncategorized',
          type_conf: 0,
          attention: 'none',
          attention_conf: 0,
          importance: 'routine',
          importance_conf: 0,
          client_label: 'everything-else',
          relationship: 'from_unknown',
          relationship_conf: 0,
          decider: 'fallback',
          reason: 'Phase 1 mapping error - no classification found',
          labels: ['ShopQ/Everything-Else']
        };
      }

      const mappedLabels = mapToLabels(classification, email);
      const result = {
        ...classification,
        id: email.id,
        threadId: email.threadId,
        from: email.from,
        subject: email.subject,
        snippet: email.snippet,  // Include snippet for digest generation
        labels: mappedLabels
      };

      // Log classification for analysis
      if (typeof logger !== 'undefined') {
        const dedupeKey = generateDedupeKey(email.from, email.subject);
        const verifierInfo = verifierInfoMap.get(dedupeKey) || null;

        logger.logClassification(email, classification, result.labels, {
          verifier: verifierInfo
        }).catch(err => console.warn('Failed to log classification:', err));
      }

      return result;
    });

    // Phase 2: Record telemetry for detector hits (T0 cost = free)
    for (const result of detected) {
      await recordClassification(
        { id: result.id, from: result.from },
        result,
        0  // Detector hits are free (T0)
      );
      await recordCacheMiss();  // Not from cache, but from detector
    }

    // Record telemetry for LLM-classified results (T3 cost)
    for (const result of expandedResults) {
      // Estimate cost: $0.0001 per Gemini call
      const cost = result.decider === 'gemini' ? 0.0001 : 0;

      await recordClassification(
        { id: result.id, from: result.from },
        result,
        cost
      );

      // Record cache miss for this email
      await recordCacheMiss();
    }

    // Record cache hits for cached emails
    for (const cachedResult of cached) {
      await recordCacheHit();
    }

    // Update cache with ALL new results (detected + LLM-classified)
    await updateCache([...detected, ...expandedResults]);

    // Combine cached + detected + LLM-classified results
    const allResults = [...cached, ...detected, ...expandedResults];

    // Phase 1+2: Verify result count equals input count (acceptance criteria)
    if (allResults.length !== emails.length) {
      console.error(`❌ Verification failed: Expected ${emails.length} results, got ${allResults.length}`);
      console.error(`   Breakdown: ${cached.length} cached + ${detected.length} detected + ${expandedResults.length} LLM`);
    }

    // Print session summary at the end (main LLM path)
    printSessionSummary(emails, cached, detected, expandedResults, verificationsNeeded.length, verifierFlips, uniqueSenders.length);

    console.log(`✅ Classified ${allResults.length} emails`);
    return allResults;

  } catch (error) {
    console.error('❌ Classification failed:', error);
    throw error;
  }
}

/**
 * Deduplicate emails by (sender, subject_signature)
 *
 * Phase 1: Prevents per-sender generalization (e.g., Amazon receipts vs promos)
 * by grouping on semantic subject type, not just sender address.
 *
 * @param {Array} emails - Emails to deduplicate
 * @returns {Array} Deduplicated emails (one per unique sender+signature combo)
 */
function deduplicateBySender(emails) {
  const dedupeMap = new Map();

  emails.forEach(email => {
    // Use composite key: sender|subject_signature
    const dedupeKey = generateDedupeKey(email.from, email.subject);

    if (!dedupeMap.has(dedupeKey)) {
      dedupeMap.set(dedupeKey, email);
    }
  });

  return Array.from(dedupeMap.values());
}

/**
 * Call the classification API
 */
async function callClassifierAPI(emails) {
  const url = `${CONFIG.SHOPQ_API_URL}${CONFIG.ENDPOINTS.CLASSIFY}`;

  console.log('🌐 classifier.request', {
    url: redactForLog(url),
    count: emails.length
  });

  const payload = {
    emails: emails.map(email => ({
      subject: email.subject,
      snippet: email.snippet,
      from: email.from
    }))
  };

  const response = await resilientFetch(
    url,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    },
    { timeoutMs: 300000, retries: 1 }  // 300s timeout for classification (matches Cloud Run timeout)
  );

  if (!response.ok) {
    console.warn('🌐 classifier.error', {
      status: response.status,
      url: redactForLog(url)
    });
    throw new Error(`API error ${response.status}`);
  }

  let data;
  try {
    data = await response.json();
  } catch (error) {
    console.error('🌐 classifier.parse_error', {
      message: error?.message || String(error)
    });
    throw error;
  }

  const resultCount = Array.isArray(data.results) ? data.results.length : 0;
  console.log('🌐 classifier.success', {
    status: response.status,
    count: resultCount
  });

  // Log backend stats if available
  if (data.stats) {
    const s = data.stats;
    console.log(`📊 Backend Stats: ${s.total} emails in ${s.elapsed_ms}ms`);
    console.log(`   High confidence: ${s.high_confidence}, Low: ${s.low_confidence}`);
    if (s.by_type && Object.keys(s.by_type).length > 0) {
      const types = Object.entries(s.by_type)
        .sort((a, b) => b[1] - a[1])
        .map(([t, c]) => `${t}:${c}`)
        .join(', ');
      console.log(`   Types: ${types}`);
    }
    if (s.by_decider && Object.keys(s.by_decider).length > 0) {
      const deciders = Object.entries(s.by_decider)
        .sort((a, b) => b[1] - a[1])
        .map(([d, c]) => `${d}:${c}`)
        .join(', ');
      console.log(`   Deciders: ${deciders}`);
    }
  }

  return data.results;
}
