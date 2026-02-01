/**
 * ShopQ Returns API Client
 * Handles communication with the backend API for return card operations
 *
 * Note: This file is loaded via importScripts in the service worker.
 * getAuthToken is available globally from auth.js which is loaded first.
 */

const API_BASE_URL = 'https://shopq-api-488078904670.us-central1.run.app';

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
 * @returns {Promise<{success: boolean, cards: Array, stats: Object}>}
 */
async function processEmailBatch(emails) {
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}/api/returns/process-batch`, {
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
