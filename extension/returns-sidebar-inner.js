/**
 * Reclaim Sidebar
 * Displays returnable purchases and their return windows
 *
 * Uses GET_VISIBLE_ORDERS for a unified purchase list sorted by urgency.
 * Triggers ENRICH_ORDER on detail view open.
 * Supports SET_MERCHANT_RULE for unknown deadlines.
 */

// =============================================================================
// STATE
// =============================================================================

let visibleOrders = [];
let currentDetailOrder = null;
let isEnriching = false;
let hasCompletedFirstScan = false;
let hideExpired = false;

// =============================================================================
// DOM ELEMENTS
// =============================================================================

const listView = document.getElementById('list-view');
const detailView = document.getElementById('detail-view');
const backBtn = document.getElementById('back-btn');
const closeBtn = document.getElementById('close-btn');
const refreshBtn = document.getElementById('refresh-btn');
const refreshStatus = document.getElementById('refresh-status');
const hideExpiredBtn = document.getElementById('hide-expired-btn');

// =============================================================================
// UTILITIES
// =============================================================================

/**
 * Escape HTML to prevent XSS attacks (SEC-001)
 * @param {string} text - Untrusted text to escape
 * @returns {string} HTML-safe string
 */
function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

/**
 * Sanitize a URL to prevent javascript: and other dangerous protocols (SEC-001)
 * Only allows http:, https:, and mailto: protocols
 * @param {string} url - Untrusted URL to sanitize
 * @returns {string} Safe URL or empty string if dangerous
 */
function sanitizeUrl(url) {
  if (!url || typeof url !== 'string') return '';
  const trimmed = url.trim().toLowerCase();
  // Only allow safe protocols
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('mailto:')) {
    return url; // Return original (preserving case)
  }
  // Block javascript:, data:, vbscript:, etc.
  console.warn('ShopQ: Blocked unsafe URL:', url.substring(0, 50));
  return '';
}

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
 * Get filtered orders based on current filter state
 */
function getFilteredOrders() {
  if (!hideExpired) return visibleOrders;
  return visibleOrders.filter(o => {
    const daysUntil = getDaysUntil(o.return_by_date);
    return daysUntil === null || daysUntil >= 0;
  });
}

/**
 * Render the returns list view — single flat list sorted by urgency
 */
function renderListView() {
  const filteredOrders = getFilteredOrders();

  if (filteredOrders.length === 0) {
    if (!hasCompletedFirstScan) {
      listView.innerHTML = `
        <div class="empty-state">
          <div class="icon">🔍</div>
          <p><strong>Finding return windows...</strong></p>
          <p style="font-size: 13px;">Scanning your emails for recent purchases.</p>
        </div>
      `;
    } else if (hideExpired && visibleOrders.length > 0) {
      // Have orders but all expired and hidden
      listView.innerHTML = `
        <div class="empty-state">
          <div class="icon">✓</div>
          <p><strong>All caught up!</strong></p>
          <p style="font-size: 13px;">${visibleOrders.length} expired order${visibleOrders.length === 1 ? '' : 's'} hidden.</p>
          <button id="show-expired-btn" style="
            margin-top: 12px;
            padding: 8px 16px;
            background: transparent;
            color: #1a73e8;
            border: 1px solid #1a73e8;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
          ">Show expired</button>
        </div>
      `;
      document.getElementById('show-expired-btn')?.addEventListener('click', toggleHideExpired);
    } else {
      listView.innerHTML = `
        <div class="empty-state">
          <div class="icon">📦</div>
          <p><strong>No returns to track</strong></p>
          <p style="font-size: 13px;">When you make purchases, they'll appear here with their return deadlines.</p>
        </div>
      `;
    }
    return;
  }

  const html = filteredOrders.map(o => renderOrderCard(o)).join('');
  listView.innerHTML = html;

  // Add click handlers to cards
  listView.querySelectorAll('.return-card').forEach(card => {
    card.addEventListener('click', (e) => {
      // Don't navigate if clicking dismiss button
      if (e.target.closest('.dismiss-btn')) return;
      const orderKey = card.dataset.id;
      const order = visibleOrders.find(o => o.order_key === orderKey);
      if (order) {
        showDetailView(order);
      }
    });
  });

  // Add dismiss button handlers
  listView.querySelectorAll('.dismiss-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const orderKey = btn.dataset.id;
      dismissOrder(orderKey);
    });
  });
}

/**
 * Render a single order card — urgency always derived from days remaining
 */
