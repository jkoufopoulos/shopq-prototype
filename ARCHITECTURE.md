# Reclaim — Architecture Document

> **Last updated**: 2026-02-10
> **Status**: Living document — every non-trivial claim cites source as `path/file.ext:lineN::symbol`

---

## 1. Overview

Reclaim is a Gmail companion that **detects online purchases from email** and **tracks return deadlines** so users never miss a return window. It consists of a **Chrome Extension** (MV3) that scans Gmail and a **Python FastAPI backend** that runs a cost-optimized 3-stage AI extraction pipeline.

### 1.1 Trust Model

Reclaim processes high-trust inbox data. This section documents exactly what data is accessed, how it's handled, and where trust boundaries exist.

#### 1.1.1 OAuth Scopes & Least-Privilege

| Scope | Where Defined | Purpose | Least-Privilege? |
|-------|--------------|---------|-----------------|
| `gmail.readonly` | `extension/manifest.json:55` | Read emails (no send/delete) | Yes — read-only |
| `userinfo.profile` | `extension/manifest.json:56` | Get user ID for data isolation | Yes — minimal profile |

**Backend OAuth** (`reclaim/gmail/oauth.py:32-35`): Requests only `gmail.readonly` for server-side flows.

**Evaluation**: Scopes are appropriately minimal. No write access to Gmail. No access to contacts, calendar, or drive.

#### 1.1.2 PII & Redaction

Raw email content flows through the pipeline but is **never stored verbatim**. Redaction occurs at multiple points:

| Function | File | What It Does |
|----------|------|-------------|
| `redact()` | `reclaim/utils/redaction.py:32-39` | SHA256 hash (12 chars) for stable log correlation |
| `redact_subject()` | `reclaim/utils/redaction.py:42-67` | Truncates to 30 chars + hash for logging |
| `redact_pii()` | `reclaim/utils/redaction.py:70-122` | Replaces emails→`[EMAIL]`, phones→`[PHONE]`, cards→`[CARD]`, SSNs→`[SSN]`, addresses→`[ADDRESS]`, zips→`[ZIP]`, names→`[NAME]` |
| `sanitize_llm_input()` | `reclaim/utils/redaction.py:125-183` | Strips prompt injection patterns, control chars, template markers before LLM calls |

**Data flow**:
1. Raw email body enters pipeline (`extractor.py:217`)
2. Body truncated to 4000 chars before LLM (`config.py:29::PIPELINE_BODY_TRUNCATION`)
3. `sanitize_llm_input()` strips injection attempts before classifier (`returnability_classifier.py:292`) and field extractor (`field_extractor.py:167`)
4. Evidence snippet PII-redacted before storage (`field_extractor.py:283`, max 200 chars)
5. Full email body is **never persisted** — only extracted fields and redacted snippets

#### 1.1.3 Data Inventory

| Data Class | Where Stored | Retention | Encryption |
|-----------|-------------|-----------|------------|
| Raw email body | **Nowhere** — transient in pipeline only | Request lifetime | N/A |
| Extracted fields (merchant, item, dates) | SQLite `return_cards` table (`database_schema.py:146-184`) + `chrome.storage.local` | Indefinite | At rest: no |
| Evidence snippet | `return_cards.evidence_snippet` | Indefinite | PII-redacted via `redact_pii()` |
| OAuth tokens (backend) | `user_credentials` table (`database_schema.py:126-143`) | Until revoked | Fernet encryption (`settings.py::RECLAIM_ENCRYPTION_KEY`) |
| OAuth tokens (extension) | Chrome identity API (managed by browser) | Browser-managed | Chrome-managed |
| Gmail message IDs | `return_cards.source_email_ids` (JSON array) | Indefinite | No (opaque IDs) |
| User profile (id, email) | `chrome.storage.local.authenticatedUserId` | Until sign-out | No |
| LLM usage counters | `llm_usage` table (`database_schema.py:187-202`) | Indefinite | No (aggregate counts only) |

#### 1.1.4 Trust Boundaries

