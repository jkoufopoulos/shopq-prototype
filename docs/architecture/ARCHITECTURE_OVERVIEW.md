# ShopQ Architecture Overview

This guide ties the Chrome extension and Python backend together so you can reason about the full ShopQ system at a glance. Use it alongside the regenerated diagrams in `code-graph/visuals/`—each section below is linked from the diagrams and vice‑versa.

## Extension

### Extension Background Service Worker
- **Source:** `extension/background.js`
- **Role:** Central orchestrator for auto-organize alarms, digest triggers, messaging between modules, and Chrome events (tab updates, manual actions).
- **Key interactions:** Calls `auto-organize.js`, forwards requests to the FastAPI backend, triggers digest generation when the Inbox tab becomes active.
- **Tests:** `extension/tests/network.test.js`

### Content Script & Selector Monitor
- **Source:** `extension/content.js`, `extension/modules/selectors.js`
- **Role:** Runs inside Gmail pages to watch DOM mutations, relay label corrections, and surface digest links.
- **Key interactions:** Receives commands from the service worker, validates selectors, and sends `LABEL_CORRECTION` messages back.
- **Tests:** `extension/tests/utils.test.js`

### Auto-Organize Engine
- **Source:** `extension/modules/auto-organize.js`
- **Role:** Schedules regular inbox sweeping, fetches unlabeled threads, applies ShopQ labels, and records digest pending state.
- **Key interactions:** Uses `gmail.js` for Gmail API calls, `classifier.js` for classification, `summary-email.js` for digest triggers.
- **Tests:** Scenario coverage via `extension/tests/network.test.js`

### Extension Classification Pipeline
- **Source:** `extension/modules/classifier.js`, `extension/modules/cache.js`, `extension/modules/detectors.js`, `extension/modules/verifier.js`
- **Role:** Deduplicates threads, checks cache, calls backend `/api/organize`, applies deterministic label mapping, and optionally routes to the verifier.
- **Key interactions:** Talks to the FastAPI API, uses `mapToLabels()` to align with Gmail labels, records telemetry via `telemetry.js`.
- **Tests:** `extension/tests/mapper.test.js`, `extension/tests/verifier.test.js`

### Digest & Summary Pipeline (Extension)
- **Source:** `extension/modules/summary-email.js`, `extension/modules/context-digest.js`
- **Role:** Collects classifications since the last digest, calls `/api/context-digest`, sends the email, labels it with `ShopQ/Digest`, and updates timestamps.
- **Key interactions:** `summary-email.js` loads classifications from the logger IndexedDB and orchestrates Gmail API send + labeling.
- **Tests:** `extension/tests/verifier.test.js` (verifier hooks), manual end-to-end via integration tests.

## Backend

### FastAPI Gateway
- **Source:** `shopq/api.py`
- **Role:** Exposes `/api/organize`, `/api/verify`, `/api/context-digest`, and supporting endpoints; wires legacy services together.
- **Key interactions:** Routes organize requests to `api_organize.py`, digest calls to `context_digest.py`, verification to `api_verify.py`.
- **Tests:** `tests/integration/test_e2e_pipeline.py`

### Organize API Adapter
- **Source:** `shopq/api_organize.py`
- **Role:** Bridges the extension to the refactored pipeline, optionally falls back to legacy classifiers.
- **Key interactions:** Wraps `pipeline_wrapper.classify_batch_refactored` and returns multi-dimensional Gmail labels.
- **Tests:** `tests/integration/test_e2e_pipeline.py`

### Pipeline Coordinator
- **Source:** `shopq/usecases/pipeline.py`
- **Role:** Orchestrates fetch → parse → classify → assemble → checkpoint flow, enforces idempotency, and tracks telemetry.
- **Key interactions:** Uses adapters (`adapters/gmail`, `adapters/storage`), domain models, and idempotency helpers.
- **Tests:** `tests/integration/test_e2e_pipeline.py`, `tests/adapters/test_resilience.py`

### Classification Domain Logic
- **Source:** `shopq/domain/classify.py`
- **Role:** Implements rules-based fallback, LLM invocation, schema validation, and idempotent `ClassifiedEmail` creation.
- **Key interactions:** Calls `adapters/llm/client.py`, uses `infra/idempotency.py`, returns domain models consumed by the pipeline.
- **Tests:** `tests/llm/test_fallback.py`

### Gmail Adapters
- **Source:** `shopq/adapters/gmail/parser.py`, `shopq/adapters/gmail/client.py`
- **Role:** Parse Gmail API payloads into domain models, handle retries/circuits, and batch fetching.
- **Key interactions:** Called by the pipeline coordinator; logs schema validation counters.
- **Tests:** `tests/contracts/test_gmail_parser.py`, `tests/adapters/test_resilience.py`

