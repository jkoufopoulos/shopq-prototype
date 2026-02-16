/**
 * Entity Resolution Module
 *
 * Pure functions for matching and merging orders:
 * - Normalized merchant identity computation
 * - Fuzzy item matching (Jaccard similarity)
 * - Order identity/fuzzy resolution for deduplication
 *
 * Loaded via importScripts BEFORE store.js (no storage dependencies).
 * All functions are deterministic given their inputs.
 */

const RESOLUTION_LOG_PREFIX = '[ReturnWatch:Resolution]';

// ============================================================
// MERCHANT NORMALIZATION
// ============================================================

/**
 * Get the effective match time for an order (stable across rescans).
 * Fallback chain: match_time -> purchase_date -> created_at -> now.
 *
 * @param {Order} order
 * @returns {number} Timestamp in milliseconds
 */
function getEffectiveMatchTime(order) {
  const raw = order.match_time || order.purchase_date || order.created_at;
  if (!raw) return Date.now();
  return new Date(raw).getTime() || Date.now();
}

// computeNormalizedMerchant() is defined in store.js (uses _resolutionStats state)

// ============================================================
// FUZZY MATCHING HELPERS
// ============================================================

/**
 * Tokenize an item summary for fuzzy comparison.
 * Lowercase, split on whitespace/punctuation, remove stop words and short tokens.
 *
 * @param {string} summary
 * @returns {Set<string>}
 */
function normalizeItemTokens(summary) {
  if (!summary) return new Set();

  const STOP_WORDS = new Set([
    'the', 'a', 'an', 'and', 'or', 'for', 'of', 'in', 'to', 'with',
    'by', 'on', 'at', 'from', 'is', 'it', 'its', 'your', 'my', 'this',
    'that', 'x', 'oz', 'ct', 'pk', 'pack', 'count', 'size', 'color', 'qty',
  ]);

  const normalized = summary.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim();
  const tokens = normalized.split(/[\s,;/|&()\-]+/);
  return new Set(tokens.filter(w => w.length >= 3 && !STOP_WORDS.has(w)));
}

/**
 * Compute Jaccard similarity between two sets.
 *
 * @param {Set<string>} setA
 * @param {Set<string>} setB
 * @returns {number} Value between 0 and 1
 */
function jaccardSimilarity(setA, setB) {
  if (setA.size === 0 && setB.size === 0) return 1.0;
  if (setA.size === 0 || setB.size === 0) return 0.0;

  let intersection = 0;
  for (const item of setA) {
    if (setB.has(item)) intersection++;
  }

  const union = setA.size + setB.size - intersection;
  return union === 0 ? 0.0 : intersection / union;
}

/**
 * Count how many "richness" fields an order has populated.
 * Used to pick the best card when merging duplicate clusters.
 *
 * @param {Order} order
 * @returns {number}
 */
function orderRichness(order) {
  let score = 0;
  if (order.delivery_date) score += 3;
  if (order.return_by_date) score += 3;
  if (order.order_id) score += 2;
  if (order.ship_date) score += 1;
  if (order.estimated_delivery_date) score += 1;
  if (order.amount) score += 1;
  if (order.return_portal_link) score += 1;
  if (order.tracking_number) score += 1;
  if (order.explicit_return_by_date) score += 2;
  if (order.return_window_days) score += 1;
  return score;
}

// ============================================================
// ORDER RESOLUTION
// ============================================================

/**
 * Resolve a matching existing order for a new/incoming order.
 * Two-phase matching:
 *   1. Identity match: exact order_id or tracking_number (O(1) via index)
 *   2. Fuzzy match: same merchant + similar items within time window
 *
 * @param {Order} newOrder - The incoming order to match
 * @param {Object} orders - All orders (order_key -> Order)
 * @param {Object} orderIdIndex - order_id -> order_key index
 * @param {Object} trackingIndex - tracking_number -> order_key index
 * @param {Object} merchantIndex - normalized_merchant -> [order_key, ...] index
 * @param {Object} [stats] - Optional stats counters to increment
 * @returns {string|null} Matched order_key, or null if no match
 */
