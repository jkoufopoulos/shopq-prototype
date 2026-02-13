/**
 * Reclaim v2 Service Worker
 * Handles order processing, deadline computation, and notifications.
 */

importScripts(
  'modules/shared/config.js',
  'modules/storage/schema.js',
  'modules/storage/store.js'
);

const BG_LOG_PREFIX = '[Reclaim:BG]';

// ============================================================
// INSTALL / STARTUP
// ============================================================

chrome.runtime.onInstalled.addListener(async (details) => {
  console.log(BG_LOG_PREFIX, 'Installed:', details.reason);

  await initializeStorage();
  await loadMerchantPolicies();

  // Set up deadline check alarm (twice daily)
  chrome.alarms.create('check-deadlines', {
    periodInMinutes: CONFIG.DEADLINE_CHECK_INTERVAL_MINUTES,
  });

  console.log(BG_LOG_PREFIX, 'Setup complete');
});

chrome.runtime.onStartup.addListener(async () => {
  console.log(BG_LOG_PREFIX, 'Startup');
  await initializeStorage();
});

// ============================================================
// MESSAGE HANDLERS
// ============================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'ORDER_CAPTURED') {
    handleOrderCaptured(message.data)
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // async response
  }

  if (message.type === 'GET_ORDERS') {
    handleGetOrders()
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === 'UPDATE_ORDER_STATUS') {
    handleUpdateOrderStatus(message.order_key, message.status)
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === 'ADD_TEST_ORDER') {
    handleAddTestOrder()
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

// ============================================================
// ORDER CAPTURED HANDLER
// ============================================================

/**
 * Process a captured order from the content script.
 *
 * @param {Object} data - Captured order data
 * @returns {Promise<{success: boolean, order_key: string}>}
 */
async function handleOrderCaptured(data) {
  const { merchant_domain, merchant_name, order_id, items, amount, order_date, capture_url } = data;

  if (!order_id) {
    return { success: false, error: 'No order ID provided' };
  }

  const order_key = generateOrderKey(merchant_domain, order_id);
  const item_description = (items && items.length > 0) ? items.join(', ') : 'Unknown item';

  // Compute return deadline
  const deadline = await computeDeadline(merchant_domain, order_date);

  const order = createOrder({
    order_key,
    merchant_domain,
    merchant_name,
    item_description,
    order_date,
    capture_url,
    order_id,
    amount,
    return_by_date: deadline.return_by_date,
    deadline_confidence: deadline.confidence,
  });

  await saveOrder(order);

  console.log(BG_LOG_PREFIX, 'Order captured:', order_key, merchant_name, order_id);
  return { success: true, order_key };
}

// ============================================================
// DEADLINE COMPUTATION
// ============================================================

/**
 * Compute return_by_date for an order based on merchant policy.
 *
 * @param {string} merchant_domain
 * @param {string} order_date - ISO date string (YYYY-MM-DD)
 * @param {string} [delivery_date] - ISO date string if known
 * @returns {Promise<{return_by_date: string, confidence: string}>}
 */
async function computeDeadline(merchant_domain, order_date, delivery_date) {
  const policy = await getMerchantPolicy(merchant_domain) ||
    { days: CONFIG.DEFAULT_RETURN_DAYS, anchor: CONFIG.DEFAULT_ANCHOR };

  let anchorDate;
  let confidence;

  if (policy.anchor === 'delivery' && delivery_date) {
    anchorDate = new Date(delivery_date);
    confidence = DEADLINE_CONFIDENCE.ESTIMATED;
  } else {
    // Use order_date as anchor (delivery unknown)
    anchorDate = new Date(order_date);
    confidence = DEADLINE_CONFIDENCE.ESTIMATED;
  }

  // Add return window days
  const returnByDate = new Date(anchorDate);
  returnByDate.setDate(returnByDate.getDate() + policy.days);

  return {
    return_by_date: returnByDate.toISOString().split('T')[0],
    confidence,
  };
}

// ============================================================
// GET ORDERS HANDLER
// ============================================================

/**
 * Get all orders sorted by return_by_date (soonest first).
 *
 * @returns {Promise<{success: boolean, orders: Order[]}>}
 */
async function handleGetOrders() {
  const orders = await getAllOrders();

  // Sort: active orders with deadlines first (soonest deadline first),
  // then orders without deadlines, then non-active orders
  orders.sort((a, b) => {
    // Active orders come first
    const aActive = a.order_status === ORDER_STATUS.ACTIVE;
    const bActive = b.order_status === ORDER_STATUS.ACTIVE;
    if (aActive !== bActive) return aActive ? -1 : 1;

    // Within same status group, sort by deadline
    if (a.return_by_date && b.return_by_date) {
      return a.return_by_date.localeCompare(b.return_by_date);
    }
    if (a.return_by_date) return -1;
    if (b.return_by_date) return 1;

    return 0;
  });

  return { success: true, orders };
}

// ============================================================
// UPDATE ORDER STATUS HANDLER
// ============================================================

/**
 * Update an order's status.
 *
 * @param {string} orderKey
 * @param {string} status
 * @returns {Promise<{success: boolean}>}
 */
async function handleUpdateOrderStatus(orderKey, status) {
  const order = await updateOrderStatus(orderKey, status);
  if (!order) {
    return { success: false, error: 'Order not found' };
  }
  return { success: true };
}

// ============================================================
// TEST ORDER
// ============================================================

/**
 * Create a test order with a near-future deadline for testing.
 *
 * @returns {Promise<{success: boolean, order_key: string}>}
 */
async function handleAddTestOrder() {
  const testId = 'TEST-' + Date.now().toString(36).toUpperCase();
  const order_key = generateOrderKey('amazon.com', testId);

  // Set order date to 25 days ago so deadline is in ~5 days
  const orderDate = new Date();
  orderDate.setDate(orderDate.getDate() - 25);

  const deadline = await computeDeadline('amazon.com', orderDate.toISOString().split('T')[0]);

  const order = createOrder({
    order_key,
    merchant_domain: 'amazon.com',
    merchant_name: 'Amazon',
    item_description: 'Test Product - Wireless Bluetooth Headphones',
    order_date: orderDate.toISOString().split('T')[0],
    capture_url: 'https://www.amazon.com/test',
    order_id: testId,
    amount: 49.99,
    return_by_date: deadline.return_by_date,
    deadline_confidence: deadline.confidence,
  });

  await saveOrder(order);

  console.log(BG_LOG_PREFIX, 'Test order created:', order_key);
  return { success: true, order_key };
}

// ============================================================
// ALARM HANDLER — DEADLINE CHECKING
// ============================================================

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== 'check-deadlines') return;

  console.log(BG_LOG_PREFIX, 'Checking deadlines...');

  const orders = await getOrdersByStatus(ORDER_STATUS.ACTIVE);
  const now = new Date();
  const todayStr = now.toISOString().split('T')[0];

  for (const order of orders) {
    if (!order.return_by_date) continue;

    const deadline = new Date(order.return_by_date);
    const daysRemaining = Math.ceil((deadline - now) / (1000 * 60 * 60 * 24));

    // 7-day notification
    if (CONFIG.NOTIFICATION_7DAY && daysRemaining <= CONFIG.EXPIRING_SOON_DAYS && daysRemaining > CONFIG.CRITICAL_DAYS && !order.notified_7day) {
      sendNotification(
        `Return deadline approaching`,
        `${order.merchant_name}: "${order.item_description}" - ${daysRemaining} days left to return`,
        order.order_key
      );
      order.notified_7day = true;
      await saveOrder(order);
    }

    // 3-day notification
    if (CONFIG.NOTIFICATION_3DAY && daysRemaining <= CONFIG.CRITICAL_DAYS && daysRemaining > 0 && !order.notified_3day) {
      sendNotification(
        `Return deadline critical!`,
        `${order.merchant_name}: "${order.item_description}" - Only ${daysRemaining} day${daysRemaining === 1 ? '' : 's'} left!`,
        order.order_key
      );
      order.notified_3day = true;
      await saveOrder(order);
    }
  }
});

/**
 * Send a Chrome notification.
 *
 * @param {string} title
 * @param {string} message
 * @param {string} [notificationId]
 */
function sendNotification(title, message, notificationId) {
  chrome.notifications.create(notificationId || '', {
    type: 'basic',
    iconUrl: 'icons/icon48.png',
    title,
    message,
    priority: 2,
  });
}
