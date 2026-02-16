/**
 * Reclaim Sidebar
 * Displays returnable purchases and their return windows
 *
 * Uses GET_VISIBLE_ORDERS for a unified purchase list sorted by urgency.
 * Triggers ENRICH_ORDER on detail view open.
 * Supports SET_MERCHANT_RULE for unknown deadlines.
 */

// =============================================================================
// NAMESPACE — all mutable state and overridable config live here.
// Enables future file splits (extracted modules access window.ReclaimSidebar).
// =============================================================================

window.ReclaimSidebar = {
  config: {
    DATE_REFRESH_INTERVAL_MS: 60000,
    TOAST_DURATION_MS: 3000,
    TOAST_FADEOUT_MS: 300,
    EXPIRING_SOON_DAYS: 7,
    CRITICAL_DAYS: 3,
  },
  state: {
    visibleOrders: [],
    returnedOrders: [],
    currentDetailOrder: null,
    isEnriching: false,
    hasCompletedFirstScan: false,
    demoMode: false,
    expiredAccordionOpen: false,
    returnedAccordionOpen: false,
    isEditingDate: false,
  },
  timers: {
    dateRefreshInterval: null,
  },
};


// =============================================================================
// DEMO MODE — masks PII (order IDs) for screen recordings
// Toggle via DevTools console in the sidebar iframe: toggleDemoMode()
// =============================================================================

const _demoMaskCache = new Map();

function maskOrderId(value) {
  if (!value) return value;
  if (_demoMaskCache.has(value)) return _demoMaskCache.get(value);
  const masked = value.replace(/[A-Za-z0-9]/g, (ch) => {
    if (ch >= '0' && ch <= '9') return String(Math.floor(Math.random() * 10));
    const base = ch >= 'a' ? 'a'.charCodeAt(0) : 'A'.charCodeAt(0);
    return String.fromCharCode(base + Math.floor(Math.random() * 26));
  });
  _demoMaskCache.set(value, masked);
  return masked;
}

window.toggleDemoMode = function () {
  ReclaimSidebar.state.demoMode = !ReclaimSidebar.state.demoMode;
  ReclaimSidebar.state.currentDetailOrder = null;
  _demoMaskCache.clear();
  renderListView();
  console.log(
    `%c[Reclaim] Demo mode ${ReclaimSidebar.state.demoMode ? 'ON — order IDs masked' : 'OFF — real data'}`,
    'color: #7c3aed; font-weight: bold'
  );
};

function startDateRefreshTimer() {
  if (ReclaimSidebar.timers.dateRefreshInterval) return;
  ReclaimSidebar.timers.dateRefreshInterval = setInterval(() => {
    if (ReclaimSidebar.state.visibleOrders.length > 0) {
      renderListView();
    }
  }, ReclaimSidebar.config.DATE_REFRESH_INTERVAL_MS);
}

function stopDateRefreshTimer() {
  if (ReclaimSidebar.timers.dateRefreshInterval) {
    clearInterval(ReclaimSidebar.timers.dateRefreshInterval);
    ReclaimSidebar.timers.dateRefreshInterval = null;
  }
}

// =============================================================================
// THEME TOGGLE
// =============================================================================

async function updateThemeToggle() {
  const btn = document.getElementById('theme-toggle-btn');
  if (!btn) return;
  const state = await getThemeToggleState();
  btn.innerHTML = state.icon;
  btn.title = state.label;
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
function showToast(message, type = 'info', duration = ReclaimSidebar.config.TOAST_DURATION_MS) {
  // Remove any existing toast
  const existing = document.querySelector('.toast-notification');
  if (existing) existing.remove();

  const TOAST_ICONS = {
    success: '<svg viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="currentColor" opacity="0.12"/><path d="M5.5 9.5L7.5 11.5L12.5 6.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    error: '<svg viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="currentColor" opacity="0.12"/><path d="M6.5 6.5L11.5 11.5M11.5 6.5L6.5 11.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    info: '<svg viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="currentColor" opacity="0.12"/><path d="M9 8V12M9 6.5V6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  };

  const toast = document.createElement('div');
  toast.className = `toast-notification toast-${type}`;

  const icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.innerHTML = TOAST_ICONS[type] || TOAST_ICONS.info;

  const msg = document.createElement('span');
  msg.className = 'toast-message';
  msg.textContent = message;

  toast.appendChild(icon);
  toast.appendChild(msg);
  document.body.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  // Auto-dismiss
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), ReclaimSidebar.config.TOAST_FADEOUT_MS);
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
  if (diffDays <= ReclaimSidebar.config.EXPIRING_SOON_DAYS) return `${diffDays} days`;

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

