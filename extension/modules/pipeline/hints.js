/**
 * P3: Thread Hinting (HINT-ONLY)
 *
 * CRITICAL: v0.6.2 BEHAVIOR
 *
 * Thread hints do NOT update lifecycle fields.
 * Thread hints do NOT trigger alerts.
 * Thread hints ONLY attach email as "related" for display/provenance.
 *
 * This is explicitly NOT a merge mechanism. It's purely for:
 * - Showing related emails in Order detail
 * - Providing context to the user
 * - Provenance tracking
 *
 * If a hint-attached email later reveals a primary key, it becomes
 * a normal primary merge at that point.
 */

const HINTS_LOG_PREFIX = '[ReturnWatch:Hints]';

// ============================================================
// CONSTANTS
// ============================================================

/**
 * Maximum age of orders to consider for thread matching.
 * Orders older than this won't be linked via thread hints.
 */
const THREAD_MATCH_WINDOW_DAYS = 30;

// ============================================================
// THREAD HINT FUNCTIONS
// ============================================================

/**
 * Find a single Order that matches by thread_id and merchant_domain.
 *
 * Per v0.6.2: Only matches if EXACTLY one Order matches.
 * If multiple match, we don't hint (ambiguous).
 *
 * @param {string} thread_id - Gmail thread ID
 * @param {string} merchant_domain - Merchant domain from email
 * @returns {Promise<Order|null>} Matching Order or null
 */
async function findOrderByThread(thread_id, merchant_domain) {
  if (!thread_id || !merchant_domain) {
    return null;
  }

  // Use the store function to find orders by thread
  const matchingOrders = await findOrdersByThread(thread_id, merchant_domain);

  // Filter to orders within the window
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - THREAD_MATCH_WINDOW_DAYS);
  const cutoffISO = cutoffDate.toISOString().split('T')[0];

  const recentOrders = matchingOrders.filter(order => {
    // Check if order is recent enough
    const orderDate = order.purchase_date || order.created_at;
    return orderDate && orderDate >= cutoffISO;
  });

  // Only return if EXACTLY one match
  if (recentOrders.length === 1) {
    console.log(HINTS_LOG_PREFIX, 'THREAD_MATCH_FOUND', thread_id, '->', recentOrders[0].order_key);
    return recentOrders[0];
  }

  if (recentOrders.length > 1) {
    console.log(HINTS_LOG_PREFIX, 'THREAD_MATCH_AMBIGUOUS', thread_id, 'matches', recentOrders.length, 'orders');
  }

  return null;
}

/**
 * Attach an email as a hint to an existing Order.
 *
 * CRITICAL: This function MUST NOT update any lifecycle fields.
 * It only adds the email_id to source_email_ids for provenance.
 *
 * @param {string} email_id - Gmail message ID
 * @param {string} order_key - Order to attach to
 * @returns {Promise<{attached: boolean, order: Order|null}>}
 */
async function attachAsHint(email_id, order_key) {
  if (!email_id || !order_key) {
    return { attached: false, order: null };
  }

  const order = await getOrder(order_key);
  if (!order) {
    console.log(HINTS_LOG_PREFIX, 'HINT_ATTACH_FAILED', 'order not found:', order_key);
    return { attached: false, order: null };
  }

  // Check if already attached
  if (order.source_email_ids.includes(email_id)) {
    console.log(HINTS_LOG_PREFIX, 'HINT_ALREADY_ATTACHED', email_id, '->', order_key);
    return { attached: true, order };
  }

  // Add to source_email_ids ONLY - no other updates
  // This is the ONLY mutation allowed for hint attachments
  order.source_email_ids.push(email_id);
  order.updated_at = new Date().toISOString();

  // Save the order
  await upsertOrder(order);

  console.log(HINTS_LOG_PREFIX, 'HINT_ATTACH', email_id, '->', order_key, '(no field updates)');

  return { attached: true, order };
}

/**
 * Attempt to attach an email via thread hint.
 *
 * This is the main entry point for P3 in the pipeline.
 *
 * @param {string} email_id - Gmail message ID
 * @param {string} thread_id - Gmail thread ID
 * @param {string} merchant_domain - Merchant domain from email
 * @returns {Promise<{hinted: boolean, order: Order|null}>}
 */
async function attemptThreadHint(email_id, thread_id, merchant_domain) {
  if (!thread_id || !merchant_domain) {
    return { hinted: false, order: null };
  }

  // Find matching order
  const order = await findOrderByThread(thread_id, merchant_domain);

  if (!order) {
    return { hinted: false, order: null };
  }

  // Attach as hint (NO lifecycle updates)
  const { attached, order: updatedOrder } = await attachAsHint(email_id, order.order_key);

  return { hinted: attached, order: updatedOrder };
}

/**
 * IMPORTANT: Documentation of what hint attachments DO NOT do.
 *
 * Per v0.6.2, hint-attached emails MUST NOT:
 * - Update purchase_date
 * - Update ship_date
 * - Update delivery_date
 * - Update return_window_days
 * - Update explicit_return_by_date
 * - Update return_by_date
 * - Update evidence_quote or evidence_message_id
 * - Update order_id or tracking_number indices
 * - Trigger alerts
 * - Update item_summary
 * - Update amount
 * - Update merchant_display_name
 *
 * Hint attachments ONLY:
 * - Add email_id to source_email_ids
 * - Update updated_at timestamp
 *
 * This is intentionally restrictive to prevent false associations
 * from polluting order data. If the email contains primary keys,
 * it should go through the normal P2 primary key linking instead.
 */
