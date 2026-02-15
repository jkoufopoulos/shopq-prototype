# File Map

> Auto-maintained during Phase 4. Last updated: Step 4.9 (post Segment 4).

## Extension

### Top-Level

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `extension/background.js` | Service worker entry; importScripts + message routing | manifest.json `service_worker` | 459 | unchanged |
| `extension/returns-sidebar-inner.js` | Sidebar UI: list/detail views, state mgmt, utilities | `<script>` in iframe HTML | 1,261 | split (delivery modal + CSS extracted) |
| `extension/returns-sidebar-delivery.js` | Delivery modal: 5-step Uber pickup wizard | `<script>` in iframe HTML | 521 | **NEW** (extracted from inner.js) |
| `extension/returns-sidebar.html` | Sidebar iframe shell (scripts + CSS link) | `chrome.runtime.getURL()` iframe | 57 | extracted (CSS to .css, delivery to .js) |
| `extension/returns-sidebar.css` | Sidebar styles | `<link>` in iframe HTML | 1,403 | **NEW** (extracted from HTML) |
| `extension/popup.js` | Extension popup: badge counts, scan trigger | `<script>` in popup.html | 108 | unchanged |
| `extension/popup.html` | Popup HTML | manifest.json `action` | 110 | unchanged |
| `extension/styles.css` | Content script injected styles (Gmail page) | manifest.json `content_scripts.css` | 150 | unchanged |
| `extension/pageWorld.js` | InboxSDK (vendored, do not modify) | `chrome.scripting.executeScript` | 20,650 | unchanged |
| `extension/src/content.js` | Content script entry; InboxSDK sidebar injection | Webpack bundle → `dist/content.bundle.js` | 727 | unchanged |
| `extension/src/config.js` | ES module re-exports of CONFIG for webpack | Webpack import | 19 | unchanged |
| `extension/webpack.config.js` | Webpack config; single entry `src/content.js` | Node.js | 18 | unchanged |

### modules/storage/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/storage/store.js` | Chrome Storage CRUD wrapper (orders, emails, scan state, merchant rules) | importScripts | 1,023 | unchanged (deferred) |
| `modules/storage/schema.js` | Storage schema constants (ORDER_STATUS, EMAIL_TYPE, etc.) | importScripts | 263 | unchanged |
| `modules/storage/crypto.js` | Encryption utilities for stored data | importScripts | 213 | unchanged |

### modules/sync/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/sync/scanner.js` | Gmail scan orchestrator; batch processing + cancellation detection | importScripts | 808 | unchanged (deferred) |
| `modules/sync/refresh.js` | Periodic refresh logic; deadline recomputation | importScripts | 383 | unchanged |

### modules/gmail/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/gmail/api.js` | Gmail API: label management, email fetching, parsing | importScripts | 673 | cleaned (dead code removed) |
| `modules/gmail/auth.js` | OAuth token management | importScripts | 207 | unchanged |

### modules/pipeline/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/pipeline/resolver.js` | P6-P7: order key generation, upsert, merge escalation | importScripts | 590 | unchanged |
| `modules/pipeline/extractor.js` | FREE regex-based field extraction (dates, amounts, links) | importScripts | 587 | unchanged |
| `modules/pipeline/lifecycle.js` | P8: deadline computation, staleness, display queries | importScripts | 549 | cleaned (dead code removed) |
| `modules/pipeline/filter.js` | P1: domain filtering + keyword heuristics | importScripts | 431 | unchanged |
| `modules/pipeline/classifier.js` | P3: LLM classification dispatch | importScripts | 321 | unchanged |
| `modules/pipeline/linker.js` | P2: order ID + tracking number extraction | importScripts | 221 | unchanged |
| `modules/pipeline/hints.js` | Template-based extraction hints | importScripts | 165 | unchanged |

### modules/returns/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/returns/api.js` | Backend API client (CRUD, process, batch) | importScripts | 451 | unchanged |

### modules/enrichment/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/enrichment/policy.js` | Return policy enrichment rules | importScripts | 404 | unchanged |
| `modules/enrichment/evidence.js` | Evidence snippet extraction | importScripts | 343 | unchanged |

### modules/observability/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/observability/telemetry.js` | Scan statistics and console reporting | importScripts | 177 | unchanged |

### modules/diagnostics/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/diagnostics/logger.js` | Structured logging with verbosity levels | importScripts | 317 | unchanged |

### modules/shared/

| Path | Purpose | Loading | Lines | Phase 4 |
|------|---------|---------|-------|---------|
| `modules/shared/config.js` | Single source of truth for extension CONFIG | importScripts / `<script>` | 74 | unchanged |
| `modules/shared/utils.js` | Shared utility functions | importScripts | 50 | unchanged |

---

## Backend (reclaim/)

### returns/ (Core Domain)

