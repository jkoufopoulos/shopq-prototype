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