// =============================================================================
// RENDERING
// =============================================================================

/**
 * Separate orders into active and expired
 */
function getOrdersByStatus() {
  const active = [];
  const expired = [];

  for (const order of ReclaimSidebar.state.visibleOrders) {
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
  ReclaimSidebar.state.expiredAccordionOpen = !ReclaimSidebar.state.expiredAccordionOpen;
  renderListView();
}

/**
 * Toggle returned accordion
 */
function toggleReturnedAccordion() {
  ReclaimSidebar.state.returnedAccordionOpen = !ReclaimSidebar.state.returnedAccordionOpen;
  renderListView();
}

/**
 * Undo marking an order as returned (set back to active)
 */
function undoReturnOrder(orderKey) {
  window.parent.postMessage({
    type: 'RECLAIM_UPDATE_ORDER_STATUS',
    order_key: orderKey,
    status: 'active'
  }, '*');
  showToast('Moved back to active returns', 'success');

  // Refresh both lists to update UI immediately
  fetchReturns();
  window.parent.postMessage({ type: 'RECLAIM_GET_RETURNED_ORDERS' }, '*');
}

/**
 * Render the returns list view — active orders + expired accordion
 */
function renderListView() {
  const { active, expired } = getOrdersByStatus();

  // Empty state - no orders at all
  if (ReclaimSidebar.state.visibleOrders.length === 0) {
    if (!ReclaimSidebar.state.hasCompletedFirstScan) {
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
  if (ReclaimSidebar.state.returnedOrders.length > 0) {
    const chevronIcon = ReclaimSidebar.state.returnedAccordionOpen
      ? `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>`;

    html += `
      <div class="returned-accordion">
        <button class="returned-accordion-header" id="returned-accordion-toggle">
          <span class="returned-accordion-title">
            <span class="returned-icon">✓</span>
            Returned (${ReclaimSidebar.state.returnedOrders.length})
          </span>
          ${chevronIcon}
        </button>
        ${ReclaimSidebar.state.returnedAccordionOpen ? `
          <div class="returned-accordion-content">
            ${ReclaimSidebar.state.returnedOrders.map(o => renderOrderCard(o, true)).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }

  // Render expired accordion if there are expired orders
  if (expired.length > 0) {
    const chevronIcon = ReclaimSidebar.state.expiredAccordionOpen
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
        ${ReclaimSidebar.state.expiredAccordionOpen ? `
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
  } else if (expired.length > 0 || ReclaimSidebar.state.returnedOrders.length > 0) {
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
      // Don't navigate if clicking dismiss or undo button
      if (e.target.closest('.dismiss-btn') || e.target.closest('.undo-btn')) return;
      const orderKey = card.dataset.id;
      const isReturned = card.dataset.returned === 'true';

      // Find order in appropriate list
      let order = ReclaimSidebar.state.visibleOrders.find(o => o.order_key === orderKey);
      if (!order && isReturned) {
        order = ReclaimSidebar.state.returnedOrders.find(o => o.order_key === orderKey);
      }

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

}

/**
 * Render a single order card — urgency always derived from days remaining
 * @param {Object} order - The order object
 * @param {boolean} isReturned - Whether this is a returned order (shows undo button)
 */
function renderOrderCard(order, isReturned = false) {
  const daysUntil = getDaysUntil(order.return_by_date);
  const isExpiring = daysUntil !== null && daysUntil <= ReclaimSidebar.config.EXPIRING_SOON_DAYS && daysUntil >= 0;
  const isCritical = daysUntil !== null && daysUntil <= ReclaimSidebar.config.CRITICAL_DAYS && daysUntil >= 0;
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
    } else if (daysUntil <= ReclaimSidebar.config.CRITICAL_DAYS) {
      dateText = `${daysUntil} day${daysUntil === 1 ? '' : 's'} left`;
      dateClass = 'urgent';
      urgentBadge = `<span class="urgent-badge critical"><span class="dot"></span>${daysUntil} day${daysUntil === 1 ? '' : 's'}</span>`;
    } else if (daysUntil <= ReclaimSidebar.config.EXPIRING_SOON_DAYS) {
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

  // Icons for buttons
  const trashIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>`;
  const undoIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z"/></svg>`;

  // For returned orders, show both undo and dismiss buttons; otherwise just dismiss
  const actionButtons = isReturned
    ? `<button class="undo-btn" data-id="${escapeHtml(order.order_key)}" title="Undo - move back to active">${undoIcon}</button>
       <button class="dismiss-btn" data-id="${escapeHtml(order.order_key)}" title="Delete">${trashIcon}</button>`
    : `<button class="dismiss-btn" data-id="${escapeHtml(order.order_key)}" title="Not a purchase / Dismiss">${trashIcon}</button>`;

  // For returned orders, show "Returned" badge
  const statusBadge = isReturned ? '<span class="returned-badge">Returned</span>' : '';

  return `
    <div class="return-card ${cardClass} ${isReturned ? 'returned' : ''}" data-id="${escapeHtml(order.order_key)}" data-returned="${isReturned}">
      <div class="card-header">
        <span class="merchant">${escapeHtml(order.merchant_display_name)}</span>
        ${statusBadge || urgentBadge}
      </div>
      <div class="item-summary">${escapeHtml(order.item_summary)}</div>
      <div class="card-footer">
        <span class="return-date ${dateClass}">${dateText}</span>
        <div class="card-actions">${actionButtons}</div>
      </div>
    </div>
  `;
}

/**
 * Show the detail view for an order (v0.6.2 Order model)
 */
function showDetailView(order) {
  ReclaimSidebar.state.currentDetailOrder = order;

  // Check if enrichment needed
  const needsEnrichment = order.deadline_confidence === 'unknown' || !order.return_by_date;

  // Trigger enrichment if needed
  if (needsEnrichment && !ReclaimSidebar.state.isEnriching) {
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
  if (!ReclaimSidebar.state.currentDetailOrder) return;

  const enrichSection = document.getElementById('enrich-section');
  if (enrichSection) {
    enrichSection.innerHTML = `
      <div class="enrich-section enrich-section--loading">
        <div class="spinner" style="margin: 0 auto 8px;"></div>
        <div class="enrich-text">Checking return policy...</div>
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
        deadlineClass = daysUntil <= ReclaimSidebar.config.CRITICAL_DAYS ? 'urgent' : '';
      } else {
        daysLeftText = `(${daysUntil} days left)`;
        deadlineClass = daysUntil <= ReclaimSidebar.config.CRITICAL_DAYS ? 'urgent' : '';
      }
    }
  }

  // Icons
  const externalLinkIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>`;
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
  const dateEditSection = ReclaimSidebar.state.isEditingDate ? `
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
          <span class="order-info-value">${escapeHtml(ReclaimSidebar.state.demoMode ? maskOrderId(order.order_id) : order.order_id)}</span>
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
  if (needsEnrichment && !ReclaimSidebar.state.isEditingDate) {
    if (ReclaimSidebar.state.isEnriching) {
      enrichSection = `
        <div id="enrich-section" class="enrich-section enrich-section--loading">
          <div class="spinner" style="margin: 0 auto 8px;"></div>
          <div class="enrich-text">Checking return policy...</div>
        </div>
      `;
    } else {
      enrichSection = `
        <div id="enrich-section" class="enrich-section enrich-section--not-found">
          <div class="enrich-text">No return deadline found</div>
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
      <button class="action-btn secondary" id="mark-returned-btn">
        Mark as Returned
      </button>
      <button class="action-btn tertiary" id="dismiss-order-btn">
        Dismiss (Not an Order)
      </button>
    </div>
    ` : ''}
    ${order.order_status === 'returned' ? `
    <div class="detail-actions">
      <button class="action-btn secondary" id="mark-active-btn">
        Mark as Active
      </button>
    </div>
    ` : ''}
  `;

  // Add action handlers
  const markReturnedBtn = document.getElementById('mark-returned-btn');
  const markActiveBtn = document.getElementById('mark-active-btn');
  const setRuleBtn = document.getElementById('set-rule-btn');
  const dismissOrderBtn = document.getElementById('dismiss-order-btn');

  // Date editing handlers
  const editDateBtn = document.getElementById('edit-date-btn');
  const saveDateBtn = document.getElementById('save-date-btn');
  const cancelDateBtn = document.getElementById('cancel-date-btn');

  if (editDateBtn) {
    editDateBtn.addEventListener('click', () => {
      ReclaimSidebar.state.isEditingDate = true;
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
      ReclaimSidebar.state.isEditingDate = false;
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

  if (markActiveBtn) {
    markActiveBtn.addEventListener('click', () => {
      updateOrderStatus(order.order_key, 'active');
      showToast('Moved back to active returns', 'success');
      // Also refresh returned orders list
      window.parent.postMessage({ type: 'RECLAIM_GET_RETURNED_ORDERS' }, '*');
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

// Delivery modal functions: see returns-sidebar-delivery.js
// (loaded after this file via <script> tag in returns-sidebar.html)

/**
 * Show the list view (hide detail view)
 */
function showListView() {
  ReclaimSidebar.state.currentDetailOrder = null;
  ReclaimSidebar.state.isEditingDate = false; // Reset date editing state
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
    window.parent.postMessage({ type: 'RECLAIM_GET_ORDERS' }, '*');
  } catch (error) {
    console.error('Reclaim Returns: Failed to request orders:', error);
    renderError('Failed to load returns');
  }
}

/**
 * Trigger enrichment for an order
 */
async function enrichOrder(orderKey) {
  ReclaimSidebar.state.isEnriching = true;
  renderEnrichingState();
  window.parent.postMessage({ type: 'RECLAIM_ENRICH_ORDER', order_key: orderKey }, '*');
}

/**
 * Set merchant return window rule
 */
async function setMerchantRule(merchantDomain, windowDays) {
  window.parent.postMessage({
    type: 'RECLAIM_SET_MERCHANT_RULE',
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
    type: 'RECLAIM_UPDATE_ORDER_RETURN_DATE',
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
      type: 'RECLAIM_UPDATE_ORDER_STATUS',
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
  showToast('Order dismissed', 'success');
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
      <button id="retry-btn" class="retry-btn">Retry</button>
    </div>
  `;

  document.getElementById('retry-btn')?.addEventListener('click', () => {
    window.parent.postMessage({ type: 'RECLAIM_RELOAD_PAGE' }, '*');
  });
}

// =============================================================================
// MESSAGE HANDLING
// =============================================================================

// SEC: Expected parent origin — set from config init or derived from document.referrer
let _trustedParentOrigin = null;

window.addEventListener('message', (event) => {
  // SEC: Only accept messages from Gmail (where our content script runs).
  // First message sets the trusted origin; subsequent messages must match.
  const origin = event.origin;
  if (origin !== 'https://mail.google.com') {
    return;
  }
  if (!_trustedParentOrigin) {
    _trustedParentOrigin = origin;
  }

  // Receive config from parent (content script) — overrides defaults
  if (event.data?.type === 'RECLAIM_CONFIG_INIT') {
    const c = event.data.config || {};
    if (c.DATE_REFRESH_INTERVAL_MS) ReclaimSidebar.config.DATE_REFRESH_INTERVAL_MS = c.DATE_REFRESH_INTERVAL_MS;
    if (c.TOAST_DURATION_MS) ReclaimSidebar.config.TOAST_DURATION_MS = c.TOAST_DURATION_MS;
    if (c.TOAST_FADEOUT_MS) ReclaimSidebar.config.TOAST_FADEOUT_MS = c.TOAST_FADEOUT_MS;
    if (c.EXPIRING_SOON_DAYS) ReclaimSidebar.config.EXPIRING_SOON_DAYS = c.EXPIRING_SOON_DAYS;
    if (c.CRITICAL_DAYS) ReclaimSidebar.config.CRITICAL_DAYS = c.CRITICAL_DAYS;
  }

  // Handle unified visible orders
  if (event.data?.type === 'RECLAIM_ORDERS_DATA') {
    ReclaimSidebar.state.visibleOrders = event.data.orders || [];
    if (ReclaimSidebar.state.visibleOrders.length > 0) {
      ReclaimSidebar.state.hasCompletedFirstScan = true;
      startDateRefreshTimer();
    }
    renderListView();
  }

  // Handle returned orders data (for undo drawer)
  if (event.data?.type === 'RECLAIM_RETURNED_ORDERS_DATA') {
    ReclaimSidebar.state.returnedOrders = event.data.orders || [];
    renderListView();
  }

  // Handle API error
  if (event.data?.type === 'RECLAIM_RETURNS_ERROR') {
    renderError(event.data.message || 'Unknown error');
  }

  // Handle status update confirmation
  if (event.data?.type === 'RECLAIM_STATUS_UPDATED') {
    // Refresh the list
    fetchReturns();
  }

  // Handle scan progress updates
  if (event.data?.type === 'RECLAIM_SCAN_PROGRESS') {
    const { checked, processed, found, pending } = event.data;
    let progressText = 'Scanning...';
    if (typeof checked === 'number' && typeof found === 'number') {
      progressText = `Scanning... checked ${checked} emails, found ${found} purchase${found === 1 ? '' : 's'}`;
    } else if (typeof pending === 'number') {
      progressText = `Processing ${pending} email${pending === 1 ? '' : 's'}...`;
    }
    refreshStatus.textContent = progressText;
    if (!refreshBtn.classList.contains('scanning')) {
      refreshBtn.classList.add('scanning');
    }
  }

  // Handle scan complete notification
  if (event.data?.type === 'RECLAIM_SCAN_COMPLETE') {
    console.log('Reclaim Returns: Scan complete', event.data);
    ReclaimSidebar.state.hasCompletedFirstScan = true;
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
  if (event.data?.type === 'RECLAIM_ENRICH_RESULT') {
    ReclaimSidebar.state.isEnriching = false;
    if (event.data.order && ReclaimSidebar.state.currentDetailOrder) {
      // Update with enriched order data
      ReclaimSidebar.state.currentDetailOrder = event.data.order;
      renderDetailView(event.data.order, event.data.state === 'not_found');
    }
  }

  // Handle merchant rule set confirmation
  if (event.data?.type === 'RECLAIM_MERCHANT_RULE_SET') {
    // Refresh to show updated deadlines
    fetchReturns();
    if (ReclaimSidebar.state.currentDetailOrder) {
      // Re-fetch the current order
      window.parent.postMessage({
        type: 'RECLAIM_GET_ORDER',
        order_key: ReclaimSidebar.state.currentDetailOrder.order_key
      }, '*');
    }
  }

  // Handle order return date update confirmation
  if (event.data?.type === 'RECLAIM_ORDER_RETURN_DATE_UPDATED') {
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
      ReclaimSidebar.state.isEditingDate = false;
      showToast('Return date updated', 'success');

      // Refresh to show updated date
      fetchReturns();
      if (ReclaimSidebar.state.currentDetailOrder && event.data.order_key === ReclaimSidebar.state.currentDetailOrder.order_key) {
        // Re-fetch the current order to get updated data
        window.parent.postMessage({
          type: 'RECLAIM_GET_ORDER',
          order_key: ReclaimSidebar.state.currentDetailOrder.order_key
        }, '*');
      }
    }
  }

  // Handle order data (for refreshing detail view)
  if (event.data?.type === 'RECLAIM_ORDER_DATA') {
    if (event.data.order && ReclaimSidebar.state.currentDetailOrder &&
        event.data.order.order_key === ReclaimSidebar.state.currentDetailOrder.order_key) {
      ReclaimSidebar.state.currentDetailOrder = event.data.order;
      renderDetailView(event.data.order, !event.data.order.return_by_date);
    }
  }

});

// =============================================================================
// EVENT HANDLERS
// =============================================================================

// Close button
closeBtn.addEventListener('click', () => {
  window.parent.postMessage({ type: 'RECLAIM_CLOSE_SIDEBAR' }, '*');
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
  window.parent.postMessage({ type: 'RECLAIM_RESCAN_EMAILS' }, '*');
});

// Expired orders now shown in accordion at top of list

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  // Initialize theme before rendering
  await initTheme();
  updateThemeToggle();

  // Theme toggle handler
  const themeToggleBtn = document.getElementById('theme-toggle-btn');
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', async () => {
      await cycleTheme();
      updateThemeToggle();
    });
  }

  // Signal ready to parent
  window.parent.postMessage({ type: 'RECLAIM_RETURNS_SIDEBAR_READY' }, '*');

  // Fetch initial data
  fetchReturns();

  // Fetch returned orders for undo drawer
  window.parent.postMessage({ type: 'RECLAIM_GET_RETURNED_ORDERS' }, '*');
});

// Refresh when tab becomes visible (user switches back to Gmail)
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && ReclaimSidebar.state.visibleOrders.length > 0) {
    renderListView();  // Refresh date displays
    fetchReturns();    // Also fetch fresh data
  }
});

// Clean up intervals when iframe is about to be destroyed (Gmail navigation)
window.addEventListener('beforeunload', () => {
  stopDateRefreshTimer();
});
