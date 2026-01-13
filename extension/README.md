# ShopQ Chrome Extension

The Chrome extension frontend for ShopQ - an AI-powered Gmail assistant that automatically organizes your inbox using intelligent classification and provides daily digest emails.

## Overview

The ShopQ extension runs in Gmail and provides:
- **Auto-organization**: Automatically classifies and labels emails in real-time
- **Manual organization**: On-demand organization via extension icon
- **Bridge mode**: Transparent label mapping with shadow logging
- **Digest generation**: Daily email summaries with context
- **Feature gates**: Progressive rollout of new features
- **Offline support**: Works with cached classifications when backend is unavailable

## Architecture

```
┌────────────────────────────────────────────────┐
│         background.js (Service Worker)         │
│  - Gmail API calls                             │
│  - Backend communication                       │
│  - Auto-organize scheduler                     │
│  - Feature gate management                     │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│           content.js (DOM Integration)         │
│  - Gmail UI integration                        │
│  - Selector-based email detection              │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│            modules/ (Business Logic)           │
│  - Classification, mapping, verification       │
│  - Caching, budget tracking, telemetry         │
└────────────────────────────────────────────────┘
```

## Directory Structure

### Core Files (Root)

| File | Purpose |
|------|---------|
| **manifest.json** | Chrome extension manifest (permissions, OAuth2) |
| **background.js** | Service worker entry point, orchestration |
| **content.js** | Gmail DOM integration, event listeners |
| **package.json** | Node.js dependencies |
| **README.md** | This documentation |

### Modules (modules/)

Directory structure aligned with `shopq/` backend for consistency:

#### modules/classification/ ← `shopq/classification/`
- **classifier.js** - Backend classification client
- **detectors.js** - Pattern detection (OTP, shipping, etc.)
- **mapper.js** - Label mapping (internal → Gmail labels)
- **verifier.js** - Classification verification and quality checks
- **Schema.json** - Classification schema definitions

#### modules/digest/ ← `shopq/digest/`
- **summary-email.js** - Digest generation and delivery
- **context-digest.js** - Context-aware digest logic

#### modules/gmail/ ← `shopq/gmail/`
- **api.js** - Gmail API client, label management, email fetching
- **auth.js** - OAuth2 authentication flow
- **selectors.js** - Gmail DOM selectors (version-resilient)

#### modules/storage/ ← `shopq/storage/`
- **cache.js** - Classification result caching
- **budget.js** - API call budget tracking
- **logger.js** - IndexedDB classification logging

#### modules/shared/ ← `shopq/shared/`
- **config.js** - Configuration constants (API URLs, timeouts)
- **config-sync.js** - Configuration synchronization with backend
- **utils.js** - Utility functions
- **signatures.js** - Email signature detection
- **notifications.js** - Chrome notifications

#### modules/observability/ ← `shopq/observability/`
- **telemetry.js** - Usage telemetry
- **structured-logger.js** - Structured JSON event logging

#### modules/automation/ (extension-specific)
- **auto-organize.js** - Auto-organization scheduler, background sync

### Tests (tests/)

Extension-specific tests using Jest:
- `detectors.test.js` - Detector pattern tests
- `mapper.test.js` - Mapper logic tests
- `verifier.test.js` - Verification tests
- `verifier.phase6.test.js` - Phase 6 verification tests
- `signatures.test.js` - Signature detection tests
- `utils.test.js` - Utility function tests
- `network.test.js` - Network layer tests

### Icons (icons/)

Extension icons in multiple sizes:
- `icon16.png` - Toolbar icon (16x16)
- `icon48.png` - Extension management (48x48)
- `icon128.png` - Chrome Web Store (128x128)

## Installation

### Development Installation

1. **Load unpacked extension**:
   ```bash
   # Navigate to Chrome extensions
   chrome://extensions/

   # Enable "Developer mode"
   # Click "Load unpacked"
   # Select: /path/to/mailq-prototype/extension/
   ```

2. **Configure backend URL**:
   - Edit `modules/shared/config.js` to point to your backend:
   ```javascript
   const API_URL = "http://localhost:8000";  // Local development
   // or
   const API_URL = "https://shopq-api-*.run.app";  // Production
   ```

3. **Test in Gmail**:
   - Open Gmail: https://mail.google.com
   - Click extension icon
   - Authorize OAuth2 permissions
   - Click "Organize Inbox" to test

### Production Build

```bash
cd extension/
npm install
npm test              # Run tests
npm run build         # Bundle for production (if configured)
```

## Key Features

### 1. Auto-Organization (Bridge Mode)

**File**: `modules/automation/auto-organize.js`

Automatically classifies and labels emails in the background:

