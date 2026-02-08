/**
 * Return Watch Storage Store
 * Wrapper for chrome.storage.local with Order and OrderEmail operations.
 *
 * All operations are atomic using single chrome.storage.local.set calls.
 * Indices are maintained automatically for fast lookups.
 *
 * Note: This file is loaded via importScripts in the service worker.
 * Schema types and helpers are available from schema.js loaded first.
 */

const STORE_LOG_PREFIX = '[ReturnWatch:Store]';

// ============================================================
// INITIALIZATION
// ============================================================

/**
 * Initialize storage with empty defaults if not present.
 * Safe to call multiple times.
 *
 * @returns {Promise<void>}
 */
async function initializeStorage() {
  const defaults = {
    [STORAGE_KEYS.ORDERS_BY_KEY]: {},
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: {},
    [STORAGE_KEYS.ORDER_KEY_BY_TRACKING]: {},
    [STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT]: {},
    [STORAGE_KEYS.ORDER_EMAILS_BY_ID]: {},
    [STORAGE_KEYS.PROCESSED_EMAIL_IDS]: [],
    [STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN]: {},
    [STORAGE_KEYS.LAST_SCAN_EPOCH_MS]: 0,
    [STORAGE_KEYS.LAST_SCAN_INTERNAL_DATE_MS]: 0,
    [STORAGE_KEYS.LAST_SCAN_WINDOW_DAYS]: 14,
    [STORAGE_KEYS.TEMPLATE_CACHE]: {},
  };

  const existing = await chrome.storage.local.get(Object.keys(defaults));

  const toSet = {};
  for (const [key, defaultValue] of Object.entries(defaults)) {
    if (existing[key] === undefined) {
      toSet[key] = defaultValue;
    }
  }

  if (Object.keys(toSet).length > 0) {
    await chrome.storage.local.set(toSet);
    console.log(STORE_LOG_PREFIX, 'Initialized storage with defaults:', Object.keys(toSet));
  }
}

// ============================================================
// ORDER OPERATIONS
// ============================================================

/**
 * Get an Order by its order_key.
 *
 * @param {string} order_key
 * @returns {Promise<Order|null>}
 */
async function getOrder(order_key) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDERS_BY_KEY);
  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  return orders[order_key] || null;
}

/**
 * Get all Orders.
 *
 * @returns {Promise<Order[]>}
 */
async function getAllOrders() {
  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDERS_BY_KEY);
  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  return Object.values(orders);
}

/**
 * Get Orders filtered by status.
 *
 * @param {OrderStatus} status
 * @returns {Promise<Order[]>}
 */
async function getOrdersByStatus(status) {
  const orders = await getAllOrders();
  return orders.filter(o => o.order_status === status);
}

/**
 * Get Orders with known deadlines (for Return Watch section).
 *
 * @returns {Promise<Order[]>}
 */
async function getOrdersWithDeadlines() {
  const orders = await getAllOrders();
  return orders.filter(o =>
    o.order_status === ORDER_STATUS.ACTIVE &&
    o.deadline_confidence !== DEADLINE_CONFIDENCE.UNKNOWN &&
    o.return_by_date
  );
}

/**
 * Find an Order by order_id (merchant order number).
 *
 * @param {string} order_id
 * @returns {Promise<Order|null>}
 */
async function findOrderByOrderId(order_id) {
  if (!order_id) return null;

  const result = await chrome.storage.local.get([
    STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID,
    STORAGE_KEYS.ORDERS_BY_KEY,
  ]);

  const index = result[STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID] || {};
  const order_key = index[order_id];
  if (!order_key) return null;

  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  return orders[order_key] || null;
}

/**
 * Find an Order by tracking number.
 *
 * @param {string} tracking_number
 * @returns {Promise<Order|null>}
 */
async function findOrderByTracking(tracking_number) {
  if (!tracking_number) return null;

  const result = await chrome.storage.local.get([
    STORAGE_KEYS.ORDER_KEY_BY_TRACKING,
    STORAGE_KEYS.ORDERS_BY_KEY,
  ]);

  const index = result[STORAGE_KEYS.ORDER_KEY_BY_TRACKING] || {};
  const order_key = index[tracking_number];
  if (!order_key) return null;

  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  return orders[order_key] || null;
}

/**
 * Resolve whether a new order matches an existing stored order.
 *
 * Matching hierarchy:
 * 1. Identity match: order_id index → tracking_number index (O(1))
 * 2. Fuzzy match: merchant-scoped Jaccard similarity (O(k) where k is small)
 *
 * Guards against bad merges:
 * - Order ID conflict: both have different order_ids → REJECT
 * - Time window: created_at must be within 14 days
 * - Jaccard threshold: item tokens must have ≥ 0.60 similarity
 *
 * @param {Order} newOrder - Incoming order to match
 * @param {Object} orders - Current orders map
 * @param {Object} orderIdIndex - order_id → order_key index
 * @param {Object} trackingIndex - tracking_number → order_key index
 * @param {Object} merchantIndex - normalized_merchant → [order_key, ...] index
 * @returns {string|null} Matched order_key, or null if no match
 */
