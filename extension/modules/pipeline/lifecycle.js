/**
 * Module: pipeline/lifecycle
 * Loading: importScripts (service worker)
 *
 * P8: Apply Event & Compute Deadline (FREE)
 *
 * Applies email events to Orders and computes return_by_date:
 *
 * Deadline Priority:
 * 1. explicit_return_by_date → deadline_confidence: 'exact'
 * 2. return_window_days + anchor_date → deadline_confidence: 'estimated'
 * 3. merchant_rules[domain] + anchor_date → deadline_confidence: 'estimated'
 * 4. null → deadline_confidence: 'unknown'
 *
 * Anchor date priority for estimated:
 * 1. delivery_date (best - clock starts at delivery)
 * 2. ship_date (fallback)
 * 3. purchase_date (last resort)
 *
 * Alert Safety:
 * - Only show in Return Watch if deadline_confidence !== 'unknown'
 * - Only alert if 'exact' OR ('estimated' + delivery_date exists)
 * - NEVER alert for hint-only links
 */

const LIFECYCLE_LOG_PREFIX = '[ReturnWatch:Lifecycle]';

// ============================================================
// CONSTANTS
// ============================================================

/**
 * Default return windows for major retailers (used when no rule set).
 * These are conservative estimates - users should set their own rules.
 */
const DEFAULT_RETURN_WINDOWS = {
  'amazon.com': 30,
  'target.com': 90,
  'walmart.com': 90,
  'bestbuy.com': 15,
  'costco.com': 90,  // Note: Costco is in blocklist for groceries, but may have other purchases
  'nordstrom.com': 365,
  'zappos.com': 365,
  'rei.com': 365,
  'llbean.com': 365,
  'kohls.com': 180,
  'macys.com': 90,
  'sephora.com': 60,
  'ulta.com': 60,
  'homedepot.com': 90,
  'lowes.com': 90,
  'wayfair.com': 30,
  'ikea.com': 365,
  'gap.com': 30,
  'oldnavy.com': 30,
  'bananarepublic.com': 30,
  'athleta.com': 60,
  'nike.com': 60,
  'adidas.com': 60,
};

// ============================================================
// DATE UTILITIES
// ============================================================

/**
 * Add days to a date string.
 *
 * @param {string} dateStr - ISO date string (YYYY-MM-DD)
 * @param {number} days - Number of days to add
 * @returns {string} New ISO date string
 */
function addDays(dateStr, days) {
  const date = new Date(dateStr.split('T')[0] + 'T00:00:00Z');
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().split('T')[0];
}

/**
 * Calculate days between two dates.
 *
 * @param {string} startDate - ISO date string
 * @param {string} endDate - ISO date string
 * @returns {number} Days between (negative if endDate is before startDate)
 */
function daysBetween(startDate, endDate) {
  const start = new Date(startDate.split('T')[0] + 'T00:00:00Z');
  const end = new Date(endDate.split('T')[0] + 'T00:00:00Z');
  const diffMs = end.getTime() - start.getTime();
  return Math.floor(diffMs / (1000 * 60 * 60 * 24));
}

/**
 * Get today's date as ISO string in user's local timezone.
 *
 * Note: We use local timezone for "today" to match user expectations.
 * If it's 11pm local time, the user expects "today" to be today, not tomorrow (UTC).
 *
 * @returns {string} Today in YYYY-MM-DD format (local timezone)
 */
function getToday() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// ============================================================
// DEADLINE COMPUTATION
// ============================================================

/**
 * Get the anchor date for computing return deadline.
 *
 * Priority:
 * 1. delivery_date (best - actual confirmed delivery, most retailers start clock here)
 * 2. estimated_delivery_date (good - estimated delivery from order confirmation)
 * 3. ship_date (fallback)
 * 4. purchase_date (last resort)
 *
 * @param {Order} order
 * @returns {{anchor_date: string|null, anchor_type: 'delivery' | 'estimated_delivery' | 'ship' | 'purchase' | null}}
 */
