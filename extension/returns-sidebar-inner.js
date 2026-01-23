/**
 * ShopQ Return Watch Sidebar
 * Displays returnable purchases and their return windows
 *
 * v0.6.2 Integration:
 * - Uses GET_RETURN_WATCH_ORDERS for Return Watch section
 * - Uses GET_ALL_PURCHASES for All Purchases section
 * - Triggers ENRICH_ORDER on detail view open
 * - Supports SET_MERCHANT_RULE for unknown deadlines
 */

// =============================================================================
// STATE
// =============================================================================

let returnWatchOrders = { expiringSoon: [], active: [] };
let allPurchases = [];
let currentDetailOrder = null;
let isEnriching = false;

// =============================================================================
// DOM ELEMENTS
// =============================================================================

const listView = document.getElementById('list-view');
const detailView = document.getElementById('detail-view');
const backBtn = document.getElementById('back-btn');
const closeBtn = document.getElementById('close-btn');
const refreshBtn = document.getElementById('refresh-btn');
const refreshStatus = document.getElementById('refresh-status');

// =============================================================================
// UTILITIES
// =============================================================================

/**
 * Format a date for display
 */
function formatDate(dateStr) {
  if (!dateStr) return 'Unknown';
  const date = new Date(dateStr);
  const now = new Date();
  const diffDays = Math.ceil((date - now) / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return 'Expired';
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Tomorrow';
  if (diffDays <= 7) return `${diffDays} days`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Get days until return deadline
 */
function getDaysUntil(dateStr) {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  const now = new Date();
  return Math.ceil((date - now) / (1000 * 60 * 60 * 24));
}

/**
 * Format currency amount
 */
function formatAmount(amount, currency = 'USD') {
  if (!amount) return null;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency
  }).format(amount);
}

// =============================================================================
// RENDERING
// =============================================================================

/**
 * Render the returns list view
 */
function renderListView() {
  const hasReturnWatch = returnWatchOrders.expiringSoon.length > 0 || returnWatchOrders.active.length > 0;
  const hasAllPurchases = allPurchases.length > 0;

  if (!hasReturnWatch && !hasAllPurchases) {
    listView.innerHTML = `
      <div class="empty-state">
        <div class="icon">📦</div>
        <p><strong>No returns to track</strong></p>
        <p style="font-size: 13px;">When you make purchases, they'll appear here with their return deadlines.</p>
      </div>
    `;
    return;
  }

  let html = '';

  // Return Watch: Expiring Soon section
  if (returnWatchOrders.expiringSoon.length > 0) {
    html += `
      <div class="section">
        <div class="section-header urgent">Expiring Soon (${returnWatchOrders.expiringSoon.length})</div>
        ${returnWatchOrders.expiringSoon.map(o => renderOrderCard(o, true)).join('')}
      </div>
    `;
  }

  // Return Watch: Active section
  if (returnWatchOrders.active.length > 0) {
    html += `
      <div class="section">
        <div class="section-header">Return Watch (${returnWatchOrders.active.length})</div>
        ${returnWatchOrders.active.map(o => renderOrderCard(o, false)).join('')}
      </div>
    `;
  }

  // All Purchases section
  if (hasAllPurchases) {
    html += `
      <div class="section">
        <div class="section-header">All Purchases (${allPurchases.length})</div>
        ${allPurchases.map(o => renderOrderCard(o, false)).join('')}
      </div>
    `;
  }

  listView.innerHTML = html;

  // Add click handlers to cards
  listView.querySelectorAll('.return-card').forEach(card => {
    card.addEventListener('click', () => {
      const orderKey = card.dataset.id;
      // Find in both lists
      let order = returnWatchOrders.expiringSoon.find(o => o.order_key === orderKey) ||
                  returnWatchOrders.active.find(o => o.order_key === orderKey) ||
                  allPurchases.find(o => o.order_key === orderKey);
      if (order) {
        showDetailView(order);
      }
    });
  });
}

/**
 * Render a single order card (v0.6.2 Order model)
 */