function resolveMatchingOrder(newOrder, orders, orderIdIndex, trackingIndex, merchantIndex) {
  const FUZZY_TIME_WINDOW_DAYS = 14;
  const JACCARD_THRESHOLD = 0.60;

  // --- Match 1: Identity match (O(1) index lookups) ---
  if (newOrder.order_id) {
    const matchKey = orderIdIndex[newOrder.order_id];
    if (matchKey && orders[matchKey]) {
      console.log(STORE_LOG_PREFIX, 'RESOLVE_IDENTITY_MATCH',
        'order_id:', newOrder.order_id, 'matched:', matchKey);
      return matchKey;
    }
  }

  if (newOrder.tracking_number) {
    const matchKey = trackingIndex[newOrder.tracking_number];
    if (matchKey && orders[matchKey]) {
      console.log(STORE_LOG_PREFIX, 'RESOLVE_IDENTITY_MATCH',
        'tracking:', newOrder.tracking_number, 'matched:', matchKey);
      return matchKey;
    }
  }

  // --- Match 2: Fuzzy match (merchant-scoped) ---
  const merchant = computeNormalizedMerchant(newOrder);
  if (!merchant) {
    console.log(STORE_LOG_PREFIX, 'RESOLVE_NO_MATCH', 'no merchant for fuzzy');
    return null;
  }

  const candidateKeys = merchantIndex[merchant];
  if (!candidateKeys || candidateKeys.length === 0) {
    console.log(STORE_LOG_PREFIX, 'RESOLVE_NO_MATCH', 'no candidates for merchant:', merchant);
    return null;
  }

  const newTokens = normalizeItemTokens(newOrder.item_summary);
  const newCreatedAt = newOrder.created_at ? new Date(newOrder.created_at).getTime() : Date.now();

  let bestMatch = null;
  let bestScore = 0;

  for (const candidateKey of candidateKeys) {
    // Skip self
    if (candidateKey === newOrder.order_key) continue;

    const candidate = orders[candidateKey];
    if (!candidate) continue;

    // Order ID conflict guard: both have different order_ids → REJECT
    const newId = (newOrder.order_id || '').trim().toUpperCase();
    const candId = (candidate.order_id || '').trim().toUpperCase();
    if (newId && candId && newId !== candId) {
      console.log(STORE_LOG_PREFIX, 'RESOLVE_CONFLICT_REJECT',
        'order_id conflict:', newId, 'vs', candId);
      continue;
    }

    // Time window check
    const candCreatedAt = candidate.created_at ? new Date(candidate.created_at).getTime() : 0;
    const daysDiff = Math.abs(newCreatedAt - candCreatedAt) / (1000 * 60 * 60 * 24);
    if (daysDiff > FUZZY_TIME_WINDOW_DAYS) {
      continue;
    }

    // Jaccard similarity on item tokens
    const candTokens = normalizeItemTokens(candidate.item_summary);

    // If both have empty tokens, we can't determine similarity — skip
    if (newTokens.size === 0 && candTokens.size === 0) {
      // Both empty summaries from same merchant within time window — match
      console.log(STORE_LOG_PREFIX, 'RESOLVE_FUZZY_MATCH',
        'both empty summaries, merchant:', merchant, 'matched:', candidateKey);
      return candidateKey;
    }

    // If only one has tokens, skip (can't compare)
    if (newTokens.size === 0 || candTokens.size === 0) {
      continue;
    }

    const score = jaccardSimilarity(newTokens, candTokens);
    if (score >= JACCARD_THRESHOLD && score > bestScore) {
      bestScore = score;
      bestMatch = candidateKey;
    }
  }

  if (bestMatch) {
    console.log(STORE_LOG_PREFIX, 'RESOLVE_FUZZY_MATCH',
      'merchant:', merchant, 'score:', bestScore.toFixed(2), 'matched:', bestMatch);
    return bestMatch;
  }

  console.log(STORE_LOG_PREFIX, 'RESOLVE_NO_MATCH',
    'merchant:', merchant, 'candidates:', candidateKeys.length);
  return null;
}

/**
 * Upsert (create or update) an Order.
 * Automatically maintains indices and updates timestamps.
 * For new orders (key not yet in storage), runs entity resolution
 * to find and merge with an existing matching order.
 *
 * @param {Order} order
 * @returns {Promise<Order>}
 */