```
Browser (User Device)                 Google Cloud              Third Parties
─────────────────────                 ────────────              ─────────────
Sidebar ◄─postMessage─► Content       Backend (Cloud Run)       Gemini LLM
                        Script ─┐     ├── SQLite DB             Uber Direct
Popup ──chrome.runtime──► Svc   │     └── Gmail API proxy
                        Worker ─┤
                          │     │
                    chrome.storage
                      .local    │
                                │
             fetch + Bearer ────┴──► Backend ──sanitized──► Gemini
                                     prompt
```

| Boundary | Auth Mechanism | Reference |
|----------|---------------|-----------|
| Extension → Backend | Bearer token + CORS + CSRF origin check | `app.py:64-88`, `middleware/csrf.py:76-157` |
| Extension → Gmail API | OAuth2 via Chrome identity, read-only | `manifest.json:55-56` |
| Backend → LLM | Input sanitized via `sanitize_llm_input()` | `utils/redaction.py:125-183` |
| Sidebar ↔ Content Script | `postMessage` with origin validation | `src/content.js:140` |

---

## 2. How to Run

### 2.1 Backend

```bash
# Install dependencies
uv sync

# Set environment (see .env.example for full list)
cp .env.example .env
# Required: GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT

# Run development server
uv run uvicorn reclaim.api.app:app --reload --port 8000

# Code quality
make fmt        # Auto-format (ruff)
make lint       # Check formatting + linting
make typecheck  # mypy
make ci         # Full pipeline: lint + typecheck + test

# Tests (LLM disabled — no API costs)
PYTHONPATH=. RECLAIM_USE_LLM=false uv run pytest tests/ -v
```

### 2.2 Extension

```bash
cd extension
npm install
npm run build    # Production webpack bundle
npm run watch    # Dev with hot reload
npm test         # Unit tests
```

Load in Chrome: `chrome://extensions` → Developer mode → Load unpacked → select `extension/`

### 2.3 Production Deployment

```bash
# Deploy to Cloud Run (see deploy.sh)
./deploy.sh
# Builds Docker image, deploys to us-central1
# 512Mi memory, 1 CPU, 10 concurrent requests
```

### 2.4 Key Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `GOOGLE_API_KEY` | Dev | — | Gemini API key (local dev) |
| `GOOGLE_CLOUD_PROJECT` | Prod | `shopq-467118` | GCP project for Vertex AI |
| `RECLAIM_ENV` | No | `development` | Environment mode |
| `RECLAIM_USE_LLM` | No | `false` | Enable LLM calls (set `false` for tests) |
| `GEMINI_MODEL` | No | `gemini-2.0-flash-001` | LLM model ID |
| `GEMINI_TEMPERATURE` | No | `0.1` | LLM temperature (low = deterministic) |
| `RECLAIM_EXTENSION_IDS` | Prod | — | Comma-separated allowed extension IDs |
| `RECLAIM_ENCRYPTION_KEY` | Prod | — | Fernet key for OAuth token encryption |
| `UBER_DIRECT_MOCK` | No | `true` | Use mock Uber API |

Full list: `.env.example` (70+ variables)

---

## 3. System Components

### 3.1 Repo Map

