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
let returnedOrders = []; // Orders marked as returned (for undo drawer)
let currentDetailOrder = null;
let isEnriching = false;
let hasCompletedFirstScan = false;
let expiredAccordionOpen = false; // Controls expired orders accordion
let returnedAccordionOpen = false; // Controls returned orders accordion
let deliveryModal = null;
let activeDeliveries = {}; // Map of order_key -> delivery object
let isEditingDate = false; // Controls inline date picker visibility
let deliveryState = {
  step: 'address', // 'address' | 'locations' | 'quote' | 'confirmed' | 'status'
  address: null,
  locations: [],
  selectedLocation: null,
  quote: null,
  delivery: null,
  loading: false,
  error: null,
};

// Periodic date refresh timer
let dateRefreshInterval = null;
const DATE_REFRESH_INTERVAL_MS = 60000; // 1 minute

function startDateRefreshTimer() {
  if (dateRefreshInterval) return;
  dateRefreshInterval = setInterval(() => {
    if (visibleOrders.length > 0) {
      renderListView();
    }
  }, DATE_REFRESH_INTERVAL_MS);
}

function stopDateRefreshTimer() {
  if (dateRefreshInterval) {
    clearInterval(dateRefreshInterval);
    dateRefreshInterval = null;
  }
}

// =============================================================================
// DOM ELEMENTS
// =============================================================================

const listView = document.getElementById('list-view');
const detailView = document.getElementById('detail-view');
const backBtn = document.getElementById('back-btn');
const closeBtn = document.getElementById('close-btn');
const refreshBtn = document.getElementById('refresh-btn');
const refreshStatus = document.getElementById('refresh-status');
// hideExpiredBtn removed - using accordion instead

// =============================================================================
// UTILITIES
// =============================================================================

// =============================================================================
// TOAST NOTIFICATIONS
// =============================================================================

/**
 * Show a toast notification
 * @param {string} message - Message to display
 * @param {string} type - 'success' | 'error' | 'info'
 * @param {number} duration - Duration in ms (default 3000)
 */