async function upsertOrder(order) {
  const result = await chrome.storage.local.get([
    STORAGE_KEYS.ORDERS_BY_KEY,
    STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID,
    STORAGE_KEYS.ORDER_KEY_BY_TRACKING,
    STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT,
  ]);

  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  const orderIdIndex = result[STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID] || {};
  const trackingIndex = result[STORAGE_KEYS.ORDER_KEY_BY_TRACKING] || {};
  const merchantIndex = result[STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT] || {};

  // Entity resolution: if this order_key doesn't exist in storage,
  // check if it matches an existing order under a different key
  if (!orders[order.order_key]) {
    const matchedKey = resolveMatchingOrder(order, orders, orderIdIndex, trackingIndex, merchantIndex);
    if (matchedKey) {
      // Re-key the incoming order to merge with the existing one
      order.order_key = matchedKey;
    }
  }

  // Merge with existing order if present
  const existing = orders[order.order_key];
  if (existing) {
    // Preserve terminal statuses during pipeline re-processing.
    // This prevents the scanner from resetting user-marked statuses.
    // For intentional status changes, use updateOrderStatus() which bypasses this.
    if (existing.order_status === 'returned' || existing.order_status === 'dismissed' || existing.order_status === 'cancelled') {
      order.order_status = existing.order_status;
    }

    // Merge source_email_ids (union)
    const emailIds = new Set([...(existing.source_email_ids || []), ...(order.source_email_ids || [])]);
    order.source_email_ids = Array.from(emailIds);

    // Keep earlier purchase_date
    if (existing.purchase_date && (!order.purchase_date || existing.purchase_date < order.purchase_date)) {
      order.purchase_date = existing.purchase_date;
    }

    // Keep existing created_at
    order.created_at = existing.created_at;

    // Prefer non-empty values from either source
    order.delivery_date = order.delivery_date || existing.delivery_date;
    order.return_by_date = order.return_by_date || existing.return_by_date;
    order.order_id = order.order_id || existing.order_id;
    order.tracking_number = order.tracking_number || existing.tracking_number;
    order.return_portal_link = order.return_portal_link || existing.return_portal_link;
    order.evidence_quote = order.evidence_quote || existing.evidence_quote;
    order.amount = order.amount || existing.amount;

    // Prefer higher-confidence deadline
    if (existing.deadline_confidence === 'exact' && order.deadline_confidence !== 'exact') {
      order.deadline_confidence = existing.deadline_confidence;
      order.return_by_date = existing.return_by_date;
    }
  }

  // Update timestamp
  order.updated_at = new Date().toISOString();

  // Store the order
  orders[order.order_key] = order;

  // Update indices
  if (order.order_id) {
    orderIdIndex[order.order_id] = order.order_key;
  }
  if (order.tracking_number) {
    trackingIndex[order.tracking_number] = order.order_key;
  }

  // Maintain merchant index
  const merchant = computeNormalizedMerchant(order);
  if (merchant) {
    if (!merchantIndex[merchant]) {
      merchantIndex[merchant] = [];
    }
    if (!merchantIndex[merchant].includes(order.order_key)) {
      merchantIndex[merchant].push(order.order_key);
    }
  }

  // Atomic write
  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDERS_BY_KEY]: orders,
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: orderIdIndex,
    [STORAGE_KEYS.ORDER_KEY_BY_TRACKING]: trackingIndex,
    [STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT]: merchantIndex,
  });

  console.log(STORE_LOG_PREFIX, 'Upserted order:', order.order_key, order.merchant_display_name);
  return order;
}

/**
 * Clear all orders and their indices.
 * Used before batch upsert to remove stale data from previous scans.
 *
 * @returns {Promise<void>}
 */
async function clearOrders() {
  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDERS_BY_KEY]: {},
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: {},
    [STORAGE_KEYS.ORDER_KEY_BY_TRACKING]: {},
    [STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT]: {},
  });
  console.log(STORE_LOG_PREFIX, 'Cleared all orders and indices');
}

/**
 * Link an email to an existing Order.
 * Adds email_id to source_email_ids if not already present.
 *
 * @param {string} email_id
 * @param {string} order_key
 * @returns {Promise<Order|null>}
 */
async function linkEmailToOrder(email_id, order_key) {
  const order = await getOrder(order_key);
  if (!order) return null;

  if (!order.source_email_ids.includes(email_id)) {
    order.source_email_ids.push(email_id);
    await upsertOrder(order);
    console.log(STORE_LOG_PREFIX, 'Linked email', email_id, 'to order', order_key);
  }

  return order;
}

/**
 * Update Order status.
 * Directly updates storage to bypass upsertOrder's terminal status preservation.
 *
 * @param {string} order_key
 * @param {OrderStatus} status
 * @returns {Promise<Order|null>}
 */
async function updateOrderStatus(order_key, status) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDERS_BY_KEY);
  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};

  const order = orders[order_key];
  if (!order) return null;

  // Update status and timestamp
  order.order_status = status;
  order.updated_at = new Date().toISOString();

  // Save directly to bypass upsertOrder's terminal status preservation
  orders[order_key] = order;
  await chrome.storage.local.set({ [STORAGE_KEYS.ORDERS_BY_KEY]: orders });

  console.log(STORE_LOG_PREFIX, 'Updated order status:', order_key, '->', status);
  return order;
}

/**
 * Cancel an order by its merchant order number (order_id).
 * Looks up the order via the order_id index and marks it as CANCELLED.
 *
 * @param {string} order_id - Merchant order number (e.g., Amazon order number)
 * @returns {Promise<Order|null>} The cancelled order, or null if not found
 */
