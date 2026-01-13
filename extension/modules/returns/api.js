/**
 * ShopQ Returns API Client
 * Handles communication with the backend API for return card operations
 */

const API_BASE_URL = 'https://shopq-api-488078904670.us-central1.run.app';

/**
 * Get the current user ID from storage
 */
async function getUserId() {
  const data = await chrome.storage.local.get('userId');
  return data.userId || 'default_user';
}

/**
 * Fetch all returns for the current user
 */
export async function fetchReturns(options = {}) {
  const userId = await getUserId();
  const { status } = options;

  let url = `${API_BASE_URL}/api/returns?user_id=${encodeURIComponent(userId)}`;
  if (status) {
    url += `&status=${encodeURIComponent(status)}`;
  }

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
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
export async function fetchExpiringReturns(withinDays = 7) {
  const userId = await getUserId();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/expiring?user_id=${encodeURIComponent(userId)}&within_days=${withinDays}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
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
export async function getReturnCounts() {
  const userId = await getUserId();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/counts?user_id=${encodeURIComponent(userId)}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
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
export async function updateReturnStatus(returnId, newStatus) {
  const response = await fetch(
    `${API_BASE_URL}/api/returns/${encodeURIComponent(returnId)}/status`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
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
export async function createReturn(returnData) {
  const response = await fetch(`${API_BASE_URL}/api/returns`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
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
export async function processEmail(emailData) {
  const userId = await getUserId();

  const response = await fetch(`${API_BASE_URL}/api/returns/process`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_id: userId,
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
export async function refreshStatuses() {
  const userId = await getUserId();

  const response = await fetch(
    `${API_BASE_URL}/api/returns/refresh-statuses?user_id=${encodeURIComponent(userId)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to refresh statuses: ${response.status} ${errorText}`);
  }

  return response.json();
}
