/**
 * Gmail OAuth Authentication Module
 */

// EXT-001: Token validation interval
const TOKEN_VALIDATION_INTERVAL_MS = CONFIG.TOKEN_VALIDATION_INTERVAL_MS;
let lastTokenValidation = 0;
let cachedValidToken = null;

/**
 * EXT-001: Validate token with Google's tokeninfo endpoint
 * @param {string} token - OAuth token to validate
 * @returns {Promise<boolean>} True if token is valid
 */
async function isTokenValid(token) {
  if (!token) return false;

  try {
    const response = await fetch(
      `https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=${encodeURIComponent(token)}`
    );

    if (!response.ok) {
      console.log('EXT-001: Token validation failed, status:', response.status);
      return false;
    }

    const tokenInfo = await response.json();

    // Check if token has required scopes
    const requiredScopes = [
      'https://www.googleapis.com/auth/gmail.readonly',
      'https://www.googleapis.com/auth/userinfo.profile'
    ];

    const tokenScopes = (tokenInfo.scope || '').split(' ');
    const hasRequiredScopes = requiredScopes.every(scope =>
      tokenScopes.some(s => s.includes(scope.split('/').pop()))
    );

    if (!hasRequiredScopes) {
      console.log('EXT-001: Token missing required scopes');
      return false;
    }

    // Check if token will expire soon (within 5 minutes)
    const expiresIn = parseInt(tokenInfo.expires_in, 10);
    if (expiresIn < CONFIG.TOKEN_MIN_LIFETIME_SECONDS) {
      console.log('EXT-001: Token expiring soon, will refresh');
      return false;
    }

    return true;
  } catch (error) {
    console.error('EXT-001: Token validation error:', error);
    return false;
  }
}

/**
 * Get Gmail OAuth token with automatic refresh
 * First attempts to use cached token, falls back to interactive auth if needed
 * @param {Object} options - Auth options
 * @param {boolean} options.forceRefresh - Force a fresh token even if cached one exists
 * @returns {Promise<string>} OAuth token
 */
async function getAuthToken(options = {}) {
  const { forceRefresh = false } = options;

  // EXT-001: Check if we need to validate the token
  const now = Date.now();
  const needsValidation = now - lastTokenValidation > TOKEN_VALIDATION_INTERVAL_MS;

  return new Promise((resolve, reject) => {
    // If forcing refresh, remove cached token first
    if (forceRefresh) {
      cachedValidToken = null;
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
      chrome.identity.getAuthToken({ interactive: false }, async (token) => {
        if (chrome.runtime.lastError || !token) {
          // No cached token or error, get fresh token interactively
          cachedValidToken = null;
          getFreshToken(resolve, reject);
        } else {
          // EXT-001: Validate token periodically
          if (needsValidation) {
            const valid = await isTokenValid(token);
            if (!valid) {
              console.log('EXT-001: Cached token invalid, refreshing...');
              cachedValidToken = null;
              // Remove invalid token and get fresh one
              chrome.identity.removeCachedAuthToken({ token }, () => {
                getFreshToken(resolve, reject);
              });
              return;
            }
            lastTokenValidation = now;
            cachedValidToken = token;
          }
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
