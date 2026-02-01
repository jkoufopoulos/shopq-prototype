/**
 * Return Watch Storage Schema
 * Type definitions and constants for chrome.storage.local
 *
 * Note: This file uses JSDoc for type annotations.
 * Types are for documentation only - no runtime validation.
 */

/**
 * @typedef {'active' | 'returned' | 'dismissed' | 'cancelled'} OrderStatus
 */

/**
 * @typedef {'exact' | 'estimated' | 'unknown'} DeadlineConfidence
 */

/**
 * @typedef {'confirmation' | 'shipping' | 'delivery' | 'cancellation' | 'other'} EmailType
 */

/**
 * Central entity representing a purchase order.
 * One Order per real-world order, linked to multiple emails.
 *
 * @typedef {Object} Order
 * @property {string} order_key - Stable internal ID (hash)
 * @property {string} user_id - User who owns this order
 * @property {string} merchant_domain - e.g., "amazon.com"
 * @property {string} merchant_display_name - e.g., "Amazon"
 * @property {string} [order_id] - Merchant order number (primary key for linking)
 * @property {string} [tracking_number] - Shipping tracking number (secondary key)
 * @property {string} purchase_date - ISO date string
 * @property {string} [ship_date] - ISO date string
 * @property {string} [delivery_date] - ISO date string
 * @property {number} [return_window_days] - Days allowed for return
 * @property {string} [explicit_return_by_date] - ISO date if explicitly stated
 * @property {string} [return_by_date] - Computed return deadline (ISO date)
 * @property {DeadlineConfidence} deadline_confidence - Confidence level
 * @property {string} item_summary - Brief description of item(s)
 * @property {number} [amount] - Purchase amount
 * @property {string} currency - Default "USD"
 * @property {string} [evidence_message_id] - Gmail ID of email with return policy
 * @property {string} [evidence_quote] - Quoted text proving return policy
 * @property {string} [return_portal_link] - URL to merchant return portal
 * @property {OrderStatus} order_status - Current status
 * @property {string[]} source_email_ids - All linked email IDs
 * @property {string} created_at - ISO datetime
 * @property {string} updated_at - ISO datetime
 */

/**
 * Extracted data from rules-based parsing.
 *
 * @typedef {Object} ExtractedData
 * @property {string} [order_id]
 * @property {string} [tracking_number]
 * @property {number} [amount]
 * @property {string} [order_date] - ISO date
 * @property {string} [ship_date] - ISO date
 * @property {string} [delivery_date] - ISO date
 */

/**
 * LLM-extracted return policy data.
 *
 * @typedef {Object} LLMExtraction
 * @property {string} [deadline_date] - YYYY-MM-DD or null
 * @property {number} [window_days] - Number of days or null
 * @property {DeadlineConfidence} confidence - exact, estimated, or unknown
 * @property {string} [quote] - Quoted evidence text
 */

/**
 * Event record for a processed email.
 *
 * @typedef {Object} OrderEmail
 * @property {string} email_id - Gmail message ID
 * @property {string} [thread_id] - Gmail thread ID
 * @property {string} received_at - ISO datetime
 * @property {string} merchant_domain
 * @property {EmailType} email_type
 * @property {boolean} blocked - Was email blocked by filter
 * @property {boolean} processed - Has email been fully processed
 * @property {ExtractedData} [extracted] - Rule-extracted data
 * @property {LLMExtraction} [llm_extraction] - LLM-extracted return policy
 * @property {string} [template_hash] - For template caching
 */

/**
 * Complete storage schema for chrome.storage.local
 *
 * @typedef {Object} StorageSchema
 * @property {Object<string, Order>} orders_by_key - Orders indexed by order_key
 * @property {Object<string, string>} order_key_by_order_id - order_id -> order_key
 * @property {Object<string, string>} order_key_by_tracking - tracking_number -> order_key
 * @property {Object<string, OrderEmail>} order_emails_by_id - email_id -> OrderEmail
 * @property {string[]} processed_email_ids - Set of processed email IDs
 * @property {number} last_scan_epoch_ms - Last scan timestamp
 * @property {number} last_scan_internal_date_ms - Last processed email date
 * @property {Object<string, LLMExtraction>} [template_cache] - Template hash -> extraction
 */

