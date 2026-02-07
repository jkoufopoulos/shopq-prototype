/**
 * P6: Order Keying & Upsert + P7: Safe Merge Escalation
 *
 * P6: Creates or updates Orders with stable order_key generation:
 * - Key priority: order_id → tracking_number → email_id (temp)
 * - Creates OrderEmail records
 * - Manages indices for lookup
 *
 * P7: Safe merge escalation when email contains BOTH order_id AND tracking_number
 *     that map to DIFFERENT existing Orders.
 * - Winner = order_id-keyed Order
 * - Loser = tracking-keyed Order
 * - Merge loser into winner, update indices
 *
 * CRITICAL: Only primary key merging. NO fuzzy matching.
 */

const RESOLVER_LOG_PREFIX = '[ReturnWatch:Resolver]';

// ============================================================
// ORDER KEY GENERATION
// ============================================================

/**
 * Generate a stable order_key for an Order.
 *
 * Priority:
 * 1. merchant_domain + order_id (best - tied to merchant's order system)
 * 2. merchant_domain + tracking_number (good - tied to shipment)
 * 3. user_id + email_id (temporary - will be replaced when better key found)
 *
 * @param {string} user_id
 * @param {string} merchant_domain
 * @param {string|null} order_id
 * @param {string|null} tracking_number
 * @param {string} email_id - Fallback for temp key
 * @returns {{order_key: string, key_type: 'order_id' | 'tracking' | 'temp'}}
 */
function computeOrderKey(user_id, merchant_domain, order_id, tracking_number, email_id) {
  // Normalize domain
  const domain = (merchant_domain || 'unknown').toLowerCase();

  // Priority 1: order_id
  if (order_id) {
    const key = `${domain}:${order_id}`;
    console.log(RESOLVER_LOG_PREFIX, 'KEY_COMPUTED', 'order_id', key);
    return { order_key: key, key_type: 'order_id' };
  }

  // Priority 2: tracking_number
  if (tracking_number) {
    const key = `${domain}:tracking:${tracking_number}`;
    console.log(RESOLVER_LOG_PREFIX, 'KEY_COMPUTED', 'tracking', key);
    return { order_key: key, key_type: 'tracking' };
  }

  // Priority 3: temp key from email_id
  const key = `${user_id}:temp:${email_id}`;
  console.log(RESOLVER_LOG_PREFIX, 'TEMP_ORDER_KEY_CREATED', key);
  return { order_key: key, key_type: 'temp' };
}

// ============================================================
// ORDER CREATION
// ============================================================

/**
 * Create a new Order from email data.
 *
 * @param {Object} params
 * @param {string} params.user_id
 * @param {string} params.email_id
 * @param {string} params.merchant_domain
 * @param {string} params.merchant_display_name
 * @param {ExtractedFields} params.extracted
 * @param {EmailType} params.email_type
 * @param {'full' | 'partial'} params.seed_type
 * @returns {Order}
 */
