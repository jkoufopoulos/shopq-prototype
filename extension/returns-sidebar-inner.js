/**
 * ShopQ Return Watch Sidebar
 * Displays returnable purchases and their return windows
 */

// =============================================================================
// STATE
// =============================================================================

let currentReturns = [];
let currentDetailCard = null;

// =============================================================================
// DOM ELEMENTS
// =============================================================================

const listView = document.getElementById('list-view');
const detailView = document.getElementById('detail-view');
const backBtn = document.getElementById('back-btn');
const closeBtn = document.getElementById('close-btn');

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
function renderListView(returns) {
  if (!returns || returns.length === 0) {
    listView.innerHTML = `
      <div class="empty-state">
        <div class="icon">📦</div>
        <p><strong>No returns to track</strong></p>
        <p style="font-size: 13px;">When you make purchases, they'll appear here with their return deadlines.</p>
      </div>
    `;
    return;
  }

  // Group returns by urgency
  const expiringSoon = returns.filter(r => r.status === 'expiring_soon');
  const active = returns.filter(r => r.status === 'active');
  const other = returns.filter(r => !['active', 'expiring_soon'].includes(r.status));

  let html = '';

  // Expiring Soon section
  if (expiringSoon.length > 0) {
    html += `
      <div class="section">
        <div class="section-header urgent">Expiring Soon (${expiringSoon.length})</div>
        ${expiringSoon.map(r => renderReturnCard(r, true)).join('')}
      </div>
    `;
  }

  // Active section
  if (active.length > 0) {
    html += `
      <div class="section">
        <div class="section-header">Active Returns (${active.length})</div>
        ${active.map(r => renderReturnCard(r, false)).join('')}
      </div>
    `;
  }

  // Other (expired, returned, dismissed)
  if (other.length > 0) {
    html += `
      <div class="section">
        <div class="section-header">Past Returns (${other.length})</div>
        ${other.map(r => renderReturnCard(r, false)).join('')}
      </div>
    `;
  }

  listView.innerHTML = html;

  // Add click handlers to cards
  listView.querySelectorAll('.return-card').forEach(card => {
    card.addEventListener('click', () => {
      const returnId = card.dataset.id;
      const returnData = returns.find(r => r.id === returnId);
      if (returnData) {
        showDetailView(returnData);
      }
    });
  });
}

/**
 * Render a single return card
 */