async function cancelOrderByOrderId(order_id) {
  if (!order_id) return null;

  const order = await findOrderByOrderId(order_id);
  if (!order) {
    console.log(STORE_LOG_PREFIX, 'Cancel: no order found for order_id:', order_id);
    return null;
  }

  if (order.order_status === ORDER_STATUS.CANCELLED) {
    console.log(STORE_LOG_PREFIX, 'Cancel: already cancelled:', order_id);
    return order;
  }

  order.order_status = ORDER_STATUS.CANCELLED;
  await upsertOrder(order);
  console.log(STORE_LOG_PREFIX, 'Cancelled order:', order_id, 'key:', order.order_key);
  return order;
}

/**
 * Merge two Orders into one (for escalation).
 * Merges source Order into target Order, deletes source.
 *
 * @param {string} target_order_key - Order to keep
 * @param {string} source_order_key - Order to merge and delete
 * @returns {Promise<Order|null>}
 */
async function mergeOrders(target_order_key, source_order_key) {
  const result = await chrome.storage.local.get([
    STORAGE_KEYS.ORDERS_BY_KEY,
    STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID,
    STORAGE_KEYS.ORDER_KEY_BY_TRACKING,
    STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT,
  ]);

  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  const orderIdIndex = result[STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID] || {};
  const trackingIndex = result[STORAGE_KEYS.ORDER_KEY_BY_TRACKING] || {};
  const merchantIndex = result[STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT] || {};

  const target = orders[target_order_key];
  const source = orders[source_order_key];

  if (!target || !source) {
    console.warn(STORE_LOG_PREFIX, 'Merge failed: missing order(s)');
    return null;
  }

  // Merge source_email_ids
  for (const email_id of source.source_email_ids) {
    if (!target.source_email_ids.includes(email_id)) {
      target.source_email_ids.push(email_id);
    }
  }

  // Merge dates (prefer earlier purchase_date, later ship/delivery)
  if (source.purchase_date && (!target.purchase_date || source.purchase_date < target.purchase_date)) {
    target.purchase_date = source.purchase_date;
  }
  if (source.ship_date && !target.ship_date) {
    target.ship_date = source.ship_date;
  }
  if (source.delivery_date && !target.delivery_date) {
    target.delivery_date = source.delivery_date;
  }

  // Merge tracking_number if target doesn't have one
  if (source.tracking_number && !target.tracking_number) {
    target.tracking_number = source.tracking_number;
    trackingIndex[source.tracking_number] = target_order_key;
  }

  // Update timestamp
  target.updated_at = new Date().toISOString();

  // Delete source order
  delete orders[source_order_key];

  // Update indices: redirect source's order_id/tracking to target
  if (source.order_id && orderIdIndex[source.order_id] === source_order_key) {
    orderIdIndex[source.order_id] = target_order_key;
  }
  if (source.tracking_number && trackingIndex[source.tracking_number] === source_order_key) {
    trackingIndex[source.tracking_number] = target_order_key;
  }

  // Remove source from merchant index
  const sourceMerchant = computeNormalizedMerchant(source);
  if (sourceMerchant && merchantIndex[sourceMerchant]) {
    merchantIndex[sourceMerchant] = merchantIndex[sourceMerchant].filter(k => k !== source_order_key);
    if (merchantIndex[sourceMerchant].length === 0) {
      delete merchantIndex[sourceMerchant];
    }
  }

  // Ensure target is in merchant index
  const targetMerchant = computeNormalizedMerchant(target);
  if (targetMerchant) {
    if (!merchantIndex[targetMerchant]) {
      merchantIndex[targetMerchant] = [];
    }
    if (!merchantIndex[targetMerchant].includes(target_order_key)) {
      merchantIndex[targetMerchant].push(target_order_key);
    }
  }

  // Atomic write
  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDERS_BY_KEY]: orders,
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: orderIdIndex,
    [STORAGE_KEYS.ORDER_KEY_BY_TRACKING]: trackingIndex,
    [STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT]: merchantIndex,
  });

  console.log(STORE_LOG_PREFIX, 'Merged order', source_order_key, 'into', target_order_key);
  return target;
}

// ============================================================
// ORDER EMAIL OPERATIONS
// ============================================================

/**
 * Get an OrderEmail by email_id.
 *
 * @param {string} email_id
 * @returns {Promise<OrderEmail|null>}
 */
async function getOrderEmail(email_id) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDER_EMAILS_BY_ID);
  const emails = result[STORAGE_KEYS.ORDER_EMAILS_BY_ID] || {};
  return emails[email_id] || null;
}

/**
 * Store an OrderEmail record.
 *
 * @param {OrderEmail} orderEmail
 * @returns {Promise<OrderEmail>}
 */
async function storeOrderEmail(orderEmail) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDER_EMAILS_BY_ID);
  const emails = result[STORAGE_KEYS.ORDER_EMAILS_BY_ID] || {};

  emails[orderEmail.email_id] = orderEmail;

  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDER_EMAILS_BY_ID]: emails,
  });

  return orderEmail;
}

/**
 * Update an OrderEmail with extracted data.
 *
 * @param {string} email_id
 * @param {ExtractedData} extracted
 * @returns {Promise<OrderEmail|null>}
 */