function getAnchorDate(order) {
  // Actual confirmed delivery date (from delivery confirmation email)
  if (order.delivery_date) {
    return { anchor_date: order.delivery_date, anchor_type: 'delivery' };
  }

  // Estimated delivery date (from order confirmation or shipping email)
  if (order.estimated_delivery_date) {
    return { anchor_date: order.estimated_delivery_date, anchor_type: 'estimated_delivery' };
  }

  if (order.ship_date) {
    return { anchor_date: order.ship_date, anchor_type: 'ship' };
  }

  if (order.purchase_date) {
    return { anchor_date: order.purchase_date, anchor_type: 'purchase' };
  }

  return { anchor_date: null, anchor_type: null };
}

/**
 * Get return window days for an order.
 *
 * Priority:
 * 1. Order's explicit return_window_days
 * 2. User-set merchant rule
 * 3. Default return window for known retailers
 * 4. null (unknown)
 *
 * @param {Order} order
 * @returns {Promise<number|null>}
 */
async function getReturnWindowDays(order) {
  // 1. Order has explicit window
  if (order.return_window_days) {
    return order.return_window_days;
  }

  // 2. Check merchant rules
  const merchantRule = await getMerchantRule(order.merchant_domain);
  if (merchantRule !== null) {
    return merchantRule;
  }

  // 3. Check default windows
  const defaultWindow = DEFAULT_RETURN_WINDOWS[order.merchant_domain];
  if (defaultWindow) {
    return defaultWindow;
  }

  return null;
}

/**
 * Compute the return_by_date and deadline_confidence for an Order.
 *
 * @param {Order} order
 * @returns {Promise<{return_by_date: string|null, deadline_confidence: DeadlineConfidence}>}
 */
async function computeReturnByDate(order) {
  // Priority 1: Explicit return-by date from email
  if (order.explicit_return_by_date) {
    console.log(LIFECYCLE_LOG_PREFIX, 'DEADLINE_EXACT', order.order_key,
      'explicit_return_by_date:', order.explicit_return_by_date);

    return {
      return_by_date: order.explicit_return_by_date,
      deadline_confidence: DEADLINE_CONFIDENCE.EXACT,
    };
  }

  // Get anchor date and window days for estimated deadline
  const { anchor_date, anchor_type } = getAnchorDate(order);
  const window_days = await getReturnWindowDays(order);

  // Priority 2: Window + anchor date
  if (window_days && anchor_date) {
    const return_by_date = addDays(anchor_date, window_days);

    console.log(LIFECYCLE_LOG_PREFIX, 'DEADLINE_ESTIMATED', order.order_key,
      `${window_days} days from ${anchor_type}(${anchor_date}) = ${return_by_date}`);

    return {
      return_by_date,
      deadline_confidence: DEADLINE_CONFIDENCE.ESTIMATED,
    };
  }

  // Priority 3: Unknown
  console.log(LIFECYCLE_LOG_PREFIX, 'DEADLINE_UNKNOWN', order.order_key,
    `window_days=${window_days}, anchor_date=${anchor_date}`);

  return {
    return_by_date: null,
    deadline_confidence: DEADLINE_CONFIDENCE.UNKNOWN,
  };
}

/**
 * Determine if an order should appear in Return Watch.
 *
 * Rules:
 * - Must have deadline_confidence !== 'unknown'
 * - Must be active (not returned/dismissed)
 * - Must not be expired (return_by_date >= today)
 *
 * @param {Order} order
 * @returns {boolean}
 */
function shouldShowInReturnWatch(order) {
  // Must be active
  if (order.order_status !== ORDER_STATUS.ACTIVE) {
    return false;
  }

  // Must have known deadline
  if (order.deadline_confidence === DEADLINE_CONFIDENCE.UNKNOWN) {
    return false;
  }

  // Must have return_by_date
  if (!order.return_by_date) {
    return false;
  }

  // Must not be expired
  const today = getToday();
  if (order.return_by_date < today) {
    return false;
  }

  return true;
}

