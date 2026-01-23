/**
 * ShopQ Returns API Client
 * Handles communication with the backend API for return card operations
 *
 * Note: This file is loaded via importScripts in the service worker.
 * getAuthToken is available globally from auth.js which is loaded first.
 */

const API_BASE_URL = 'https://shopq-api-488078904670.us-central1.run.app';

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

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to process email: ${response.status} ${errorText}`);
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

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to refresh statuses: ${response.status} ${errorText}`);
  }

  return response.json();
}
