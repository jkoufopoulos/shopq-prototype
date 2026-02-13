/**
 * Reclaim v2 Popup
 * Displays tracked orders and their return deadlines.
 */

const EXPIRING_SOON_DAYS = 7;
const CRITICAL_DAYS = 3;

document.addEventListener('DOMContentLoaded', () => {
  loadOrders();

  document.getElementById('add-test-btn').addEventListener('click', addTestOrder);
  document.getElementById('empty-test-btn').addEventListener('click', addTestOrder);
});

/**
 * Load and render all orders.
 */
function loadOrders() {
  chrome.runtime.sendMessage({ type: 'GET_ORDERS' }, (response) => {
    if (chrome.runtime.lastError) {
      console.error('Failed to load orders:', chrome.runtime.lastError.message);
      return;
    }

    if (!response?.success) {
      console.error('Failed to load orders:', response?.error);
      return;
    }

    renderOrders(response.orders);
  });
}

/**
 * Render the order list.
 *
 * @param {Object[]} orders
 */
function renderOrders(orders) {
  const listEl = document.getElementById('order-list');
  const emptyEl = document.getElementById('empty-state');

  if (!orders || orders.length === 0) {
    listEl.classList.add('hidden');
    emptyEl.classList.remove('hidden');
    return;
  }

  listEl.classList.remove('hidden');
  emptyEl.classList.add('hidden');
  listEl.innerHTML = '';

  // Separate active vs inactive orders
  const active = orders.filter(o => o.order_status === 'active');
  const inactive = orders.filter(o => o.order_status !== 'active');

  if (active.length > 0) {
    const header = document.createElement('div');
    header.className = 'section-header';
    header.textContent = `Active Returns (${active.length})`;
    listEl.appendChild(header);
    active.forEach(order => listEl.appendChild(createOrderCard(order)));
  }

  if (inactive.length > 0) {
    const header = document.createElement('div');
    header.className = 'section-header';
    header.textContent = `Resolved (${inactive.length})`;
    listEl.appendChild(header);
    inactive.forEach(order => listEl.appendChild(createOrderCard(order)));
  }
}

/**
 * Create a DOM element for an order card.
 *
 * @param {Object} order
 * @returns {HTMLElement}
 */
function createOrderCard(order) {
  const card = document.createElement('div');
  card.className = 'order-card';

  const urgency = getUrgency(order);
  card.classList.add(urgency);

  // Summary (always visible)
  const summary = document.createElement('div');
  summary.className = 'card-summary';
  summary.innerHTML = `
    <div class="card-info">
      <div class="card-merchant">${escapeHtml(order.merchant_name)}</div>
      <div class="card-items">${escapeHtml(order.item_description)}</div>
    </div>
    <span class="card-deadline ${urgency}">${formatDeadline(order)}</span>
  `;

  // Details (expandable)
  const details = document.createElement('div');
  details.className = 'card-details';
  details.innerHTML = `
    <div class="detail-row">
      <span class="detail-label">Order ID</span>
      <span class="detail-value">${escapeHtml(order.order_id || 'Unknown')}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Order Date</span>
      <span class="detail-value">${formatDate(order.order_date)}</span>
    </div>
    ${order.amount ? `
    <div class="detail-row">
      <span class="detail-label">Amount</span>
      <span class="detail-value">$${order.amount.toFixed(2)}</span>
    </div>` : ''}
    <div class="detail-row">
      <span class="detail-label">Return By</span>
      <span class="detail-value">${order.return_by_date ? formatDate(order.return_by_date) : 'Unknown'}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Confidence</span>
      <span class="detail-value">${order.deadline_confidence || 'unknown'}</span>
    </div>
    ${order.order_status === 'active' ? `
    <div class="card-actions">
      <button class="action-btn returned" data-key="${escapeHtml(order.order_key)}" data-action="returned">Mark Returned</button>
      <button class="action-btn dismiss" data-key="${escapeHtml(order.order_key)}" data-action="dismissed">Dismiss</button>
    </div>` : ''}
  `;

  // Toggle expand/collapse
  summary.addEventListener('click', () => {
    details.classList.toggle('expanded');
  });

  // Action buttons
  details.querySelectorAll('.action-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const orderKey = btn.dataset.key;
      const status = btn.dataset.action;
      updateStatus(orderKey, status);
    });
  });

  card.appendChild(summary);
  card.appendChild(details);
  return card;
}

/**
 * Determine urgency level for an order.
 *
 * @param {Object} order
 * @returns {string} 'safe' | 'expiring' | 'critical' | 'expired' | 'returned' | 'dismissed'
 */
function getUrgency(order) {
  if (order.order_status === 'returned') return 'returned';
  if (order.order_status === 'dismissed') return 'dismissed';

  if (!order.return_by_date) return 'safe';

  const now = new Date();
  const deadline = new Date(order.return_by_date);
  const daysRemaining = Math.ceil((deadline - now) / (1000 * 60 * 60 * 24));

  if (daysRemaining <= 0) return 'expired';
  if (daysRemaining <= CRITICAL_DAYS) return 'critical';
  if (daysRemaining <= EXPIRING_SOON_DAYS) return 'expiring';
  return 'safe';
}

/**
 * Format deadline as a human-readable string.
 *
 * @param {Object} order
 * @returns {string}
 */
function formatDeadline(order) {
  if (order.order_status === 'returned') return 'Returned';
  if (order.order_status === 'dismissed') return 'Dismissed';
  if (!order.return_by_date) return 'No deadline';

  const now = new Date();
  const deadline = new Date(order.return_by_date);
  const daysRemaining = Math.ceil((deadline - now) / (1000 * 60 * 60 * 24));

  if (daysRemaining <= 0) return 'Expired';
  if (daysRemaining === 1) return '1 day left';
  return `${daysRemaining} days left`;
}

/**
 * Format ISO date string as a readable date.
 *
 * @param {string} isoDate
 * @returns {string}
 */
function formatDate(isoDate) {
  if (!isoDate) return 'Unknown';
  const date = new Date(isoDate + 'T00:00:00');
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Update order status via service worker.
 *
 * @param {string} orderKey
 * @param {string} status
 */
function updateStatus(orderKey, status) {
  chrome.runtime.sendMessage(
    { type: 'UPDATE_ORDER_STATUS', order_key: orderKey, status },
    (response) => {
      if (response?.success) {
        loadOrders(); // Refresh
      }
    }
  );
}

/**
 * Add a test order for development testing.
 */
function addTestOrder() {
  chrome.runtime.sendMessage({ type: 'ADD_TEST_ORDER' }, (response) => {
    if (response?.success) {
      loadOrders(); // Refresh
    }
  });
}

/**
 * Escape HTML to prevent XSS.
 *
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
