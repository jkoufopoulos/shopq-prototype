# Reclaim v2: Local-First Browser Extension Architecture

## Context

Reclaim v1 scans Gmail for order/delivery emails using a backend API + Gemini LLM. The privacy objection ("you're reading my email?") is the biggest barrier to adoption. v2 pivots to a Honey-style browser extension that passively captures order confirmations from shopping sites, stores everything locally, and needs no backend or email access.

## High-Level Flow

```
User completes checkout on amazon.com
       |
Content script detects order confirmation page
       |
Scrapes: merchant, items, order ID, amount, dates
       |
Sends to service worker via chrome.runtime.sendMessage
       |
Service worker looks up return policy (cached or scrapes merchant's /returns page)
       |
Computes return deadline, stores in chrome.storage.local
       |
chrome.alarms fires daily check
       |
Approaching deadlines -> chrome.notifications
       |
User clicks notification -> extension popup with order details
```

## Components

### 1. Content Scripts (Order Capture)

**What:** Content scripts injected on shopping sites that detect order confirmation pages and scrape order details from the DOM.

**Matching:** Broad match on known retailer domains + generic heuristic detection.

```json
"content_scripts": [
  {
    "matches": ["https://*.amazon.com/*", "https://*.target.com/*", ...],
    "js": ["dist/capture.bundle.js"],
    "run_at": "document_idle"
  }
]
```

**Detection heuristics** (for unknown retailers):
- URL patterns: `/order-confirmation`, `/checkout/thank-you`, `/order/complete`
- Page content signals: "order confirmed", "thank you for your order", "order #"
- DOM patterns: presence of order number, item list, total amount

**Extraction:** Hybrid approach (same philosophy as v1):
- Regex for structured data (order IDs, amounts, dates, tracking numbers)
- DOM selectors for known retailers (Amazon, Target, etc. have stable page structures)
- Fallback: send page text to on-device model for unstructured extraction (future)

**Reusable from v1:** `modules/pipeline/extractor.js` -- regex patterns for order IDs, dates, amounts.

### 2. Content Scripts (Return Policy Scraper)

**What:** When a new merchant is encountered, fetch their return policy page and extract the policy.

**How:**
- Try predictable URLs: `merchant.com/returns`, `/return-policy`, `/help/returns`
- Parse the page for: return window days, anchor (order vs delivery), exceptions
- For v1: use regex + keyword matching ("30 days", "from delivery", "final sale")
- For v2: on-device model extracts structured policy from page text

**Storage:** Cache extracted policies in `chrome.storage.local` keyed by domain. Expire after 30 days.

**Seed data:** Convert existing `config/merchant_rules.yaml` (23 merchants) to JSON, ship with extension as defaults.

### 3. Background Service Worker

**What:** Central coordinator. Receives captured orders, manages storage, fires deadline notifications.

**Message handlers:**
- `ORDER_CAPTURED` -- content script detected an order confirmation, store it
- `POLICY_FETCHED` -- return policy scraped, update merchant rules cache
- `CHECK_DEADLINES` -- alarm-triggered, scan stored orders for approaching deadlines
- `DISMISS_ORDER` / `MARK_RETURNED` -- user actions from popup

**Alarms:**

```js
chrome.alarms.create('check-deadlines', { periodInMinutes: 720 }); // twice daily
```

**Notifications:**

```js
chrome.notifications.create(orderId, {
  type: 'basic',
  title: 'Return window closing soon',
  message: 'Your Nike order expires in 3 days',
  iconUrl: 'icons/icon128.png'
});
```

**Notification schedule:**
- First alert: 7 days before deadline
- Final alert: 3 days before deadline
- Each order only notifies once per threshold (tracked in storage)

**Reusable from v1:** Message dispatcher pattern, sender validation, rate limiting from `background.js`. Notification creation code already exists.

### 4. Storage Layer

**What:** All data in `chrome.storage.local`. No backend. No API calls.

**Schema:**

```js
{
  // Orders
  ORDERS_BY_KEY: {
    "amazon_123-456": {
      order_key: "amazon_123-456",
      merchant_name: "Amazon",
      merchant_domain: "amazon.com",
      items: "Blue Nike Jacket, Running Shoes",
      order_id: "123-4567890-1234567",
      amount: 184.99,
      currency: "USD",
      order_date: "2025-01-15",
      delivery_date: "2025-01-20",     // null until detected
      return_by_date: "2025-02-19",
      status: "active",                // active | expiring_soon | expired | returned | dismissed
      confidence: "estimated",         // exact | estimated | unknown
      capture_url: "https://amazon.com/order/123",
      captured_at: "2025-01-15T10:30:00Z",
      notified_7day: false,
      notified_3day: false
    }
  },

  // Merchant return policies (cached)
  MERCHANT_POLICIES: {
    "amazon.com": {
      days: 30,
      anchor: "delivery",
      return_url: "https://amazon.com/returns",
      scraped_at: "2025-01-01T00:00:00Z",
      source: "seed"                   // seed | scraped | user
    }
  },

  // Settings
  SETTINGS: {
    notification_7day: true,
    notification_3day: true,
    default_return_days: 30,
    default_anchor: "delivery"
  }
}
```

