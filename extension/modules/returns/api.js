/**
 * Reclaim Returns API Client
 * Handles communication with the backend API for extraction operations.
 *
 * Note: This file is loaded via importScripts in the service worker.
 * getAuthToken is available globally from auth.js which is loaded first.
 */

// API URL from centralized config (loaded via importScripts before this file)
const API_BASE_URL = CONFIG.API_BASE_URL;

/**
 * SEC-014: Validate that response came from expected API origin
 * Prevents MITM attacks where responses could be intercepted and modified
 * @param {Response} response - Fetch response object
 * @throws {Error} If response origin doesn't match expected API
 */
function validateResponseOrigin(response) {
  const responseUrl = new URL(response.url);
  const expectedUrl = new URL(API_BASE_URL);

  if (responseUrl.origin !== expectedUrl.origin) {
    console.error(`SEC-014: Response origin mismatch. Expected ${expectedUrl.origin}, got ${responseUrl.origin}`);
    throw new Error('Response origin validation failed - possible security issue');
  }
}

/**
 * Get headers with authentication token
 * @returns {Promise<Object>} Headers object with Authorization
 */
async function getAuthHeaders() {
  const token = await getAuthToken();
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };
}

/**
 * Process a batch of emails through the stateless extraction pipeline.
 * Sends all emails in one request for cross-email dedup and cancellation suppression.
 * No data is persisted on the server — results are returned as JSON.
 *
 * @param {Array<{email_id: string, from_address: string, subject: string, body: string, body_html?: string, received_at?: string}>} emails
 * @returns {Promise<{results: Array<{email_id: string, success: boolean, card?: Object, rejection_reason?: string}>, stats: Object}>}
 */
async function processEmailBatch(emails) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/extract`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ emails }),
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to extract email batch: ${response.status} ${errorText}`);
  }

  const data = await response.json();

  // Adapt response format: extract successful cards into a flat list
  // for backward compatibility with scanner.js expectations
  const cards = data.results
    .filter(r => r.success && r.card)
    .map(r => r.card);

  return {
    success: true,
    cards,
    stats: {
      total: data.stats.total,
      rejected_filter: data.stats.rejected_filter,
      rejected_classifier: data.stats.rejected_classifier,
      rejected_empty: data.stats.rejected_empty,
      cards_created: data.stats.cards_extracted,
      cards_merged: 0,
    },
  };
}

// ============================================================
// DELIVERY API (Uber Direct Integration)
// ============================================================

/**
 * Get carrier locations (UPS/FedEx drop-off points)
 * @param {Object} [options]
 * @param {number} [options.lat] - User latitude for distance sorting
 * @param {number} [options.lng] - User longitude for distance sorting
 * @param {string} [options.carrier] - Filter by carrier ("UPS" or "FedEx")
 * @param {number} [options.limit=10] - Max locations to return
 * @returns {Promise<{locations: Array}>}
 */
async function fetchDeliveryLocations(options = {}) {
  const headers = await getAuthHeaders();

  const params = new URLSearchParams();
  if (options.lat != null) params.append('lat', options.lat);
  if (options.lng != null) params.append('lng', options.lng);
  if (options.carrier) params.append('carrier', options.carrier);
  if (options.limit) params.append('limit', options.limit);

  const queryString = params.toString() ? `?${params.toString()}` : '';
  const response = await fetch(`${API_BASE_URL}/api/delivery/locations${queryString}`, {
    method: 'GET',
    headers,
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch delivery locations: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Request a delivery quote
 * @param {Object} quoteData
 * @param {string} quoteData.order_key - Return card ID
 * @param {Object} quoteData.pickup_address - User's pickup address
 * @param {string} quoteData.dropoff_location_id - Carrier location ID
 * @returns {Promise<{delivery_id: string, quote_id: string, fee_cents: number, fee_display: string, ...}>}
 */
async function requestDeliveryQuote(quoteData) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/delivery/quote`, {
    method: 'POST',
    headers,
    body: JSON.stringify(quoteData),
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to get delivery quote: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Confirm a delivery quote and dispatch driver
 * @param {string} deliveryId - Delivery ID from quote response
 * @returns {Promise<{id: string, status: string, tracking_url?: string, ...}>}
 */
async function confirmDelivery(deliveryId) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/delivery/confirm`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ delivery_id: deliveryId }),
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to confirm delivery: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Get delivery status
 * @param {string} deliveryId - Delivery ID
 * @returns {Promise<{id: string, status: string, driver_name?: string, tracking_url?: string, ...}>}
 */
async function getDeliveryStatus(deliveryId) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/delivery/${encodeURIComponent(deliveryId)}`, {
    method: 'GET',
    headers,
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to get delivery status: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Get delivery for a specific return card
 * @param {string} orderKey - Return card ID
 * @returns {Promise<{id: string, status: string, ...}|null>}
 */
async function getDeliveryForOrder(orderKey) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/delivery/order/${encodeURIComponent(orderKey)}`, {
    method: 'GET',
    headers,
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    const errorText = await response.text();
    throw new Error(`Failed to get delivery for order: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Cancel a pending delivery
 * @param {string} deliveryId - Delivery ID
 * @returns {Promise<{success: boolean, message: string}>}
 */
async function cancelDelivery(deliveryId) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/delivery/${encodeURIComponent(deliveryId)}/cancel`, {
    method: 'POST',
    headers,
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to cancel delivery: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * List all active deliveries for the user
 * @returns {Promise<Array<{id: string, status: string, ...}>>}
 */
async function fetchActiveDeliveries() {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/delivery/active`, {
    method: 'GET',
    headers,
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch active deliveries: ${response.status} ${errorText}`);
  }

  return response.json();
}
