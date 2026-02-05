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
let deliveryModal = null;
let activeDeliveries = {}; // Map of order_key -> delivery object
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
  const infoIcon = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>`;

  // Build confidence badge
  const confidenceBadge = `
    <div class="confidence-badge">
      ${infoIcon}
      <span>Confidence: <strong>${order.deadline_confidence || 'unknown'}</strong></span>
      <span class="edit-link" id="edit-deadline-btn">Edit</span>
    </div>
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
  if (needsEnrichment) {
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
      <div class="detail-value large ${deadlineClass}">
        ${deadlineDate}${daysLeftText ? `<span class="days-left">${daysLeftText}</span>` : ''}
      </div>
      ${confidenceBadge}
    </div>

    ${enrichSection}
    ${orderInfoCard}

    ${order.order_status === 'active' ? `
    <div class="detail-actions">
      <button class="action-btn primary" id="deliver-carrier-btn">
        ${truckIcon}
        Schedule Delivery
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
  const editDeadlineBtn = document.getElementById('edit-deadline-btn');

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

  if (deliverCarrierBtn) {
    deliverCarrierBtn.addEventListener('click', () => {
      showDeliveryModal(order);
    });
  }

  if (editDeadlineBtn) {
    editDeadlineBtn.addEventListener('click', () => {
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

  // Fetch active deliveries
  window.parent.postMessage({ type: 'SHOPQ_GET_ACTIVE_DELIVERIES' }, '*');
});