### Context Digest Engine
- **Source:** `shopq/context_digest.py`, `shopq/context_enricher.py`, `shopq/narrative_generator.py`
- **Role:** Extract entities, synthesize timeline narratives, and enrich with weather/context data.
- **Key interactions:** Consumed by `/api/context-digest` and the extension’s digest pipeline.
- **Tests:** Covered indirectly via integration/digest scenarios.

### Digest Rendering & Delivery
- **Source:** `shopq/card_renderer.py`, `shopq/digest_renderer.py`
- **Role:** Render HTML cards for digests, build Gmail search links, assemble featured/overview sections.
- **Key interactions:** Used by the context digest engine and summary email worker.
- **Tests:** Integration coverage via digest flows.

### Infrastructure & Reliability Helpers
- **Source:** `infra/telemetry.py`, `infra/retry.py`, `infra/idempotency.py`, `adapters/storage/checkpoint.py`
- **Role:** Provide instrumentation, retry/circuit primitives, in-memory idempotency cache, and checkpoint stub.
- **Tests:** `tests/adapters/test_resilience.py`, `tests/infra/test_telemetry.py`

## Data Contracts

### Classification Payload Contract

When the extension sends classifications to `/api/context-digest`, each email item must include a `classification` object. This contract defines the expected fields and their defaults.

**Single Source of Truth:** `extension/modules/shared/config.js` defines `CLASSIFICATION_DEFAULTS` and `applyClassificationDefaults()` helper.

**Required Email Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | IndexedDB auto-generated ID (not email's messageId) |
| `messageId` | string | Gmail message ID |
| `subject` | string | Email subject line |
| `classification` | object | Classification data (see below) |

**Classification Object Fields:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | `'notification'` | Email type: notification, receipt, newsletter, event, promotion, message, otp, uncategorized |
| `type_conf` | number | `0` | Confidence score (0.0-1.0) |
| `attention` | string | `'none'` | Attention level: none, action_required |
| `attention_conf` | number | `0` | Confidence score |
| `importance` | string | `'routine'` | Importance: critical, time_sensitive, routine |
| `importance_conf` | number | `0` | Confidence score |
| `client_label` | string | `'everything-else'` | UI category: action-required, receipts, messages, everything-else |
| `relationship` | string | `'from_unknown'` | Sender relationship |
| `relationship_conf` | number | `0` | Confidence score |
| `decider` | string | `'unknown'` | Classification source: rule, gemini, detector, cache |
| `reason` | string | `''` | Human-readable explanation |

**Guarantees:**
1. **JavaScript logger (storage):** Ensures all fields have values before IndexedDB write
2. **JavaScript logger (retrieval):** Normalizes legacy entries missing fields on read
3. **Python API:** Applies defaults as defense-in-depth (logs telemetry when triggered)

**Telemetry:**
- Extension logs `⚠️ [LOGGER] Incomplete classification` when fields are missing at storage
- Extension logs `⚠️ [LOGGER] Normalized X/Y legacy entries` when old data needs defaults
- API logs `[TELEMETRY] Classification data quality issue` and emits `api.context_digest.incomplete_classification` event

**Debug Mode:**
- Extension: Set `CONFIG.DEBUG_CLASSIFICATION = true` in `config.js`
- API: Set environment variable `SHOPQ_DEBUG_CLASSIFICATION=true`

## Cross-Cutting Data Flow

1. **Extension auto-organize** uses `gmail.js` to fetch unlabeled threads, relays them to `/api/organize`, and applies ShopQ labels.
2. The **backend pipeline** parses Gmail payloads, classifies via rules/LLM, assembles digests, and checkpoints output.
3. **Digest generation** pulls classifications since the last digest, calls `/api/context-digest`, and sends an HTML card via Gmail.
4. Telemetry counters (`infra/telemetry.py`, `extension/modules/telemetry.js`) expose pipeline metrics for diagnostics.

## Related Resources
- `code-graph/visuals/html/system_architecture.html` – interactive system diagram (click components for docs/source).
- `code-graph/visuals/html/classification_flow.html` – classification sequence breakdown.
- `code-graph/visuals/html/auto_organize_sequence.html` – step-by-step auto-organize/alarm flow.
- `docs/ARCHITECTURE.md` – legacy architecture doc, kept for historical context.

Regenerate diagrams anytime with `./code-graph/scripts/quick_regen.sh` to keep visuals aligned with the codebase.