function createNewOrder({
  user_id,
  email_id,
  merchant_domain,
  merchant_display_name,
  extracted,
  email_type,
  seed_type,
}) {
  const { order_key, key_type } = computeOrderKey(
    user_id,
    merchant_domain,
    extracted.order_id,
    extracted.tracking_number,
    email_id
  );

  const now = new Date().toISOString();

  // Determine initial dates based on email type
  let purchase_date = extracted.purchase_date;
  let ship_date = extracted.ship_date;
  let delivery_date = null;
  let estimated_delivery_date = extracted.estimated_delivery_date;

  // For confirmation emails, use today as purchase date if not extracted
  if (email_type === EMAIL_TYPE.CONFIRMATION && !purchase_date) {
    purchase_date = now.split('T')[0];
  }

  // For shipping emails, use today as ship date if not extracted
  if (email_type === EMAIL_TYPE.SHIPPING && !ship_date) {
    ship_date = now.split('T')[0];
  }

  // For delivery emails, set actual delivery_date
  // Only DELIVERY emails set the actual delivery_date
  if (email_type === EMAIL_TYPE.DELIVERY) {
    delivery_date = extracted.actual_delivery_date || extracted.delivery_date || now.split('T')[0];
  }

  // For confirmation/shipping emails, preserve estimated delivery date
  // Don't set delivery_date from confirmation/shipping - only estimated_delivery_date
  if ((email_type === EMAIL_TYPE.CONFIRMATION || email_type === EMAIL_TYPE.SHIPPING) && !estimated_delivery_date) {
    // Check if we have an estimated date from extraction
    estimated_delivery_date = extracted.estimated_delivery_date || null;
  }

  const order = createOrder({
    order_key,
    user_id,
    merchant_domain,
    order_id: extracted.order_id,
    tracking_number: extracted.tracking_number,
    merchant_display_name,
    item_summary: extracted.item_summary || 'Unknown item',
    amount: extracted.amount,
    currency: extracted.currency || 'USD',
    purchase_date,
    ship_date,
    delivery_date,
    estimated_delivery_date,
    return_window_days: extracted.return_window_days,
    explicit_return_by_date: extracted.explicit_return_by_date,
    return_portal_link: extracted.return_portal_link,
    source_email_ids: [email_id],
  });

  console.log(RESOLVER_LOG_PREFIX, seed_type === 'full' ? 'CREATE_ORDER_FULL' : 'CREATE_ORDER_PARTIAL',
    order_key, 'from email', email_id);

  return order;
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
 * @param {boolean} params.blocked
 * @param {ExtractedFields} [params.extracted]
 * @returns {OrderEmail}
 */
function createEmailRecord({
  email_id,
  thread_id,
  received_at,
  merchant_domain,
  email_type,
  blocked,
  extracted,
}) {
  return {
    email_id,
    thread_id: thread_id || null,
    received_at,
    merchant_domain,
    email_type,
    blocked,
    processed: true,
    extracted: extracted || null,
    llm_extraction: null,
    template_hash: null,
  };
}

// ============================================================
// ORDER UPSERT
// ============================================================

/**
 * Upsert an Order: update if exists, create if not.
 * Also maintains indices for order_id and tracking_number.
 *
 * @param {Order} order
 * @returns {Promise<Order>}
 */
async function upsertOrderWithIndices(order) {
  // Store the order
  await upsertOrder(order);

  // Update order_id index if present
  if (order.order_id) {
    await updateOrderIdIndex(order.order_id, order.order_key);
  }

  // Update tracking index if present
  if (order.tracking_number) {
    await updateTrackingIndex(order.tracking_number, order.order_key);
  }

  return order;
}

/**
 * Update an existing Order with new data from an email.
 * Only updates fields that are currently null/missing.
 *
 * IMPORTANT: This is for PRIMARY KEY merges only.
 * Thread hint attachments go through hints.js and DO NOT update fields.
 *
 * @param {Order} order - Existing order
 * @param {ExtractedFields} extracted - New extracted data
 * @param {EmailType} email_type - Type of email
 * @param {string} email_id - Email being processed
 * @returns {Order} Updated order
 */
function updateOrderFromEmail(order, extracted, email_type, email_id) {
  const now = new Date().toISOString();

  // Add email to source list if not already there
  if (!order.source_email_ids.includes(email_id)) {
    order.source_email_ids.push(email_id);
  }

  // Update primary keys if we have better ones
  if (!order.order_id && extracted.order_id) {
    order.order_id = extracted.order_id;
    console.log(RESOLVER_LOG_PREFIX, 'ORDER_UPDATE', order.order_key, 'added order_id:', extracted.order_id);
  }

  if (!order.tracking_number && extracted.tracking_number) {
    order.tracking_number = extracted.tracking_number;
    console.log(RESOLVER_LOG_PREFIX, 'ORDER_UPDATE', order.order_key, 'added tracking:', extracted.tracking_number);
  }

  // Update display fields if missing
  if ((!order.item_summary || order.item_summary === 'Unknown item') && extracted.item_summary) {
    order.item_summary = extracted.item_summary;
  }

  if (!order.amount && extracted.amount) {
    order.amount = extracted.amount;
    order.currency = extracted.currency || order.currency;
  }

  // Update dates based on email type (don't overwrite existing)
  if (email_type === EMAIL_TYPE.CONFIRMATION) {
    if (!order.purchase_date && extracted.purchase_date) {
      order.purchase_date = extracted.purchase_date;
    } else if (!order.purchase_date) {
      order.purchase_date = now.split('T')[0];
    }
  }

  if (email_type === EMAIL_TYPE.SHIPPING) {
    if (!order.ship_date && extracted.ship_date) {
      order.ship_date = extracted.ship_date;
    } else if (!order.ship_date) {
      order.ship_date = now.split('T')[0];
    }
  }

  if (email_type === EMAIL_TYPE.DELIVERY) {
    // DELIVERY emails set the actual delivery_date
    if (!order.delivery_date) {
      order.delivery_date = extracted.actual_delivery_date || extracted.delivery_date || now.split('T')[0];
    }
  }

  // For confirmation/shipping emails, update estimated_delivery_date if we don't have an actual delivery
  if ((email_type === EMAIL_TYPE.CONFIRMATION || email_type === EMAIL_TYPE.SHIPPING) && !order.delivery_date) {
    if (!order.estimated_delivery_date && extracted.estimated_delivery_date) {
      order.estimated_delivery_date = extracted.estimated_delivery_date;
    }
  }

  // Update return policy info if missing
  if (!order.return_window_days && extracted.return_window_days) {
    order.return_window_days = extracted.return_window_days;
  }

  if (!order.explicit_return_by_date && extracted.explicit_return_by_date) {
    order.explicit_return_by_date = extracted.explicit_return_by_date;
  }

  if (!order.return_portal_link && extracted.return_portal_link) {
    order.return_portal_link = extracted.return_portal_link;
  }

  order.updated_at = now;

  return order;
}

// ============================================================
// SAFE MERGE ESCALATION (P7)
// ============================================================

/**
 * Handle merge escalation when email contains BOTH order_id AND tracking_number
 * that map to DIFFERENT existing Orders.
 *
 * Winner = Order keyed by order_id (more stable identifier)
 * Loser = Order keyed by tracking_number
 *
 * @param {Order} orderIdOrder - Order found by order_id
 * @param {Order} trackingOrder - Order found by tracking_number
 * @returns {Promise<Order>} The merged winner Order
 */
async function handleMergeEscalation(orderIdOrder, trackingOrder) {
  console.log(RESOLVER_LOG_PREFIX, 'SAFE_MERGE_ESCALATION',
    'winner:', orderIdOrder.order_key,
    'loser:', trackingOrder.order_key);

  const winner = orderIdOrder;
  const loser = trackingOrder;

  // 1. Move source_email_ids from loser to winner
  for (const emailId of loser.source_email_ids) {
    if (!winner.source_email_ids.includes(emailId)) {
      winner.source_email_ids.push(emailId);
    }
  }

  // 2. Copy missing lifecycle fields from loser
  if (!winner.ship_date && loser.ship_date) {
    winner.ship_date = loser.ship_date;
    console.log(RESOLVER_LOG_PREFIX, 'MERGE_COPY', 'ship_date from loser');
  }

  if (!winner.delivery_date && loser.delivery_date) {
    winner.delivery_date = loser.delivery_date;
    console.log(RESOLVER_LOG_PREFIX, 'MERGE_COPY', 'delivery_date from loser');
  }

  if (!winner.estimated_delivery_date && loser.estimated_delivery_date) {
    winner.estimated_delivery_date = loser.estimated_delivery_date;
    console.log(RESOLVER_LOG_PREFIX, 'MERGE_COPY', 'estimated_delivery_date from loser');
  }

  if (!winner.tracking_number && loser.tracking_number) {
    winner.tracking_number = loser.tracking_number;
    console.log(RESOLVER_LOG_PREFIX, 'MERGE_COPY', 'tracking_number from loser');
  }

  // 3. Copy best-available display fields if winner is weak
  if ((!winner.item_summary || winner.item_summary === 'Unknown item') && loser.item_summary) {
    winner.item_summary = loser.item_summary;
  }

  if (!winner.amount && loser.amount) {
    winner.amount = loser.amount;
    winner.currency = loser.currency || winner.currency;
  }

  if (!winner.return_window_days && loser.return_window_days) {
    winner.return_window_days = loser.return_window_days;
  }

  if (!winner.explicit_return_by_date && loser.explicit_return_by_date) {
    winner.explicit_return_by_date = loser.explicit_return_by_date;
  }

  if (!winner.return_portal_link && loser.return_portal_link) {
    winner.return_portal_link = loser.return_portal_link;
  }

  // 4. Update winner
  winner.updated_at = new Date().toISOString();
  await upsertOrderWithIndices(winner);

  // 5. Mark loser as dismissed (soft delete)
  loser.order_status = ORDER_STATUS.DISMISSED;
  loser.updated_at = new Date().toISOString();
  await upsertOrder(loser);

  // 6. Update tracking index to point to winner
  if (loser.tracking_number) {
    await updateTrackingIndex(loser.tracking_number, winner.order_key);
  }

  console.log(RESOLVER_LOG_PREFIX, 'SAFE_MERGE_ESCALATION_COMPLETE',
    'merged into:', winner.order_key);

  return winner;
}

// ============================================================
// MAIN RESOLUTION FUNCTION
// ============================================================

/**
 * Resolve an email through the P6-P7 pipeline.
 *
 * This function:
 * 1. Checks for merge escalation (P7)
 * 2. Creates or updates Order (P6)
 * 3. Maintains indices
 * 4. Creates OrderEmail record
 *
 * @param {Object} params
 * @param {string} params.user_id
 * @param {string} params.email_id
 * @param {string} [params.thread_id]
 * @param {string} params.received_at
 * @param {string} params.merchant_domain
 * @param {string} params.merchant_display_name
 * @param {ExtractedFields} params.extracted
 * @param {EmailType} params.email_type
 * @param {boolean} params.purchase_confirmed
 * @param {Order|null} params.linked_order - Order found by P2 linking
 * @param {string|null} params.linked_by - How it was linked ('order_id' or 'tracking_number')
 * @returns {Promise<{order: Order|null, email_record: OrderEmail, action: string}>}
 */
async function resolveEmail({
  user_id,
  email_id,
  thread_id,
  received_at,
  merchant_domain,
  merchant_display_name,
  extracted,
  email_type,
  purchase_confirmed,
  linked_order,
  linked_by,
}) {
  // Create email record
  const email_record = createEmailRecord({
    email_id,
    thread_id,
    received_at,
    merchant_domain,
    email_type,
    blocked: false,
    extracted,
  });

  // Check for merge escalation (P7)
  // This only happens when email has BOTH order_id AND tracking_number
  if (extracted.order_id && extracted.tracking_number) {
    const escalation = await checkMergeEscalation(extracted.order_id, extracted.tracking_number);

    if (escalation.needs_escalation) {
      // Handle merge: order_id order wins
      const mergedOrder = await handleMergeEscalation(
        escalation.order_id_order,
        escalation.tracking_order
      );

      // Update merged order with current email data
      const updatedOrder = updateOrderFromEmail(mergedOrder, extracted, email_type, email_id);
      await upsertOrderWithIndices(updatedOrder);

      // Store email record and mark processed
      await storeOrderEmail(email_record);
      await markEmailProcessed(email_id);

      return {
        order: updatedOrder,
        email_record,
        action: 'merge_escalation',
      };
    }
  }

  // If we have a linked order from P2, update it
  if (linked_order) {
    const updatedOrder = updateOrderFromEmail(linked_order, extracted, email_type, email_id);
    await upsertOrderWithIndices(updatedOrder);

    // Store email record and mark processed
    await storeOrderEmail(email_record);
    await markEmailProcessed(email_id);

    return {
      order: updatedOrder,
      email_record,
      action: 'primary_merge',
    };
  }

  // Determine if we should seed a new Order
  const has_tracking = !!extracted.tracking_number;
  const has_order_id = !!extracted.order_id;
  const { should_seed, seed_type } = shouldSeedOrder(email_type, purchase_confirmed, has_tracking, has_order_id);

  if (!should_seed) {
    // No order created - just record the email
    await storeOrderEmail(email_record);
    await markEmailProcessed(email_id);

    return {
      order: null,
      email_record,
      action: 'no_seed',
    };
  }

  // Create new Order
  const newOrder = createNewOrder({
    user_id,
    email_id,
    merchant_domain,
    merchant_display_name,
    extracted,
    email_type,
    seed_type,
  });

  await upsertOrderWithIndices(newOrder);

  // Store email record and mark processed
  await storeOrderEmail(email_record);
  await markEmailProcessed(email_id);

  return {
    order: newOrder,
    email_record,
    action: seed_type === 'full' ? 'create_full' : 'create_partial',
  };
}

/**
 * Check if an order key is temporary.
 *
 * @param {string} order_key
 * @returns {boolean}
 */
function isTempOrderKey(order_key) {
  return order_key && order_key.includes(':temp:');
}

/**
 * Upgrade a temporary order key to a permanent one.
 * Called when we discover order_id or tracking_number for a temp-keyed order.
 *
 * @param {Order} order - Order with temp key
 * @param {string|null} order_id - New order_id
 * @param {string|null} tracking_number - New tracking_number
 * @returns {Promise<Order>} Order with new key
 */
async function upgradeOrderKey(order, order_id, tracking_number) {
  if (!isTempOrderKey(order.order_key)) {
    return order; // Already has permanent key
  }

  const { order_key: newKey, key_type } = computeOrderKey(
    order.user_id,
    order.merchant_domain,
    order_id,
    tracking_number,
    '' // Not needed since we have better keys
  );

  if (key_type === 'temp') {
    return order; // Still temp, no upgrade possible
  }

  console.log(RESOLVER_LOG_PREFIX, 'KEY_UPGRADE', order.order_key, '->', newKey);

  // Create new order with new key
  const upgradedOrder = { ...order };
  upgradedOrder.order_key = newKey;
  upgradedOrder.order_id = order_id || order.order_id;
  upgradedOrder.tracking_number = tracking_number || order.tracking_number;
  upgradedOrder.updated_at = new Date().toISOString();

  // Store upgraded order
  await upsertOrderWithIndices(upgradedOrder);

  // Remove old temp order
  await deleteOrder(order.order_key);

  return upgradedOrder;
}