/**
 * Determine if an order should trigger an alert.
 *
 * Alert Safety Rules:
 * - Exact deadline: always OK to alert
 * - Estimated deadline: only if delivery_date exists (more reliable)
 * - Unknown deadline: NEVER alert
 *
 * @param {Order} order
 * @returns {boolean}
 */
function shouldAlert(order) {
  if (!shouldShowInReturnWatch(order)) {
    return false;
  }

  // Exact deadline: always safe to alert
  if (order.deadline_confidence === DEADLINE_CONFIDENCE.EXACT) {
    return true;
  }

  // Estimated: only if we have delivery date (clock started)
  if (order.deadline_confidence === DEADLINE_CONFIDENCE.ESTIMATED) {
    return !!order.delivery_date;
  }

  return false;
}

/**
 * Calculate days remaining until return deadline.
 *
 * @param {Order} order
 * @returns {number|null} Days remaining (negative if expired), null if no deadline
 */
function getDaysRemaining(order) {
  if (!order.return_by_date) {
    return null;
  }

  const today = getToday();
  return daysBetween(today, order.return_by_date);
}

/**
 * Determine urgency level for an order.
 *
 * @param {Order} order
 * @returns {'expired' | 'urgent' | 'soon' | 'normal' | null}
 */
function getUrgencyLevel(order) {
  const daysRemaining = getDaysRemaining(order);

  if (daysRemaining === null) {
    return null;
  }

  if (daysRemaining < 0) {
    return 'expired';
  }

  if (daysRemaining <= 3) {
    return 'urgent';
  }

  if (daysRemaining <= 7) {
    return 'soon';
  }

  return 'normal';
}

// ============================================================
// EVENT APPLICATION
// ============================================================

/**
 * Apply an email event to an Order and recompute deadline.
 *
 * This is the final step of the pipeline for each email.
 *
 * @param {Order} order
 * @returns {Promise<Order>} Updated order with computed deadline
 */
async function applyEventAndComputeDeadline(order) {
  // Compute return_by_date and confidence
  const { return_by_date, deadline_confidence } = await computeReturnByDate(order);

  // Update order
  order.return_by_date = return_by_date;
  order.deadline_confidence = deadline_confidence;
  order.updated_at = new Date().toISOString();

  console.log(LIFECYCLE_LOG_PREFIX, 'DEADLINE_COMPUTED', order.order_key,
    `return_by_date=${return_by_date}, confidence=${deadline_confidence}`);

  return order;
}

/**
 * Recompute deadline for an order.
 * Call this when merchant rules change or new data is available.
 *
 * @param {string} order_key
 * @returns {Promise<Order|null>}
 */
async function recomputeOrderDeadline(order_key) {
  const order = await getOrder(order_key);
  if (!order) {
    console.log(LIFECYCLE_LOG_PREFIX, 'RECOMPUTE_FAILED', 'order not found:', order_key);
    return null;
  }

  const updatedOrder = await applyEventAndComputeDeadline(order);
  await upsertOrder(updatedOrder);

  return updatedOrder;
}

/**
 * Recompute deadlines for all orders from a specific merchant.
 * Call this when a merchant rule is added/updated.
 *
 * @param {string} merchant_domain
 * @returns {Promise<number>} Number of orders updated
 */
async function recomputeMerchantDeadlines(merchant_domain) {
  const allOrders = await getAllOrders();
  let updated = 0;

  for (const order of allOrders) {
    if (order.merchant_domain === merchant_domain && order.order_status === ORDER_STATUS.ACTIVE) {
      await recomputeOrderDeadline(order.order_key);
      updated++;
    }
  }

  console.log(LIFECYCLE_LOG_PREFIX, 'RECOMPUTE_MERCHANT', merchant_domain, `updated ${updated} orders`);

  return updated;
}

// ============================================================
// QUERY HELPERS
// ============================================================

/**
 * Get orders for Return Watch display.
 * Filters to deadline-known, active, non-expired orders.
 *
 * @returns {Promise<{expiringSoon: Order[], active: Order[]}>}
 */
