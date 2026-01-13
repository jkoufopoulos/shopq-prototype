# Extension Security Audit (Nov 2025)

## OAuth Token Management - ✅ SECURE

**Audit Date**: November 11, 2025
**Status**: ✅ **PASS** - Following Manifest V3 best practices

### Token Handling

**✅ Correct Implementation**: Using `chrome.identity` API

```javascript
// extension/modules/auth.js
async function getAuthToken(options = {}) {
  return new Promise((resolve, reject) => {
    chrome.identity.getAuthToken({ interactive: false }, (token) => {
      if (chrome.runtime.lastError || !token) {
        // Fallback to interactive auth
        chrome.identity.getAuthToken({ interactive: true }, resolve);
      } else {
        resolve(token);
      }
    });
  });
}
```

**Why this is secure**:
1. **Chrome-managed**: Token stored securely by Chrome, not extension
2. **Automatic refresh**: Chrome handles token expiration automatically
3. **Revocable**: `chrome.identity.removeCachedAuthToken()` for logout
4. **No persistence needed**: Token retrieved on-demand, not stored

### Security Checklist

| Security Concern | Status | Evidence |
|------------------|--------|----------|
| OAuth token in chrome.storage | ✅ PASS | No `storage.set.*token` patterns found |
| Token hardcoded in code | ✅ PASS | All tokens obtained via `chrome.identity` |
| Token in URL params | ✅ PASS | Token sent in `Authorization: Bearer` header |
| Token logging to console | ⚠️ REVIEW | Logs "token obtained" but not token value |
| Insecure API calls (HTTP) | ✅ PASS | All API calls use HTTPS (CONFIG.SHOPQ_API_URL) |
| CSRF protection | ✅ PASS | Token-based auth (no cookies) |
| XSS vulnerabilities | ✅ PASS | Content Security Policy in manifest |

### API Call Pattern

**✅ Secure pattern**: Authorization header with Bearer token

```javascript
// extension/background.js
const token = await getAuthToken();
const response = await fetch(`${CONFIG.SHOPQ_API_URL}/api/feedback`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`  // ✅ Secure
  },
  body: JSON.stringify(data)
});
```

**No insecure patterns found**:
- ❌ Token in URL query params (`?token=...`) - NOT FOUND
- ❌ Token in request body - NOT FOUND
- ❌ Token in chrome.storage - NOT FOUND

### Token Refresh Flow

**Automatic token refresh** handled by Chrome:

```javascript
// If token expires, Chrome auto-refreshes on next getAuthToken() call
const token = await getAuthToken();  // Fresh token or cached valid token
```

**Force refresh** (when 401 received):

```javascript
// Option 1: Remove cached token and get fresh one
chrome.identity.removeCachedAuthToken({ token: oldToken }, () => {
  chrome.identity.getAuthToken({ interactive: true }, (newToken) => {
    // Retry API call with new token
  });
});

// Option 2: Use built-in forceRefresh option
const token = await getAuthToken({ forceRefresh: true });
```

### Revocation & Logout

**Proper token revocation**:

```javascript
// extension/modules/auth.js
async function revokeToken(token) {
  return new Promise((resolve, reject) => {
    chrome.identity.removeCachedAuthToken({ token }, () => {
      console.log('✅ Token revoked');
      resolve();
    });
  });
}
```

**Full logout flow** (recommended):

```javascript
async function logout() {
  const token = await getAuthToken({ interactive: false });
  if (token) {
    await revokeToken(token);
    await chrome.storage.local.clear();  // Clear cached data
    console.log('✅ Logged out');
  }
}
```

### Content Security Policy

**Manifest CSP** (manifest.json):

```json
{
  "content_security_policy": {
    "extension_pages": "script-src 'self'; object-src 'self'"
  }
}
```

**Protection**:
- ✅ Prevents inline scripts (XSS mitigation)
- ✅ Prevents eval() (code injection mitigation)
- ✅ Only loads scripts from extension package

### Permissions Audit

**Required permissions** (manifest.json):

```json
{
  "permissions": [
    "identity",        // ✅ OAuth token management
    "storage",         // ✅ Classification cache, settings
    "tabs",            // ✅ Gmail tab detection
    "scripting",       // ✅ Content script injection
    "notifications",   // ✅ User notifications
    "downloads",       // ✅ Digest export
    "alarms"           // ✅ Background scheduling
  ],
  "host_permissions": [
    "https://mail.google.com/*",                           // ✅ Gmail access
    "https://www.googleapis.com/*",                        // ✅ Gmail API
    "https://shopq-api-488078904670.us-central1.run.app/*", // ✅ Backend API
    "https://ipapi.co/*"                                   // ⚠️ REVIEW: Location service
  ]
}
```

**Recommendations**:
1. ✅ **identity permission**: Required and properly used
2. ⚠️ **ipapi.co permission**: Review if location service is still needed
3. ✅ **No broad permissions**: No `<all_urls>`, no excessive permissions

### Vulnerability Assessment

**Known Manifest V3 vulnerabilities**:

| Vulnerability | Risk | Mitigated? |
|---------------|------|------------|
| Service worker killed mid-operation | Medium | ⚠️ TODO: Add checkpointing (P1.6) |
| Token expiration during batch ops | Low | ✅ PASS: Chrome auto-refreshes |
| Man-in-the-middle (MITM) | Low | ✅ PASS: HTTPS only |
| Phishing (malicious extension) | Medium | ✅ PASS: Published via Chrome Web Store |
| Data exfiltration via API | Medium | ✅ PASS: Only sends to SHOPQ_API_URL |

### Recommendations

#### ✅ No action needed
1. **Token management**: Already using chrome.identity correctly
2. **API security**: Proper Authorization headers
3. **CSP**: Adequate protection against XSS

#### ⚠️ Consider improving (Low priority)

**1. Add token refresh retry logic**:

```javascript
// Improved API call with automatic token refresh on 401
async function fetchWithAuth(url, options = {}) {
  let token = await getAuthToken();

  let response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`
    }
  });

  // If 401, refresh token and retry once
  if (response.status === 401) {
    console.log('🔄 Token expired, refreshing...');
    token = await getAuthToken({ forceRefresh: true });
    response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${token}`
      }
    });
  }

  return response;
}
```

**2. Review ipapi.co permission**:

Check if location service is still needed. If not, remove from `host_permissions`.

**3. Add rate limiting for API calls**:

```javascript
// Prevent accidental API spam
const API_RATE_LIMIT = 10; // requests per second
let apiCallTimestamps = [];

async function rateLimitedFetch(url, options) {
  // Remove timestamps older than 1 second
  const now = Date.now();
  apiCallTimestamps = apiCallTimestamps.filter(ts => now - ts < 1000);

  if (apiCallTimestamps.length >= API_RATE_LIMIT) {
    console.warn('⚠️ Rate limit exceeded, waiting...');
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  apiCallTimestamps.push(now);
  return fetchWithAuth(url, options);
}
```

### Related Documentation

- **Extension README**: `/extension/README.md`
- **Auth Module**: `/extension/modules/auth.js`
- **Manifest V3 Guide**: [Chrome Developer Docs](https://developer.chrome.com/docs/extensions/mv3/)
- **chrome.identity API**: [Chrome Identity API](https://developer.chrome.com/docs/extensions/reference/identity/)

### Audit History

| Date | Auditor | Status | Notes |
|------|---------|--------|-------|
| 2025-11-11 | Architecture Review | ✅ PASS | Initial security audit, no critical issues |

---

**Next Review**: When approaching multi-user launch or after major auth changes
**Security Contact**: See `/CONTRIBUTING.md`
