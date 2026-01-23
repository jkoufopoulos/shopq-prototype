/**
 * P2: Primary Key Linking (FREE)
 *
 * Links emails to existing Orders using primary keys only:
 * - order_id (merchant order number)
 * - tracking_number (shipping tracking)
 *
 * No fuzzy matching. No fingerprinting. Primary keys only.
 */

const LINKER_LOG_PREFIX = '[ReturnWatch:Linker]';

// ============================================================
// REGEX PATTERNS FOR EXTRACTION
// ============================================================

/**
 * Order ID patterns.
 * Matches various formats like:
 * - Order #123-456-789
 * - Order: ABC123456
 * - Order Number: 12345678
 */
const ORDER_ID_PATTERNS = [
  // Amazon-style: 123-4567890-1234567
  /order[#:\s]+(\d{3}-\d{7}-\d{7})/i,

  // Generic: Order #ABC123456 or Order: 12345678
  /order[#:\s]+([A-Z0-9]{6,20})/i,

  // Order Number: format
  /order\s+number[:\s]+([A-Z0-9-]{5,25})/i,

  // Confirmation number
  /confirmation[#:\s]+([A-Z0-9-]{5,20})/i,

  // Invoice number (fallback)
  /invoice[#:\s]+([A-Z0-9-]{5,20})/i,
];

/**
 * Tracking number patterns.
 * Matches various carrier formats.
 */
const TRACKING_PATTERNS = [
  // UPS: 1Z followed by 16 chars
  /(1Z[A-Z0-9]{16})/i,

  // FedEx: 12 or 15 or 20 digits
  /\b(\d{12,15})\b/,
  /\b(\d{20,22})\b/,

  // USPS: 20-22 digits or starts with specific prefixes
  /\b(9[0-9]{21,22})\b/,  // Starts with 9
  /\b(7[0-9]{19,21})\b/,  // Starts with 7

  // Generic "tracking" + number
  /tracking[#:\s]+([A-Z0-9]{10,30})/i,

  // "Track your package" patterns
  /track[^a-z]*package[^a-z]*([A-Z0-9]{10,25})/i,
];

// ============================================================
// EXTRACTION FUNCTIONS
// ============================================================

/**
 * Extract order_id from text.
 *
 * @param {string} text - Subject, snippet, or body text
 * @returns {string|null} Order ID or null
 */
function extractOrderId(text) {
  if (!text) return null;

  for (const pattern of ORDER_ID_PATTERNS) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const orderId = match[1].toUpperCase();
      // Basic validation: not too short, not all zeros
      if (orderId.length >= 5 && !/^0+$/.test(orderId.replace(/-/g, ''))) {
        return orderId;
      }
    }
  }

  return null;
}

/**
 * Extract tracking_number from text.
 *
 * @param {string} text - Subject, snippet, or body text
 * @returns {string|null} Tracking number or null
 */
function extractTrackingNumber(text) {
  if (!text) return null;

  for (const pattern of TRACKING_PATTERNS) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const tracking = match[1].toUpperCase();
      // Basic validation: reasonable length
      if (tracking.length >= 10 && tracking.length <= 35) {
        return tracking;
      }
    }
  }

  return null;
}

/**
 * Extract both primary keys from available text.
 *
 * @param {string} subject
 * @param {string} snippet
 * @param {string} [body] - Optional body text
 * @returns {{order_id: string|null, tracking_number: string|null}}
 */
function extractPrimaryKeys(subject, snippet, body = '') {
  // Combine all text sources, prioritizing subject
  const combined = `${subject || ''} ${snippet || ''} ${body || ''}`;

  return {
    order_id: extractOrderId(combined),
    tracking_number: extractTrackingNumber(combined),
  };
}

// ============================================================
// LINKING FUNCTIONS
// ============================================================

/**
 * Find existing Order by primary keys.
 * Priority: order_id first, then tracking_number.
 *
 * @param {string|null} order_id
 * @param {string|null} tracking_number
 * @returns {Promise<{order: Order|null, linked_by: string|null}>}
 */
async function linkByPrimaryKey(order_id, tracking_number) {
  // Try order_id first (higher priority)
  if (order_id) {
    const order = await findOrderByOrderId(order_id);
    if (order) {
      console.log(LINKER_LOG_PREFIX, 'PRIMARY_MERGE_BY_ORDER_ID', order_id, '->', order.order_key);
      return { order, linked_by: 'order_id' };
    }
  }

  // Try tracking_number
  if (tracking_number) {
    const order = await findOrderByTracking(tracking_number);
    if (order) {
      console.log(LINKER_LOG_PREFIX, 'PRIMARY_MERGE_BY_TRACKING', tracking_number, '->', order.order_key);
      return { order, linked_by: 'tracking_number' };
    }
  }

  // No match found
  return { order: null, linked_by: null };
}

/**
 * Check if email can be linked to existing Order via primary keys.
 *
 * @param {string} subject
 * @param {string} snippet
 * @param {string} [body]
 * @returns {Promise<{linked: boolean, order: Order|null, linked_by: string|null, keys: {order_id: string|null, tracking_number: string|null}}>}
 */
async function attemptPrimaryKeyLink(subject, snippet, body = '') {
  const keys = extractPrimaryKeys(subject, snippet, body);

  if (!keys.order_id && !keys.tracking_number) {
    return { linked: false, order: null, linked_by: null, keys };
  }

  const { order, linked_by } = await linkByPrimaryKey(keys.order_id, keys.tracking_number);

  return {
    linked: order !== null,
    order,
    linked_by,
    keys,
  };
}

/**
 * Detect if email contains BOTH primary keys (for merge escalation).
 *
 * @param {string|null} order_id
 * @param {string|null} tracking_number
 * @returns {Promise<{needs_escalation: boolean, order_id_order: Order|null, tracking_order: Order|null}>}
 */
async function checkMergeEscalation(order_id, tracking_number) {
  if (!order_id || !tracking_number) {
    return { needs_escalation: false, order_id_order: null, tracking_order: null };
  }

  const order_id_order = await findOrderByOrderId(order_id);
  const tracking_order = await findOrderByTracking(tracking_number);

  // Check if both exist AND are different orders
  if (order_id_order && tracking_order && order_id_order.order_key !== tracking_order.order_key) {
    console.log(LINKER_LOG_PREFIX, 'MERGE_ESCALATION_DETECTED',
      'order_id:', order_id, '-> order_key:', order_id_order.order_key,
      'tracking:', tracking_number, '-> order_key:', tracking_order.order_key
    );
    return {
      needs_escalation: true,
      order_id_order,
      tracking_order,
    };
  }

  return { needs_escalation: false, order_id_order: null, tracking_order: null };
}
