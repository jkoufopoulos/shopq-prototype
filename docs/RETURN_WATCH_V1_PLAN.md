# Return Watch V1 Implementation Plan

> **Version**: 0.6.1 (Locked MVP)
> **Promise**: One card per order. Return Watch highlights only deadline-known returns with traceable evidence.

---

## Table of Contents

1. [Scope Lock](#scope-lock)
2. [Architecture Overview](#architecture-overview)
3. [Data Model](#data-model)
4. [Pipeline Specification](#pipeline-specification)
5. [Implementation Phases](#implementation-phases)
6. [Test Harness](#test-harness)

---

## Scope Lock

### MUST DO (V1)

- [ ] ONE Order card per real order (not per email)
- [ ] Single screen UI with two stacked sections: **Return Watch** (deadline-known) + **All Purchases** (complete)
- [ ] SAFE linking/merging: primary keys only (order_id, tracking_number)
- [ ] Evidence-first return policy extraction: values must be provably present in quoted text
- [ ] Minimize LLM calls: rules first, LLM only for return policy when anchors exist

### DO NOT DO (V1)

- No fuzzy/fingerprint-based auto-merge (no item similarity, no amount/date matching)
- No scraping/crawling merchant websites
- No courier / pickup / refund / disputes automation
- No broad scanning of Promotions (Purchases category only)
- No deep logistics/friction extraction (printer/QR/etc.)

### Hard Blocklist (Never Create Orders)

- Groceries (Whole Foods, Instacart, meal kits)
- Digital goods (ebooks, app stores, streaming purchases)
- Subscriptions/renewals
- Banking/financial alerts
- Rideshare/travel (Uber, Lyft, airlines, hotels)

---

## Architecture Overview

### Sidebar Strategy

```
┌─────────────────────────────────────────────────────┐
│  Gmail Tab                                          │
│  ┌─────────────────────────────────┬──────────────┐ │
│  │                                 │   SIDEBAR    │ │
│  │         Gmail Content           │   (iframe)   │ │
│  │                                 │              │ │
│  │                                 │ ┌──────────┐ │ │
│  │                                 │ │ Return   │ │ │
│  │                                 │ │ Watch    │ │ │
│  │                                 │ ├──────────┤ │ │
│  │                                 │ │ All      │ │ │
│  │                                 │ │Purchases │ │ │
│  │                                 │ └──────────┘ │ │
│  └─────────────────────────────────┴──────────────┘ │
└─────────────────────────────────────────────────────┘
```

- **Mechanism**: Iframe isolation (sidebar.html)
- **Navigation**: Links use `target=_top` to open in Gmail
- **Width**: Fixed 300px with `contain: strict`

### UI Sections

| Section | Filter | Sort | Alert? |
|---------|--------|------|--------|
| **Return Watch > Expiring Soon** | deadline_confidence != unknown AND days_remaining <= 7 | return_by_date ASC | Yes |
| **Return Watch > Active** | deadline_confidence != unknown AND days_remaining > 7 | return_by_date ASC | No |
| **All Purchases** | All orders | purchase_date DESC | No |

---

## Data Model

### Order (Central Entity)

```typescript
interface Order {
  // Identity
  order_key: string;              // Stable internal ID (hash)
  merchant_domain: string;        // "amazon.com"
  merchant_display_name: string;  // "Amazon"

  // Primary Keys (for linking)
  order_id?: string;              // "123-456-789"
  tracking_number?: string;       // "1Z999AA..."

  // Lifecycle Dates
  purchase_date: string;          // ISO date
  ship_date?: string;
  delivery_date?: string;

  // Return Tracking
  return_window_days?: number;
  explicit_return_by_date?: string;
  return_by_date?: string;        // Computed
  deadline_confidence: 'exact' | 'estimated' | 'unknown';

  // Details
  item_summary: string;
  amount?: number;
  currency: string;               // Default: "USD"

  // Evidence
  evidence_message_id?: string;
  evidence_quote?: string;
  return_portal_link?: string;

  // State
  order_status: 'active' | 'returned' | 'dismissed';
  source_email_ids: string[];     // All linked emails (primary + thread-hinted)

  // Metadata
  created_at: string;
  updated_at: string;
}
```

### OrderEmail (Event Record)

```typescript
interface OrderEmail {
  email_id: string;               // Gmail message ID
  thread_id?: string;             // Gmail thread ID
  received_at: string;            // ISO datetime
  merchant_domain: string;
  email_type: 'confirmation' | 'shipping' | 'delivery' | 'other';
  blocked: boolean;
  processed: boolean;
  extracted?: {                   // Rule-extracted data
    order_id?: string;
    tracking_number?: string;
    amount?: number;
    order_date?: string;
    ship_date?: string;
    delivery_date?: string;
  };
  llm_extraction?: {              // LLM-extracted return policy
    deadline_date?: string;
    window_days?: number;
    confidence: 'exact' | 'estimated' | 'unknown';
    quote?: string;
  };
}
```

### Storage Keys (chrome.storage.local)

```typescript
interface StorageSchema {
  orders_by_key: Record<string, Order>;
  order_key_by_order_id: Record<string, string>;
  order_key_by_tracking: Record<string, string>;
  order_emails_by_id: Record<string, OrderEmail>;
  processed_email_ids: string[];
  last_scan_epoch_ms: number;
  last_scan_internal_date_ms: number;
  template_cache?: Record<string, LLMExtraction>;
}
```

---

## Pipeline Specification

### P0: Ingest

```
Input: Gmail messages from category:purchases
Fetch: Metadata first (id, from, subject, snippet, internalDate, threadId)
       Body only when required by later stages
```

### P1: Early Filter (FREE)

```
Gates:
  1. If email_id in processed_email_ids → SKIP
  2. Extract merchant_domain from From address
  3. If merchant_domain matches blocklist → blocked=true, SKIP

Blocklist domains:
  - wholefoodsmarket.com, instacart.com, hellofresh.com
  - uber.com, lyft.com, doordash.com
  - netflix.com, spotify.com, hulu.com
  - chase.com, bankofamerica.com, paypal.com (alerts only)
  - apple.com (App Store), google.com (Play Store)

Note: 'unsubscribe' in footer is NOT a block signal
```

### P2: Safe Prelink (FREE, Primary Keys Only)

```
Extract with regex:
  - order_id: /order[#:\s]*([A-Z0-9-]{5,})/i
  - tracking_number: /tracking[#:\s]*([A-Z0-9]{10,})/i, /1Z[A-Z0-9]{16}/

Link rules:
  1. If order_id AND order_key_by_order_id[order_id] exists
     → Link email to existing Order
  2. Else if tracking_number AND order_key_by_tracking[tracking_number] exists
     → Link email to existing Order
  3. Else → Unlinked, continue to P3
```

### P2.5: Thread-ID Soft Hint (FREE)

```
Condition:
  - Email is unlinked from P2
  - threadId exists
  - merchant_domain matches EXACTLY one Order in last 30 days

Action:
  - Add email_id to Order.source_email_ids

State updates:
  ALLOW:  [ship_date, delivery_date]   # Updates lifecycle clock
  FORBID: [order_id, item_summary, amount, merchant_name]  # Protects identity

Trust gates (ALL must pass):
  1. Only update ship_date if Order.ship_date is NULL
  2. Only update delivery_date if Order.delivery_date is NULL
  3. P3 email_type must match the date being updated:
     - email_type = shipping  → may update ship_date
     - email_type = delivery  → may update delivery_date
```

### P3: Sentinel Classification (Rules First)

```
Keyword matching (case-insensitive):
  delivery_keywords:  ["delivered", "was delivered", "left at your door"]
  shipping_keywords:  ["shipped", "on the way", "has shipped", "tracking"]
  confirmation_keywords: ["order confirmed", "thanks for your order", "receipt"]

Output:
  - email_type: confirmation | shipping | delivery | other
  - purchase_confirmed: boolean

purchase_confirmed = true if:
  - order_id extracted, OR
  - confirmation_keywords hit AND amount extracted, OR
  - confirmation_keywords hit AND strong purchase phrase

Seed rules:
  - confirmation + purchase_confirmed → Create full Order
  - shipping/delivery + tracking_number → Create partial Order
  - Otherwise → Do not create Order
```

### P4: Targeted Extraction (Minimize Body Fetch)

```
Fetch body only if:
  - Need order_id/tracking/date/amount not found in metadata
  - Return anchor found and want policy extraction
  - User opened Order detail (on-demand enrichment)

Rules extract (FREE):
  - order_id, tracking_number
  - amount, currency
  - order_date, ship_date, delivery_date
  - return_portal_link candidate
  - item_summary (fallback: cleaned subject)

Return anchor detection:
  Keywords: ["return", "returns", "return by", "return within", "refund"]
  If any anchor hit → Run P5 LLM extraction
```

### P5: LLM Return Policy Extraction (Evidence-First)

```
Run if: Return anchor detected AND template_cache miss

Input to LLM:
  - subject
  - snippet
  - context_window around anchors (≤1000 chars, original text)

Required output JSON:
{
  "deadline_date": "YYYY-MM-DD" | null,
  "window_days": number | null,
  "confidence": "exact" | "estimated" | "unknown",
  "quote": "string" | null
}

HARD VALIDATION RULES:
  1. If quote is null → confidence = unknown
  2. If deadline_date not literally in quote → deadline_date = null, confidence = unknown
  3. If window_days not literally in quote → window_days = null, confidence = unknown
  4. No guessing from general merchant knowledge

Post-validation: validateEvidence(output) → normalized_output

Caching (optional):
  template_hash = hash(body with IDs/dates stripped)
  template_cache[template_hash] = normalized_output
```

### P6: Order Keying & Upsert (FREE)

```
Keying rules (priority order):
  1. If order_id → order_key = hash(user_id + merchant_domain + order_id)
     Update: order_key_by_order_id[order_id] = order_key

  2. Else if tracking_number → order_key = hash(user_id + merchant_domain + tracking_number)
     Update: order_key_by_tracking[tracking_number] = order_key

  3. Else → order_key = hash(user_id + merchant_domain + email_id)
     Log: "TEMP_ORDER_KEY" (expected V1 duplicates)

Merge policy:
  - If order_key exists → Merge into existing Order
  - Else → Create new Order
  - Append email_id to source_email_ids
  - Store OrderEmail record

SAFE MERGE ESCALATION:
  If email contains BOTH order_id AND tracking_number
  AND they map to DIFFERENT existing Orders
  → Merge tracking-keyed Order into order_id-keyed Order
  → Delete tracking-keyed Order
  → Update order_key_by_tracking to point to merged Order
```

### P7: Apply Event & Compute Deadline (FREE)

```
Event updates by email_type:

  confirmation:
    - purchase_date = min(existing, extracted_order_date or received_at)
    - item_summary = best available (extracted > subject fallback)
    - amount, currency
    - order_id, tracking_number (if present)
    - return_window_days, explicit_return_by_date (from LLM if valid)
    - evidence_quote, evidence_message_id (if policy extracted)

  shipping:
    - ship_date
    - tracking_number → update index

  delivery:
    - delivery_date
    - tracking_number, order_id → update indices

  thread-hinted:
    Trust gates (ALL must pass):
      - Only update ship_date if current value is NULL AND email_type = shipping
      - Only update delivery_date if current value is NULL AND email_type = delivery
    Forbidden: order_id, item_summary, amount, merchant_name

Compute return_by_date:
  1. If explicit_return_by_date → return_by_date = explicit; confidence = exact
  2. Else if return_window_days:
     anchor = delivery_date ?? purchase_date
     return_by_date = anchor + return_window_days
     confidence = estimated
  3. Else → return_by_date = null; confidence = unknown

Alert safety:
  - Only alert if confidence = exact
  - OR confidence = estimated AND delivery_date exists
  - NEVER alert for unknown
```

---

## Implementation Phases

### Phase 1: Storage & Data Model

**Files to create/modify:**
- `extension/modules/storage/schema.ts` - Type definitions
- `extension/modules/storage/store.ts` - chrome.storage.local wrapper
- `extension/modules/storage/indices.ts` - Index management

**Acceptance Criteria:**
- [ ] Order and OrderEmail types defined
- [ ] `getOrder(order_key)` returns Order or null
- [ ] `upsertOrder(order)` creates or updates Order
- [ ] `linkEmailToOrder(email_id, order_key)` updates indices
- [ ] `findOrderByOrderId(order_id)` uses index lookup
- [ ] `findOrderByTracking(tracking_number)` uses index lookup
- [ ] `isEmailProcessed(email_id)` returns boolean
- [ ] `markEmailProcessed(email_id)` adds to processed set
- [ ] All operations are atomic (single chrome.storage.local.set call)

---

### Phase 2: Pipeline Core (P1-P3)

**Files to create/modify:**
- `extension/modules/pipeline/filter.ts` - P1 blocklist
- `extension/modules/pipeline/prelink.ts` - P2 primary key linking
- `extension/modules/pipeline/classifier.ts` - P3 email type classification

**Acceptance Criteria:**
- [ ] `isBlocked(merchant_domain)` returns true for blocklist domains
- [ ] `extractPrimaryKeys(subject, snippet)` returns { order_id?, tracking_number? }
- [ ] `findExistingOrder(order_id, tracking_number)` returns Order or null
- [ ] `classifyEmail(subject, snippet)` returns { email_type, purchase_confirmed }
- [ ] Grocery emails (Whole Foods, Instacart) blocked
- [ ] Subscription emails (Netflix, Spotify) blocked
- [ ] Rideshare emails (Uber, Lyft) blocked
- [ ] Order confirmation with order_id creates Order
- [ ] Shipping email with tracking links to existing Order

---

### Phase 3: Pipeline Extraction (P4-P5)

**Files to create/modify:**
- `extension/modules/pipeline/extractor.ts` - P4 rules extraction
- `extension/modules/pipeline/llm.ts` - P5 LLM return policy
- `extension/modules/pipeline/evidence.ts` - Quote validation

**Acceptance Criteria:**
- [ ] `extractFields(subject, body)` returns order_id, tracking, dates, amount
- [ ] `detectReturnAnchors(text)` returns boolean
- [ ] `extractReturnPolicy(subject, snippet, body_context)` calls LLM
- [ ] `validateEvidence(llm_output)` enforces quote presence
- [ ] If quote is null → confidence becomes unknown
- [ ] If deadline_date not in quote → deadline_date becomes null
- [ ] Template caching reduces duplicate LLM calls

---

### Phase 4: Pipeline Resolution (P6-P7)

**Files to create/modify:**
- `extension/modules/pipeline/resolver.ts` - P6 keying and merge
- `extension/modules/pipeline/lifecycle.ts` - P7 event application

**Acceptance Criteria:**
- [ ] `computeOrderKey(user_id, merchant_domain, order_id?, tracking?, email_id)` returns stable key
- [ ] `mergeEmailIntoOrder(order, email, extracted_data)` updates Order fields
- [ ] `handleMergeEscalation(order_id, tracking_number)` merges split Orders
- [ ] `computeReturnByDate(order)` applies priority rules
- [ ] `computeDeadlineConfidence(order)` returns exact/estimated/unknown
- [ ] Confirmation email sets purchase_date, item_summary, amount
- [ ] Delivery email sets delivery_date and recomputes return_by_date
- [ ] Thread-hinted emails update dates only if NULL and email_type matches
- [ ] Thread-hinted emails never update identity fields (order_id, item_summary, amount)

---

### Phase 5: Background Sync

**Files to create/modify:**
- `extension/background.js` - Service worker updates
- `extension/modules/sync/scanner.ts` - Gmail scanning
- `extension/modules/sync/refresh.ts` - Incremental refresh

**Acceptance Criteria:**
- [ ] `scanPurchases()` fetches category:purchases from Gmail
- [ ] Incremental scan uses `after:[last_date]` filter
- [ ] `chrome.alarms` schedules periodic background scan
- [ ] Tab focus triggers scan if >10 minutes since last
- [ ] Refresh button in sidebar triggers immediate scan
- [ ] `last_scan_epoch_ms` and `last_scan_internal_date_ms` persisted

---

### Phase 6: UI - Sidebar Shell

**Files to create/modify:**
- `extension/sidebar/sidebar.html` - Iframe container
- `extension/sidebar/sidebar.js` - Main sidebar logic
- `extension/sidebar/styles.css` - Isolated styles

**Acceptance Criteria:**
- [ ] Sidebar renders in iframe (isolated from Gmail CSS)
- [ ] Width fixed at 300px, no Gmail layout squeeze
- [ ] Links open in Gmail tab (target=_top)
- [ ] Refresh button visible in header
- [ ] Loading state shown during scan

---

### Phase 7: UI - Order Cards

**Files to create/modify:**
- `extension/sidebar/components/order-card.js`
- `extension/sidebar/components/section.js`

**Acceptance Criteria:**
- [ ] Return Watch section shows deadline-known orders only
- [ ] "Expiring Soon" subsection for days_remaining <= 7
- [ ] "Active" subsection for days_remaining > 7
- [ ] All Purchases section shows all orders
- [ ] Order card displays: merchant, item_summary, return_by_date, days_remaining
- [ ] Expiring Soon cards show countdown badge
- [ ] Empty states render correctly

---

### Phase 8: UI - Order Detail

**Files to create/modify:**
- `extension/sidebar/components/order-detail.js`
- `extension/sidebar/components/evidence-panel.js`

**Acceptance Criteria:**
- [ ] Clicking Order card opens detail view
- [ ] Detail shows full order info (dates, amount, tracking)
- [ ] "Show Evidence" displays evidence_quote
- [ ] "View Email" opens source email in Gmail (via Router or target=_top)
- [ ] On-demand enrichment triggers if deadline_confidence = unknown
- [ ] Skeleton loader shows "Checking return policy..." during enrichment
- [ ] "Mark as Returned" button updates order_status
- [ ] "Dismiss" button updates order_status

---

### Phase 9: Diagnostics & Logging

**Files to create/modify:**
- `extension/modules/diagnostics/logger.ts`

**Acceptance Criteria:**
- [ ] Pipeline logs decision per email_id (blocked, skipped, linked, created, updated)
- [ ] Logs "MERGE_BY_ORDER_ID" or "MERGE_BY_TRACKING" on link
- [ ] Logs "TEMP_ORDER_KEY" on fallback keying
- [ ] Logs evidence validation failures
- [ ] Console logs filterable by "[ReturnWatch]" prefix

---

## Test Harness

### Synthetic Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| 1 | Confirmation with order_id + "30-day returns" quote | Order created, return_window_days=30, confidence=estimated |
| 2 | Shipping with tracking_number (same order) | Links to existing Order, sets ship_date |
| 3 | Delivery with same order_id | Sets delivery_date, computes return_by_date |
| 4 | Promo/discount email | Blocked or rejected, no Order |
| 5 | Grocery (Whole Foods) | Blocked, no Order |
| 6 | Second confirmation, same merchant, no order_id | Separate temp Order (no fuzzy merge) |
| 7 | Shipping email with only tracking, then delivery with order_id + tracking | Merge escalation triggers, one Order remains |
| 8 | Email with "Return by January 30, 2026" in body | confidence=exact, explicit_return_by_date set |
| 9 | Netflix subscription renewal | Blocked, no Order |
| 10 | Amazon order, no return policy in email | Order created, confidence=unknown, not in Return Watch |
| 11 | Thread-hinted delivery email, Order already has delivery_date | No update (trust gate: NULL check fails) |
| 12 | Thread-hinted shipping email trying to set delivery_date | No update (trust gate: email_type mismatch) |

### Assertions

- [ ] Only ONE Order card for confirmation+shipping+delivery chain
- [ ] Return Watch shows orders with computed return_by_date
- [ ] All Purchases shows orders even if deadline unknown
- [ ] No fuzzy merge occurs in any test case
- [ ] Evidence quote matches return policy text in email

---

## File Structure

```
extension/
├── background.js                 # Service worker (existing, modify)
├── manifest.json                 # (existing, modify for alarms)
├── sidebar/
│   ├── sidebar.html              # Iframe container
│   ├── sidebar.js                # Main sidebar logic
│   ├── styles.css                # Isolated styles
│   └── components/
│       ├── order-card.js
│       ├── order-detail.js
│       ├── evidence-panel.js
│       └── section.js
└── modules/
    ├── storage/
    │   ├── schema.ts
    │   ├── store.ts
    │   └── indices.ts
    ├── pipeline/
    │   ├── filter.ts
    │   ├── prelink.ts
    │   ├── classifier.ts
    │   ├── extractor.ts
    │   ├── llm.ts
    │   ├── evidence.ts
    │   ├── resolver.ts
    │   └── lifecycle.ts
    ├── sync/
    │   ├── scanner.ts
    │   └── refresh.ts
    └── diagnostics/
        └── logger.ts
```

---

## Cost Estimate

Per 100 emails scanned:
- P1 Filter: 100 × $0 = $0
- P2-P3 Prelink/Classify: 100 × $0 = $0
- P4 Extract (rules): ~35 × $0 = $0
- P5 LLM (return anchors only): ~10 × $0.0002 = $0.002

**Total per 100 emails: ~$0.002**

Monthly (500 emails/user): **~$0.01/user**

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.6 | 2026-01-15 | Initial locked MVP spec |
| 0.6.1 | 2026-01-15 | Added refresh, on-demand enrichment, thread-hint |