async function updateOrderEmailExtracted(email_id, extracted) {
  const orderEmail = await getOrderEmail(email_id);
  if (!orderEmail) return null;

  orderEmail.extracted = extracted;
  orderEmail.processed = true;

  return storeOrderEmail(orderEmail);
}

/**
 * Update an OrderEmail with LLM extraction results.
 *
 * @param {string} email_id
 * @param {LLMExtraction} llm_extraction
 * @returns {Promise<OrderEmail|null>}
 */
async function updateOrderEmailLLM(email_id, llm_extraction) {
  const orderEmail = await getOrderEmail(email_id);
  if (!orderEmail) return null;

  orderEmail.llm_extraction = llm_extraction;

  return storeOrderEmail(orderEmail);
}

// ============================================================
// PROCESSED EMAIL TRACKING
// ============================================================

/**
 * Check if an email has already been processed.
 *
 * @param {string} email_id
 * @returns {Promise<boolean>}
 */
async function isEmailProcessed(email_id) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.PROCESSED_EMAIL_IDS);
  const processed = result[STORAGE_KEYS.PROCESSED_EMAIL_IDS] || [];
  return processed.includes(email_id);
}

/**
 * Mark an email as processed.
 *
 * @param {string} email_id
 * @returns {Promise<void>}
 */
async function markEmailProcessed(email_id) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.PROCESSED_EMAIL_IDS);
  const processed = result[STORAGE_KEYS.PROCESSED_EMAIL_IDS] || [];

  if (!processed.includes(email_id)) {
    processed.push(email_id);
    await chrome.storage.local.set({
      [STORAGE_KEYS.PROCESSED_EMAIL_IDS]: processed,
    });
  }
}

/**
 * Mark multiple emails as processed (batch operation).
 *
 * @param {string[]} email_ids
 * @returns {Promise<void>}
 */
async function markEmailsProcessed(email_ids) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.PROCESSED_EMAIL_IDS);
  const processed = new Set(result[STORAGE_KEYS.PROCESSED_EMAIL_IDS] || []);

  for (const id of email_ids) {
    processed.add(id);
  }

  await chrome.storage.local.set({
    [STORAGE_KEYS.PROCESSED_EMAIL_IDS]: Array.from(processed),
  });
}

// ============================================================
// SCAN STATE
// ============================================================

/**
 * Get last scan state.
 *
 * @returns {Promise<{epoch_ms: number, internal_date_ms: number, window_days: number}>}
 */
async function getLastScanState() {
  const result = await chrome.storage.local.get([
    STORAGE_KEYS.LAST_SCAN_EPOCH_MS,
    STORAGE_KEYS.LAST_SCAN_INTERNAL_DATE_MS,
    STORAGE_KEYS.LAST_SCAN_WINDOW_DAYS,
  ]);

  return {
    epoch_ms: result[STORAGE_KEYS.LAST_SCAN_EPOCH_MS] || 0,
    internal_date_ms: result[STORAGE_KEYS.LAST_SCAN_INTERNAL_DATE_MS] || 0,
    window_days: result[STORAGE_KEYS.LAST_SCAN_WINDOW_DAYS] || 14,
  };
}

/**
 * Update last scan state.
 *
 * @param {number} epoch_ms - Current time in ms
 * @param {number} internal_date_ms - Latest email internalDate
 * @param {number} [window_days=14] - Scan window in days
 * @returns {Promise<void>}
 */
async function updateLastScanState(epoch_ms, internal_date_ms, window_days = 14) {
  await chrome.storage.local.set({
    [STORAGE_KEYS.LAST_SCAN_EPOCH_MS]: epoch_ms,
    [STORAGE_KEYS.LAST_SCAN_INTERNAL_DATE_MS]: internal_date_ms,
    [STORAGE_KEYS.LAST_SCAN_WINDOW_DAYS]: window_days,
  });
}

// ============================================================
// TEMPLATE CACHE
// ============================================================

/**
 * Get cached LLM extraction by template hash.
 *
 * @param {string} template_hash
 * @returns {Promise<LLMExtraction|null>}
 */
async function getTemplateCache(template_hash) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.TEMPLATE_CACHE);
  const cache = result[STORAGE_KEYS.TEMPLATE_CACHE] || {};
  return cache[template_hash] || null;
}

/**
 * Store LLM extraction in template cache.
 *
 * @param {string} template_hash
 * @param {LLMExtraction} extraction
 * @returns {Promise<void>}
 */
async function setTemplateCache(template_hash, extraction) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.TEMPLATE_CACHE);
  const cache = result[STORAGE_KEYS.TEMPLATE_CACHE] || {};

  cache[template_hash] = extraction;

  await chrome.storage.local.set({
    [STORAGE_KEYS.TEMPLATE_CACHE]: cache,
  });
}

// ============================================================
// MERCHANT RULES
// ============================================================

/**
 * Get merchant return window rule.
 *
 * @param {string} merchant_domain
 * @returns {Promise<number|null>} Return window days or null
 */
async function getMerchantRule(merchant_domain) {
  if (!merchant_domain) return null;

  const result = await chrome.storage.local.get(STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN);
  const rules = result[STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN] || {};
  return rules[merchant_domain] || null;
}