| Path | Purpose | Lines | Phase 4 |
|------|---------|-------|---------|
| `returns/extractor.py` | 3-stage pipeline orchestrator; batch dedup + cancellation | 862 | cleaned (types extracted) |
| `returns/repository.py` | ReturnCard CRUD (pure persistence) | 722 | unchanged (deferred) |
| `returns/field_extractor.py` | Stage 3: hybrid LLM + rules field extraction | 564 | cleaned (types extracted) |
| `returns/filters.py` | Stage 1: domain filter + keyword heuristics | 280 | split (constants + types extracted) |
| `returns/filter_data.py` | Filter constants: blocklist, keywords, patterns | 337 | **NEW** (extracted from filters.py) |
| `returns/types.py` | Shared domain types: FilterResult, ExtractedFields, etc. | 175 | **NEW** (seam for future splits) |
| `returns/returnability_classifier.py` | Stage 2: LLM returnability check | 350 | unchanged |
| `returns/service.py` | Business logic: dedup, merge, ownership | 263 | unchanged |
| `returns/models.py` | ReturnCard, ReturnStatus, ReturnConfidence | 263 | unchanged |

### api/

| Path | Purpose | Lines | Phase 4 |
|------|---------|-------|---------|
| `api/routes/returns.py` | Returns API endpoints + Pydantic schemas | 680 | unchanged (deferred) |
| `api/routes/delivery.py` | Delivery API endpoints | 407 | unchanged |
| `api/app.py` | FastAPI app setup, middleware, router registration | 143 | unchanged |
| `api/middleware/rate_limit.py` | Rate limiting middleware | 238 | unchanged |
| `api/middleware/user_auth.py` | User authentication middleware | 229 | unchanged |
| `api/middleware/csrf.py` | CSRF protection | 157 | unchanged |

### infrastructure/

| Path | Purpose | Lines | Phase 4 |
|------|---------|-------|---------|
| `infrastructure/database.py` | SQLite connection pool, retry decorator, WAL mode | 615 | unchanged (deferred) |
| `infrastructure/database_schema.py` | Table creation, index management | 301 | unchanged |
| `infrastructure/llm_budget.py` | LLM cost tracking and budget enforcement | 217 | unchanged |
| `infrastructure/auth.py` | Auth utilities | 163 | unchanged |
| `infrastructure/retry.py` | Generic retry utilities | 128 | unchanged |

### Other

| Path | Purpose | Lines | Phase 4 |
|------|---------|-------|---------|
| `gmail/gmail_link_builder.py` | Gmail deep link construction | 507 | unchanged |
| `gmail/oauth.py` | OAuth flow for Gmail API | 411 | unchanged |
| `gmail/parser.py` | Email parsing utilities | 200 | unchanged |
| `gmail/authenticated_client.py` | Authenticated Gmail API client | 183 | unchanged |
| `observability/structured.py` | Structured logging framework | 476 | unchanged |
| `observability/telemetry.py` | Telemetry counters | 123 | unchanged |
| `delivery/repository.py` | Delivery CRUD | 474 | unchanged |
| `delivery/service.py` | Delivery business logic | 381 | unchanged |
| `delivery/carrier_locations.py` | Carrier location data | 333 | unchanged |
| `delivery/uber_client.py` | Uber Returns API client | 290 | unchanged |
| `delivery/models.py` | Delivery data models | 278 | unchanged |
| `storage/models.py` | Storage data models | 286 | unchanged |
| `storage/user_credentials_repository.py` | User credentials CRUD | 298 | unchanged |
| `storage/cloud.py` | Cloud storage utilities | 232 | unchanged |
| `storage/cache.py` | Caching layer | 121 | unchanged |
| `utils/redaction.py` | PII redaction + LLM input sanitization | 220 | unchanged |
| `utils/validators.py` | Input validators | 142 | unchanged |
| `utils/error_sanitizer.py` | Error message sanitization | 116 | unchanged |
| `llm/client.py` | Gemini LLM client abstraction | 204 | unchanged |
| `runtime/flags.py` | Feature flags | 227 | unchanged |
| `config.py` | Config re-exports + typed constants | — | unchanged |

---

## Tests

| Path | Purpose | Lines |
|------|---------|-------|
| `reclaim/tests/test_extraction_pipeline.py` | Backend pipeline integration tests | 701 |
| `extension/tests/integration/pipeline_test.js` | Extension pipeline integration tests | 310 |
| `extension/tests/unit/lifecycle.test.js` | Lifecycle module unit tests | 293 |
| `extension/tests/unit/filter.test.js` | Filter module unit tests | 292 |
| `extension/tests/unit/run-unit-tests.js` | Test runner | 284 |
| `extension/tests/storage_test.js` | Storage module tests | 224 |
| `extension/tests/unit/extractor.test.js` | Extractor module unit tests | 216 |
| `extension/tests/integration/hints_test.js` | Hints integration tests | 212 |
| `extension/tests/unit/evidence.test.js` | Evidence module unit tests | 181 |
| `extension/tests/unit/classifier.test.js` | Classifier module unit tests | 181 |
| `tests/fixtures/golden_emails.json` | Golden email test fixtures | — |
