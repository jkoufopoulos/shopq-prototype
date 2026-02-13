/**
 * Reclaim v2 Storage Schema
 * Local-first order tracking — no email/user/tracking fields.
 *
 * Loaded via importScripts in the service worker.
 */

/**
 * @typedef {'active' | 'returned' | 'dismissed'} OrderStatus
 */

/**
 * @typedef {'exact' | 'estimated' | 'unknown'} DeadlineConfidence
 */

/**
 * Local-captured order.
 *
 * @typedef {Object} Order
 * @property {string} order_key - Stable internal ID (hash)
 * @property {string} merchant_domain - e.g., "amazon.com"
 * @property {string} merchant_name - e.g., "Amazon"
 * @property {string} [order_id] - Merchant order number
 * @property {string} item_description - Brief description of item(s)
 * @property {number} [amount] - Purchase amount
 * @property {string} [currency] - Currency code (default "USD")
 * @property {string} order_date - ISO date (when order was placed)
 * @property {string} [return_by_date] - Computed return deadline (ISO date)
 * @property {DeadlineConfidence} deadline_confidence - Confidence level
 * @property {OrderStatus} order_status - Current status
 * @property {string} capture_url - URL where order was captured
 * @property {string} captured_at - ISO datetime of capture
 * @property {boolean} notified_7day - Whether 7-day notification was sent
 * @property {boolean} notified_3day - Whether 3-day notification was sent
 * @property {string} created_at - ISO datetime
 * @property {string} updated_at - ISO datetime
 */

// Storage keys
const STORAGE_KEYS = {
  ORDERS_BY_KEY: 'orders_by_key',
  ORDER_KEY_BY_ORDER_ID: 'order_key_by_order_id',
  MERCHANT_POLICIES: 'merchant_policies',
  SETTINGS: 'settings',
};

// Order status values
const ORDER_STATUS = {
  ACTIVE: 'active',
  RETURNED: 'returned',
  DISMISSED: 'dismissed',
};

// Deadline confidence levels
const DEADLINE_CONFIDENCE = {
  EXACT: 'exact',
  ESTIMATED: 'estimated',
  UNKNOWN: 'unknown',
};

/**
 * Generate a stable order key from merchant domain + order ID.
 * Simplified from v1 — no user_id (local-only).
 *
 * @param {string} merchant_domain
 * @param {string} identifier - order_id or fallback identifier
 * @returns {string} Stable hash key
 */
function generateOrderKey(merchant_domain, identifier) {
  const input = `${merchant_domain}:${identifier}`;
  // djb2 hash
  let hash = 5381;
  for (let i = 0; i < input.length; i++) {
    hash = ((hash << 5) + hash) + input.charCodeAt(i);
    hash = hash & hash;
  }
  return 'order_' + (hash >>> 0).toString(16);
}

/**
 * Create an Order object with all fields.
 *
 * @param {Object} params
 * @param {string} params.order_key
 * @param {string} params.merchant_domain
 * @param {string} params.merchant_name
 * @param {string} params.item_description
 * @param {string} params.order_date - ISO date
 * @param {string} params.capture_url
 * @param {string} [params.order_id]
 * @param {number} [params.amount]
 * @param {string} [params.currency]
 * @param {string} [params.return_by_date]
 * @param {DeadlineConfidence} [params.deadline_confidence]
 * @returns {Order}
 */
function createOrder({
  order_key,
  merchant_domain,
  merchant_name,
  item_description,
  order_date,
  capture_url,
  order_id,
  amount,
  currency,
  return_by_date,
  deadline_confidence,
}) {
  const now = new Date().toISOString();
  return {
    order_key,
    merchant_domain,
    merchant_name,
    order_id: order_id || null,
    item_description,
    amount: amount || null,
    currency: currency || 'USD',
    order_date,
    return_by_date: return_by_date || null,
    deadline_confidence: deadline_confidence || DEADLINE_CONFIDENCE.UNKNOWN,
    order_status: ORDER_STATUS.ACTIVE,
    capture_url,
    captured_at: now,
    notified_7day: false,
    notified_3day: false,
    created_at: now,
    updated_at: now,
  };
}