function renderOrderCard(order, isUrgent) {
  const daysUntil = getDaysUntil(order.return_by_date);
  const isExpiring = daysUntil !== null && daysUntil <= 7 && daysUntil >= 0;
  const isCritical = daysUntil !== null && daysUntil <= 3 && daysUntil >= 0;

  let dateText = 'No deadline';
  let dateClass = '';
  let urgentBadge = '';

  if (order.return_by_date) {
    if (daysUntil < 0) {
      dateText = 'Expired';
      dateClass = 'urgent';
      urgentBadge = '<span class="urgent-badge critical"><span class="dot"></span>Expired</span>';
    } else if (daysUntil === 0) {
      dateText = 'Due today!';
      dateClass = 'urgent';
      urgentBadge = '<span class="urgent-badge critical"><span class="dot"></span>Today!</span>';
    } else if (daysUntil === 1) {
      dateText = 'Due tomorrow';
      dateClass = isUrgent ? 'urgent' : '';
      urgentBadge = '<span class="urgent-badge critical"><span class="dot"></span>1 day</span>';
    } else if (daysUntil <= 3) {
      dateText = `${daysUntil} days left`;
      dateClass = 'urgent';
      urgentBadge = `<span class="urgent-badge critical"><span class="dot"></span>${daysUntil} days</span>`;
    } else if (daysUntil <= 7) {
      dateText = `${daysUntil} days left`;
      dateClass = isUrgent ? 'urgent' : '';
      urgentBadge = `<span class="urgent-badge warning"><span class="dot"></span>${daysUntil} days</span>`;
    } else {
      dateText = `Due ${formatDate(order.return_by_date)}`;
    }
  } else if (order.deadline_confidence === 'unknown') {
    dateText = 'Deadline unknown';
    dateClass = '';
  }

  const cardClass = isCritical ? 'critical' : (isExpiring ? 'expiring' : '');

  return `
    <div class="return-card ${cardClass}" data-id="${order.order_key}">
      <div class="card-header">
        <span class="merchant">${escapeHtml(order.merchant_display_name)}</span>
        ${urgentBadge}
      </div>
      <div class="item-summary">${escapeHtml(order.item_summary)}</div>
      <div class="card-footer">
        <span class="return-date ${dateClass}">${dateText}</span>
        <span class="confidence">${order.deadline_confidence || 'unknown'}</span>
      </div>
    </div>
  `;
}

/**
 * Get status badge HTML
 */
function getStatusBadge(status) {
  const badges = {
    'active': '<span class="status-badge active">Active</span>',
    'expiring_soon': '<span class="status-badge expiring_soon">Expiring</span>',
    'expired': '<span class="status-badge expired">Expired</span>',
    'returned': '<span class="status-badge active">Returned</span>',
    'dismissed': '<span class="status-badge">Dismissed</span>'
  };
  return badges[status] || '';
}

/**
 * Show the detail view for an order (v0.6.2 Order model)
 */
function showDetailView(order) {
  currentDetailOrder = order;

  // Check if enrichment needed
  const needsEnrichment = order.deadline_confidence === 'unknown' || !order.return_by_date;

  // Trigger enrichment if needed
  if (needsEnrichment && !isEnriching) {
    enrichOrder(order.order_key);
  }

  renderDetailView(order, needsEnrichment);

  // Show detail view, hide list view
  listView.classList.add('hidden');
  detailView.classList.add('active');
  backBtn.classList.remove('hidden');
}

/**
 * Render enriching state in detail view
 */
function renderEnrichingState() {
  if (!currentDetailOrder) return;

  const enrichSection = document.getElementById('enrich-section');
  if (enrichSection) {
    enrichSection.innerHTML = `
      <div class="detail-section" style="text-align: center; padding: 16px; background: #f8f9fa; border-radius: 8px;">
        <div class="spinner" style="margin: 0 auto 8px;"></div>
        <div style="color: #5f6368;">Checking return policy...</div>
      </div>
    `;
  }
}

/**
 * Render the detail view content
 */