```
reclaim/                        # Python FastAPI backend
├── api/
│   ├── app.py                  # FastAPI app, middleware stack, route registration
│   ├── routes/
│   │   ├── returns.py          # CRUD + extraction endpoints (/api/returns/*)
│   │   ├── delivery.py         # Uber Direct pickup endpoints (/api/delivery/*)
│   │   └── health.py           # Health checks (/health, /health/db, /debug/stats)
│   └── middleware/
│       ├── user_auth.py        # Google OAuth token validation (SEC-005)
│       ├── csrf.py             # Origin validation on mutations (SEC-006/007)
│       ├── rate_limit.py       # Per-IP rate limiting (60/min, 1000/hr)
│       └── security_headers.py # CSP, HSTS, X-Frame-Options
├── returns/                    # Core domain
│   ├── models.py               # ReturnCard, ReturnStatus, ReturnConfidence
│   ├── types.py                # FilterResult, ExtractionResult, ExtractionStage
│   ├── extractor.py            # Pipeline orchestrator (3-stage + dedup + cancellation)
│   ├── filters.py              # Stage 1: Domain blocklist/allowlist + heuristics
│   ├── filter_data.py          # Blocklists, grocery patterns, survey keywords
│   ├── returnability_classifier.py  # Stage 2: LLM returnability check
│   ├── field_extractor.py      # Stage 3: LLM field extraction + date computation
│   ├── repository.py           # SQLite persistence (ReturnCardRepository)
│   └── service.py              # Business logic layer (ReturnsService)
├── delivery/                   # Uber Direct integration (experimental)
│   ├── service.py              # Delivery orchestration
│   └── models.py               # Delivery data models
├── infrastructure/
│   ├── database.py             # Connection pool, WAL mode, @retry_on_db_lock
│   ├── database_schema.py      # CREATE TABLE statements (idempotent)
│   ├── settings.py             # Environment variable loading
│   ├── retry.py                # RetryPolicy + CircuitBreaker
│   ├── idempotency.py          # Email dedup key generation
│   └── llm_budget.py           # Per-user + global LLM call budget (SCALE-001)
├── gmail/
│   ├── oauth.py                # Server-side OAuth flow + token management
│   └── parser.py               # MIME parsing → ParsedEmail
├── llm/
│   ├── gemini.py               # Vertex AI / google-generativeai model init
│   ├── client.py               # LLM abstraction with caching + validation
│   └── retry.py                # Tenacity-based LLM retry (exponential backoff)
├── utils/
│   ├── redaction.py            # PII redaction, prompt sanitization
│   └── error_sanitizer.py      # Safe error messages for HTTP responses
├── observability/
│   ├── logging.py              # Structured logging setup
│   └── telemetry.py            # In-memory counters, latency tracking (P95/P99)
└── config.py                   # Re-exports settings + typed constants

extension/                      # Chrome Extension (Manifest V3)
├── manifest.json               # Permissions, CSP, OAuth config, content scripts
├── background.js               # Service worker: 40+ message handlers, alarm setup
├── src/
│   ├── content.js              # Webpack entry: InboxSDK sidebar injection
│   └── config.js               # ES module config for webpack bundle
├── returns-sidebar-inner.js    # Sidebar UI: list/detail views, actions
├── returns-sidebar-delivery.js # Delivery modal (Uber pickup flow)
├── popup.js                    # Popup: stats + scan trigger
├── popup.html                  # Popup layout
├── returns-sidebar.html        # Sidebar iframe shell
├── modules/
│   ├── shared/config.js        # CONFIG object (loaded via importScripts)
│   ├── returns/api.js          # Backend API client (all endpoints)
│   ├── gmail/
│   │   ├── auth.js             # Chrome identity OAuth + token validation
│   │   └── api.js              # Gmail API requests with retry
│   ├── sync/
│   │   ├── scanner.js          # Email scan orchestration
│   │   └── refresh.js          # Scan triggers (tab focus, periodic, manual)
│   ├── pipeline/               # Client-side filter, classifier, extractor, linker
│   └── storage/
│       ├── schema.js           # Storage key definitions
│       └── store.js            # chrome.storage.local with mutex lock
├── webpack.config.js           # Bundles src/content.js → dist/content.bundle.js
└── dist/                       # Built artifacts

config/
├── merchant_rules.yaml         # 24 merchants + _default (return windows, anchors)

Makefile                        # fmt, lint, typecheck, test, ci, temporal-eval
Dockerfile                      # python:3.11-slim, uvicorn on port 8080
deploy.sh                       # gcloud run deploy to us-central1
```

### 3.2 Entrypoints

| Entrypoint | Type | File | Description |
|-----------|------|------|-------------|
| FastAPI server | HTTP | `reclaim/api/app.py:29` | Backend API (uvicorn) |
| Service worker | Browser | `extension/background.js` | Extension background (alarms, messages) |
| Content script | Injected | `extension/dist/content.bundle.js` | Gmail page injection (sidebar) |
| Popup | Browser | `extension/popup.html` + `popup.js` | Extension popup UI |
| Sidebar | iframe | `extension/returns-sidebar.html` + `returns-sidebar-inner.js` | Gmail sidebar panel |

