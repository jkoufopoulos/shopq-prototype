# Reclaim Architecture

> Last updated: Phase 4, Step 4.0 (skeleton). Will be completed in Step 4.11.

## System Overview

Reclaim is a Gmail companion that detects online purchase emails and tracks return deadlines.

```
Gmail Inbox
    |
    v
Chrome Extension (MV3)
    |--- Content Script (webpack bundle, injected into Gmail)
    |       |--- InboxSDK sidebar injection
    |       |--- Sidebar iframe (returns-sidebar.html)
    |
    |--- Service Worker (background.js + importScripts modules)
    |       |--- Gmail API scanning (OAuth)
    |       |--- Client-side pipeline (filter → classify → extract → resolve → lifecycle)
    |       |--- Chrome Storage persistence
    |       |--- Backend API communication
    |
    |--- Popup (popup.html + popup.js)
    |
    v
FastAPI Backend (Cloud Run)
    |--- 3-Stage Extraction Pipeline
    |       |--- Stage 1: Domain filter (FREE)
    |       |--- Stage 2: LLM classifier (~$0.0001/email)
    |       |--- Stage 3: LLM field extractor (~$0.0002/email)
    |
    |--- Service Layer (dedup, merge, ownership)
    |--- Repository Layer (SQLite CRUD)
    |--- Gemini LLM (Vertex AI)
    |--- SQLite Database
```

## Extension Architecture

### Loading Mechanisms

| Context | Mechanism | Module System | Shared State |
|---------|-----------|--------------|--------------|
| Service worker | `importScripts()` | Global scope | `CONFIG`, all module functions |
| Content script | Webpack bundle | ES modules (bundled) | Isolated; communicates via `chrome.runtime.sendMessage` |
| Sidebar iframe | `<script>` tags | Global scope (iframe) | `window.ReclaimSidebar` namespace; communicates via `postMessage` |
| Popup | `<script>` tags | Global scope | `CONFIG` via shared script tag |

### Data Flow: Email Scan

```
1. User clicks "Scan" (popup or sidebar refresh)
2. Service worker receives message
3. scanner.js → Gmail API: fetch unread purchase-like emails
4. For each email:
   a. filter.js: domain check (FREE)
   b. classifier.js: LLM returnability (if filter passes)
   c. extractor.js: regex field extraction (FREE)
   d. linker.js: order ID + tracking extraction
   e. resolver.js: dedup + upsert to Chrome Storage
   f. lifecycle.js: compute return deadline
5. Backend API: POST /api/returns/process-batch (server-side extraction)
6. Service worker merges backend results with local orders
7. Sidebar receives updated orders via postMessage
```

### Config Propagation

Single source: `extension/modules/shared/config.js`

- Service worker: `importScripts` → global `CONFIG`
- Content script: `src/config.js` re-exports via webpack `require()`
- Popup: `<script src="modules/shared/config.js">` → global `CONFIG`
- Sidebar iframe: parent sends `SHOPQ_CONFIG_INIT` postMessage → `ReclaimSidebar.config`

## Backend Architecture

### Three-Stage Pipeline

```
Email Input
    |
    v
Stage 1: MerchantDomainFilter (filters.py)
    |--- Blocklist/allowlist check (FREE)
    |--- Keyword heuristic scoring
    |--- Returns FilterResult
    |
    v (if candidate)
Stage 2: ReturnabilityClassifier (returnability_classifier.py)
    |--- LLM call with retry
    |--- Returns ReturnabilityResult
    |--- On failure: REJECT (strict)
    |
    v (if returnable)
Stage 3: ReturnFieldExtractor (field_extractor.py)
    |--- Rules-based extraction (regex)
    |--- LLM extraction with retry
    |--- Hybrid merge (LLM + rules)
    |--- Returns ExtractedFields
    |--- On LLM failure: rules-only fallback (permissive)
    |
    v
ReturnableReceiptExtractor (extractor.py)
    |--- Builds ReturnCard from extracted fields
    |--- Batch: deduplication + cancellation suppression
    |
    v
ReturnsService (service.py)
    |--- Dedup strategy (order_number → item_summary → email_id)
    |--- Merge precedence rules
    |--- Ownership verification
    |
    v
ReturnCardRepository (repository.py)
    |--- SQLite CRUD operations
    |--- @retry_on_db_lock decorator
```

### Layer Responsibilities

| Layer | Files | Owns |
|-------|-------|------|
| Routes | `api/routes/returns.py` | Request parsing, response construction, HTTP status mapping |
| Service | `returns/service.py` | Dedup strategy, merge precedence, ownership checks |
| Repository | `returns/repository.py` | SQL queries, connection management, retry on lock |
| Pipeline | `returns/extractor.py` | Stage orchestration, batch dedup, cancellation detection |
| Types | `returns/types.py` | Shared domain types (ExtractionStage, ExtractionResult, etc.) |

## Build & Deployment

### Extension Build

```bash
cd extension
npm run build     # Webpack: src/content.js → dist/content.bundle.js
npm run watch     # Dev mode with hot reload
```

Only `src/content.js` is webpack-bundled. All other files are loaded directly.

### Backend

```bash
uv sync                              # Install dependencies
uv run uvicorn shopq.api.app:app     # Run server
```

### Deployment

- Backend: Google Cloud Run (Docker container)
- Extension: Chrome Web Store (manual upload of extension/ directory)
- Database: SQLite on Cloud Run ephemeral storage (known limitation)

## Data Models

### ReturnCard (Backend)

Core fields: `id`, `user_id`, `merchant_name`, `merchant_domain`, `item_description`,
`item_summary`, `purchase_date`, `delivery_date`, `return_by_date`, `order_number`,
`status` (ACTIVE | EXPIRING_SOON | EXPIRED | RETURNED | DISMISSED),
`confidence` (EXACT | ESTIMATED | UNKNOWN).

### Order (Extension/Chrome Storage)

Local representation with fields mapped from backend ReturnCard plus client-side state
(enrichment status, delivery info, display flags).

### Merchant Rules

YAML config at `config/merchant_rules.yaml`. Per-domain return window and anchor date.
Default: 30 days from delivery for unknown merchants.