/**
 * Set merchant return window rule.
 *
 * @param {string} merchant_domain
 * @param {number} window_days - Return window in days (30, 60, 90, or custom)
 * @returns {Promise<void>}
 */
async function setMerchantRule(merchant_domain, window_days) {
  if (!merchant_domain || !window_days) return;

  const result = await chrome.storage.local.get(STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN);
  const rules = result[STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN] || {};

  rules[merchant_domain] = window_days;

  await chrome.storage.local.set({
    [STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN]: rules,
  });

  console.log(STORE_LOG_PREFIX, 'Set merchant rule:', merchant_domain, '=', window_days, 'days');
}

/**
 * Get all merchant rules.
 *
 * @returns {Promise<Object<string, number>>} Map of merchant_domain -> window_days
 */
async function getAllMerchantRules() {
  const result = await chrome.storage.local.get(STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN);
  return result[STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN] || {};
}

/**
 * Delete a merchant rule.
 *
 * @param {string} merchant_domain
 * @returns {Promise<void>}
 */
async function deleteMerchantRule(merchant_domain) {
  if (!merchant_domain) return;

  const result = await chrome.storage.local.get(STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN);
  const rules = result[STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN] || {};

  delete rules[merchant_domain];

  await chrome.storage.local.set({
    [STORAGE_KEYS.MERCHANT_RULES_BY_DOMAIN]: rules,
  });

  console.log(STORE_LOG_PREFIX, 'Deleted merchant rule:', merchant_domain);
}

// ============================================================
// USER ADDRESS (for Uber Delivery)
// ============================================================

/**
 * Get saved user pickup address.
 *
 * @typedef {Object} UserAddress
 * @property {string} street - Street address
 * @property {string} city - City
 * @property {string} state - State code (e.g., "CA")
 * @property {string} zip_code - ZIP code
 * @property {string} [country] - Country code (default "US")
 * @property {number} [lat] - Latitude
 * @property {number} [lng] - Longitude
 *
 * @returns {Promise<UserAddress|null>}
 */
async function getUserAddress() {
  const result = await chrome.storage.local.get(STORAGE_KEYS.USER_ADDRESS);
  return result[STORAGE_KEYS.USER_ADDRESS] || null;
}

/**
 * Save user pickup address.
 *
 * @param {UserAddress} address
 * @returns {Promise<void>}
 */
async function setUserAddress(address) {
  if (!address || !address.street || !address.city || !address.state || !address.zip_code) {
    console.warn(STORE_LOG_PREFIX, 'Invalid address - missing required fields');
    return;
  }

  await chrome.storage.local.set({
    [STORAGE_KEYS.USER_ADDRESS]: {
      street: address.street,
      city: address.city,
      state: address.state,
      zip_code: address.zip_code,
      country: address.country || 'US',
      lat: address.lat || null,
      lng: address.lng || null,
    },
  });

  console.log(STORE_LOG_PREFIX, 'Saved user address:', address.city, address.state);
}

/**
 * Clear saved user address.
 *
 * @returns {Promise<void>}
 */
async function clearUserAddress() {
  await chrome.storage.local.remove(STORAGE_KEYS.USER_ADDRESS);
  console.log(STORE_LOG_PREFIX, 'Cleared user address');
}

// ============================================================
// UTILITIES
// ============================================================

/**
 * Clear all storage (for testing/reset).
 *
 * @returns {Promise<void>}
 */
async function clearAllStorage() {
  await chrome.storage.local.clear();
  console.log(STORE_LOG_PREFIX, 'Cleared all storage');
  await initializeStorage();
}

/**
 * Reset pipeline data while preserving user settings (merchant rules, label cache).
 * Called on extension reload to ensure pipeline improvements take effect immediately.
 *
 * @returns {Promise<void>}
 */
async function resetPipelineData() {
  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDERS_BY_KEY]: {},
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: {},
    [STORAGE_KEYS.ORDER_KEY_BY_TRACKING]: {},
    [STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT]: {},
    [STORAGE_KEYS.ORDER_EMAILS_BY_ID]: {},
    [STORAGE_KEYS.PROCESSED_EMAIL_IDS]: [],
    [STORAGE_KEYS.TEMPLATE_CACHE]: {},
    [STORAGE_KEYS.LAST_SCAN_EPOCH_MS]: 0,
    [STORAGE_KEYS.LAST_SCAN_INTERNAL_DATE_MS]: 0,
  });
  console.log(STORE_LOG_PREFIX, 'Reset pipeline data (preserved merchant rules)');
}

/**
 * Soft reset: clear scan state so emails get re-evaluated, but preserve existing orders.
 * Called on extension update so cards persist across reloads while allowing
 * updated pipeline code to re-process emails.
 *
 * Clears: processed email IDs, scan timestamps, template cache
 * Preserves: orders, indices, merchant rules
 *
 * @returns {Promise<void>}
 */