---

## 4. Core Flows

### 4.1 Flow A: Discovery Loop (Inbox Scan → Detection → Extraction → Storage)

```
Trigger (alarm/tab/manual)
  │
  ▼
Service Worker                        Gmail API
  │── messages.list(category:purchases) ──►│
  │◄── message IDs ───────────────────────│
  │── messages.get(id) per message ──────►│
  │◄── headers + snippet ────────────────│
  │
  ▼
POST /api/returns/process-batch ────────► Backend
                                           │
                              ┌────────────┤ Per email:
                              │            │
                              │  Stage 1: Domain Filter (FREE)     filters.py:85
                              │    ↓ ~30% pass
                              │  Stage 2: Budget Check             llm_budget.py:52
                              │    ↓ if within limit
                              │  Stage 3: LLM Classify (~$0.0001) classifier.py:194
                              │    ↓ if returnable
                              │  Stage 4: LLM Extract (~$0.0002)  field_extractor.py:101
                              │    ↓
                              │  Build ReturnCard + deadline
                              │    ↓
                              └────► Deduplicate (3-pass)          extractor.py:646
                                     Suppress cancellations        extractor.py:465
                                           │
  ◄── {cards[], stats} ───────────────────│
  │
  ▼
chrome.storage.local (upsert w/ mutex)    store.js:63
  │
  ▼
Notify sidebar → re-render                refresh.js:139
```

**Scan triggers** (`extension/modules/sync/refresh.js:111-150`):

| Trigger | Condition | Window |
|---------|-----------|--------|
| `on_gmail_load` | Gmail tab loads + >6h since last scan | 14 days |
| `on_tab_focus` | Gmail tab focused + >10min since last scan | 7 days |
| `periodic` | Chrome alarm every 45min | 3 days |
| `manual_refresh` | User clicks refresh button | 7 days |

**Failure modes**:
- **Gmail API 429/500/503**: Exponential backoff with retry (`extension/modules/gmail/api.js:33-67`)
- **Backend unreachable**: 10s timeout, error shown in sidebar toast
- **LLM timeout/error**: Tenacity retry (3 attempts, 1-10s backoff) (`reclaim/llm/retry.py:24-62`)
- **Budget exceeded**: Email skipped with `budget_exceeded` reason, no LLM call made
- **Storage mutex contention**: Promise-chain serializes writes (`extension/modules/storage/store.js:23-66`)

**Idempotency**: Duplicate emails detected via `(message_id, received_ts, body_hash)` key (`reclaim/infrastructure/idempotency.py:20-33`). Extension also tracks `processed_email_ids` in `chrome.storage.local` (`extension/modules/storage/schema.js:115`).

### 4.2 Flow B: Return Action (User Marks Return / Triggers Pickup)

There is **no automated fulfillment orchestration** — Reclaim currently surfaces deadlines and lets users act. Two action paths exist:

#### B1: Mark as Returned / Dismissed

```
User clicks "Mark as Returned"
  → Sidebar posts RECLAIM_UPDATE_ORDER_STATUS       sidebar-inner.js:279
    → Content script sends UPDATE_ORDER_STATUS      src/content.js:420
      → Service worker calls PUT /api/returns/{id}  returns.py:334
        → Backend updates DB, returns card
      ← upsert into chrome.storage.local
    ← RECLAIM_STATUS_UPDATED
  ← Toast + refresh list
```

#### B2: Courier Pickup (Uber Direct — Experimental)

```
User clicks "Courier Pickup with Uber"         sidebar-delivery.js:29
  │
  ├─ 1. Get/set pickup address                 → chrome.storage.local
  ├─ 2. GET /api/delivery/locations             → Uber: nearby drop-offs
  ├─ 3. User selects location
  ├─ 4. POST /api/delivery/quote                → Uber: price + ETA
  ├─ 5. User confirms
  └─ 6. POST /api/delivery/confirm              → Uber: dispatch driver
       └─ Sidebar shows confirmation + tracking badge
```