function resolveMatchingOrder(newOrder, orders, orderIdIndex, trackingIndex, merchantIndex, stats) {
  const FUZZY_TIME_WINDOW_DAYS = 14;
  const MIN_TOKENS_FOR_FUZZY = 2;
  const JACCARD_THRESHOLD_HIGH = 0.60;  // 4+ tokens on smaller side
  const JACCARD_THRESHOLD_LOW = 0.75;   // 2-3 tokens on smaller side
  const LOW_TOKEN_CEILING = 3;

  // --- Match 1: Identity match (O(1) index lookups) ---
  if (newOrder.order_id) {
    const matchKey = orderIdIndex[newOrder.order_id];
    if (matchKey && orders[matchKey]) {
      if (stats) stats.identity_order_id = (stats.identity_order_id || 0) + 1;
      console.log(RESOLUTION_LOG_PREFIX, 'IDENTITY_MATCH',
        'order_id:', newOrder.order_id, 'matched:', matchKey);
      return matchKey;
    }
  }

  if (newOrder.tracking_number) {
    const matchKey = trackingIndex[newOrder.tracking_number];
    if (matchKey && orders[matchKey]) {
      if (stats) stats.identity_tracking = (stats.identity_tracking || 0) + 1;
      console.log(RESOLUTION_LOG_PREFIX, 'IDENTITY_MATCH',
        'tracking:', newOrder.tracking_number, 'matched:', matchKey);
      return matchKey;
    }
  }

  // --- Match 2: Fuzzy match (merchant-scoped) ---
  const merchant = computeNormalizedMerchant(newOrder);
  if (!merchant) {
    console.log(RESOLUTION_LOG_PREFIX, 'NO_MATCH', 'no merchant for fuzzy');
    return null;
  }

  const candidateKeys = merchantIndex[merchant];
  if (!candidateKeys || candidateKeys.length === 0) {
    console.log(RESOLUTION_LOG_PREFIX, 'NO_MATCH', 'no candidates for merchant:', merchant);
    return null;
  }

  const newTokens = normalizeItemTokens(newOrder.item_summary);
  const newMatchTime = getEffectiveMatchTime(newOrder);

  let bestMatch = null;
  let bestScore = 0;

  for (const candidateKey of candidateKeys) {
    // Skip self
    if (candidateKey === newOrder.order_key) continue;

    const candidate = orders[candidateKey];
    if (!candidate) continue;

    // Order ID conflict guard: both have different order_ids -> REJECT
    const newId = (newOrder.order_id || '').trim().toUpperCase();
    const candId = (candidate.order_id || '').trim().toUpperCase();
    if (newId && candId && newId !== candId) {
      if (stats) stats.conflict_reject = (stats.conflict_reject || 0) + 1;
      console.log(RESOLUTION_LOG_PREFIX, 'CONFLICT_REJECT',
        'order_id conflict:', newId, 'vs', candId);
      continue;
    }

    // Time window check (using stable match_time, not scan wall-clock)
    const candMatchTime = getEffectiveMatchTime(candidate);
    const daysDiff = Math.abs(newMatchTime - candMatchTime) / (1000 * 60 * 60 * 24);
    if (daysDiff > FUZZY_TIME_WINDOW_DAYS) {
      continue;
    }

    // Jaccard similarity on item tokens — require minimum tokens on both sides
    const candTokens = normalizeItemTokens(candidate.item_summary);

    if (newTokens.size < MIN_TOKENS_FOR_FUZZY || candTokens.size < MIN_TOKENS_FOR_FUZZY) {
      continue;
    }

    const score = jaccardSimilarity(newTokens, candTokens);
    const minTokens = Math.min(newTokens.size, candTokens.size);
    const threshold = minTokens <= LOW_TOKEN_CEILING ? JACCARD_THRESHOLD_LOW : JACCARD_THRESHOLD_HIGH;
    if (score >= threshold && score > bestScore) {
      bestScore = score;
      bestMatch = candidateKey;
    }
  }

  if (bestMatch) {
    if (stats) stats.fuzzy_match = (stats.fuzzy_match || 0) + 1;
    console.log(RESOLUTION_LOG_PREFIX, 'FUZZY_MATCH',
      'merchant:', merchant, 'score:', bestScore.toFixed(2), 'matched:', bestMatch);
    return bestMatch;
  }

  if (stats) stats.no_match = (stats.no_match || 0) + 1;
  console.log(RESOLUTION_LOG_PREFIX, 'NO_MATCH',
    'merchant:', merchant, 'candidates:', candidateKeys.length);
  return null;
}