// Storage keys (must match StorageSchema properties)
const STORAGE_KEYS = {
  ORDERS_BY_KEY: 'orders_by_key',
  ORDER_KEY_BY_ORDER_ID: 'order_key_by_order_id',
  ORDER_KEY_BY_TRACKING: 'order_key_by_tracking',
  ORDER_EMAILS_BY_ID: 'order_emails_by_id',
  PROCESSED_EMAIL_IDS: 'processed_email_ids',
  MERCHANT_RULES_BY_DOMAIN: 'merchant_rules_by_domain',
  LAST_SCAN_EPOCH_MS: 'last_scan_epoch_ms',
  LAST_SCAN_INTERNAL_DATE_MS: 'last_scan_internal_date_ms',
  LAST_SCAN_WINDOW_DAYS: 'last_scan_window_days',
  TEMPLATE_CACHE: 'template_cache',
};

// Order status values
const ORDER_STATUS = {
  ACTIVE: 'active',
  RETURNED: 'returned',
  DISMISSED: 'dismissed',
  CANCELLED: 'cancelled',
};

// Deadline confidence levels
const DEADLINE_CONFIDENCE = {
  EXACT: 'exact',
  ESTIMATED: 'estimated',
  UNKNOWN: 'unknown',
};

// Email type classifications
const EMAIL_TYPE = {
  CONFIRMATION: 'confirmation',
  SHIPPING: 'shipping',
  DELIVERY: 'delivery',
  CANCELLATION: 'cancellation',
  OTHER: 'other',
};

/**
 * Generate a stable order key from components.
 * Uses simple hash for consistency.
 *
 * @param {string} user_id
 * @param {string} merchant_domain
 * @param {string} identifier - order_id, tracking_number, or email_id
 * @returns {string} Stable hash key
 */
function generateOrderKey(user_id, merchant_domain, identifier) {
  const input = `${user_id}:${merchant_domain}:${identifier}`;
  // Simple hash function (djb2)
  let hash = 5381;
  for (let i = 0; i < input.length; i++) {
    hash = ((hash << 5) + hash) + input.charCodeAt(i);
    hash = hash & hash; // Convert to 32bit integer
  }
  // Convert to positive hex string
  return 'order_' + (hash >>> 0).toString(16);
}

/**
 * Create an Order object with all fields.
 *
 * @param {Object} params
 * @param {string} params.order_key
 * @param {string} params.user_id
 * @param {string} params.merchant_domain
 * @param {string} params.merchant_display_name
 * @param {string} params.item_summary
 * @param {string} params.purchase_date
 * @param {string[]} params.source_email_ids - Source email IDs
 * @param {string} [params.order_id] - Merchant order number
 * @param {string} [params.tracking_number] - Shipping tracking number
 * @param {string} [params.ship_date] - Ship date
 * @param {string} [params.delivery_date] - Delivery date
 * @param {number} [params.amount] - Purchase amount
 * @param {string} [params.currency] - Currency code
 * @param {number} [params.return_window_days] - Return window in days
 * @param {string} [params.explicit_return_by_date] - Explicit return deadline
 * @param {string} [params.return_portal_link] - Return portal URL
 * @returns {Order}
 */
function createOrder({
  order_key,
  user_id,
  merchant_domain,
  merchant_display_name,
  item_summary,
  purchase_date,
  source_email_ids,
  order_id,
  tracking_number,
  ship_date,
  delivery_date,
  amount,
  currency,
  return_window_days,
  explicit_return_by_date,
  return_portal_link,
}) {
  const now = new Date().toISOString();
  return {
    order_key,
    user_id,
    merchant_domain,
    merchant_display_name,
    order_id: order_id || null,
    tracking_number: tracking_number || null,
    item_summary,
    purchase_date,
    ship_date: ship_date || null,
    delivery_date: delivery_date || null,
    amount: amount || null,
    currency: currency || 'USD',
    return_window_days: return_window_days || null,
    explicit_return_by_date: explicit_return_by_date || null,
    return_portal_link: return_portal_link || null,
    deadline_confidence: DEADLINE_CONFIDENCE.UNKNOWN,
    order_status: ORDER_STATUS.ACTIVE,
    source_email_ids: source_email_ids || [],
    created_at: now,
    updated_at: now,
  };
}

/**
 * Create an OrderEmail record.
 *
 * @param {Object} params
 * @param {string} params.email_id
 * @param {string} [params.thread_id]
 * @param {string} params.received_at
 * @param {string} params.merchant_domain
 * @param {EmailType} params.email_type
 * @param {boolean} [params.blocked=false]
 * @returns {OrderEmail}
 */
function createOrderEmail({
  email_id,
  thread_id,
  received_at,
  merchant_domain,
  email_type,
  blocked = false,
}) {
  return {
    email_id,
    thread_id,
    received_at,
    merchant_domain,
    email_type,
    blocked,
    processed: false,
  };
}