**Note**: Uber Direct is behind `UBER_DIRECT_MOCK=true` by default (`.env.example:179`). Real API requires client credentials.

### 4.3 Flow C: Persistence (Return Window Tracking Across Sessions)

Return data is persisted in **two locations** that stay synchronized:

```
chrome.storage.local (primary)  ◄──scan results──►  SQLite reclaim.db (secondary)
├── orders_by_key                                    ├── return_cards
├── processed_email_ids                              ├── llm_usage
├── merchant_rules_by_domain                         └── deliveries
└── last_scan_epoch_ms
```

**Extension storage schema** (`extension/modules/storage/schema.js:106-121`):

| Key | Type | Content |
|-----|------|---------|
| `orders_by_key` | Object | `{order_key: {merchant, dates, status, ...}}` |
| `order_key_by_order_id` | Object | `{order_id: order_key}` — dedup index |
| `order_key_by_tracking` | Object | `{tracking_number: order_key}` |
| `order_keys_by_merchant` | Object | `{domain: [order_keys]}` — merchant index |
| `order_emails_by_id` | Object | `{email_id: {metadata, extraction_result}}` |
| `processed_email_ids` | Array | Gmail message IDs already processed |
| `merchant_rules_by_domain` | Object | `{domain: days}` — user overrides |
| `last_scan_epoch_ms` | Number | Timestamp of last scan |
| `user_address` | Object | Saved pickup address for Uber |

**Backend schema** (`reclaim/infrastructure/database_schema.py:146-184`):

`return_cards` table with composite index on `(user_id, status, return_by_date)`.

**Status lifecycle** (`reclaim/returns/models.py:131-159::compute_status`):

```
                    ┌──────────┐
                    │  ACTIVE  │
                    └────┬─────┘
                         │ days <= threshold (7)
                    ┌────▼──────────┐
                    │ EXPIRING_SOON │
                    └────┬──────────┘
                         │ days <= 0
                    ┌────▼─────┐
                    │ EXPIRED  │
                    └──────────┘

    User action:     RETURNED  (terminal)
    User action:     DISMISSED (terminal)
```

**How deadlines are computed** (`reclaim/returns/field_extractor.py::_compute_return_by_date`):

| Priority | Source | Confidence |
|----------|--------|-----------|
| 1 | Explicit return-by date found in email text | `EXACT` |
| 2 | `delivery_date + merchant_rules.days` | `ESTIMATED` |
| 3 | `order_date + merchant_rules.days` | `ESTIMATED` |
| 4 | No date information available | `UNKNOWN` |

Merchant rules loaded from `config/merchant_rules.yaml` (24 merchants + `_default`: 30 days, delivery anchor).

