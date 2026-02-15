/**
 * Reclaim Returns API Client
 * Handles communication with the backend API for return card operations
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
 * Fetch all returns for the current user
 */
async function fetchReturns(options = {}) {
  const { status } = options;

  let url = `${API_BASE_URL}/api/returns`;
  if (status) {
    url += `?status=${encodeURIComponent(status)}`;
  }

  const headers = await getAuthHeaders();
  const response = await fetch(url, {
    method: 'GET',
    headers,
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch returns: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Fetch returns that are expiring soon
 */
async function fetchExpiringReturns(withinDays = 7) {
  const headers = await getAuthHeaders();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/expiring?threshold_days=${withinDays}`,
    {
      method: 'GET',
      headers,
    }
  );

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch expiring returns: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Get return card counts by status
 */
async function getReturnCounts() {
  const headers = await getAuthHeaders();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/counts`,
    {
      method: 'GET',
      headers,
    }
  );

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch return counts: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Update the status of a return card
 */
async function updateReturnStatus(returnId, newStatus) {
  const headers = await getAuthHeaders();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/${encodeURIComponent(returnId)}/status`,
    {
      method: 'PUT',
      headers,
      body: JSON.stringify({ status: newStatus }),
    }
  );

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to update return status: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Create a new return card
 */
async function createReturn(returnData) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/returns`, {
    method: 'POST',
    headers,
    body: JSON.stringify(returnData),
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to create return: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Process an email through the extraction pipeline
 */
async function processEmail(emailData) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/returns/process`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      email_id: emailData.id,
      from_address: emailData.from,
      subject: emailData.subject,
      body: emailData.body,
    }),
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to process email: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Process a batch of emails through the extraction pipeline.
 * Sends all emails in one request for cross-email dedup and cancellation suppression.
 *
 * @param {Array<{email_id: string, from_address: string, subject: string, body: string, body_html?: string, received_at?: string}>} emails
 * @param {Object} [options]
 * @param {boolean} [options.skipPersistence=false] - Skip DB save/dedup (for testing)
 * @returns {Promise<{success: boolean, cards: Array, stats: Object}>}
 */
async function processEmailBatch(emails, options = {}) {
  const headers = await getAuthHeaders();
  const params = options.skipPersistence ? '?skip_persistence=true' : '';

  const response = await fetch(`${API_BASE_URL}/api/returns/process-batch${params}`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ emails }),
  });

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to process email batch: ${response.status} ${errorText}`);
  }

  return response.json();
}

/**
 * Refresh statuses (update expiring_soon based on current date)
 */
async function refreshStatuses() {
  const headers = await getAuthHeaders();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/refresh-statuses`,
    {
      method: 'POST',
      headers,
    }
  );

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to refresh statuses: ${response.status} ${errorText}`);
  }

  return response.json();
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

/**
 * Update the return-by date for a specific order
 * @param {string} orderKey - The order/return card ID
 * @param {string} returnByDate - The new return-by date (YYYY-MM-DD format)
 * @returns {Promise<Object>} Updated order object
 */
async function updateOrderReturnDate(orderKey, returnByDate) {
  const headers = await getAuthHeaders();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/${encodeURIComponent(orderKey)}`,
    {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ return_by_date: returnByDate }),
    }
  );

  validateResponseOrigin(response);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to update return date: ${response.status} ${errorText}`);
  }

  return response.json();
}