```javascript
// Extension icon clicked → organize inbox
chrome.action.onClicked.addListener(async (tab) => {
  await organizeInbox();
});

// Scheduled auto-organization every 15 minutes
chrome.alarms.create('autoOrganize', { periodInMinutes: 15 });
```

**How it works**:
1. Fetches recent unread emails via Gmail API
2. Sends to backend for classification
3. Maps internal importance → Gmail labels
4. Applies labels using Gmail API
5. Logs actions to backend for quality monitoring

### 2. Bridge Mapper (Label Mapping)

**File**: `modules/classification/mapper.js`

Decouples internal classification from Gmail label names:

```javascript
// Backend returns: { importance: "critical", type: "notification" }
// Mapper produces: { labels: ["IMPORTANT", "CATEGORY_PERSONAL"] }

const decision = mapToGmailLabels(classification);
// Transparent to users: they see Gmail labels, not internal categories
```

**Benefits**:
- Gmail policy (labels) decoupled from LLM outputs
- Easy to change label names without retraining
- Shadow logging for A/B testing

### 3. Classification Cache

**File**: `modules/storage/cache.js`

Caches classifications to reduce backend calls:

```javascript
// Check cache before calling backend
const cached = await getFromCache(emailId);
if (cached && !isExpired(cached)) {
  return cached.classification;
}

// Cache miss → call backend
const result = await classifyEmail(email);
await saveToCache(emailId, result, ttl=3600);
```

**Cache key**: `email_${gmailMessageId}`
**TTL**: 1 hour (configurable)

### 4. Budget Tracking

**File**: `modules/storage/budget.js`

Tracks API usage to prevent quota exhaustion:

```javascript
// Check budget before expensive operations
if (!await hasBudget('classification', 1)) {
  console.warn('Budget exceeded, skipping classification');
  return null;
}

// Deduct from budget after operation
await deductBudget('classification', 1);
```

**Budgets**:
- Classification: 1000 calls/day
- LLM digest: 10 calls/day
- Gmail API: 2500 calls/day

### 5. Verification & Quality Control

**File**: `modules/classification/verifier.js`

Verifies classifications match expected patterns:

```javascript
// Verify critical classification
const isValid = await verifyClassification(email, 'critical');
if (!isValid) {
  logQualityIssue(email, 'critical_mismatch');
  // Potentially downgrade or flag for review
}
```

**Verification rules**:
- Critical: Must have action keywords or deadline
- Routine: Cannot have urgent keywords
- OTP codes: Always routine (guardrail)
- Shipping: Time-sensitive if arriving soon

### 6. Feature Gates

**File**: `background.js`, backend controls

Progressive rollout of new features:

```javascript
// Check if feature is enabled for this user
if (await isFeatureEnabled('bridge_mode')) {
  // Use bridge mapper
  decision = await bridgeMapper.map(email);
} else {
  // Use legacy direct classification
  decision = await legacyClassifier.classify(email);
}
```

**Current features**:
- `bridge_mode` - Bridge mapper (enabled)
- `digest_v3` - Digest v3 generation (testing)
- `auto_organize` - Background auto-organization (enabled)

### 7. Digest Generation

**File**: `modules/digest/summary-email.js`

Generates daily digest emails with context:

```javascript
// User clicks "Generate Digest"
await generateDailyDigest({
  lookbackDays: 1,
  includeRoutine: false,
  groupByContext: true
});
```

**Digest structure**:
- **Critical** - Action required
- **Coming Up** - Events/deadlines approaching
- **Worth Knowing** - Time-sensitive updates
- **Routine** (optional) - Low-priority items

## Configuration

### API Endpoint (modules/shared/config.js)

```javascript
// Development
const API_URL = "http://localhost:8000";

// Staging
const API_URL = "https://shopq-api-staging-*.run.app";

// Production
const API_URL = "https://shopq-api-488078904670.us-central1.run.app";
```

### OAuth2 Scopes (manifest.json)

```json
"scopes": [
  "https://www.googleapis.com/auth/gmail.modify",
  "https://www.googleapis.com/auth/gmail.labels"
]
```

**Required permissions**:
- `gmail.modify` - Read emails, apply labels
- `gmail.labels` - Create/manage labels
- `identity` - OAuth2 authentication
- `storage` - Cache classifications
- `notifications` - User notifications

### Timeouts & Retries

```javascript
// API call timeout: 30 seconds
const CLASSIFICATION_TIMEOUT = 30000;

// Retry policy: 3 attempts with exponential backoff
const MAX_RETRIES = 3;
const RETRY_DELAY = [1000, 2000, 4000];
```

## Development Workflow

### 1. Local Development