function renderReturnCard(returnData, isUrgent) {
  const daysUntil = getDaysUntil(returnData.return_by_date);
  const isExpiring = daysUntil !== null && daysUntil <= 7 && daysUntil >= 0;
  const isCritical = daysUntil !== null && daysUntil <= 3 && daysUntil >= 0;

  let dateText = 'No deadline';
  let dateClass = '';
  if (returnData.return_by_date) {
    if (daysUntil < 0) {
      dateText = 'Expired';
      dateClass = 'urgent';
    } else if (daysUntil === 0) {
      dateText = 'Due today!';
      dateClass = 'urgent';
    } else if (daysUntil === 1) {
      dateText = 'Due tomorrow';
      dateClass = isUrgent ? 'urgent' : '';
    } else if (daysUntil <= 7) {
      dateText = `${daysUntil} days left`;
      dateClass = isUrgent ? 'urgent' : '';
    } else {
      dateText = `Due ${formatDate(returnData.return_by_date)}`;
    }
  }

  const statusBadge = getStatusBadge(returnData.status);
  const cardClass = isCritical ? 'critical' : (isExpiring ? 'expiring' : '');

  return `
    <div class="return-card ${cardClass}" data-id="${returnData.id}">
      <div class="card-header">
        <span class="merchant">${escapeHtml(returnData.merchant)}</span>
        ${statusBadge}
      </div>
      <div class="item-summary">${escapeHtml(returnData.item_summary)}</div>
      <div class="card-footer">
        <span class="return-date ${dateClass}">${dateText}</span>
        <span class="confidence">${returnData.confidence || 'unknown'}</span>
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
 * Show the detail view for a return card
 */
function showDetailView(returnData) {
  currentDetailCard = returnData;

  const daysUntil = getDaysUntil(returnData.return_by_date);
  let deadlineText = 'No deadline set';
  let deadlineClass = '';

  if (returnData.return_by_date) {
    const date = new Date(returnData.return_by_date);
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

  const amount = formatAmount(returnData.amount, returnData.currency);

  detailView.innerHTML = `
    <div class="detail-header">
      <div class="detail-merchant">${escapeHtml(returnData.merchant)}</div>
      <div class="detail-item">${escapeHtml(returnData.item_summary)}</div>
    </div>

    <div class="detail-section">
      <div class="detail-label">Return By</div>
      <div class="detail-value large ${deadlineClass}">${deadlineText}</div>
      <div style="font-size: 12px; color: #9aa0a6; margin-top: 4px;">
        Confidence: ${returnData.confidence || 'unknown'}
      </div>
    </div>

    ${amount ? `
    <div class="detail-section">
      <div class="detail-label">Purchase Amount</div>
      <div class="detail-value">${amount}</div>
    </div>
    ` : ''}

    ${returnData.order_number ? `
    <div class="detail-section">
      <div class="detail-label">Order Number</div>
      <div class="detail-value">${escapeHtml(returnData.order_number)}</div>
    </div>
    ` : ''}

    ${returnData.order_date ? `
    <div class="detail-section">
      <div class="detail-label">Order Date</div>
      <div class="detail-value">${new Date(returnData.order_date).toLocaleDateString()}</div>
    </div>
    ` : ''}

    ${returnData.delivery_date ? `
    <div class="detail-section">
      <div class="detail-label">Delivery Date</div>
      <div class="detail-value">${new Date(returnData.delivery_date).toLocaleDateString()}</div>
    </div>
    ` : ''}

    ${returnData.return_portal_link ? `
    <div class="detail-section">
      <div class="detail-label">Return Portal</div>
      <div class="detail-value">
        <a href="${escapeHtml(returnData.return_portal_link)}" target="_top">Start Return</a>
      </div>
    </div>
    ` : ''}

    ${returnData.shipping_tracking_link ? `
    <div class="detail-section">
      <div class="detail-label">Tracking</div>
      <div class="detail-value">
        <a href="${escapeHtml(returnData.shipping_tracking_link)}" target="_top">Track Package</a>
      </div>
    </div>
    ` : ''}

    ${returnData.status === 'active' || returnData.status === 'expiring_soon' ? `
    <div class="detail-actions">
      <button class="action-btn primary" id="mark-returned-btn">Mark Returned</button>
      <button class="action-btn secondary" id="dismiss-btn">Dismiss</button>
    </div>
    ` : ''}
  `;

  // Show detail view, hide list view
  listView.classList.add('hidden');
  detailView.classList.add('active');
  backBtn.classList.remove('hidden');

  // Add action handlers
  const markReturnedBtn = document.getElementById('mark-returned-btn');
  const dismissBtn = document.getElementById('dismiss-btn');

  if (markReturnedBtn) {
    markReturnedBtn.addEventListener('click', () => {
      updateReturnStatus(returnData.id, 'returned');
    });
  }

  if (dismissBtn) {
    dismissBtn.addEventListener('click', () => {
      updateReturnStatus(returnData.id, 'dismissed');
    });
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
    // Request returns data from parent window (content script)
    window.parent.postMessage({ type: 'SHOPQ_FETCH_RETURNS' }, '*');
  } catch (error) {
    console.error('ShopQ Returns: Failed to request returns:', error);
    renderError('Failed to load returns');
  }
}

/**
 * Update return status via API
 */
async function updateReturnStatus(returnId, newStatus) {
  try {
    window.parent.postMessage({
      type: 'SHOPQ_UPDATE_RETURN_STATUS',
      returnId,
      status: newStatus
    }, '*');

    // Optimistically update UI
    const returnData = currentReturns.find(r => r.id === returnId);
    if (returnData) {
      returnData.status = newStatus;
      showListView();
      renderListView(currentReturns);
    }
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
  // Handle returns data from parent
  if (event.data?.type === 'SHOPQ_RETURNS_DATA') {
    currentReturns = event.data.returns || [];
    renderListView(currentReturns);
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

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Signal ready to parent
  window.parent.postMessage({ type: 'SHOPQ_RETURNS_SIDEBAR_READY' }, '*');

  // Fetch initial data
  fetchReturns();
});