async function resetScanState() {
  await chrome.storage.local.set({
    [STORAGE_KEYS.PROCESSED_EMAIL_IDS]: [],
    [STORAGE_KEYS.LAST_SCAN_EPOCH_MS]: 0,
    [STORAGE_KEYS.LAST_SCAN_INTERNAL_DATE_MS]: 0,
    [STORAGE_KEYS.TEMPLATE_CACHE]: {},
  });
  console.log(STORE_LOG_PREFIX, 'Reset scan state (preserved orders and merchant rules)');
}

/**
 * Backfill estimated_delivery_date for existing orders.
 *
 * For orders that have delivery_date but no delivery confirmation email,
 * the delivery_date was likely an estimated date. This moves it to
 * estimated_delivery_date so the anchor date logic works correctly.
 *
 * @returns {Promise<{updated: number, skipped: number}>}
 */
async function backfillEstimatedDeliveryDates() {
  const result = await chrome.storage.local.get([
    STORAGE_KEYS.ORDERS_BY_KEY,
    STORAGE_KEYS.ORDER_EMAILS_BY_ID,
  ]);

  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  const orderEmails = result[STORAGE_KEYS.ORDER_EMAILS_BY_ID] || {};

  let updated = 0;
  let skipped = 0;

  for (const [order_key, order] of Object.entries(orders)) {
    // Skip if no delivery_date to migrate
    if (!order.delivery_date) {
      skipped++;
      continue;
    }

    // Skip if already has estimated_delivery_date (already migrated)
    if (order.estimated_delivery_date) {
      skipped++;
      continue;
    }

    // Check if any source email is a DELIVERY type
    const hasDeliveryEmail = (order.source_email_ids || []).some(emailId => {
      const emailRecord = orderEmails[emailId];
      return emailRecord && emailRecord.email_type === 'delivery';
    });

    if (hasDeliveryEmail) {
      // This order has an actual delivery email, so delivery_date is correct
      console.log(STORE_LOG_PREFIX, 'BACKFILL_SKIP', order_key, 'has delivery email');
      skipped++;
      continue;
    }

    // No delivery email - the delivery_date was probably estimated
    // Move it to estimated_delivery_date
    console.log(STORE_LOG_PREFIX, 'BACKFILL_MIGRATE', order_key,
      'moving delivery_date to estimated_delivery_date:', order.delivery_date);

    order.estimated_delivery_date = order.delivery_date;
    order.delivery_date = null;
    order.updated_at = new Date().toISOString();
    updated++;
  }

  // Save updated orders
  if (updated > 0) {
    await chrome.storage.local.set({
      [STORAGE_KEYS.ORDERS_BY_KEY]: orders,
    });
  }

  console.log(STORE_LOG_PREFIX, 'BACKFILL_COMPLETE', `updated: ${updated}, skipped: ${skipped}`);
  return { updated, skipped };
}

/**
 * Get storage stats for diagnostics.
 *
 * @returns {Promise<Object>}
 */
async function getStorageStats() {
  const result = await chrome.storage.local.get(null);

  const orders = Object.values(result[STORAGE_KEYS.ORDERS_BY_KEY] || {});
  const emails = Object.keys(result[STORAGE_KEYS.ORDER_EMAILS_BY_ID] || {});
  const processed = result[STORAGE_KEYS.PROCESSED_EMAIL_IDS] || [];

  return {
    order_count: orders.length,
    active_orders: orders.filter(o => o.order_status === ORDER_STATUS.ACTIVE).length,
    deadline_known: orders.filter(o => o.deadline_confidence !== DEADLINE_CONFIDENCE.UNKNOWN).length,
    email_count: emails.length,
    processed_count: processed.length,
    last_scan: new Date(result[STORAGE_KEYS.LAST_SCAN_EPOCH_MS] || 0).toISOString(),
  };
}

/**
 * Find existing order by order_id or tracking_number.
 * Used for safe prelink (P2).
 *
 * @param {string} [order_id]
 * @param {string} [tracking_number]
 * @returns {Promise<Order|null>}
 */
async function findExistingOrder(order_id, tracking_number) {
  // Priority: order_id first, then tracking_number
  if (order_id) {
    const order = await findOrderByOrderId(order_id);
    if (order) return order;
  }

  if (tracking_number) {
    const order = await findOrderByTracking(tracking_number);
    if (order) return order;
  }

  return null;
}

/**
 * Delete an Order by order_key.
 * Also removes entries from indices.
 *
 * @param {string} order_key
 * @returns {Promise<boolean>} True if deleted, false if not found
 */
