# Stateless Migration Review

Full findings from architecture, code, and UX reviews of the stateless migration (`stateless` branch).
Each item is triaged with an action decision.

---

## Completed

- [x] **A1 / C1 / C3** — Broken imports in `reclaim/__init__.py` and `reclaim/storage/__init__.py` reference deleted modules (0a4c93b)
- [x] **U3** — Manifest `host_permissions` and CSP reference old `shopq-api` domain instead of `reclaim-api` (0a4c93b)
- [x] **U2** — No `unlimitedStorage` permission; 10MB default quota causes silent write failures (0a4c93b)
- [x] **A2 / A7 / C2 / C9** — Dead delivery API functions and broken backend imports removed
- [x] **C4** — `from None` changed to `from e` with `exc_info=True` in extract endpoint
- [x] **C5** — Result-to-email correlation fixed; removed fragile positional index lookup
- [x] **C11** — Added `max_length` on `body` (50K), `body_html` (100K), `from_address` (500), `subject` (2K)
- [x] **A8 / C12** — Removed dead `DB_*` config, `to_db_dict`/`from_db_row`, `ReturnCardCreate`/`ReturnCardUpdate` exports
- [x] **U8** — Popup scan now awaits actual completion instead of fixed 3-second timeout
- [x] **A3 / U9** — `processed_email_ids` converted from array to object for O(1) lookups; backward-compatible migration

---

## Skipped — with rationale

### TTLCache race condition on concurrent requests (C7)
**Original severity:** P1
**Decision:** Skip — not a real issue. Uvicorn runs async in a single thread by default. With `--workers N` it's multiprocessing with separate caches (not shared memory), so there's no race. The read-increment-write pattern is safe in async context.

### `from_address` PII not redacted before LLM calls (C8)
**Original severity:** P1
**Decision:** Skip — false positive. FROM is the merchant sender ("Amazon.com <ship-confirm@amazon.com>"), not the user. User PII is in the TO/recipient field, which is never sent to the LLM. No user personal data leaks through `from_address` in order confirmation emails.

### No 429 response when LLM budget exceeded mid-batch (C6)
**Original severity:** P1
**Decision:** Skip — current design is correct. Partial results (process what you can, reject the rest) are better UX than a hard 429 that rejects the entire batch. The caller can see rejection counts in `stats`.

### `extract-policy` swallows all exceptions, returns empty 200 (C10)
**Original severity:** P2
**Decision:** Skip — intentional. Policy enrichment is best-effort. If LLM call fails, showing no policy data is better than showing an error toast when the core return tracking feature works fine.

### Merchant rules YAML parsing has no error handling (C13)
**Original severity:** P2
**Decision:** Skip — the YAML file is bundled at deploy time, not user input. Malformed YAML is a deployment bug caught by testing. Adding try/except would mask deployment errors rather than fix them.

### LLM budget TTLCache resets on Cloud Run instance restart (A4)
**Original severity:** P1
**Decision:** Skip — acceptable for pre-launch abuse prevention. Budget exists to prevent runaway costs, not to be a billing system. Worst case on restart: a user gets extra LLM calls for one day. With Cloud Run `min-instances=0`, restarts are frequent anyway. Revisit if actual abuse appears.

### In-memory state (rate limits, budget) not shared across Cloud Run instances (A6)
**Original severity:** P1
**Decision:** Skip — same reasoning as A4. With low pre-launch traffic and likely single instance, this is theoretical. Each instance having its own counters is "good enough." Would need Redis/Memorystore for proper cross-instance state, which is over-engineering for current scale.

### No user-scoped rate limiting, only IP-based (A5)
**Original severity:** P1
**Decision:** Skip — for a Chrome extension, each user makes requests from their own browser/IP. IP-based rate limiting IS effectively user-scoped. Would only matter with a web client where multiple users share a corporate proxy IP.

### No multi-device support — data locked to single browser profile (U4)
**Original severity:** P1
**Decision:** Skip — feature request, not a bug. Chrome extension storage is inherently per-profile. Multi-device sync via `chrome.storage.sync` (100KB limit) is a V2 feature. The stateless architecture actually makes this easier to add later.

### Extension update triggers full email re-scan (U5)
**Original severity:** P1
**Decision:** Skip — intentional design. `resetScanState()` on update clears processed IDs so emails get re-processed with improved pipeline code. Orders are preserved via `upsertOrder` merge logic. The re-scan cost is acceptable during active development when pipeline quality is iterating. Could gate on `pipeline_version` later.

### API downtime error messaging unclear (U6)
**Original severity:** P1
**Decision:** Partially addressed by P2 #6 (popup timeout fix). The scanner already retries failed emails on next scan. Error messaging in the sidebar toast could be improved but is low priority.