function showToast(message, type = 'info', duration = 3000) {
  // Remove any existing toast
  const existing = document.querySelector('.toast-notification');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast-notification toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  // Auto-dismiss
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * Show a confirmation dialog
 * @param {string} title - Dialog title
 * @param {string} message - Dialog message
 * @param {Function} onConfirm - Callback when confirmed
 * @param {Function} [onCancel] - Optional callback when cancelled
 */
function showConfirmDialog(title, message, onConfirm, onCancel) {
  // Remove any existing dialog
  const existing = document.querySelector('.confirm-dialog-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.className = 'confirm-dialog-overlay';
  overlay.innerHTML = `
    <div class="confirm-dialog">
      <div class="confirm-dialog-title">${escapeHtml(title)}</div>
      <div class="confirm-dialog-message">${escapeHtml(message)}</div>
      <div class="confirm-dialog-actions">
        <button class="confirm-dialog-btn cancel">Cancel</button>
        <button class="confirm-dialog-btn confirm">Confirm</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Handle clicks
  overlay.querySelector('.confirm-dialog-btn.cancel').addEventListener('click', () => {
    overlay.remove();
    if (onCancel) onCancel();
  });

  overlay.querySelector('.confirm-dialog-btn.confirm').addEventListener('click', () => {
    overlay.remove();
    onConfirm();
  });

  // Close on overlay click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.remove();
      if (onCancel) onCancel();
    }
  });
}

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
  console.warn('Reclaim: Blocked unsafe URL:', url.substring(0, 50));
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
 * Separate orders into active and expired
 */
function getOrdersByStatus() {
  const active = [];
  const expired = [];

  for (const order of visibleOrders) {
    const daysUntil = getDaysUntil(order.return_by_date);
    if (daysUntil !== null && daysUntil < 0) {
      expired.push(order);
    } else {
      active.push(order);
    }
  }

  return { active, expired };
}

/**
 * Toggle expired accordion
 */
function toggleExpiredAccordion() {
  expiredAccordionOpen = !expiredAccordionOpen;
  renderListView();
}

/**
 * Toggle returned accordion
 */
function toggleReturnedAccordion() {
  returnedAccordionOpen = !returnedAccordionOpen;
  renderListView();
}

/**
 * Undo marking an order as returned (set back to active)
 */
function undoReturnOrder(orderKey) {
  window.parent.postMessage({
    type: 'SHOPQ_UPDATE_ORDER_STATUS',
    order_key: orderKey,
    status: 'active'
  }, '*');
  showToast('Moved back to active returns', 'success');

  // Refresh both lists to update UI immediately
  fetchReturns();
  window.parent.postMessage({ type: 'SHOPQ_GET_RETURNED_ORDERS' }, '*');
}

/**
 * Render the returns list view — active orders + expired accordion
 */
function renderListView() {
  const { active, expired } = getOrdersByStatus();

  // Empty state - no orders at all
  if (visibleOrders.length === 0) {
    if (!hasCompletedFirstScan) {
      listView.innerHTML = `
        <div class="empty-state">
          <div class="icon">🔍</div>
          <p><strong>Finding return windows...</strong></p>
          <p style="font-size: 13px;">Scanning your emails for recent purchases.</p>
        </div>
      `;
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

  let html = '';

  // Render returned accordion at the TOP if there are returned orders
  if (returnedOrders.length > 0) {
    const chevronIcon = returnedAccordionOpen
      ? `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>`;

    html += `
      <div class="returned-accordion">
        <button class="returned-accordion-header" id="returned-accordion-toggle">
          <span class="returned-accordion-title">
            <span class="returned-icon">✓</span>
            Returned (${returnedOrders.length})
          </span>
          ${chevronIcon}
        </button>
        ${returnedAccordionOpen ? `
          <div class="returned-accordion-content">
            ${returnedOrders.map(o => renderReturnedCard(o)).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }

  // Render expired accordion if there are expired orders
  if (expired.length > 0) {
    const chevronIcon = expiredAccordionOpen
      ? `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>`;

    html += `
      <div class="expired-accordion">
        <button class="expired-accordion-header" id="expired-accordion-toggle">
          <span class="expired-accordion-title">
            <span class="expired-icon">📦</span>
            Expired (${expired.length})
          </span>
          ${chevronIcon}
        </button>
        ${expiredAccordionOpen ? `
          <div class="expired-accordion-content">
            ${expired.map(o => renderOrderCard(o)).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }

  // Render active orders below the accordions
  if (active.length > 0) {
    html += active.map(o => renderOrderCard(o)).join('');
  } else if (expired.length > 0 || returnedOrders.length > 0) {
    // Only expired/returned orders exist
    html += `
      <div class="empty-state" style="padding: 24px 20px;">
        <div class="icon">✓</div>
        <p><strong>All caught up!</strong></p>
        <p style="font-size: 13px;">No active return windows.</p>
      </div>
    `;
  }

  listView.innerHTML = html;

  // Add accordion toggle handlers
  document.getElementById('expired-accordion-toggle')?.addEventListener('click', toggleExpiredAccordion);
  document.getElementById('returned-accordion-toggle')?.addEventListener('click', toggleReturnedAccordion);

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

  // Add undo button handlers (for returned orders)
  listView.querySelectorAll('.undo-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const orderKey = btn.dataset.id;
      undoReturnOrder(orderKey);
    });
  });

  // Add delivery badge click handlers
  listView.querySelectorAll('.delivery-badge').forEach(badge => {
    badge.addEventListener('click', (e) => {
      e.stopPropagation();
      const orderKey = badge.dataset.orderKey;
      const delivery = activeDeliveries[orderKey];
      if (delivery) {
        showDeliveryStatus(delivery);
      }
    });
  });
}

/**
 * Render a returned order card with undo button
 */
function renderReturnedCard(order) {
  const undoIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z"/></svg>`;

  return `
    <div class="returned-card" data-id="${escapeHtml(order.order_key)}">
      <div class="returned-card-content">
        <span class="returned-merchant">${escapeHtml(order.merchant_display_name || 'Unknown')}</span>
        <span class="returned-item">${escapeHtml(order.item_summary || 'Unknown item')}</span>
      </div>
      <button class="undo-btn" data-id="${escapeHtml(order.order_key)}" title="Undo - move back to active">
        ${undoIcon}
      </button>
    </div>
  `;
}

/**
 * Build delivery badge HTML for an order
 */
function getDeliveryBadge(orderKey) {
  const delivery = activeDeliveries[orderKey];
  if (!delivery) return '';

  const statusLabels = {
    'quote_pending': 'Getting quote',
    'quoted': 'Quote ready',
    'pending': 'Finding driver',
    'pickup': 'Driver en route',
    'pickup_complete': 'Picked up',
    'dropoff': 'In transit',
    'delivered': 'Delivered',
    'canceled': 'Canceled',
    'failed': 'Failed',
  };

  const statusClasses = {
    'delivered': 'delivery-badge-success',
    'canceled': 'delivery-badge-error',
    'failed': 'delivery-badge-error',
  };

  const statusClass = statusClasses[delivery.status] || 'delivery-badge-active';
  const label = statusLabels[delivery.status] || delivery.status;

  const truckIcon = `<svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/></svg>`;

  return `<span class="delivery-badge ${statusClass}" data-order-key="${escapeHtml(orderKey)}">${truckIcon} ${escapeHtml(label)}</span>`;
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
  const deliveryBadge = getDeliveryBadge(order.order_key);

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
        ${deliveryBadge || urgentBadge}
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
  let deadlineDate = 'No deadline set';
  let daysLeftText = '';
  let deadlineClass = '';

  if (order.return_by_date) {
    const date = new Date(order.return_by_date);
    deadlineDate = date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'short',
      day: 'numeric'
    });

    if (daysUntil !== null) {
      if (daysUntil < 0) {
        daysLeftText = '(Expired)';
        deadlineClass = 'urgent';
      } else if (daysUntil === 0) {
        daysLeftText = '(Today!)';
        deadlineClass = 'urgent';
      } else if (daysUntil === 1) {
        daysLeftText = '(1 day left)';
        deadlineClass = daysUntil <= 3 ? 'urgent' : '';
      } else {
        daysLeftText = `(${daysUntil} days left)`;
        deadlineClass = daysUntil <= 3 ? 'urgent' : '';
      }
    }
  }

  // Icons
  const externalLinkIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>`;
  const truckIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/></svg>`;
  const editIcon = `<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>`;

  // Determine deadline basis text (what date the deadline is calculated from)
  // Only show for estimated deadlines - exact deadlines from email need no explanation
  let deadlineBasisText = '';
  if (order.return_by_date && order.deadline_confidence === 'estimated') {
    if (order.delivery_date) {
      deadlineBasisText = 'Estimated based on delivery date';
    } else if (order.estimated_delivery_date) {
      deadlineBasisText = 'Estimated based on expected delivery';
    } else if (order.ship_date) {
      deadlineBasisText = 'Estimated based on ship date';
    } else if (order.purchase_date) {
      deadlineBasisText = 'Estimated based on purchase date';
    }
  }
  // No text for 'exact' - the date speaks for itself

  // Build editable return date section
  const currentDateValue = order.return_by_date ? order.return_by_date.split('T')[0] : '';
  const dateEditSection = isEditingDate ? `
    <div class="date-edit-container">
      <input type="date" id="return-date-input"
             value="${currentDateValue}"
             class="date-input">
      <div class="date-error" id="date-error"></div>
      <div class="date-edit-actions">
        <button class="date-save-btn" id="save-date-btn">Save</button>
        <button class="date-cancel-btn" id="cancel-date-btn">Cancel</button>
      </div>
    </div>
  ` : `
    <div class="date-display-container">
      <div class="detail-value large ${deadlineClass}">
        ${deadlineDate}${daysLeftText ? `<span class="days-left">${daysLeftText}</span>` : ''}
      </div>
      <button class="edit-date-btn" id="edit-date-btn" title="Edit return date">
        ${editIcon}
      </button>
    </div>
    ${deadlineBasisText ? `<div class="deadline-basis">${deadlineBasisText}</div>` : ''}
  `;

  // Build order info card
  let orderInfoCard = '';
  if (order.order_id || order.purchase_date) {
    orderInfoCard = `
      <div class="order-info-card">
        ${order.order_id ? `
        <div class="order-info-item">
          <span class="order-info-label">Order ID</span>
          <span class="order-info-value">${escapeHtml(order.order_id)}</span>
        </div>
        ` : ''}
        ${order.purchase_date ? `
        <div class="order-info-item">
          <span class="order-info-label">Date</span>
          <span class="order-info-value">${new Date(order.purchase_date).toLocaleDateString()}</span>
        </div>
        ` : ''}
      </div>
    `;
  }

  // Build enrichment section (for unknown deadlines)
  let enrichSection = '';
  if (needsEnrichment && !isEditingDate) {
    if (isEnriching) {
      enrichSection = `
        <div id="enrich-section" style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 12px; margin-bottom: 20px;">
          <div class="spinner" style="margin: 0 auto 8px;"></div>
          <div style="color: #5f6368; font-size: 13px;">Checking return policy...</div>
        </div>
      `;
    } else {
      enrichSection = `
        <div id="enrich-section" style="text-align: center; padding: 20px; background: #fff3e0; border-radius: 12px; margin-bottom: 20px;">
          <div style="color: #e65100; margin-bottom: 12px; font-size: 14px;">No return deadline found</div>
          <button id="set-rule-btn" class="action-btn secondary" style="width: auto; padding: 10px 20px;">
            Set Return Window
          </button>
        </div>
      `;
    }
  }

  detailView.innerHTML = `
    <div class="detail-header">
      <div class="detail-merchant">${escapeHtml(order.merchant_display_name)}</div>
      <div class="detail-item">${escapeHtml(order.item_summary)}</div>
      ${order.source_email_ids && order.source_email_ids.length > 0 ? `
      <a href="https://mail.google.com/mail/u/0/#inbox/${encodeURIComponent(order.source_email_ids[0])}"
         target="_top"
         class="detail-email-link">
        View Order Email ${externalLinkIcon}
      </a>
      ` : ''}
    </div>

    <div class="detail-section">
      <div class="detail-label">Return By</div>
      ${dateEditSection}
    </div>

    ${enrichSection}
    ${orderInfoCard}

    ${order.order_status === 'active' ? `
    <div class="detail-actions">
      <button class="action-btn uber" id="deliver-carrier-btn">
        ${truckIcon}
        Courier Pickup with Uber
      </button>
      <button class="action-btn secondary" id="mark-returned-btn">
        Mark as Returned
      </button>
      <button class="action-btn tertiary" id="dismiss-order-btn">
        Dismiss (Not an Order)
      </button>
    </div>
    ` : ''}
  `;

  // Add action handlers
  const markReturnedBtn = document.getElementById('mark-returned-btn');
  const setRuleBtn = document.getElementById('set-rule-btn');
  const dismissOrderBtn = document.getElementById('dismiss-order-btn');
  const deliverCarrierBtn = document.getElementById('deliver-carrier-btn');

  // Date editing handlers
  const editDateBtn = document.getElementById('edit-date-btn');
  const saveDateBtn = document.getElementById('save-date-btn');
  const cancelDateBtn = document.getElementById('cancel-date-btn');

  if (editDateBtn) {
    editDateBtn.addEventListener('click', () => {
      isEditingDate = true;
      renderDetailView(order, false);
    });
  }

  if (saveDateBtn) {
    saveDateBtn.addEventListener('click', () => {
      const input = document.getElementById('return-date-input');
      const errorEl = document.getElementById('date-error');

      // Clear previous error
      if (errorEl) errorEl.textContent = '';

      if (input?.value) {
        // Validate date before sending
        const validation = validateReturnDate(input.value);
        if (!validation.valid) {
          if (errorEl) {
            errorEl.textContent = validation.error;
          } else {
            showToast(validation.error, 'error');
          }
          return;
        }
        // Show saving state
        saveDateBtn.disabled = true;
        saveDateBtn.textContent = 'Saving...';
        updateOrderReturnDate(order.order_key, input.value);
      }
    });
  }

  if (cancelDateBtn) {
    cancelDateBtn.addEventListener('click', () => {
      isEditingDate = false;
      renderDetailView(order, needsEnrichment);
    });
  }

  if (markReturnedBtn) {
    markReturnedBtn.addEventListener('click', () => {
      showConfirmDialog(
        'Mark as Returned?',
        'This will remove the item from your active returns list.',
        () => {
          updateOrderStatus(order.order_key, 'returned');
          showToast('Marked as returned', 'success');
        }
      );
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

  if (deliverCarrierBtn) {
    deliverCarrierBtn.addEventListener('click', () => {
      showDeliveryModal(order);
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

// =============================================================================
// DELIVERY MODAL
// =============================================================================

/**
 * Show the delivery scheduling modal
 */
function showDeliveryModal(order) {
  // Reset delivery state
  deliveryState = {
    step: 'address',
    address: null,
    locations: [],
    selectedLocation: null,
    quote: null,
    delivery: null,
    loading: true,
    error: null,
  };

  // Create modal overlay
  deliveryModal = document.createElement('div');
  deliveryModal.className = 'delivery-modal-overlay';
  deliveryModal.innerHTML = `
    <div class="delivery-modal">
      <div class="delivery-modal-header">
        <h3>Schedule Return Pickup</h3>
        <button class="delivery-modal-close">&times;</button>
      </div>
      <div class="delivery-modal-content">
        <div class="delivery-loading">
          <div class="spinner"></div>
          <div>Loading...</div>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(deliveryModal);

  // Close handlers
  deliveryModal.querySelector('.delivery-modal-close').addEventListener('click', closeDeliveryModal);
  deliveryModal.addEventListener('click', (e) => {
    if (e.target === deliveryModal) closeDeliveryModal();
  });

  // Check for saved address
  window.parent.postMessage({ type: 'SHOPQ_GET_USER_ADDRESS' }, '*');
}

/**
 * Close the delivery modal
 */
function closeDeliveryModal() {
  if (deliveryModal) {
    deliveryModal.remove();
    deliveryModal = null;
  }
}

/**
 * Show delivery status modal for an existing delivery
 */
function showDeliveryStatus(delivery) {
  deliveryState = {
    step: 'status',
    address: null,
    locations: [],
    selectedLocation: null,
    quote: null,
    delivery: delivery,
    loading: false,
    error: null,
  };

  deliveryModal = document.createElement('div');
  deliveryModal.className = 'delivery-modal-overlay';
  deliveryModal.innerHTML = `
    <div class="delivery-modal">
      <div class="delivery-modal-header">
        <h3>Delivery Status</h3>
        <button class="delivery-modal-close">&times;</button>
      </div>
      <div class="delivery-modal-content"></div>
    </div>
  `;

  document.body.appendChild(deliveryModal);

  deliveryModal.querySelector('.delivery-modal-close').addEventListener('click', closeDeliveryModal);
  deliveryModal.addEventListener('click', (e) => {
    if (e.target === deliveryModal) closeDeliveryModal();
  });

  renderDeliveryModal();
}

/**
 * Render the current delivery modal step
 */
function renderDeliveryModal() {
  if (!deliveryModal) return;

  const content = deliveryModal.querySelector('.delivery-modal-content');
  if (!content) return;

  if (deliveryState.loading) {
    content.innerHTML = `
      <div class="delivery-loading">
        <div class="spinner"></div>
        <div>${deliveryState.step === 'quote' ? 'Getting quote...' : 'Loading...'}</div>
      </div>
    `;
    return;
  }

  if (deliveryState.error) {
    content.innerHTML = `
      <div class="delivery-error">
        <div class="error-icon">⚠️</div>
        <div class="error-message">${escapeHtml(deliveryState.error)}</div>
        <button class="action-btn secondary" id="delivery-retry-btn">Try Again</button>
      </div>
    `;
    content.querySelector('#delivery-retry-btn')?.addEventListener('click', () => {
      deliveryState.error = null;
      deliveryState.step = 'address';
      renderDeliveryModal();
    });
    return;
  }

  switch (deliveryState.step) {
    case 'address':
      renderAddressStep(content);
      break;
    case 'locations':
      renderLocationsStep(content);
      break;
    case 'quote':
      renderQuoteStep(content);
      break;
    case 'confirmed':
      renderConfirmedStep(content);
      break;
    case 'status':
      renderStatusStep(content);
      break;
  }
}

/**
 * Render address input step
 */
function renderAddressStep(content) {
  const addr = deliveryState.address || {};

  content.innerHTML = `
    <div class="delivery-step">
      <div class="step-title">Pickup Address</div>
      <p class="step-description">Where should the driver pick up your return?</p>

      <div class="address-form">
        <div class="form-group">
          <label>Street Address</label>
          <input type="text" id="addr-street" placeholder="123 Main St" value="${escapeHtml(addr.street || '')}">
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>City</label>
            <input type="text" id="addr-city" placeholder="San Francisco" value="${escapeHtml(addr.city || '')}">
          </div>
          <div class="form-group small">
            <label>State</label>
            <input type="text" id="addr-state" placeholder="CA" maxlength="2" value="${escapeHtml(addr.state || '')}">
          </div>
        </div>
        <div class="form-group">
          <label>ZIP Code</label>
          <input type="text" id="addr-zip" placeholder="94102" maxlength="10" value="${escapeHtml(addr.zip_code || '')}">
        </div>
      </div>

      <div class="delivery-actions">
        <button class="action-btn secondary" id="delivery-cancel-btn">Cancel</button>
        <button class="action-btn primary" id="delivery-next-btn">Find Drop-off Locations</button>
      </div>
    </div>
  `;

  content.querySelector('#delivery-cancel-btn').addEventListener('click', closeDeliveryModal);
  content.querySelector('#delivery-next-btn').addEventListener('click', () => {
    const street = content.querySelector('#addr-street').value.trim();
    const city = content.querySelector('#addr-city').value.trim();
    const state = content.querySelector('#addr-state').value.trim().toUpperCase();
    const zip = content.querySelector('#addr-zip').value.trim();

    if (!street || !city || !state || !zip) {
      alert('Please fill in all address fields');
      return;
    }

    deliveryState.address = {
      street,
      city,
      state,
      zip_code: zip,
      country: 'US',
    };

    // Save address for future use
    window.parent.postMessage({
      type: 'SHOPQ_SET_USER_ADDRESS',
      address: deliveryState.address,
    }, '*');

    // Fetch locations
    deliveryState.loading = true;
    deliveryState.step = 'locations';
    renderDeliveryModal();

    window.parent.postMessage({
      type: 'SHOPQ_GET_DELIVERY_LOCATIONS',
      address: deliveryState.address,
    }, '*');
  });
}

/**
 * Render carrier location selection step
 */
function renderLocationsStep(content) {
  if (deliveryState.locations.length === 0) {
    content.innerHTML = `
      <div class="delivery-step">
        <div class="step-title">No Locations Found</div>
        <p class="step-description">We couldn't find any drop-off locations near you.</p>
        <div class="delivery-actions">
          <button class="action-btn secondary" id="delivery-back-btn">Back</button>
        </div>
      </div>
    `;
    content.querySelector('#delivery-back-btn').addEventListener('click', () => {
      deliveryState.step = 'address';
      renderDeliveryModal();
    });
    return;
  }

  const locationCards = deliveryState.locations.map((loc, i) => `
    <div class="location-card ${deliveryState.selectedLocation?.id === loc.id ? 'selected' : ''}" data-index="${i}">
      <div class="location-carrier">${escapeHtml(loc.carrier)}</div>
      <div class="location-name">${escapeHtml(loc.name)}</div>
      <div class="location-address">${escapeHtml(loc.address.street)}, ${escapeHtml(loc.address.city)}</div>
      ${loc.distance_miles ? `<div class="location-distance">${loc.distance_miles} mi</div>` : ''}
      <div class="location-hours">${escapeHtml(loc.hours || '')}</div>
    </div>
  `).join('');

  content.innerHTML = `
    <div class="delivery-step">
      <div class="step-title">Select Drop-off Location</div>
      <p class="step-description">Choose where to deliver your return package</p>

      <div class="locations-list">
        ${locationCards}
      </div>

      <div class="delivery-actions">
        <button class="action-btn secondary" id="delivery-back-btn">Back</button>
        <button class="action-btn primary" id="delivery-quote-btn" ${!deliveryState.selectedLocation ? 'disabled' : ''}>
          Get Quote
        </button>
      </div>
    </div>
  `;

  // Location selection handlers
  content.querySelectorAll('.location-card').forEach(card => {
    card.addEventListener('click', () => {
      const index = parseInt(card.dataset.index);
      deliveryState.selectedLocation = deliveryState.locations[index];
      renderDeliveryModal();
    });
  });

  content.querySelector('#delivery-back-btn').addEventListener('click', () => {
    deliveryState.step = 'address';
    renderDeliveryModal();
  });

  content.querySelector('#delivery-quote-btn').addEventListener('click', () => {
    if (!deliveryState.selectedLocation) return;

    deliveryState.loading = true;
    renderDeliveryModal();

    window.parent.postMessage({
      type: 'SHOPQ_GET_DELIVERY_QUOTE',
      order_key: currentDetailOrder.order_key,
      pickup_address: deliveryState.address,
      dropoff_location_id: deliveryState.selectedLocation.id,
    }, '*');
  });
}

/**
 * Render quote confirmation step
 */
function renderQuoteStep(content) {
  const quote = deliveryState.quote;
  if (!quote) {
    deliveryState.error = 'Failed to get quote';
    renderDeliveryModal();
    return;
  }

  const pickupTime = new Date(quote.estimated_pickup_time);
  const dropoffTime = new Date(quote.estimated_dropoff_time);
  const expiresAt = new Date(quote.expires_at);
  const now = new Date();
  const expiresIn = Math.max(0, Math.floor((expiresAt - now) / 1000 / 60));

  content.innerHTML = `
    <div class="delivery-step">
      <div class="step-title">Confirm Delivery</div>

      <div class="quote-summary">
        <div class="quote-fee">${escapeHtml(quote.fee_display)}</div>
        <div class="quote-label">Uber delivery fee</div>
      </div>

      <div class="quote-details">
        <div class="quote-row">
          <span class="quote-label">Pickup</span>
          <span class="quote-value">${escapeHtml(deliveryState.address.street)}</span>
        </div>
        <div class="quote-row">
          <span class="quote-label">Drop-off</span>
          <span class="quote-value">${escapeHtml(quote.dropoff_location_name)}</span>
        </div>
        <div class="quote-row">
          <span class="quote-label">Est. Pickup</span>
          <span class="quote-value">${pickupTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
        </div>
        <div class="quote-row">
          <span class="quote-label">Est. Drop-off</span>
          <span class="quote-value">${dropoffTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
        </div>
      </div>

      <div class="quote-expires">
        Quote expires in ${expiresIn} minute${expiresIn === 1 ? '' : 's'}
      </div>

      <div class="delivery-actions">
        <button class="action-btn secondary" id="delivery-back-btn">Back</button>
        <button class="action-btn primary" id="delivery-confirm-btn">Confirm & Schedule</button>
      </div>
    </div>
  `;

  content.querySelector('#delivery-back-btn').addEventListener('click', () => {
    deliveryState.step = 'locations';
    deliveryState.quote = null;
    renderDeliveryModal();
  });

  content.querySelector('#delivery-confirm-btn').addEventListener('click', () => {
    deliveryState.loading = true;
    renderDeliveryModal();

    window.parent.postMessage({
      type: 'SHOPQ_CONFIRM_DELIVERY',
      delivery_id: quote.delivery_id,
    }, '*');
  });
}

/**
 * Render confirmed step
 */
function renderConfirmedStep(content) {
  const delivery = deliveryState.delivery;

  content.innerHTML = `
    <div class="delivery-step">
      <div class="success-icon">✓</div>
      <div class="step-title">Delivery Scheduled!</div>
      <p class="step-description">
        An Uber driver will pick up your return and deliver it to
        ${escapeHtml(delivery.dropoff_location_name)}.
      </p>

      ${delivery.tracking_url ? `
      <a href="${sanitizeUrl(delivery.tracking_url)}" target="_blank" class="tracking-link">
        Track Delivery
        <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
          <path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/>
        </svg>
      </a>
      ` : ''}

      <div class="delivery-actions">
        <button class="action-btn primary" id="delivery-done-btn">Done</button>
      </div>
    </div>
  `;

  content.querySelector('#delivery-done-btn').addEventListener('click', () => {
    closeDeliveryModal();
    // Refresh the detail view to show delivery badge
    if (currentDetailOrder) {
      renderDetailView(currentDetailOrder, false);
    }
  });
}

/**
 * Render status step (for viewing existing delivery)
 */
function renderStatusStep(content) {
  const delivery = deliveryState.delivery;
  if (!delivery) return;

  const statusLabels = {
    'quote_pending': 'Getting quote...',
    'quoted': 'Quote ready',
    'pending': 'Finding driver...',
    'pickup': 'Driver en route to pickup',
    'pickup_complete': 'Package picked up',
    'dropoff': 'On the way to drop-off',
    'delivered': 'Delivered',
    'canceled': 'Canceled',
    'failed': 'Failed',
  };

  const statusClass = {
    'delivered': 'success',
    'canceled': 'error',
    'failed': 'error',
  }[delivery.status] || 'active';

  content.innerHTML = `
    <div class="delivery-step">
      <div class="step-title">Delivery Status</div>

      <div class="status-badge ${statusClass}">
        ${escapeHtml(statusLabels[delivery.status] || delivery.status)}
      </div>

      ${delivery.driver_name ? `
      <div class="driver-info">
        <div class="driver-name">${escapeHtml(delivery.driver_name)}</div>
        ${delivery.driver_phone ? `<div class="driver-phone">${escapeHtml(delivery.driver_phone)}</div>` : ''}
      </div>
      ` : ''}

      ${delivery.tracking_url ? `
      <a href="${sanitizeUrl(delivery.tracking_url)}" target="_blank" class="tracking-link">
        Track Delivery
        <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
          <path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/>
        </svg>
      </a>
      ` : ''}

      <div class="quote-details">
        <div class="quote-row">
          <span class="quote-label">Fee</span>
          <span class="quote-value">${escapeHtml(delivery.fee_display || 'N/A')}</span>
        </div>
        <div class="quote-row">
          <span class="quote-label">Drop-off</span>
          <span class="quote-value">${escapeHtml(delivery.dropoff_location_name)}</span>
        </div>
      </div>

      <div class="delivery-actions">
        ${delivery.status !== 'delivered' && delivery.status !== 'canceled' && delivery.status !== 'failed' ? `
        <button class="action-btn tertiary" id="delivery-cancel-btn">Cancel Delivery</button>
        ` : ''}
        <button class="action-btn primary" id="delivery-close-btn">Close</button>
      </div>
    </div>
  `;

  content.querySelector('#delivery-close-btn')?.addEventListener('click', closeDeliveryModal);

  content.querySelector('#delivery-cancel-btn')?.addEventListener('click', () => {
    if (confirm('Are you sure you want to cancel this delivery?')) {
      deliveryState.loading = true;
      renderDeliveryModal();
      window.parent.postMessage({
        type: 'SHOPQ_CANCEL_DELIVERY',
        delivery_id: delivery.id,
      }, '*');
    }
  });
}

/**
 * Show the list view (hide detail view)
 */
function showListView() {
  currentDetailCard = null;
  isEditingDate = false; // Reset date editing state
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
    console.error('Reclaim Returns: Failed to request orders:', error);
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
 * Validate YYYY-MM-DD date format
 */
function validateReturnDate(dateStr) {
  if (!dateStr) return { valid: false, error: 'Date is required' };

  // Check format
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
  if (!dateRegex.test(dateStr)) {
    return { valid: false, error: 'Invalid date format' };
  }

  // Check if parseable
  const date = new Date(dateStr + 'T00:00:00');
  if (isNaN(date.getTime())) {
    return { valid: false, error: 'Invalid date' };
  }

  // Warn if more than 365 days in future (probably a typo)
  const oneYearFromNow = new Date();
  oneYearFromNow.setFullYear(oneYearFromNow.getFullYear() + 1);
  if (date > oneYearFromNow) {
    return {
      valid: false,
      error: 'Return date is more than 1 year away. Please double-check.'
    };
  }

  return { valid: true };
}

/**
 * Update the return-by date for a specific order
 */
function updateOrderReturnDate(orderKey, returnByDate) {
  window.parent.postMessage({
    type: 'SHOPQ_UPDATE_ORDER_RETURN_DATE',
    order_key: orderKey,
    return_by_date: returnByDate
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
    console.error('Reclaim Returns: Failed to update status:', error);
  }
}

/**
 * Dismiss an order (mark as not a purchase / irrelevant)
 */
function dismissOrder(orderKey) {
  updateOrderStatus(orderKey, 'dismissed');
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
      startDateRefreshTimer();
    }
    renderListView();
  }

  // Handle returned orders data (for undo drawer)
  if (event.data?.type === 'SHOPQ_RETURNED_ORDERS_DATA') {
    returnedOrders = event.data.orders || [];
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
    console.log('Reclaim Returns: Scan complete', event.data);
    hasCompletedFirstScan = true;
    refreshBtn.classList.remove('scanning');
    refreshStatus.textContent = '';

    // Show toast with results
    const newCount = event.data.new_orders || 0;
    const processedCount = event.data.processed || 0;
    if (newCount > 0) {
      showToast(`Found ${newCount} new return${newCount === 1 ? '' : 's'}`, 'success');
    } else if (processedCount > 0) {
      showToast('Scan complete - no new returns found', 'info');
    } else {
      showToast('Scan complete', 'info');
    }

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

  // Handle order return date update confirmation
  if (event.data?.type === 'SHOPQ_ORDER_RETURN_DATE_UPDATED') {
    if (event.data.error) {
      // Show error but keep editing mode open so user can retry
      const errorEl = document.getElementById('date-error');
      const saveBtn = document.getElementById('save-date-btn');
      if (errorEl) {
        errorEl.textContent = event.data.error;
      } else {
        showToast('Failed to save: ' + event.data.error, 'error');
      }
      // Re-enable save button
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
      }
    } else {
      // Success - close editor and show confirmation
      isEditingDate = false;
      showToast('Return date updated', 'success');

      // Refresh to show updated date
      fetchReturns();
      if (currentDetailOrder && event.data.order_key === currentDetailOrder.order_key) {
        // Re-fetch the current order to get updated data
        window.parent.postMessage({
          type: 'SHOPQ_GET_ORDER',
          order_key: currentDetailOrder.order_key
        }, '*');
      }
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

  // =========================================================================
  // DELIVERY MODAL MESSAGE HANDLERS
  // =========================================================================

  // Handle user address response
  if (event.data?.type === 'SHOPQ_USER_ADDRESS') {
    if (deliveryModal) {
      deliveryState.address = event.data.address || null;
      deliveryState.loading = false;
      renderDeliveryModal();
    }
  }

  // Handle delivery locations response
  if (event.data?.type === 'SHOPQ_DELIVERY_LOCATIONS') {
    if (deliveryModal) {
      deliveryState.locations = event.data.locations || [];
      deliveryState.loading = false;
      renderDeliveryModal();
    }
  }

  // Handle delivery quote response
  if (event.data?.type === 'SHOPQ_DELIVERY_QUOTE') {
    if (deliveryModal) {
      if (event.data.error) {
        deliveryState.error = event.data.error;
        deliveryState.loading = false;
      } else {
        deliveryState.quote = event.data.quote;
        deliveryState.step = 'quote';
        deliveryState.loading = false;
      }
      renderDeliveryModal();
    }
  }

  // Handle delivery confirmation response
  if (event.data?.type === 'SHOPQ_DELIVERY_CONFIRMED') {
    if (deliveryModal) {
      if (event.data.error) {
        deliveryState.error = event.data.error;
        deliveryState.loading = false;
      } else {
        deliveryState.delivery = event.data.delivery;
        deliveryState.step = 'confirmed';
        deliveryState.loading = false;
      }
      renderDeliveryModal();
    }
  }

  // Handle delivery status response
  if (event.data?.type === 'SHOPQ_DELIVERY_STATUS') {
    if (deliveryModal) {
      deliveryState.delivery = event.data.delivery;
      deliveryState.step = 'status';
      deliveryState.loading = false;
      renderDeliveryModal();
    }
  }

  // Handle delivery cancel response
  if (event.data?.type === 'SHOPQ_DELIVERY_CANCELED') {
    if (deliveryModal) {
      deliveryState.loading = false;
      if (event.data.error) {
        deliveryState.error = event.data.error;
      } else {
        // Remove from active deliveries
        if (deliveryState.delivery) {
          delete activeDeliveries[deliveryState.delivery.order_key];
        }
        closeDeliveryModal();
        renderListView();
      }
      renderDeliveryModal();
    }
  }

  // Handle active deliveries response
  if (event.data?.type === 'SHOPQ_ACTIVE_DELIVERIES') {
    const deliveries = event.data.deliveries || [];
    activeDeliveries = {};
    for (const delivery of deliveries) {
      if (delivery.order_key) {
        activeDeliveries[delivery.order_key] = delivery;
      }
    }
    renderListView();
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

// Expired orders now shown in accordion at top of list

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Signal ready to parent
  window.parent.postMessage({ type: 'SHOPQ_RETURNS_SIDEBAR_READY' }, '*');

  // Fetch initial data
  fetchReturns();

  // Fetch returned orders for undo drawer
  window.parent.postMessage({ type: 'SHOPQ_GET_RETURNED_ORDERS' }, '*');

  // Fetch active deliveries
  window.parent.postMessage({ type: 'SHOPQ_GET_ACTIVE_DELIVERIES' }, '*');
});

// Refresh when tab becomes visible (user switches back to Gmail)
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && visibleOrders.length > 0) {
    renderListView();  // Refresh date displays
    fetchReturns();    // Also fetch fresh data
  }
});