function renderDetailView(order, needsEnrichment) {
  const daysUntil = getDaysUntil(order.return_by_date);
  let deadlineText = 'No deadline set';
  let deadlineClass = '';

  if (order.return_by_date) {
    const date = new Date(order.return_by_date);
    deadlineText = date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric'
    });

    if (daysUntil !== null) {
      if (daysUntil < 0) {
        deadlineText += ' (Expired)';
        deadlineClass = 'urgent';
      } else if (daysUntil === 0) {
        deadlineText += ' (Today!)';
        deadlineClass = 'urgent';
      } else if (daysUntil <= 3) {
        deadlineText += ` (${daysUntil} days)`;
        deadlineClass = 'urgent';
      } else {
        deadlineText += ` (${daysUntil} days)`;
      }
    }
  }

  const amount = formatAmount(order.amount, order.currency);

  // Build enrichment section
  let enrichSection = '';
  if (needsEnrichment) {
    if (isEnriching) {
      enrichSection = `
        <div id="enrich-section" class="detail-section" style="text-align: center; padding: 16px; background: #f8f9fa; border-radius: 8px;">
          <div class="spinner" style="margin: 0 auto 8px;"></div>
          <div style="color: #5f6368;">Checking return policy...</div>
        </div>
      `;
    } else {
      enrichSection = `
        <div id="enrich-section" class="detail-section" style="text-align: center; padding: 16px; background: #fff3e0; border-radius: 8px;">
          <div style="color: #e65100; margin-bottom: 8px;">No return deadline found</div>
          <button id="set-rule-btn" class="action-btn secondary" style="margin-top: 8px;">
            Set Return Window for ${escapeHtml(order.merchant_display_name)}
          </button>
        </div>
      `;
    }
  }

  // Build evidence section if available
  let evidenceSection = '';
  if (order.evidence_quote) {
    evidenceSection = `
      <div class="detail-section">
        <div class="detail-label">Evidence</div>
        <div class="detail-value" style="font-style: italic; color: #5f6368; font-size: 12px; padding: 8px; background: #f8f9fa; border-radius: 4px;">
          "${escapeHtml(order.evidence_quote)}"
        </div>
      </div>
    `;
  }

  detailView.innerHTML = `
    <div class="detail-header">
      <div class="detail-merchant">${escapeHtml(order.merchant_display_name)}</div>
      <div class="detail-item">${escapeHtml(order.item_summary)}</div>
    </div>

    <div class="detail-section">
      <div class="detail-label">Return By</div>
      <div class="detail-value large ${deadlineClass}">${deadlineText}</div>
      <div style="font-size: 12px; color: #9aa0a6; margin-top: 4px;">
        Confidence: ${order.deadline_confidence || 'unknown'}
      </div>
    </div>

    ${enrichSection}
    ${evidenceSection}

    ${amount ? `
    <div class="detail-section">
      <div class="detail-label">Purchase Amount</div>
      <div class="detail-value">${amount}</div>
    </div>
    ` : ''}

    ${order.order_id ? `
    <div class="detail-section">
      <div class="detail-label">Order Number</div>
      <div class="detail-value">${escapeHtml(order.order_id)}</div>
    </div>
    ` : ''}

    ${order.purchase_date ? `
    <div class="detail-section">
      <div class="detail-label">Order Date</div>
      <div class="detail-value">${new Date(order.purchase_date).toLocaleDateString()}</div>
    </div>
    ` : ''}

    ${order.delivery_date ? `
    <div class="detail-section">
      <div class="detail-label">Delivery Date</div>
      <div class="detail-value">${new Date(order.delivery_date).toLocaleDateString()}</div>
    </div>
    ` : ''}

    ${order.return_portal_link ? `
    <div class="detail-section">
      <div class="detail-label">Return Portal</div>
      <div class="detail-value">
        <a href="${escapeHtml(order.return_portal_link)}" target="_top">Start Return</a>
      </div>
    </div>
    ` : ''}

    ${order.tracking_number ? `
    <div class="detail-section">
      <div class="detail-label">Tracking Number</div>
      <div class="detail-value">${escapeHtml(order.tracking_number)}</div>
    </div>
    ` : ''}

    ${order.order_status === 'active' ? `
    <div class="detail-actions">
      <button class="action-btn primary" id="mark-returned-btn">Mark Returned</button>
      <button class="action-btn secondary" id="dismiss-btn">Dismiss</button>
    </div>
    ` : ''}
  `;

  // Add action handlers
  const markReturnedBtn = document.getElementById('mark-returned-btn');
  const dismissBtn = document.getElementById('dismiss-btn');
  const setRuleBtn = document.getElementById('set-rule-btn');

  if (markReturnedBtn) {
    markReturnedBtn.addEventListener('click', () => {
      updateOrderStatus(order.order_key, 'returned');
    });
  }

  if (dismissBtn) {
    dismissBtn.addEventListener('click', () => {
      updateOrderStatus(order.order_key, 'dismissed');
    });
  }

  if (setRuleBtn) {
    setRuleBtn.addEventListener('click', () => {
      showMerchantRuleDialog(order.merchant_domain, order.merchant_display_name);
    });
  }
}

/**
 * Show dialog to set merchant return window
 */
function showMerchantRuleDialog(merchantDomain, merchantName) {
  const windowDays = prompt(
    `Enter return window (in days) for ${merchantName}:`,
    '30'
  );

  if (windowDays && !isNaN(parseInt(windowDays))) {
    setMerchantRule(merchantDomain, parseInt(windowDays));
  }
}

/**
 * Show the list view (hide detail view)
 */