### Privacy improvements not communicated anywhere in UI (U7)
**Original severity:** P1
**Decision:** Skip — marketing/copy task, not a code fix. Important for Chrome Web Store listing but doesn't belong in a code review remediation list.

### No storage usage indicator for users (U10)
**Original severity:** P2
**Decision:** Skip — nice-to-have. `getStorageStats()` already exists in `store.js`. Could surface in popup later but adds UI complexity for minimal user value pre-launch.

### Destructive functions (clearAllStorage) exposed without safeguards (U11)
**Original severity:** P2
**Decision:** Skip — dev-only functions loaded via `importScripts` in the service worker. Not callable from any UI. Only accessible from DevTools console. Adding safeguards is over-engineering for internal tooling.

### Extension uninstall destroys all data — no export/backup (U1)
**Original severity:** P0
**Decision:** Skip for now — uncommon scenario pre-launch. No real users with accumulated data yet. Revisit post-launch when data loss has actual user impact.

### Dead `ReturnCardCreate`/`ReturnCardUpdate` exports (C12)
**Original severity:** P2
**Decision:** Folded into P2 #5 (dead code cleanup).

### Template cache grows without bounds (U9)
**Original severity:** P2
**Decision:** Folded into P2 #7 (storage growth). Template cache is smaller concern than `processed_email_ids` — fewer entries, larger per-entry but bounded by unique email templates.

---

## Raw Findings Reference

### Architecture Review (A1-A8)

| # | Sev | Issue |
|---|-----|-------|
| A1 | P0 | Dead module imports (`reclaim/__init__.py`, `reclaim/storage/__init__.py`) reference deleted `repository`/`database` modules — will crash on import |
| A2 | P1 | Delivery API functions in extension call unregistered `/api/delivery/*` endpoints — 404s |
| A3 | P1 | `chrome.storage.local` has no GC, eviction, or quota monitoring — unbounded growth |
| A4 | P1 | LLM budget TTLCache resets on Cloud Run instance restart — exploitable |
| A5 | P1 | No user-scoped rate limiting (only IP-based) |
| A6 | P1 | In-memory state (rate limits, budget) not shared across Cloud Run instances |
| A7 | P1 | `reclaim/gmail/oauth.py` imports deleted database module |
| A8 | P2 | Dead code in models (`to_db_dict`, `from_db_row`), config (`DB_*` constants) |

### Code Review (C1-C13)

| # | Sev | Issue |
|---|-----|-------|
| C1 | P0 | `reclaim/__init__.py` lazy import references deleted `repository` module |
| C2 | P0 | `reclaim/delivery/repository.py` imports deleted `database` module |
| C3 | P0 | `reclaim/storage/__init__.py` imports deleted `database` module |
| C4 | P1 | `from None` suppresses exception chain in extract endpoint (line 241) |
| C5 | P1 | Result-to-email index correlation broken by dedup reordering |
| C6 | P1 | No 429 response when LLM budget exceeded mid-batch |
| C7 | P1 | TTLCache race condition on concurrent requests (not thread-safe) |
| C8 | P1 | `from_address` PII not redacted before LLM calls |
| C9 | P2 | Dead delivery API functions in extension `api.js` |
| C10 | P2 | `extract-policy` swallows all exceptions, returns empty 200 |
| C11 | P2 | No request body size limit per email |
| C12 | P2 | Dead `ReturnCardCreate`/`ReturnCardUpdate` exports |
| C13 | P2 | Merchant rules YAML parsing has no error handling |

### UX Review (U1-U11)

| # | Sev | Issue |
|---|-----|-------|
| U1 | P0 | Extension uninstall destroys all data — no export/backup capability |
| U2 | P0 | No storage quota monitoring; 10MB limit with no `unlimitedStorage` permission |
| U3 | P0 | Manifest `host_permissions` and CSP reference old `shopq-api` domain, not `reclaim-api` |
| U4 | P1 | No multi-device support — data locked to single browser profile |
| U5 | P1 | Extension update triggers full email re-scan (clears processed IDs every time) |
| U6 | P1 | API downtime error messaging unclear ("no new returns" vs "scan failed") |
| U7 | P1 | Privacy improvements not communicated anywhere in UI |
| U8 | P2 | Popup shows "Scan complete" after fixed 3-second timeout, not actual completion |
| U9 | P2 | Template cache and `processed_email_ids` grow without bounds |
| U10 | P2 | No storage usage indicator for users |
| U11 | P2 | Destructive functions (`clearAllStorage`) exposed without safeguards |
