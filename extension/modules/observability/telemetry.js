/**
 * Telemetry Module
 */


/**
 * Record a single classification result (Phase 3: Per-message tracking)
 */
async function recordClassification(email, classification, cost = 0) {
  const stats = await getStats();

  // Phase 3: Increment for EACH email, not just unique senders
  stats.totalClassified = (stats.totalClassified || 0) + 1;

  // Phase 3: Track decider breakdown (rule vs gemini vs verifier)
  if (!stats.deciderBreakdown) {
    stats.deciderBreakdown = {};
  }
  const decider = classification.decider || 'unknown';
  stats.deciderBreakdown[decider] = (stats.deciderBreakdown[decider] || 0) + 1;

  // Phase 3: Track tier distribution based on cost
  // T0 = free (detectors/rules)
  // T1 = heuristics (currently unused)
  // T2 = LLM lite (currently unused, but could be used for simpler models)
  // T3 = Gemini ($0.0001 per call)
  const tier = cost === 0 ? 'T0' :
               cost < 0.00005 ? 'T1' :
               cost < 0.00015 ? 'T2' :
               'T3';

  if (!stats.tierDistribution) {
    stats.tierDistribution = {};
  }
  stats.tierDistribution[tier] = (stats.tierDistribution[tier] || 0) + 1;

  // Track cost
  stats.costUsd = (stats.costUsd || 0) + cost;

  // Phase 3: Track confidence scores for averaging
  if (!stats.confidences) {
    stats.confidences = [];
  }
  stats.confidences.push(classification.type_conf || 0);

  // Calculate rolling average confidence
  const sum = stats.confidences.reduce((a, b) => a + b, 0);
  stats.avgConfidence = sum / stats.confidences.length;

  // Update last classified timestamp
  stats.lastClassified = new Date().toISOString();

  await chrome.storage.local.set({ [CONFIG.KEYS.STATS]: stats });
}

/**
 * Record a cache hit
 */
async function recordCacheHit() {
  const stats = await getStats();
  stats.cacheHits = (stats.cacheHits || 0) + 1;
  stats.totalRequests = (stats.totalRequests || 0) + 1;
  await chrome.storage.local.set({ [CONFIG.KEYS.STATS]: stats });
}

/**
 * Record a cache miss
 */
async function recordCacheMiss() {
  const stats = await getStats();
  stats.totalRequests = (stats.totalRequests || 0) + 1;
  await chrome.storage.local.set({ [CONFIG.KEYS.STATS]: stats });
}

/**
 * Get current stats (Phase 3: Added deciderBreakdown)
 * Auto-resets when version changes to keep stats relevant
 */
async function getStats() {
  const result = await chrome.storage.local.get(CONFIG.KEYS.STATS);
  const stats = result[CONFIG.KEYS.STATS];

  // Auto-reset if version changed
  if (stats && stats.version !== CONFIG.VERSION) {
    console.log(`📊 Stats version mismatch (${stats.version} → ${CONFIG.VERSION}), resetting stats`);
    await resetStats();
    return getStats();
  }

  return stats || {
    version: CONFIG.VERSION,
    totalClassified: 0,
    costUsd: 0,
    tierDistribution: {},
    deciderBreakdown: {},  // Phase 3: Track by decider type
    confidences: [],
    avgConfidence: 0,
    cacheHits: 0,
    totalRequests: 0,
    lastClassified: null
  };
}

/**
 * Reset stats (Phase 3: Added deciderBreakdown)
 */
async function resetStats() {
  await chrome.storage.local.set({
    [CONFIG.KEYS.STATS]: {
      version: CONFIG.VERSION,
      totalClassified: 0,
      costUsd: 0,
      tierDistribution: {},
      deciderBreakdown: {},
      confidences: [],
      avgConfidence: 0,
      cacheHits: 0,
      totalRequests: 0,
      lastClassified: null
    }
  });
  console.log(`📊 Stats reset (v${CONFIG.VERSION})`);
}

/**
 * Show stats in console (Phase 3: Enhanced with decider breakdown)
 */
async function showStats() {
  const stats = await getStats();

  console.log(`📊 ShopQ Stats (v${stats.version || 'unknown'})`);
  console.log(`Total Classified: ${stats.totalClassified}`);

  // Phase 3: Show decider breakdown
  if (stats.deciderBreakdown && Object.keys(stats.deciderBreakdown).length > 0) {
    console.log('Decider Breakdown:');
    for (const [decider, count] of Object.entries(stats.deciderBreakdown)) {
      const percentage = ((count / stats.totalClassified) * 100).toFixed(1);
      console.log(`  ${decider}: ${count} (${percentage}%)`);
    }
  }

  // Cache hit rate
  if (stats.totalRequests > 0) {
    const cacheHitRate = ((stats.cacheHits / stats.totalRequests) * 100).toFixed(1);
    console.log(`Cache Hit Rate: ${cacheHitRate}%`);
  } else {
    console.log('Cache Hit Rate: N/A');
  }

  // Cost and tier distribution
  console.log(`Cost Estimate: $${stats.costUsd.toFixed(4)}`);

  // Phase 3: Enhanced tier distribution display
  if (stats.tierDistribution && Object.keys(stats.tierDistribution).length > 0) {
    const tierStr = Object.entries(stats.tierDistribution)
      .map(([tier, count]) => `${tier}: ${count}`)
      .join(', ');
    console.log(`Tier Distribution: ${tierStr}`);
  }

  // Average confidence
  console.log(`Avg Confidence: ${(stats.avgConfidence * 100).toFixed(1)}%`);

  // Last classified timestamp
  if (stats.lastClassified) {
    console.log(`Last Classified: ${new Date(stats.lastClassified).toLocaleString()}`);
  }

  return stats;
}

// Make showStats available globally for console access
if (typeof self !== 'undefined') {
  self.showStats = showStats;
  self.resetStats = resetStats;
}
