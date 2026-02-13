/**
 * Reclaim v2 Storage Store
 * CRUD operations for chrome.storage.local with mutex serialization.
 *
 * Loaded via importScripts in the service worker.
 * Depends on schema.js being loaded first.
 */

const STORE_LOG_PREFIX = '[Reclaim:Store]';

// ============================================================
// STORAGE MUTEX (copied from v1)
// ============================================================

/**
 * Promise-chain serializer for mutating storage operations.
 * Prevents read-modify-write races when multiple upserts overlap.
 */
let _storageMutex = Promise.resolve();

function withStorageLock(fn) {
  const next = _storageMutex.then(fn, fn);
  _storageMutex = next.catch(() => {});
  return next;
}

// ============================================================
// INITIALIZATION
// ============================================================

/**
 * Initialize storage with empty defaults if not present.
 * Safe to call multiple times (idempotent).
 *
 * @returns {Promise<void>}
 */
async function initializeStorage() {
  const defaults = {
    [STORAGE_KEYS.ORDERS_BY_KEY]: {},
    [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: {},
    [STORAGE_KEYS.MERCHANT_POLICIES]: {},
    [STORAGE_KEYS.SETTINGS]: {},
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
 * Save (upsert) an order. Updates order_id index atomically.
 *
 * @param {Order} order
 * @returns {Promise<Order>}
 */
async function saveOrder(order) {
  return withStorageLock(async () => {
    const result = await chrome.storage.local.get([
      STORAGE_KEYS.ORDERS_BY_KEY,
      STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID,
    ]);

    const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
    const orderIdIndex = result[STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID] || {};

    // Check for existing order with same key
    const existing = orders[order.order_key];
    if (existing) {
      // Preserve terminal statuses
      if (existing.order_status === ORDER_STATUS.RETURNED || existing.order_status === ORDER_STATUS.DISMISSED) {
        order.order_status = existing.order_status;
      }
      // Keep earlier created_at
      order.created_at = existing.created_at;
      // Keep notification state
      order.notified_7day = existing.notified_7day || order.notified_7day;
      order.notified_3day = existing.notified_3day || order.notified_3day;
    }

    order.updated_at = new Date().toISOString();
    orders[order.order_key] = order;

    // Update order_id index
    if (order.order_id) {
      orderIdIndex[order.order_id] = order.order_key;
    }

    // Atomic write
    await chrome.storage.local.set({
      [STORAGE_KEYS.ORDERS_BY_KEY]: orders,
      [STORAGE_KEYS.ORDER_KEY_BY_ORDER_ID]: orderIdIndex,
    });

    console.log(STORE_LOG_PREFIX, 'Saved order:', order.order_key, order.merchant_name);
    return order;
  });
}

/**
 * Get an Order by its order_key.
 *
 * @param {string} orderKey
 * @returns {Promise<Order|null>}
 */
async function getOrder(orderKey) {
  const result = await chrome.storage.local.get(STORAGE_KEYS.ORDERS_BY_KEY);
  const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};
  return orders[orderKey] || null;
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
 * Update Order status. Bypasses upsert's terminal status preservation.
 *
 * @param {string} orderKey
 * @param {OrderStatus} status
 * @returns {Promise<Order|null>}
 */
async function updateOrderStatus(orderKey, status) {
  return withStorageLock(async () => {
    const result = await chrome.storage.local.get(STORAGE_KEYS.ORDERS_BY_KEY);
    const orders = result[STORAGE_KEYS.ORDERS_BY_KEY] || {};

    const order = orders[orderKey];
    if (!order) return null;

    order.order_status = status;
    order.updated_at = new Date().toISOString();

    orders[orderKey] = order;
    await chrome.storage.local.set({ [STORAGE_KEYS.ORDERS_BY_KEY]: orders });

    console.log(STORE_LOG_PREFIX, 'Updated order status:', orderKey, '->', status);
    return order;
  });
}

// ============================================================
// MERCHANT POLICY OPERATIONS
// ============================================================

/**
 * Get merchant return policy.
 *
 * @param {string} domain
 * @returns {Promise<{days: number, anchor: string, return_url?: string}|null>}
 */
async function getMerchantPolicy(domain) {
  if (!domain) return null;
  const result = await chrome.storage.local.get(STORAGE_KEYS.MERCHANT_POLICIES);
  const policies = result[STORAGE_KEYS.MERCHANT_POLICIES] || {};
  return policies[domain] || null;
}

/**
 * Set merchant return policy.
 *
 * @param {string} domain
 * @param {{days: number, anchor: string, return_url?: string}} policy
 * @returns {Promise<void>}
 */
async function setMerchantPolicy(domain, policy) {
  if (!domain || !policy) return;
  const result = await chrome.storage.local.get(STORAGE_KEYS.MERCHANT_POLICIES);
  const policies = result[STORAGE_KEYS.MERCHANT_POLICIES] || {};
  policies[domain] = policy;
  await chrome.storage.local.set({ [STORAGE_KEYS.MERCHANT_POLICIES]: policies });
}

/**
 * Load seed merchant policies from bundled merchant_rules.json.
 * Only loads if merchant_policies storage is empty (first install).
 *
 * @returns {Promise<void>}
 */
async function loadMerchantPolicies() {
  const result = await chrome.storage.local.get(STORAGE_KEYS.MERCHANT_POLICIES);
  const existing = result[STORAGE_KEYS.MERCHANT_POLICIES] || {};

  if (Object.keys(existing).length > 0) {
    console.log(STORE_LOG_PREFIX, 'Merchant policies already loaded, skipping seed');
    return;
  }

  try {
    const url = chrome.runtime.getURL('data/merchant_rules.json');
    const response = await fetch(url);
    const rules = await response.json();

    const policies = {};
    for (const [domain, rule] of Object.entries(rules)) {
      if (domain === '_default') continue;
      policies[domain] = {
        days: rule.days,
        anchor: rule.anchor || 'delivery',
      };
      if (rule.return_url) {
        policies[domain].return_url = rule.return_url;
      }
    }

    await chrome.storage.local.set({ [STORAGE_KEYS.MERCHANT_POLICIES]: policies });
    console.log(STORE_LOG_PREFIX, 'Loaded', Object.keys(policies).length, 'merchant policies from seed data');
  } catch (err) {
    console.error(STORE_LOG_PREFIX, 'Failed to load merchant policies:', err);
  }
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