function renderOrderCard(order) {
  const daysUntil = getDaysUntil(order.return_by_date);
  const isExpiring = daysUntil !== null && daysUntil <= 7 && daysUntil >= 0;
  const isCritical = daysUntil !== null && daysUntil <= 3 && daysUntil >= 0;
  const isExpired = daysUntil !== null && daysUntil < 0;

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
    } else if (daysUntil <= 3) {
      dateText = `${daysUntil} day${daysUntil === 1 ? '' : 's'} left`;
      dateClass = 'urgent';
      urgentBadge = `<span class="urgent-badge critical"><span class="dot"></span>${daysUntil} day${daysUntil === 1 ? '' : 's'}</span>`;
    } else if (daysUntil <= 7) {
      dateText = `${daysUntil} days left`;
      dateClass = '';
      urgentBadge = `<span class="urgent-badge warning"><span class="dot"></span>${daysUntil} days</span>`;
    } else {
      dateText = `Due ${formatDate(order.return_by_date)}`;
    }
  } else if (order.deadline_confidence === 'unknown') {
    dateText = 'Deadline unknown';
    dateClass = '';
  }

  let cardClass = isCritical ? 'critical' : (isExpiring ? 'expiring' : '');
  if (isExpired) cardClass += ' expired';

  // Trash icon SVG for dismiss button
  const trashIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>`;

  return `
    <div class="return-card ${cardClass}" data-id="${escapeHtml(order.order_key)}">
      <div class="card-header">
        <span class="merchant">${escapeHtml(order.merchant_display_name)}</span>
        ${urgentBadge}
      </div>
      <div class="item-summary">${escapeHtml(order.item_summary)}</div>
      <div class="card-footer">
        <span class="return-date ${dateClass}">${dateText}</span>
        <button class="dismiss-btn" data-id="${escapeHtml(order.order_key)}" title="Not a purchase / Dismiss">
          ${trashIcon}
        </button>
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
    'dismissed': '<span class="status-badge">Dismissed</span>',
    'cancelled': '<span class="status-badge">Cancelled</span>'
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
        <div class="detail-label">Return Policy</div>
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

    ${order.source_email_ids && order.source_email_ids.length > 0 ? `
    <div class="detail-section">
      <a href="https://mail.google.com/mail/u/0/#inbox/${encodeURIComponent(order.source_email_ids[0])}"
         target="_top"
         style="color: #1a73e8; text-decoration: none; font-size: 13px;">
        View Order Email &rarr;
      </a>
    </div>
    ` : ''}

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

    ${order.return_portal_link && sanitizeUrl(order.return_portal_link) ? `
    <div class="detail-section">
      <div class="detail-label">Return Portal</div>
      <div class="detail-value">
        <a href="${sanitizeUrl(order.return_portal_link)}" target="_top">Start Return</a>
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
    </div>
    <div style="text-align: center; margin-top: 16px;">
      <button id="dismiss-order-btn" style="
        background: none;
        border: none;
        color: #9aa0a6;
        font-size: 12px;
        cursor: pointer;
        padding: 8px;
      ">Not a purchase? Dismiss</button>
    </div>
    ` : ''}
  `;

  // Add action handlers
  const markReturnedBtn = document.getElementById('mark-returned-btn');
  const setRuleBtn = document.getElementById('set-rule-btn');
  const dismissOrderBtn = document.getElementById('dismiss-order-btn');

  if (markReturnedBtn) {
    markReturnedBtn.addEventListener('click', () => {
      updateOrderStatus(order.order_key, 'returned');
    });
  }

  if (setRuleBtn) {
    setRuleBtn.addEventListener('click', () => {
      showMerchantRuleDialog(order.merchant_domain, order.merchant_display_name);
    });
  }

  if (dismissOrderBtn) {
    dismissOrderBtn.addEventListener('click', () => {
      dismissOrder(order.order_key);
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


// =============================================================================
// API CALLS
// =============================================================================

/**
 * Fetch visible orders from content script
 */
async function fetchReturns() {
  try {
    window.parent.postMessage({ type: 'SHOPQ_GET_ORDERS' }, '*');
  } catch (error) {
    console.error('ShopQ Returns: Failed to request orders:', error);
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
 * Dismiss an order (mark as not a purchase / irrelevant)
 */
function dismissOrder(orderKey) {
  updateOrderStatus(orderKey, 'dismissed');
}

/**
 * Toggle hide expired orders
 */
function toggleHideExpired() {
  hideExpired = !hideExpired;
  hideExpiredBtn.classList.toggle('active', hideExpired);
  hideExpiredBtn.title = hideExpired ? 'Show expired orders' : 'Hide expired orders';

  // Update icon to show eye-off when hiding
  if (hideExpired) {
    hideExpiredBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
      </svg>
    `;
  } else {
    hideExpiredBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
      </svg>
    `;
  }

  renderListView();
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
  // Handle unified visible orders
  if (event.data?.type === 'SHOPQ_ORDERS_DATA') {
    visibleOrders = event.data.orders || [];
    if (visibleOrders.length > 0) {
      hasCompletedFirstScan = true;
    }
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
    hasCompletedFirstScan = true;
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

// Hide expired toggle
hideExpiredBtn.addEventListener('click', toggleHideExpired);

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Signal ready to parent
  window.parent.postMessage({ type: 'SHOPQ_RETURNS_SIDEBAR_READY' }, '*');

  // Fetch initial data
  fetchReturns();
});
