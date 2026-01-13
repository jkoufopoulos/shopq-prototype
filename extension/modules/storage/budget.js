/**
 * Spend Tracking & Budget Module
 */


/**
 * Check if user has budget for estimated cost
 * @param {number} estimatedCost - Estimated cost in USD
 * @returns {Promise<boolean>} Can spend
 */
async function checkSpendBudget(estimatedCost) {
  const today = getToday();
  const result = await chrome.storage.local.get([CONFIG.KEYS.SPEND_TRACKER]);
  const tracker = result[CONFIG.KEYS.SPEND_TRACKER] || {};

  const todaySpend = tracker[today] || 0;

  if (todaySpend + estimatedCost > CONFIG.DAILY_SPEND_CAP_USD) {
    console.warn(`⚠️ Daily spend cap reached: $${todaySpend.toFixed(4)} (limit: $${CONFIG.DAILY_SPEND_CAP_USD})`);
    return false;
  }

  return true;
}

/**
 * Check if budget allows for auto-organize operation
 * Estimates cost for typical batch (30 emails) and checks budget
 * @returns {Promise<{allowed: boolean, reason?: string}>}
 */
async function checkBudget() {
  try {
    // Estimate cost for typical auto-organize batch (30 emails max)
    // Assume worst case: all emails need LLM classification (T3)
    const estimatedEmailCount = 30;
    const estimatedCost = estimatedEmailCount * CONFIG.TIER_COSTS.T3;

    const canSpend = await checkSpendBudget(estimatedCost);

    if (!canSpend) {
      const today = getToday();
      const result = await chrome.storage.local.get([CONFIG.KEYS.SPEND_TRACKER]);
      const tracker = result[CONFIG.KEYS.SPEND_TRACKER] || {};
      const todaySpend = tracker[today] || 0;

      return {
        allowed: false,
        reason: `Daily spend cap reached: $${todaySpend.toFixed(4)} / $${CONFIG.DAILY_SPEND_CAP_USD}`
      };
    }

    return { allowed: true };
  } catch (error) {
    console.error('❌ Budget check failed:', error);
    // Fail open - allow operation if budget check fails
    return { allowed: true };
  }
}

/**
 * Record budget usage from classifications
 * Calculates cost based on tier used for each email
 * @param {Array} classifications - Array of classification results with tier info
 */
async function recordBudget(classifications) {
  if (!classifications || classifications.length === 0) {
    return;
  }

  // Calculate total cost by tier
  const tierCounts = {
    T0: 0,
    T1: 0,
    T2_LITE: 0,
    T3: 0
  };

  classifications.forEach(result => {
    const tier = result.tier || result.decider || 'T3'; // Default to T3 if unknown
    if (tierCounts[tier] !== undefined) {
      tierCounts[tier]++;
    } else {
      tierCounts.T3++; // Unknown tiers count as T3
    }
  });

  // Record spend for each tier
  for (const [tier, count] of Object.entries(tierCounts)) {
    if (count > 0) {
      const cost = count * CONFIG.TIER_COSTS[tier];
      await recordSpend(cost, tier, count);
    }
  }
}

/**
 * Record actual spend
 * @param {number} cost - Cost in USD
 * @param {string} tier - Tier used
 * @param {number} count - Number of emails
 */
async function recordSpend(cost, tier, count) {
  const today = getToday();
  const result = await chrome.storage.local.get([CONFIG.KEYS.SPEND_TRACKER]);
  const tracker = result[CONFIG.KEYS.SPEND_TRACKER] || {};

  if (!tracker[today]) {
    tracker[today] = 0;
  }
  tracker[today] += cost;

  // Keep only last 7 days
  const cutoffDate = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const cutoff = cutoffDate.toISOString().split('T')[0];

  for (const date in tracker) {
    if (date < cutoff) delete tracker[date];
  }

  await chrome.storage.local.set({ [CONFIG.KEYS.SPEND_TRACKER]: tracker });

  console.log(`💰 Recorded: $${cost.toFixed(4)} for ${count} emails at ${tier} (today: $${tracker[today].toFixed(4)})`);
}

/**
 * Get spend statistics
 * @returns {Promise<Object>} Spend stats
 */
async function getSpendStats() {
  const result = await chrome.storage.local.get([CONFIG.KEYS.SPEND_TRACKER]);
  const tracker = result[CONFIG.KEYS.SPEND_TRACKER] || {};

  const sortedDays = Object.keys(tracker).sort().reverse();
  const last7Days = sortedDays.slice(0, 7);

  const total = last7Days.reduce((sum, date) => sum + tracker[date], 0);
  const avg = last7Days.length > 0 ? total / last7Days.length : 0;

  return {
    dailyStats: last7Days.map(date => ({
      date,
      spend: tracker[date]
    })),
    avgDaily: avg,
    projectedMonthly: avg * 30,
    today: tracker[getToday()] || 0
  };
}