async function deleteOrder(order_key) {
  const result = await chrome.storage.local.get([
    STORAGE_KEYS.ORDERS_BY_KEY,
    STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID,
    STORAGE_KEYS.ORDER_KEY_BY_TRACKING,
    STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT,
  ]);

  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  const orderIdIndex = result[STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID] || {};
  const trackingIndex = result[STORAGE_KEYS.ORDER_KEY_BY_TRACKING] || {};
  const merchantIndex = result[STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT] || {};

  const order = orders[order_key];
  if (!order) {
    console.log(STORE_LOG_PREFIX, 'Delete failed: order not found:', order_key);
    return false;
  }

  // Remove from indices
  if (order.order_id && orderIdIndex[order.order_id] === order_key) {
    delete orderIdIndex[order.order_id];
  }
  if (order.tracking_number && trackingIndex[order.tracking_number] === order_key) {
    delete trackingIndex[order.tracking_number];
  }

  // Remove from merchant index
  const merchant = computeNormalizedMerchant(order);
  if (merchant && merchantIndex[merchant]) {
    merchantIndex[merchant] = merchantIndex[merchant].filter(k => k !== order_key);
    if (merchantIndex[merchant].length === 0) {
      delete merchantIndex[merchant];
    }
  }

  // Delete the order
  delete orders[order_key];

  // Atomic write
  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDERS_BY_KEY]: orders,
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: orderIdIndex,
    [STORAGE_KEYS.ORDER_KEY_BY_TRACKING]: trackingIndex,
    [STORAGE_KEYS.ORDER_KEYS_BY_MERCHANT]: merchantIndex,
  });

  console.log(STORE_LOG_PREFIX, 'Deleted order:', order_key);
  return true;
}

/**
 * Update order_id index to point to a specific order_key.
 * Used for merge escalation and key upgrades.
 *
 * @param {string} order_id
 * @param {string} order_key
 * @returns {Promise<void>}
 */
async function updateOrderIdIndex(order_id, order_key) {
  if (!order_id || !order_key) return;

  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID);
  const index = result[STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID] || {};

  index[order_id] = order_key;

  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: index,
  });

  console.log(STORE_LOG_PREFIX, 'Updated order_id index:', order_id, '->', order_key);
}

/**
 * Update tracking index to point to a specific order_key.
 * Used for merge escalation and key upgrades.
 *
 * @param {string} tracking_number
 * @param {string} order_key
 * @returns {Promise<void>}
 */
async function updateTrackingIndex(tracking_number, order_key) {
  if (!tracking_number || !order_key) return;

  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDER_KEY_BY_TRACKING);
  const index = result[STORAGE_KEYS.ORDER_KEY_BY_TRACKING] || {};

  index[tracking_number] = order_key;

  await chrome.storage.local.set({
    [STORAGE_KEYS.ORDER_KEY_BY_TRACKING]: index,
  });

  console.log(STORE_LOG_PREFIX, 'Updated tracking index:', tracking_number, '->', order_key);
}

// ============================================================
// ENTITY RESOLUTION HELPERS
// ============================================================

/**
 * Compute a normalized merchant identity for an order.
 * Uses the normalized_merchant field if present (set at scan time),
 * otherwise derives from merchant_domain + merchant_display_name.
 *
 * @param {Order} order
 * @returns {string} Canonical merchant key for indexing/matching
 */
function computeNormalizedMerchant(order) {
  // Prefer pre-computed value (set by scanner in Commit 2)
  if (order.normalized_merchant) {
    return order.normalized_merchant;
  }

  // Derive from domain, applying same normalization as scanner
  let domain = (order.merchant_domain || '').toLowerCase().trim();
  domain = domain.replace(/^(www\.|shop\.|store\.|mail\.|email\.|orders?\.)/, '');

  const domainAliases = {
    'iliabeauty.com': 'ilia.com',
    'shopifyemail.com': null,
    'postmarkapp.com': null,
    'sendgrid.net': null,
    'mailchimp.com': null,
    'klaviyo.com': null,
  };

  if (domainAliases[domain] !== undefined) {
    domain = domainAliases[domain];
  }

  // If domain resolved to null (email service) or empty, use display name
  if (!domain) {
    const name = (order.merchant_display_name || 'unknown').toLowerCase().trim();
    return name.replace(/\s*(beauty|store|shop|official|us|inc|llc|co)\s*$/i, '')
      .replace(/[^a-z0-9]/g, '') || 'unknown';
  }

  return domain;
}

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
 * Find Orders by thread_id for thread-hint linking.
 * Returns orders where any source_email has matching thread_id.
 *
 * @param {string} thread_id
 * @param {string} merchant_domain
 * @returns {Promise<Order[]>}
 */
async function findOrdersByThread(thread_id, merchant_domain) {
  if (!thread_id) return [];

  const result = await chrome.storage.local.get([
    STORAGE_KEYS.ORDER_EMAILS_BY_ID,
    STORAGE_KEYS.ORDERS_BY_KEY,
  ]);

  const orderEmails = result[STORAGE_KEYS.ORDER_EMAILS_BY_ID] || {};
  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};

  // Find email_ids in this thread
  const emailsInThread = Object.values(orderEmails).filter(
    e => e.thread_id === thread_id && e.merchant_domain === merchant_domain
  );

  if (emailsInThread.length === 0) return [];

  // Find orders containing these emails
  const matchingOrders = [];
  for (const order of Object.values(orders)) {
    if (order.merchant_domain !== merchant_domain) continue;

    const hasMatchingEmail = order.source_email_ids.some(
      email_id => emailsInThread.find(e => e.email_id === email_id)
    );

    if (hasMatchingEmail) {
      matchingOrders.push(order);
    }
  }

  return matchingOrders;
}