async function getReturnWatchOrders() {
  const allOrders = await getAllOrders();

  const returnWatchOrders = allOrders.filter(shouldShowInReturnWatch);

  // Sort by return_by_date ASC
  returnWatchOrders.sort((a, b) => {
    if (!a.return_by_date) return 1;
    if (!b.return_by_date) return -1;
    return a.return_by_date.localeCompare(b.return_by_date);
  });

  // Split into expiring soon (<=7 days) and active (>7 days)
  const expiringSoon = [];
  const active = [];

  for (const order of returnWatchOrders) {
    const daysRemaining = getDaysRemaining(order);
    if (daysRemaining !== null && daysRemaining <= 7) {
      expiringSoon.push(order);
    } else {
      active.push(order);
    }
  }

  return { expiringSoon, active };
}

/**
 * Get all purchases for "All Purchases" display.
 * Shows all active orders, sorted by purchase_date DESC.
 *
 * @returns {Promise<Order[]>}
 */
async function getAllPurchasesForDisplay() {
  const allOrders = await getAllOrders();

  // Filter to active only
  const activeOrders = allOrders.filter(o => o.order_status === ORDER_STATUS.ACTIVE);

  // Sort by purchase_date DESC (most recent first)
  activeOrders.sort((a, b) => {
    if (!a.purchase_date) return 1;
    if (!b.purchase_date) return -1;
    return b.purchase_date.localeCompare(a.purchase_date);
  });

  return activeOrders;
}

// ============================================================
// UNIFIED VISIBLE ORDERS
// ============================================================

/**
 * Check if an order is stale (expired more than 14 days ago).
 * Stale orders are hidden from the unified list.
 *
 * @param {Order} order
 * @returns {boolean}
 */
function isStaleOrder(order) {
  if (!order.return_by_date) return false;

  const today = getToday();
  const returnDate = order.return_by_date.split('T')[0];

  // Not expired yet
  if (returnDate >= today) return false;

  // Expired more than 14 days ago — too old to act on
  const daysSinceExpiry = daysBetween(returnDate, today);
  return daysSinceExpiry > 14;
}

/**
 * Get all visible orders for the unified purchase list.
 * Storage is the single source of truth — dedup happens at write time
 * via entity resolution (store.js resolveMatchingOrder + deduplicateStoredOrders).
 *
 * Visibility rules:
 * - Show: All orders with order_status === 'active'
 * - Hide: returned, cancelled, dismissed
 * - Hide stale: expired AND 90+ days since purchase_date
 *
 * Sort order:
 * 1. Orders with return_by_date — deadline ASC (soonest first)
 * 2. Orders without return_by_date — purchase_date DESC (newest first)
 *
 * @returns {Promise<Order[]>}
 */
async function getVisibleOrders() {
  const allOrders = await getAllOrders();

  // Filter: active only, exclude stale
  const visible = allOrders.filter(o =>
    o.order_status === ORDER_STATUS.ACTIVE && !isStaleOrder(o)
  );

  // Split into has-deadline and no-deadline groups
  const withDeadline = [];
  const withoutDeadline = [];

  for (const order of visible) {
    if (order.return_by_date) {
      withDeadline.push(order);
    } else {
      withoutDeadline.push(order);
    }
  }

  // Sort with-deadline by return_by_date ASC (soonest first)
  withDeadline.sort((a, b) => a.return_by_date.localeCompare(b.return_by_date));

  // Sort without-deadline by purchase_date DESC (newest first)
  withoutDeadline.sort((a, b) => {
    if (!a.purchase_date) return 1;
    if (!b.purchase_date) return -1;
    return b.purchase_date.localeCompare(a.purchase_date);
  });

  return [...withDeadline, ...withoutDeadline];
}

/**
 * Get orders that have been marked as returned.
 * Used for the "Returned" accordion with undo functionality.
 *
 * @returns {Promise<Order[]>}
 */
async function getReturnedOrders() {
  const allOrders = await getAllOrders();

  return allOrders
    .filter(o => o.order_status === ORDER_STATUS.RETURNED)
    .sort((a, b) => {
      if (!a.updated_at) return 1;
      if (!b.updated_at) return -1;
      return b.updated_at.localeCompare(a.updated_at);
    });
}
