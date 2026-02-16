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