**Reusable from v1:** `modules/storage/store.js` (chrome.storage.local wrapper with mutex), `modules/storage/schema.js` (adapt field names). ~85% reusable.

### 5. Extension Popup

**What:** The primary UI. Shows captured orders sorted by urgency. Replaces the Gmail sidebar.

**Views:**
- **Order list:** Cards sorted by return deadline (soonest first). Color-coded: green (>7 days), yellow (3-7 days), red (<3 days), gray (expired/returned).
- **Order detail:** Merchant, items, dates, return policy info, action buttons (mark returned, dismiss, edit deadline).
- **Settings:** Notification preferences, default return window.

**New build, but design can mirror** the existing sidebar UI in `returns-sidebar-inner.js`.

### 6. Order History Crawl (v2 feature)

**What:** "Scan my orders" button that walks a retailer's order history page and captures past orders in bulk.

**How:** Content script navigates Amazon order history, paginates, extracts each order. User-initiated, not background.

**Why:** Solves the "only captures orders after install" gap.

## Permissions

```json
{
  "permissions": [
    "storage",
    "alarms",
    "notifications"
  ],
  "host_permissions": [
    "https://*.amazon.com/*",
    "https://*.target.com/*",
    "https://*.walmart.com/*",
    "https://*.bestbuy.com/*",
    "https://*.nike.com/*",
    "https://*.shopify.com/*"
  ]
}
```

No `identity`, no `tabs`, no Gmail scopes. Comparable to Honey/Capital One Shopping permissions.

## Dependencies

**Runtime (ships with extension):**
- `merchant_rules.json` -- seeded from existing `config/merchant_rules.yaml` (23 merchants)
- No external APIs required for core functionality

**Build:**
- Webpack (existing setup, extend for multiple entry points)
- No new npm dependencies expected for v1

**Optional / Future:**
- Chrome built-in AI APIs or Gemini Nano -- on-device extraction for unstructured pages
- Plaid -- transaction data backfill (v2+)

## What's Reused from v1

| Module | Reuse | Notes |
|--------|-------|-------|
| `modules/storage/store.js` | 85% | Chrome storage wrapper + mutex |
| `modules/storage/schema.js` | 80% | Adapt field names |
| `modules/shared/config.js` | 70% | Add retailer domains, remove API URLs |
| `modules/pipeline/extractor.js` | 80% | Regex for order IDs, dates, amounts |
| `modules/pipeline/filter.js` | 50% | Domain blocklist concept |
| `modules/diagnostics/logger.js` | 100% | As-is |
| `background.js` patterns | 40% | Message dispatcher, validation |
| `config/merchant_rules.yaml` | 100% | Convert to JSON |

## What's New

1. **Shopping site content scripts** -- DOM-based order capture (replaces email parsing)
2. **Return policy scraper** -- auto-fetch + extract merchant policies
3. **`chrome.alarms` deadline checker** -- daily scan of stored orders
4. **Extension popup UI** -- order list + detail views (replaces Gmail sidebar)
5. **Merchant policy cache** -- auto-growing return policy database

## Key Differences from v1

| | v1 (Gmail) | v2 (Browser) |
|---|---|---|
| Data source | Gmail emails | Shopping site DOM |
| Privacy | Sends email to Gemini API | Nothing leaves the machine |
| Backend | FastAPI on Cloud Run | None |
| Storage | SQLite on server | chrome.storage.local |
| AI | Gemini Flash (cloud) | Regex + rules (local). On-device models later |
| Permissions | Gmail read access | Shopping site access (same as Honey) |
| Historical orders | Full inbox scan | Only after install (unless history crawl) |
| Delivery tracking | From delivery emails | From tracking pages or manual input |

## Open Questions

1. **Broad host permissions vs activeTab:** Requesting access to all shopping sites upfront is the Honey model. Alternative: use `activeTab` + user click, but breaks the "set and forget" requirement.
2. **Delivery date gap:** Without email access, how do we know when something was delivered? Options: watch carrier tracking pages, conservative estimate from order date, or user marks delivered.
3. **Unknown retailers:** For merchants without seed data or scrapable policy pages, default to 30 days from order and prompt user to confirm.
4. **Chrome Web Store review:** Broad host permissions + DOM scraping may trigger extra review. Honey/Capital One Shopping set the precedent.