function showListView() {
  currentDetailCard = null;
  listView.classList.remove('hidden');
  detailView.classList.remove('active');
  backBtn.classList.add('hidden');
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// =============================================================================
// API CALLS
// =============================================================================

/**
 * Fetch returns from the API
 */
async function fetchReturns() {
  try {
    // Request Return Watch orders (deadline-known)
    window.parent.postMessage({ type: 'SHOPQ_GET_RETURN_WATCH' }, '*');
    // Request all purchases
    window.parent.postMessage({ type: 'SHOPQ_GET_ALL_PURCHASES' }, '*');
  } catch (error) {
    console.error('ShopQ Returns: Failed to request returns:', error);
    renderError('Failed to load returns');
  }
}

/**
 * Trigger enrichment for an order
 */
async function enrichOrder(orderKey) {
  isEnriching = true;
  renderEnrichingState();
  window.parent.postMessage({ type: 'SHOPQ_ENRICH_ORDER', order_key: orderKey }, '*');
}

/**
 * Set merchant return window rule
 */
async function setMerchantRule(merchantDomain, windowDays) {
  window.parent.postMessage({
    type: 'SHOPQ_SET_MERCHANT_RULE',
    merchant_domain: merchantDomain,
    window_days: windowDays
  }, '*');
}

/**
 * Update order status via API (v0.6.2)
 */
async function updateOrderStatus(orderKey, newStatus) {
  try {
    window.parent.postMessage({
      type: 'SHOPQ_UPDATE_ORDER_STATUS',
      order_key: orderKey,
      status: newStatus
    }, '*');

    // Go back to list and refresh
    showListView();
    fetchReturns();
  } catch (error) {
    console.error('ShopQ Returns: Failed to update status:', error);
  }
}

/**
 * Render error state
 */
function renderError(message) {
  listView.innerHTML = `
    <div class="empty-state">
      <div class="icon">⚠️</div>
      <p><strong>Error</strong></p>
      <p style="font-size: 13px;">${escapeHtml(message)}</p>
      <button id="retry-btn" style="
        margin-top: 16px;
        padding: 8px 16px;
        background: #1a73e8;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
      ">Retry</button>
    </div>
  `;

  document.getElementById('retry-btn')?.addEventListener('click', fetchReturns);
}

// =============================================================================
// MESSAGE HANDLING
// =============================================================================

window.addEventListener('message', (event) => {
  // Handle Return Watch orders (v0.6.2)
  if (event.data?.type === 'SHOPQ_RETURN_WATCH_DATA') {
    returnWatchOrders = {
      expiringSoon: event.data.expiringSoon || [],
      active: event.data.active || []
    };
    renderListView();
  }

  // Handle All Purchases (v0.6.2)
  if (event.data?.type === 'SHOPQ_ALL_PURCHASES_DATA') {
    allPurchases = event.data.orders || [];
    renderListView();
  }

  // Handle API error
  if (event.data?.type === 'SHOPQ_RETURNS_ERROR') {
    renderError(event.data.message || 'Unknown error');
  }

  // Handle status update confirmation
  if (event.data?.type === 'SHOPQ_STATUS_UPDATED') {
    // Refresh the list
    fetchReturns();
  }

  // Handle scan complete notification
  if (event.data?.type === 'SHOPQ_SCAN_COMPLETE') {
    console.log('ShopQ Returns: Scan complete', event.data);
    refreshBtn.classList.remove('scanning');
    refreshStatus.textContent = '';
    // Refresh the returns list
    fetchReturns();
  }

  // Handle enrichment result (v0.6.2)
  if (event.data?.type === 'SHOPQ_ENRICH_RESULT') {
    isEnriching = false;
    if (event.data.order && currentDetailOrder) {
      // Update with enriched order data
      currentDetailOrder = event.data.order;
      renderDetailView(event.data.order, event.data.state === 'not_found');
    }
  }

  // Handle merchant rule set confirmation
  if (event.data?.type === 'SHOPQ_MERCHANT_RULE_SET') {
    // Refresh to show updated deadlines
    fetchReturns();
    if (currentDetailOrder) {
      // Re-fetch the current order
      window.parent.postMessage({
        type: 'SHOPQ_GET_ORDER',
        order_key: currentDetailOrder.order_key
      }, '*');
    }
  }

  // Handle order data (for refreshing detail view)
  if (event.data?.type === 'SHOPQ_ORDER_DATA') {
    if (event.data.order && currentDetailOrder &&
        event.data.order.order_key === currentDetailOrder.order_key) {
      currentDetailOrder = event.data.order;
      renderDetailView(event.data.order, !event.data.order.return_by_date);
    }
  }
});

// =============================================================================
// EVENT HANDLERS
// =============================================================================

// Close button
closeBtn.addEventListener('click', () => {
  window.parent.postMessage({ type: 'SHOPQ_CLOSE_SIDEBAR' }, '*');
});

// Back button
backBtn.addEventListener('click', () => {
  showListView();
});

// Refresh button - trigger rescan
refreshBtn.addEventListener('click', () => {
  refreshBtn.classList.add('scanning');
  refreshStatus.textContent = 'Scanning...';
  // Request rescan from parent (content script)
  window.parent.postMessage({ type: 'SHOPQ_RESCAN_EMAILS' }, '*');
});

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Signal ready to parent
  window.parent.postMessage({ type: 'SHOPQ_RETURNS_SIDEBAR_READY' }, '*');

  // Fetch initial data
  fetchReturns();
});