**When browser is closed**: No background sync occurs. Chrome alarms only fire while Chrome is running. Scans resume on next Gmail tab load (14-day window catch-up). There is no server-side cron or push notification system. See [Open Questions](#9-open-questions--todos).

---

## 5. Data Model

### 5.1 ReturnCard (Core Domain Model)

**Definition**: `reclaim/returns/models.py:40-227`

```
ReturnCard
├── Identity
│   ├── id: UUID
│   ├── user_id: str
│   └── version: "v1"
├── Core
│   ├── merchant: str                    # "Amazon"
│   ├── merchant_domain: str             # "amazon.com"
│   ├── item_summary: str                # "Wireless Headphones"
│   ├── status: ReturnStatus             # ACTIVE | EXPIRING_SOON | EXPIRED | RETURNED | DISMISSED
│   ├── confidence: ReturnConfidence     # EXACT | ESTIMATED | UNKNOWN
│   └── source_email_ids: list[str]      # Gmail message IDs
├── Order Info
│   ├── order_number: str?
│   ├── tracking_number: str?
│   ├── amount: float?
│   └── currency: str = "USD"
├── Dates
│   ├── order_date: date?
│   ├── delivery_date: date?
│   └── return_by_date: date?            # The key deadline
├── Links
│   ├── return_portal_link: str?         # Merchant return URL
│   └── shipping_tracking_link: str?
├── Evidence
│   ├── evidence_snippet: str?           # PII-redacted excerpt
│   └── notes: str?                      # User notes
└── Timestamps
    ├── created_at: datetime (UTC)
    ├── updated_at: datetime (UTC)
    └── alerted_at: datetime? (UTC)
```

**Key methods**:
- `is_alertable()` — `models.py:107-118`: True if confidence is EXACT/ESTIMATED, status is ACTIVE/EXPIRING_SOON, and not yet alerted
- `days_until_expiry()` — `models.py:120-129`: Integer days remaining (min 0)
- `compute_status()` — `models.py:131-159`: Derives status from `return_by_date` vs current date
- `to_db_dict()` / `from_db_row()` — `models.py:161-227`: Serialization for SQLite

### 5.2 Database Tables

**Full schema**: `reclaim/infrastructure/database_schema.py:36-244`

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| `return_cards` | Core return tracking | id, user_id, merchant, status, return_by_date |
| `llm_usage` | LLM budget enforcement | user_id, call_type, call_date, call_count |
| `deliveries` | Uber Direct pickups | order_key, status, quote, driver info |
| `user_credentials` | Encrypted OAuth tokens | user_id, encrypted_token, token_expiry |
| `rules` | Classification rules (legacy) | pattern_type, pattern, category |
| `feedback` | User corrections (legacy) | predicted_label, actual_label |

---

## 6. Integrations

### 6.1 Gmail API

| Aspect | Detail | Reference |
|--------|--------|-----------|
| **Client** | Extension-side via Chrome identity API | `extension/modules/gmail/api.js` |
| **Auth** | `chrome.identity.getAuthToken()` | `extension/modules/gmail/auth.js:67-118` |
| **Token validation** | Every 5min via tokeninfo endpoint | `extension/modules/gmail/auth.js:15-58` |
| **Search queries** | `category:purchases`, cancellation subjects | `extension/modules/gmail/api.js:79-150` |
| **Rate limiting** | 100ms delay between requests | `extension/modules/shared/config.js:48` |
| **Retry** | Exponential backoff on 429/500/503 | `extension/modules/gmail/api.js:33-67` |

### 6.2 Gemini LLM (Vertex AI)

| Aspect | Detail | Reference |
|--------|--------|-----------|
| **Model** | `gemini-2.0-flash-001` | `reclaim/infrastructure/settings.py:28` |
| **Init** | Vertex AI (prod) or google-generativeai (dev) | `reclaim/llm/gemini.py:28-98` |
| **Temperature** | 0.1 (deterministic) | `reclaim/infrastructure/settings.py:31` |
| **Max tokens** | 1024 | `reclaim/infrastructure/settings.py:30` |
| **Retry** | 3 attempts, 1-10s exponential backoff | `reclaim/llm/retry.py:24-62` |
| **Budget** | 500 calls/user/day, 10000 global/day | `reclaim/config.py:55-56` |
| **Input sanitization** | `sanitize_llm_input()` strips injection patterns | `reclaim/utils/redaction.py:125-183` |
| **Caching** | 24h TTL keyed by (prompt_hash, email_key) | `reclaim/llm/client.py` |

**What is sent to the LLM**: Truncated email body (4000 chars max), subject, from address. All sanitized via `sanitize_llm_input()`. No raw PII — but email content inherently contains personal data. LLM responses are validated against Pydantic schemas.

### 6.3 Uber Direct (Experimental)

| Aspect | Detail | Reference |
|--------|--------|-----------|
| **Status** | Mock mode by default | `.env.example:179::UBER_DIRECT_MOCK=true` |
| **Endpoints** | locations, quote, confirm, status, cancel | `extension/modules/returns/api.js:345-397` |
| **Backend proxy** | `/api/delivery/*` routes | `reclaim/api/routes/delivery.py` |

### 6.4 InboxSDK

| Aspect | Detail | Reference |
|--------|--------|-----------|
| **Purpose** | Inject sidebar panel into Gmail UI | `extension/src/content.js:288` |
| **Page world** | `pageWorld.js` injected via `chrome.scripting.executeScript()` | `extension/background.js:7-28` |
| **CSP** | Allowed via `connect-src` in manifest | `extension/manifest.json:26-28` |

---

## 7. Operational Concerns

### 7.1 Logging & Metrics

**Logging** (`reclaim/observability/logging.py:1-35`):
- Standard Python `logging` module with structured format
- Level configurable via `RECLAIM_LOG_LEVEL` env var (default: INFO)
- PII redacted in all log messages via `redact()` / `redact_subject()`

**Telemetry** (`reclaim/observability/telemetry.py:1-124`):
- **In-memory only** — no external metrics platform
- `log_event(name, **fields)`: Structured event logging
- `counter(name, increment)`: In-memory counters
- `time_block(name)`: Latency tracking with P50/P95/P99 calculation
- Key counters: `returns.extraction.started`, `.rejected_filter`, `.rejected_classifier`, `.passed_*`, `llm.cache_hit`, `api.rate_limit.request_exceeded`

**Extension logging**: Console-based, no structured telemetry framework.

### 7.2 Rate Limiting

**Backend** (`reclaim/api/middleware/rate_limit.py:33-238`):

| Limit | Value | Scope |
|-------|-------|-------|
| Requests per minute | 60 | Per IP |
| Requests per hour | 1000 | Per IP |
| Response | 429 + `Retry-After` header | — |
| IP detection | Trusts `X-Forwarded-For` only from Cloud Run (via `X-Cloud-Trace-Context`) | SEC-010 |

**Extension** (`extension/background.js:80-135`):
- Message rate limiting: 100 messages per 1000ms per sender
- Prevents runaway content scripts

**Known limitation**: Backend rate limiting is **in-memory** (TTLCache). Does not work across multiple Cloud Run instances. Needs Redis for production scale.

### 7.3 Retries & Circuit Breaker

| Component | Strategy | Config | Reference |
|-----------|----------|--------|-----------|
| SQLite locks | Exponential backoff + jitter | 5 retries, 0.1-2s delay | `infrastructure/database.py:57-132` |
| LLM calls | Tenacity exponential backoff | 3 retries, 1-10s delay | `llm/retry.py:24-62` |
| Gmail API | Exponential backoff on 429/5xx | Configurable | `extension/modules/gmail/api.js:33-67` |
| Pipeline stages | RetryPolicy + CircuitBreaker | 3 attempts, 5 failures → open | `infrastructure/retry.py:24-128` |

**Circuit breaker** (`reclaim/infrastructure/retry.py:86-128`): Trips after 5 consecutive failures, auto-resets after 60s. States: `closed → open → half_open`.

### 7.4 Security Summary

| Control | Implementation | Reference |
|---------|---------------|-----------|
| **Authentication** | Google OAuth token validation, `aud` claim check | `middleware/user_auth.py:98-120` |
| **CSRF** | Origin header validation on mutations | `middleware/csrf.py:76-157` |
| **Extension whitelist** | `RECLAIM_EXTENSION_IDS` env var | `middleware/csrf.py:91-114` |
| **Rate limiting** | Per-IP with spoofing protection | `middleware/rate_limit.py` |
| **Security headers** | CSP, HSTS, X-Frame-Options DENY, Permissions-Policy | `middleware/security_headers.py:35-70` |
| **Input validation** | Pydantic models, sanitized error responses | `api/app.py:36-60` |
| **SQL injection** | Parameterized queries, column whitelist | `returns/repository.py:26-34` |
| **Prompt injection** | `sanitize_llm_input()` strips known patterns | `utils/redaction.py:125-183` |
| **PII in storage** | `redact_pii()` on evidence snippets | `utils/redaction.py:70-122` |
| **XSS (extension)** | `escapeHtml()`, `sanitizeUrl()`, DOMPurify | `returns-sidebar-inner.js:183-206` |
| **Token caching** | 10-min TTL handles revocation | `middleware/user_auth.py:42-47` |
| **DB corruption** | `PRAGMA quick_check` on new connections | `infrastructure/database.py:184-197` |

### 7.5 Privacy Considerations

- Raw email body is **transient** — never stored in database or chrome.storage
- Only extracted fields (merchant, item, dates, order IDs) are persisted
- Evidence snippets are PII-redacted before storage
- Email content is sent to Gemini LLM (Google) for classification/extraction — subject to Google's data processing terms
- No data is sent to non-Google third parties (except Uber Direct when enabled)
- No analytics, no user tracking, no telemetry exfiltration

---

## 8. Change Guide

### 8.1 Add a New Retailer

1. Edit `config/merchant_rules.yaml`:
   ```yaml
   newstore.com:
     days: 14
     anchor: order      # or "delivery"
     return_url: https://newstore.com/returns
     notes: "Optional policy clarification"
   ```
2. No code changes required — filter reads rules at startup (`reclaim/returns/filters.py:243-261`)
3. The domain will automatically be allowlisted in Stage 1

### 8.2 Modify an Extraction Prompt

**Returnability classifier** prompt: `reclaim/returns/returnability_classifier.py:102-178`
- Controls what's classified as "returnable" vs not
- Returns JSON: `{is_returnable, confidence, receipt_type, reasoning}`

**Field extractor** prompt: `reclaim/returns/field_extractor.py:101-147`
- Controls what fields are extracted from emails
- Returns JSON matching `LLMExtractionSchema`

After editing prompts, run the temporal decay eval to check for regressions:
```bash
make temporal-eval
make temporal-report
```

### 8.3 Add a Fulfillment Provider

1. Create module under `reclaim/delivery/` (follow Uber Direct pattern)
2. Add API routes in `reclaim/api/routes/delivery.py`
3. Add message types in `extension/background.js` message handler
4. Add UI in `extension/returns-sidebar-delivery.js`
5. Wire sidebar → content script → background → backend → provider

### 8.4 Modify the Extraction Pipeline

Pipeline stages are defined in `reclaim/returns/extractor.py:217-432`:
- **Add a stage**: Insert between existing stages, update `ExtractionStage` enum (`types.py:80-93`)
- **Modify dedup**: Edit 3-pass algorithm in `extractor.py:646-835`
- **Add rejection rule**: Add to empty-card check (`extractor.py:365-417`) or filter (`filters.py`)

---

## 9. Open Questions / TODOs

### Architecture Gaps

| Issue | Impact | Where to Investigate |
|-------|--------|---------------------|
| **No server-side background sync** | Deadlines can expire while browser is closed; user only catches up on next Gmail visit | Need cron/Cloud Scheduler or push notifications |
| **SQLite on ephemeral Cloud Run storage** | Database is lost on instance restart | Migrate to Cloud SQL or persistent volume |
| **In-memory rate limiting** | Bypassed with multiple Cloud Run instances | Needs Redis or Cloud Memorystore |
| **In-memory idempotency** | `_SEEN_KEYS` set lost on restart | Persist to database (`infrastructure/idempotency.py:36-48`) |
| **No user authentication on extension storage** | `chrome.storage.local` is per-profile but not encrypted | Evaluate Chrome storage encryption |
| **Dual storage (extension + backend)** | Potential consistency drift between `chrome.storage.local` and SQLite | Need sync reconciliation strategy |
| **`default_user` in dev mode** | Auth bypassed entirely in development | `middleware/user_auth.py:202-203` |

### Security Gaps (from CLAUDE.md)

| Issue | Severity | Reference |
|-------|----------|-----------|
| All users share `default_user` in dev | P0 | `middleware/user_auth.py:202` |
| No migration system | P1 | Schema changes require manual DDL |
| `datetime.utcnow()` deprecated | P1 | Should use `datetime.now(timezone.utc)` |
| Extension `postMessage` uses `'*'` origin | Low | `returns-sidebar-inner.js:279` — mitigated by content script origin check |

### Missing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| External metrics (Datadog, Cloud Monitoring) | Not implemented | All telemetry is in-memory only |
| Alerting on expiring returns | Infrastructure exists (`is_alertable()`) | No notification delivery system |
| Database migrations | Not implemented | Only `CREATE TABLE IF NOT EXISTS` |
| CI/CD pipeline | Makefile targets exist | No GitHub Actions or Cloud Build config found |
| End-to-end encryption | Partial | OAuth tokens encrypted; extracted data is not |