```bash
# Terminal 1: Start backend
cd /path/to/mailq-prototype
uvicorn shopq.api:app --reload --port 8000

# Terminal 2: Watch extension changes
cd extension/
npm run watch  # If configured

# Chrome: Reload extension on changes
chrome://extensions/ → Click reload icon
```

### 2. Testing

```bash
cd extension/
npm test                    # Run all tests
npm test -- verifier       # Run specific test
npm test -- --coverage     # With coverage
```

### 3. Debugging

**Background service worker**:
```
chrome://extensions/ → ShopQ → "Inspect views: service worker"
```

**Content script**:
```
Gmail → F12 DevTools → Console → Check for logs
```

**Network requests**:
```
DevTools → Network tab → Filter: "mailq"
```

### 4. Testing in Gmail

**Manual organization**:
1. Open Gmail
2. Click extension icon
3. Check console for logs
4. Verify labels applied

**Auto-organization**:
1. Wait 15 minutes (or trigger alarm manually)
2. Check background service worker logs
3. Verify labels applied to recent emails

## Common Tasks

### Add New Detector Pattern

Edit `modules/classification/detectors.js`:

```javascript
export function isPatternX(subject, body) {
  return /pattern regex/.test(subject + ' ' + body);
}
```

Add test in `tests/detectors.test.js`:

```javascript
test('detects pattern X', () => {
  expect(isPatternX('Pattern X subject', 'body')).toBe(true);
});
```

### Add New Mapper Rule

Edit `modules/classification/mapper.js`:

```javascript
function mapImportanceToLabels(importance, email) {
  // Add custom rule
  if (isSpecialCase(email)) {
    return ['CUSTOM_LABEL'];
  }

  // Default mapping
  return standardMapping[importance];
}
```

### Change Cache TTL

Edit `modules/storage/cache.js`:

```javascript
const DEFAULT_TTL = 3600;  // 1 hour → change to desired value
```

### Add Telemetry Event

Edit `modules/observability/telemetry.js`:

```javascript
export async function trackEvent(category, action, label, value) {
  const event = {
    category,
    action,
    label,
    value,
    timestamp: Date.now()
  };

  await sendToBackend('/api/telemetry', event);
}
```

## Troubleshooting

### Extension Not Working

1. **Check service worker logs**:
   - `chrome://extensions/` → ShopQ → "Inspect views"
   - Look for error messages

2. **Verify backend connection**:
   ```javascript
   // In console:
   fetch(API_URL + '/health').then(r => r.json()).then(console.log);
   ```

3. **Check OAuth2 token**:
   ```javascript
   // In console:
   chrome.storage.local.get(['auth_token'], console.log);
   ```

### Classifications Not Applied

1. **Check budget**:
   ```javascript
   chrome.storage.local.get(['budgets'], console.log);
   ```

2. **Check cache**:
   ```javascript
   chrome.storage.local.get(null, console.log);  // All cached data
   ```

3. **Check Gmail API quota**:
   - Google Cloud Console → APIs → Gmail API → Quotas

### Labels Not Visible in Gmail

1. **Verify labels exist**:
   ```javascript
   // In background service worker console:
   listAllLabels().then(console.log);
   ```

2. **Check label creation**:
   - Some labels may be hidden in Gmail settings
   - Settings → Labels → Show label

## Architecture Notes

### Why Service Worker?

Manifest V3 requires service workers instead of persistent background pages:
- Event-driven (wakes on events, sleeps otherwise)
- Better resource efficiency
- Chrome's direction for all extensions

**Implications**:
- Cannot maintain long-lived connections
- Must use `chrome.alarms` for scheduling
- State must be persisted to `chrome.storage`

### Why Separate Mapper?

Bridge pattern decouples classification logic from Gmail labels:
- **Backend** returns generic importance (critical, time_sensitive, routine)
- **Mapper** converts to Gmail labels (IMPORTANT, CATEGORY_*, etc.)
- **Benefits**: Easy to change labels, A/B test, shadow log

### Why Cache Classifications?

Reduces backend load and improves responsiveness:
- Backend classification can take 2-5 seconds (LLM call)
- Most emails don't change classification over time
- Cache hit rate: ~60% after initial organization

## Related Documentation

- **Backend API**: `/shopq/README.md`
- **Architecture**: `/docs/ARCHITECTURE.md`
- **Testing**: `/docs/TESTING.md`
- **Deployment**: `/docs/DEPLOYMENT_PLAYBOOK.md`

## Support

- **Issues**: Create GitHub issue with `extension` label
- **Debugging**: `/TROUBLESHOOTING.md`
- **Contributing**: `/CONTRIBUTING.md`

---

**Extension Version**: 1.0.10
**Chrome Version Required**: 88+
**Manifest Version**: 3
**Last Updated**: November 2025
