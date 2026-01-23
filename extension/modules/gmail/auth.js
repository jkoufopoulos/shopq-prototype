/**
 * Gmail OAuth Authentication Module
 */

/**
 * Get Gmail OAuth token with automatic refresh
 * First attempts to use cached token, falls back to interactive auth if needed
 * @param {Object} options - Auth options
 * @param {boolean} options.forceRefresh - Force a fresh token even if cached one exists
 * @returns {Promise<string>} OAuth token
 */
async function getAuthToken(options = {}) {
  const { forceRefresh = false } = options;

  return new Promise((resolve, reject) => {
    // If forcing refresh, remove cached token first
    if (forceRefresh) {
      chrome.identity.getAuthToken({ interactive: false }, (oldToken) => {
        if (oldToken) {
          chrome.identity.removeCachedAuthToken({ token: oldToken }, () => {
            // After removing, get a fresh token
            getFreshToken(resolve, reject);
          });
        } else {
          // No cached token to remove, just get fresh one
          getFreshToken(resolve, reject);
        }
      });
    } else {
      // Try cached token first
      chrome.identity.getAuthToken({ interactive: false }, (token) => {
        if (chrome.runtime.lastError || !token) {
          // No cached token or error, get fresh token interactively
          getFreshToken(resolve, reject);
        } else {
          console.log('✅ OAuth token obtained (cached)');
          resolve(token);
        }
      });
    }
  });
}

/**
 * Helper to get a fresh token interactively
 * @private
 */
function getFreshToken(resolve, reject) {
  chrome.identity.getAuthToken({ interactive: true }, (token) => {
    if (chrome.runtime.lastError) {
      console.error('❌ Auth error:', chrome.runtime.lastError);
      reject(chrome.runtime.lastError);
    } else {
      console.log('✅ OAuth token obtained (fresh)');
      resolve(token);
    }
  });
}

/**
 * Revoke OAuth token (for logout)
 * @param {string} token - Token to revoke
 */
async function revokeToken(token) {
  return new Promise((resolve, reject) => {
    chrome.identity.removeCachedAuthToken({ token }, () => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else {
        console.log('✅ Token revoked');
        resolve();
      }
    });
  });
}

/**
 * Get the current user's info from Google
 * @param {string} token - OAuth token
 * @returns {Promise<{id: string, email: string, name: string, picture: string}>}
 */
async function getUserInfo(token) {
  const response = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to get user info: ${response.status}`);
  }

  return response.json();
}

/**
 * Get and cache the current user's ID
 * Uses Google's unique user ID for consistent identification
 * @returns {Promise<string>} User ID
 */
async function getAuthenticatedUserId() {
  // Check cache first
  const cached = await chrome.storage.local.get('authenticatedUserId');
  if (cached.authenticatedUserId) {
    return cached.authenticatedUserId;
  }

  // Get token and fetch user info
  const token = await getAuthToken();
  const userInfo = await getUserInfo(token);

  // Cache the user ID
  await chrome.storage.local.set({
    authenticatedUserId: userInfo.id,
    userEmail: userInfo.email,
    userName: userInfo.name,
  });

  console.log('✅ User authenticated:', userInfo.email);
  return userInfo.id;
}

/**
 * Clear cached user info (for logout)
 */
async function clearUserCache() {
  await chrome.storage.local.remove(['authenticatedUserId', 'userEmail', 'userName']);
}

// Functions are available globally when loaded via importScripts in service worker
// For ES module contexts (content scripts), these are also exported below
