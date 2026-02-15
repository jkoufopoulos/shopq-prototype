/**
 * returns-sidebar-delivery.js
 *
 * Delivery modal UI for scheduling return pickups via Uber.
 * 5-step wizard: address → locations → quote → confirmed → status.
 *
 * Dependencies (provided by returns-sidebar-inner.js, loaded first):
 *   - window.ReclaimSidebar  (namespace: state.deliveryState, state.deliveryModal, etc.)
 *   - escapeHtml()           (XSS-safe string interpolation)
 *   - sanitizeUrl()          (URL validation for tracking links)
 *   - renderDetailView()     (refresh detail view after delivery complete)
 *   - closeDeliveryModal()   is defined HERE, called by inner.js message handlers
 *
 * Load order in returns-sidebar.html:
 *   1. returns-sidebar-inner.js   (creates namespace + utilities)
 *   2. returns-sidebar-delivery.js (this file — defines delivery functions)
 */

// Shorthand alias for the namespace (available after inner.js loads)
const ReclaimSidebar = window.ReclaimSidebar;

// =============================================================================
// DELIVERY MODAL
// =============================================================================

/**
 * Show the delivery scheduling modal
 */
function showDeliveryModal(order) {
  // Reset delivery state
  ReclaimSidebar.state.deliveryState = {
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
  ReclaimSidebar.state.deliveryModal = document.createElement('div');
  ReclaimSidebar.state.deliveryModal.className = 'delivery-modal-overlay';
  ReclaimSidebar.state.deliveryModal.innerHTML = `
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

  document.body.appendChild(ReclaimSidebar.state.deliveryModal);

  // Close handlers
  ReclaimSidebar.state.deliveryModal.querySelector('.delivery-modal-close').addEventListener('click', closeDeliveryModal);
  ReclaimSidebar.state.deliveryModal.addEventListener('click', (e) => {
    if (e.target === ReclaimSidebar.state.deliveryModal) closeDeliveryModal();
  });

  // Check for saved address
  window.parent.postMessage({ type: 'RECLAIM_GET_USER_ADDRESS' }, '*');
}

/**
 * Close the delivery modal
 */
function closeDeliveryModal() {
  if (ReclaimSidebar.state.deliveryModal) {
    ReclaimSidebar.state.deliveryModal.remove();
    ReclaimSidebar.state.deliveryModal = null;
  }
}

/**
 * Show delivery status modal for an existing delivery
 */
function showDeliveryStatus(delivery) {
  ReclaimSidebar.state.deliveryState = {
    step: 'status',
    address: null,
    locations: [],
    selectedLocation: null,
    quote: null,
    delivery: delivery,
    loading: false,
    error: null,
  };

  ReclaimSidebar.state.deliveryModal = document.createElement('div');
  ReclaimSidebar.state.deliveryModal.className = 'delivery-modal-overlay';
  ReclaimSidebar.state.deliveryModal.innerHTML = `
    <div class="delivery-modal">
      <div class="delivery-modal-header">
        <h3>Delivery Status</h3>
        <button class="delivery-modal-close">&times;</button>
      </div>
      <div class="delivery-modal-content"></div>
    </div>
  `;

  document.body.appendChild(ReclaimSidebar.state.deliveryModal);

  ReclaimSidebar.state.deliveryModal.querySelector('.delivery-modal-close').addEventListener('click', closeDeliveryModal);
  ReclaimSidebar.state.deliveryModal.addEventListener('click', (e) => {
    if (e.target === ReclaimSidebar.state.deliveryModal) closeDeliveryModal();
  });

  renderDeliveryModal();
}

/**
 * Render the current delivery modal step
 */
function renderDeliveryModal() {
  if (!ReclaimSidebar.state.deliveryModal) return;

  const content = ReclaimSidebar.state.deliveryModal.querySelector('.delivery-modal-content');
  if (!content) return;

  if (ReclaimSidebar.state.deliveryState.loading) {
    content.innerHTML = `
      <div class="delivery-loading">
        <div class="spinner"></div>
        <div>${ReclaimSidebar.state.deliveryState.step === 'quote' ? 'Getting quote...' : 'Loading...'}</div>
      </div>
    `;
    return;
  }

  if (ReclaimSidebar.state.deliveryState.error) {
    content.innerHTML = `
      <div class="delivery-error">
        <div class="error-icon">⚠️</div>
        <div class="error-message">${escapeHtml(ReclaimSidebar.state.deliveryState.error)}</div>
        <button class="action-btn secondary" id="delivery-retry-btn">Try Again</button>
      </div>
    `;
    content.querySelector('#delivery-retry-btn')?.addEventListener('click', () => {
      ReclaimSidebar.state.deliveryState.error = null;
      ReclaimSidebar.state.deliveryState.step = 'address';
      renderDeliveryModal();
    });
    return;
  }

  switch (ReclaimSidebar.state.deliveryState.step) {
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
  const addr = ReclaimSidebar.state.deliveryState.address || {};

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

    ReclaimSidebar.state.deliveryState.address = {
      street,
      city,
      state,
      zip_code: zip,
      country: 'US',
    };

    // Save address for future use
    window.parent.postMessage({
      type: 'RECLAIM_SET_USER_ADDRESS',
      address: ReclaimSidebar.state.deliveryState.address,
    }, '*');

    // Fetch locations
    ReclaimSidebar.state.deliveryState.loading = true;
    ReclaimSidebar.state.deliveryState.step = 'locations';
    renderDeliveryModal();

    window.parent.postMessage({
      type: 'RECLAIM_GET_DELIVERY_LOCATIONS',
      address: ReclaimSidebar.state.deliveryState.address,
    }, '*');
  });
}

/**
 * Render carrier location selection step
 */
function renderLocationsStep(content) {
  if (ReclaimSidebar.state.deliveryState.locations.length === 0) {
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
      ReclaimSidebar.state.deliveryState.step = 'address';
      renderDeliveryModal();
    });
    return;
  }

  const locationCards = ReclaimSidebar.state.deliveryState.locations.map((loc, i) => `
    <div class="location-card ${ReclaimSidebar.state.deliveryState.selectedLocation?.id === loc.id ? 'selected' : ''}" data-index="${i}">
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
        <button class="action-btn primary" id="delivery-quote-btn" ${!ReclaimSidebar.state.deliveryState.selectedLocation ? 'disabled' : ''}>
          Get Quote
        </button>
      </div>
    </div>
  `;

  // Location selection handlers
  content.querySelectorAll('.location-card').forEach(card => {
    card.addEventListener('click', () => {
      const index = parseInt(card.dataset.index);
      ReclaimSidebar.state.deliveryState.selectedLocation = ReclaimSidebar.state.deliveryState.locations[index];
      renderDeliveryModal();
    });
  });

  content.querySelector('#delivery-back-btn').addEventListener('click', () => {
    ReclaimSidebar.state.deliveryState.step = 'address';
    renderDeliveryModal();
  });

  content.querySelector('#delivery-quote-btn').addEventListener('click', () => {
    if (!ReclaimSidebar.state.deliveryState.selectedLocation) return;

    ReclaimSidebar.state.deliveryState.loading = true;
    renderDeliveryModal();

    window.parent.postMessage({
      type: 'RECLAIM_GET_DELIVERY_QUOTE',
      order_key: ReclaimSidebar.state.currentDetailOrder.order_key,
      pickup_address: ReclaimSidebar.state.deliveryState.address,
      dropoff_location_id: ReclaimSidebar.state.deliveryState.selectedLocation.id,
    }, '*');
  });
}

/**
 * Render quote confirmation step
 */
function renderQuoteStep(content) {
  const quote = ReclaimSidebar.state.deliveryState.quote;
  if (!quote) {
    ReclaimSidebar.state.deliveryState.error = 'Failed to get quote';
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
          <span class="quote-value">${escapeHtml(ReclaimSidebar.state.deliveryState.address.street)}</span>
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
    ReclaimSidebar.state.deliveryState.step = 'locations';
    ReclaimSidebar.state.deliveryState.quote = null;
    renderDeliveryModal();
  });

  content.querySelector('#delivery-confirm-btn').addEventListener('click', () => {
    ReclaimSidebar.state.deliveryState.loading = true;
    renderDeliveryModal();

    window.parent.postMessage({
      type: 'RECLAIM_CONFIRM_DELIVERY',
      delivery_id: quote.delivery_id,
    }, '*');
  });
}

/**
 * Render confirmed step
 */
function renderConfirmedStep(content) {
  const delivery = ReclaimSidebar.state.deliveryState.delivery;

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
    if (ReclaimSidebar.state.currentDetailOrder) {
      renderDetailView(ReclaimSidebar.state.currentDetailOrder, false);
    }
  });
}

/**
 * Render status step (for viewing existing delivery)
 */
function renderStatusStep(content) {
  const delivery = ReclaimSidebar.state.deliveryState.delivery;
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
      ReclaimSidebar.state.deliveryState.loading = true;
      renderDeliveryModal();
      window.parent.postMessage({
        type: 'RECLAIM_CANCEL_DELIVERY',
        delivery_id: delivery.id,
      }, '*');
    }
  });
}
