# Phase 4: Project-Wide Cleanup Plan

> **Status**: DRAFT — awaiting approval
> **Precondition**: Phases 0–3 complete. App is demoable end-to-end.
> **Constraint**: App must remain demoable after every commit. No big-bang rewrites.
> **Doctrine**: Seams before Splits — encapsulate behind a facade in the same file before
> moving code to new modules. No new file unless it creates a stable boundary.

---

## A) Objectives

### Primary (must achieve)

1. **Reduce cognitive load** — The two largest authored files (sidebar inner 1756 lines,
   sidebar HTML 1458 lines) are too large to reason about. The delivery modal (~490 lines)
   is a self-contained feature buried inside the sidebar file. CSS is inline in HTML.
2. **Create stable boundaries** — Introduce seam layers (backend types module, sidebar
   namespace object) that make future splits safe and mechanical.
3. **Remove dead code with proof** — Eliminate unreachable code paths in both extension and
   backend, with grep evidence and dynamic-reference checks before every deletion.
4. **Keep demo safe** — Tier 0 smoke after every commit, Tier 1 smoke after every segment.

### Secondary (nice to have)

5. **Improve AI navigability** — Module headers, a FILE_MAP, and an architecture doc make
   it easier for AI tools (and future contributors) to orient in the codebase.
6. **Reduce large-constant noise** — Move 310+ lines of keyword/domain frozensets out of
   `filters.py` into a dedicated data module, leaving `filters.py` focused on logic.
7. **Soft target: authored files under ~500 lines** — Not a hard cap. Files that are
   cohesive and well-sectioned (e.g., `store.js` at 1023 lines) stay as-is.

---

## B) Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Sidebar delivery extraction breaks event wiring | Medium | Sidebar unusable | Namespace seam first (Step 4.2). Delivery file defines functions only — no top-level execution. Load order: delivery.js before inner.js. Tier 0 catches immediately. |
| R2 | Missing file in `web_accessible_resources` | Medium | Sidebar blank (404) | Explicit manifest.json checklist in every step that adds a file. Tier 0 includes sidebar-renders check. |
| R3 | CSS extraction breaks sidebar styling | Low | Visual regression | Pure cut-paste from `<style>` block to `.css` file. No selector changes. Visual diff in Tier 0. |
| R4 | Backend types.py creates circular import | Low | Server won't start | types.py imports only stdlib + Pydantic. Original modules re-export from types.py. Verify with `python -c "from shopq.api.app import app"`. |
| R5 | Dead code deletion removes dynamically-referenced function | Medium | Runtime crash | Proof gate: grep for function name, string-based references (`getattr`, `globals()`, string dispatch), and message handler keys. |
| R6 | Filter data extraction changes import resolution | Low | Pipeline rejects wrongly | `filter_data.py` is pure constants. `filters.py` does `from shopq.returns.filter_data import *`. All downstream behavior identical. |
| R7 | `importScripts` load order violated | Low | Service worker crash | Phase 4 does NOT add files to service worker `importScripts`. Sidebar files are loaded via `<script>` tags in iframe HTML — independent. |

---

## C) Packaging / Build Assumptions & Verification

### Architecture Facts (validated from repo)

| Component | Loading Mechanism | Bundled? | Module System |
|-----------|------------------|----------|---------------|
| Service worker (`background.js`) | Direct + `importScripts()` | No | Global scope (no ES modules) |
| Content script (`src/content.js`) | Webpack → `dist/content.bundle.js` | Yes | ES modules (webpack resolves) |
| Popup (`popup.js`) | `<script>` tag in `popup.html` | No | Global scope |
| Sidebar inner (`returns-sidebar-inner.js`) | `<script>` tag in iframe HTML | No | Global scope (iframe-isolated) |
| Page world (`pageWorld.js`) | `chrome.scripting.executeScript()` | No | Injected into main world |

### Key Constraint: Sidebar Runs in an Iframe

- `returns-sidebar.html` is loaded via `chrome.runtime.getURL()` in an iframe.
- Scripts in the iframe share the **same global scope within the iframe** but are
  **isolated from the parent page and service worker**.
- Any new `.js` or `.css` file loaded by the sidebar HTML **must** be listed in
  `manifest.json` → `web_accessible_resources`.
- Load order of `<script>` tags matters: files loaded first can define functions that
  later files call, but NOT vice versa at load time (only at event-handler time).

### Phase 4 Does NOT Touch

- `importScripts()` list in `background.js` — no service worker modules are split.
- Webpack config — no new entry points or build changes.
- `dist/` output — content bundle is unchanged.

### Verification Procedure (run after any step that adds/moves files)

```bash
# 1. Backend boots
uv run python -c "from shopq.api.app import app; print('OK')"

# 2. Extension builds (content script unchanged, but verify)
cd extension && npm run build && cd ..

# 3. Verify all web_accessible_resources files exist
node -e "
const m = require('./extension/manifest.json');
const fs = require('fs');
const res = m.web_accessible_resources[0].resources;
const missing = res.filter(r => !fs.existsSync('extension/' + r));
if (missing.length) { console.error('MISSING:', missing); process.exit(1); }
console.log('All', res.length, 'web_accessible_resources present');
"

# 4. Verify sidebar HTML script/link tags resolve
node -e "
const html = require('fs').readFileSync('extension/returns-sidebar.html', 'utf8');
const scripts = [...html.matchAll(/src=[\"']([^\"']+)[\"']/g)].map(m => m[1]);
const links = [...html.matchAll(/href=[\"']([^\"']+\.css)[\"']/g)].map(m => m[1]);
const all = [...scripts, ...links];
const fs = require('fs');
const missing = all.filter(f => !fs.existsSync('extension/' + f));
if (missing.length) { console.error('MISSING:', missing); process.exit(1); }
console.log('All', all.length, 'sidebar resources present');
"
```

---

## D) Global Smoke Tests

### Tier 0 — Boots & Renders (~2 minutes)

Run after **every commit**.

| # | Check | Command / Action | Expected |
|---|-------|-----------------|----------|
| T0.1 | Backend imports | `uv run python -c "from shopq.api.app import app; print('OK')"` | Prints `OK` |
| T0.2 | Backend health | `curl -s localhost:8000/health \| jq .status` | `"healthy"` |
| T0.3 | Extension build | `cd extension && npm run build` | Exit 0, no errors |
| T0.4 | Extension loads | Load unpacked at `chrome://extensions` | No error badge |
| T0.5 | Service worker | Check SW status on extensions page | Shows "Active" |
| T0.6 | Sidebar renders | Open Gmail → sidebar panel appears | Orders visible, no blank |
| T0.7 | No console errors | Chrome DevTools console (Gmail tab + sidebar) | Zero red errors |

### Tier 1 — Full Demo Loop (~10 minutes)

Run after **each segment completes** (Segments 1–5).

| # | Check | Action | Expected |
|---|-------|--------|----------|
| T1.1 | All T0 checks | — | Pass |
| T1.2 | Backend CRUD | `curl` create → read → update status → delete | 201, 200, 200, 204 |
| T1.3 | Backend counts | `curl localhost:8000/api/returns/counts` | JSON with status counts |
| T1.4 | Popup works | Click extension icon | Popup shows badge count |
| T1.5 | Sidebar orders | Sidebar shows order cards with merchant + dates | Correct data |
| T1.6 | Detail view | Click a card → detail view opens | Merchant, dates, links shown |
| T1.7 | Mark returned | Click "Mark Returned" on a card | Card moves to Returned section |
| T1.8 | Undo | Click "Undo" in returned section | Card returns to active |
| T1.9 | Persistence | Reload Gmail page | Returned status persists |
| T1.10 | Scan trigger | Click refresh/rescan button | Scan runs, orders update |
| T1.11 | Expiring display | Check expiring orders section | Countdown days correct |
| T1.12 | Delivery modal | Open detail → click delivery button (if visible) | Modal renders all steps |

### Golden Email Replay (manual, ~5 minutes)

Use `tests/fixtures/golden_emails.json` if backend is running locally:

```bash
# Process each golden email and verify stage_reached
for email in golden_order_confirmation golden_shipping_notification \
             golden_newsletter_reject golden_different_merchant; do
  echo "=== $email ==="
  curl -s -X POST localhost:8000/api/returns/process \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer test" \
    -d "$(jq --arg id "$email" '.emails[] | select(.id == $id) |
      {email_id: .email_id, from_address: .from_address,
       subject: .subject, body: .body, user_id: "test_user"}' \
      tests/fixtures/golden_emails.json)" | jq '{stage_reached, success}'
done
```

Expected:
- `golden_order_confirmation`: `stage_reached: "complete"`, `success: true`
- `golden_shipping_notification`: `stage_reached: "complete"`, `success: true` (merge)
- `golden_newsletter_reject`: `stage_reached: "filter"`, `success: false`
- `golden_different_merchant`: `stage_reached: "complete"`, `success: true`

---

## E) Execution Plan

### New Files Budget

Phase 4 creates exactly **6 new files** (4 code + 2 docs). Each justified below.

| New File | Lines | Justification |
|----------|-------|---------------|
| `shopq/returns/types.py` | ~80 | Stable import boundary for shared types (ExtractionStage, ExtractionResult). Prevents circular imports when future phases split extractor.py. |
| `shopq/returns/filter_data.py` | ~320 | Pure data (5 frozensets, 310+ lines of keywords/domains). Separates policy data from filter logic. High cohesion: all keyword lists in one place. |
| `extension/returns-sidebar.css` | ~1400 | CSS extracted from inline `<style>` in HTML. The HTML file drops from 1458 to ~50 lines. Standard web practice. |
| `extension/returns-sidebar-delivery.js` | ~490 | Self-contained delivery modal UI. 9 functions, 0 shared state mutations (reads state, sends postMessages). Clean extraction boundary. |
| `docs/FILE_MAP.md` | ~150 | File inventory with purpose, loading mechanism, and size. |
| `docs/ARCHITECTURE.md` | ~200 | System overview: data flow, module boundaries, deployment. |

---

### Segment 1: Foundations (Steps 4.0–4.2)

**Risk**: Zero to low. Seams only — no behavior change.
**Smoke after segment**: Tier 1 full demo loop.

---

#### Step 4.0: Documentation scaffolding

**Goal**: Create orientation docs that will be maintained through the rest of Phase 4.

**Changes**:
- Create `docs/FILE_MAP.md` with current file inventory (name, purpose, loading mechanism,
  line count, Phase 4 plan status)
- Create `docs/ARCHITECTURE.md` skeleton with sections: System Overview, Data Flow,
  Extension Architecture, Backend Architecture, Build & Deployment

**New files**: `docs/FILE_MAP.md`, `docs/ARCHITECTURE.md`
**Justification**: These docs are referenced by every subsequent step. Creating them first
means each step can update them incrementally.

**Files touched**: None (new files only)
**Proof gates**: N/A
**Rollback**: `git revert`
**Smoke**: T0.1 (backend still boots — no code changed)

**Commit**: `docs: add FILE_MAP.md and ARCHITECTURE.md skeleton`

---

#### Step 4.1: Backend shared types seam

**Goal**: Create `shopq/returns/types.py` as a stable import boundary for types shared
across the returns domain (extractor, service, routes).

**This is a SEAM step** — types are defined in `types.py` and re-exported from their
original locations. No downstream imports change.

**Changes**:
1. Create `shopq/returns/types.py` containing:
   - `ExtractionStage` (str Enum) — moved from `extractor.py`
   - `ExtractionResult` (dataclass) — moved from `extractor.py`
   - `FilterResult` (dataclass) — moved from `filters.py`
   - `ExtractedFields` (dataclass) — moved from `field_extractor.py`
2. In `extractor.py`: replace class definitions with
   `from shopq.returns.types import ExtractionStage, ExtractionResult`
3. In `filters.py`: replace class definition with
   `from shopq.returns.types import FilterResult`
4. In `field_extractor.py`: replace class definition with
   `from shopq.returns.types import ExtractedFields`
5. Verify all existing imports still resolve (they import from the original modules,
   which now re-export from types.py).

**New files**: `shopq/returns/types.py` (~80 lines)
**Justification**: Shared types boundary. Currently `ExtractionStage` and
`ExtractionResult` are imported by routes, service, and extractor. Having them in a
leaf module with zero internal dependencies prevents circular imports if we ever split
extractor.py.

**Files touched**: `extractor.py`, `filters.py`, `field_extractor.py` (import swap only)
**Proof gates**: N/A (no deletion)
**Rollback**: `git revert`
**Smoke**: T0.1, T0.2

**Commit**: `refactor: extract shared types to shopq/returns/types.py (seam)`

---

#### Step 4.2: Sidebar namespace seam

**Goal**: Introduce `window.ReclaimSidebar` as a single namespace object for all sidebar
mutable state. This is the prerequisite for any future file split.

**This is a SEAM step** — all 13 top-level `let` variables move into the namespace.
Function signatures and behavior are unchanged. No file splits.

**Changes in `returns-sidebar-inner.js`**:
1. At the top of the file (after constants section), add:
   ```javascript
   window.ReclaimSidebar = {
     state: {
       visibleOrders: [],
       returnedOrders: [],
       currentDetailOrder: null,
       isEnriching: false,
       hasCompletedFirstScan: false,
       expiredAccordionOpen: false,
       returnedAccordionOpen: false,
       deliveryModal: null,
       activeDeliveries: {},
       isEditingDate: false,
       deliveryState: { step: 'address', /* ... defaults ... */ },
     },
     config: {
       DATE_REFRESH_INTERVAL_MS: 60000,
       TOAST_DURATION_MS: 3000,
       TOAST_FADEOUT_MS: 300,
       EXPIRING_SOON_DAYS: 7,
       CRITICAL_DAYS: 3,
     },
     timers: {
       dateRefreshInterval: null,
     },
   };
   ```
2. Find-replace all bare state references:
   - `visibleOrders` → `ReclaimSidebar.state.visibleOrders`
   - `returnedOrders` → `ReclaimSidebar.state.returnedOrders`
   - `currentDetailOrder` → `ReclaimSidebar.state.currentDetailOrder`
   - `isEnriching` → `ReclaimSidebar.state.isEnriching`
   - `hasCompletedFirstScan` → `ReclaimSidebar.state.hasCompletedFirstScan`
   - `expiredAccordionOpen` → `ReclaimSidebar.state.expiredAccordionOpen`
   - `returnedAccordionOpen` → `ReclaimSidebar.state.returnedAccordionOpen`
   - `deliveryModal` → `ReclaimSidebar.state.deliveryModal`
   - `activeDeliveries` → `ReclaimSidebar.state.activeDeliveries`
   - `isEditingDate` → `ReclaimSidebar.state.isEditingDate`
   - `deliveryState` → `ReclaimSidebar.state.deliveryState`
   - `dateRefreshInterval` → `ReclaimSidebar.timers.dateRefreshInterval`
3. Find-replace config references:
   - `DATE_REFRESH_INTERVAL_MS` → `ReclaimSidebar.config.DATE_REFRESH_INTERVAL_MS`
   - `TOAST_DURATION_MS` → `ReclaimSidebar.config.TOAST_DURATION_MS`
   - (etc. for all 5 config constants)
4. Update `SHOPQ_CONFIG_INIT` handler to write into `ReclaimSidebar.config.*`
5. Remove the 13 top-level `let` declarations (now in namespace)
6. Remove the 5 top-level config `let` declarations (now in namespace)

**New files**: None
**Files touched**: `returns-sidebar-inner.js` only
**Proof gates**: N/A (no deletion, pure rename)
**Rollback**: `git revert` — single file, mechanical change
**Smoke**: T0.6, T0.7 (sidebar renders, no console errors)

**Why this matters**: After this step, any extracted file (e.g., delivery modal) can access
shared state via `window.ReclaimSidebar.state.*` without receiving parameters. This makes
splits safe and mechanical.

**Commit**: `refactor: consolidate sidebar state into window.ReclaimSidebar namespace (seam)`

---

### Segment 2: Dead Code Removal (Steps 4.3–4.4)

**Risk**: Low with proof gates. Every deletion has grep evidence.
**Smoke after segment**: Tier 1 full demo loop.

---

#### Step 4.3: Extension dead code removal

**Goal**: Remove unreachable code from extension modules with proof.

**Proof Gate Protocol** (apply to every item below):
1. Grep for function/variable name across entire `extension/` directory
2. Check for string-based references: `['functionName']`, template literals, `eval()`
3. Check for dynamic dispatch: message handler `type` matching, `window[name]()` patterns
4. If any reference found outside the definition site: **DO NOT DELETE**

**Candidates** (validate with grep before deleting):

| Item | File | Evidence | Lines |
|------|------|----------|-------|
| `filterAlreadyLabeledThreads()` | `gmail/api.js` | Disabled at line ~262, commented out call site | ~37 |
| `checkThreadForShopQLabels()` | `gmail/api.js` | Disabled per agent analysis (Gmail caching issues) | ~20 |
| `hasShopQLabels()` | `gmail/api.js` | Only called by `checkThreadForShopQLabels` (also dead) | ~15 |
| `DEMO_HIDDEN_ITEMS` + filtering logic | `pipeline/lifecycle.js` | Hardcoded demo filter for "e.l.f. wow brow gel" | ~5 |
| Dead `cleanupOldLabels` reference | `gmail/api.js` | Comment references removed function (line ~802) | ~2 |

**Expected net deletion**: ~70-80 lines across 2 files.

**Changes**:
- `gmail/api.js`: Remove 3 dead functions + dead comment
- `pipeline/lifecycle.js`: Remove `DEMO_HIDDEN_ITEMS` constant + filtering logic

**New files**: None
**Files touched**: `gmail/api.js`, `pipeline/lifecycle.js`
**Rollback**: `git revert`
**Smoke**: T0.5 (SW active), T0.6 (sidebar renders), T0.7 (no console errors)

**Commit**: `chore: remove dead code from gmail/api.js and lifecycle.js (with proof)`

---

#### Step 4.4: Backend dead code removal

**Goal**: Remove unreachable code from Python backend with proof.

**Proof Gate Protocol**: Same as Step 4.3 but for Python. Additionally:
- Check for `getattr(obj, 'name')` patterns
- Check for references in tests (`tests/`)
- Check for references in route registrations

**Candidates** (validate with grep before deleting):

| Item | File | Evidence | Lines |
|------|------|----------|-------|
| `received_at` unused parameter | `extractor.py` `_build_return_card()` | Marked `# noqa: ARG002` — explicitly flagged as unused | ~0 (param removal) |
| Stale comments / TODO markers | Multiple | Audit for `# TODO`, `# HACK`, `# FIXME` that reference completed work | Variable |

**Important**: This step has a SMALL scope. Do NOT remove:
- `extraction_method` field in `field_extractor.py` (used in telemetry — confirmed Phase 1)
- Any function that appears in test files
- Any function referenced by string name in logging/telemetry

**Expected net deletion**: ~10-20 lines.

**Changes**: `extractor.py` (remove unused parameter), minor cleanups in other files
**New files**: None
**Rollback**: `git revert`
**Smoke**: T0.1, T0.2

**Commit**: `chore: remove dead code from backend (with proof)`

---

### Segment 3: Data & CSS Extraction (Steps 4.5–4.7)

**Risk**: Low to medium. Pure data movement — no logic changes.
**Smoke after segment**: Tier 1 full demo loop.

---

#### Step 4.5: Extract CSS from sidebar HTML

**Goal**: Move ~1400 lines of inline CSS from `returns-sidebar.html` to a dedicated
`returns-sidebar.css` file.

**Changes**:
1. Create `extension/returns-sidebar.css` containing the full content of the `<style>` block
2. In `returns-sidebar.html`: replace `<style>...</style>` block with
   `<link rel="stylesheet" href="returns-sidebar.css">`
3. In `manifest.json`: add `"returns-sidebar.css"` to `web_accessible_resources`

**MV3 Packaging Check**:
- File `extension/returns-sidebar.css` must exist
- `manifest.json` → `web_accessible_resources` must include `"returns-sidebar.css"`
- CSP `style-src 'self' 'unsafe-inline'` already permits linked stylesheets (`'self'`)
  — no CSP change needed (keep `'unsafe-inline'` for any inline `style=""` attributes)

**New files**: `extension/returns-sidebar.css` (~1400 lines)
**Justification**: Standard web practice. Separates structure from presentation. HTML file
drops from 1458 to ~50 lines. CSS can be independently cached by the browser.

**Files touched**: `returns-sidebar.html`, `manifest.json`
**Proof gates**: N/A (no deletion of logic)
**Rollback**: `git revert`
**Smoke**: T0.6 (sidebar renders with correct styling), T0.7 (no console errors)

**Visual regression check**: Open sidebar, verify:
- Order cards have correct colors, borders, shadows
- Detail view layout matches before
- Delivery modal styling (if accessible) unchanged
- Toast notifications positioned correctly
- Accordion chevrons animate

**Commit**: `refactor: extract sidebar CSS to returns-sidebar.css`

---

#### Step 4.6: Extract filter constants to data module

**Goal**: Move 310+ lines of keyword/domain frozensets from `filters.py` to a dedicated
`filter_data.py` module.

**Changes**:
1. Create `shopq/returns/filter_data.py` containing:
   - `DEFAULT_BLOCKLIST` (frozenset, ~95 lines — was `_DEFAULT_BLOCKLIST`)
   - `PURCHASE_CONFIRMATION_KEYWORDS` (set, ~25 lines)
   - `DELIVERY_KEYWORDS` (set, ~15 lines)
   - `GROCERY_PERISHABLE_PATTERNS` (set, ~50 lines)
   - `NON_PURCHASE_KEYWORDS` (set, ~80 lines)
   - `SHIPPING_SERVICE_DOMAINS` (set, ~5 lines)
   - `SURVEY_SUBJECT_KEYWORDS` (list, ~5 lines)
2. In `filters.py`: replace all constant definitions with
   `from shopq.returns.filter_data import *`
3. Make previously private `_DEFAULT_BLOCKLIST` public as `DEFAULT_BLOCKLIST`
   (it's now in a data module — the underscore prefix was an implementation detail)
4. Update any direct references to `_DEFAULT_BLOCKLIST` in `filters.py` to
   `DEFAULT_BLOCKLIST`

**New files**: `shopq/returns/filter_data.py` (~320 lines)
**Justification**: Pure data with zero logic. Separates "what to filter" from "how to
filter." `filters.py` drops from 589 to ~280 lines, focused entirely on filtering logic.
Adding a new keyword to the blocklist means editing `filter_data.py` — no risk of
accidentally changing filter logic.

**Files touched**: `filters.py`
**Proof gates**: N/A (data movement, no deletion)
**Rollback**: `git revert`
**Smoke**: T0.1, T0.2

**Commit**: `refactor: extract filter constants to shopq/returns/filter_data.py`

---

#### Step 4.7: Update FILE_MAP.md with new files

**Goal**: Keep FILE_MAP.md current after Segment 3 changes.

**Changes**: Update `docs/FILE_MAP.md` entries for modified and new files.

**New files**: None
**Rollback**: `git revert`
**Smoke**: N/A (docs only)

**Commit**: `docs: update FILE_MAP.md after Segment 3`

---

### Segment 4: Sidebar Delivery Modal Extraction (Steps 4.8–4.9)

**Risk**: Medium. This is the only file split in Phase 4. The namespace seam (Step 4.2)
makes this safe.
**Smoke after segment**: Tier 1 full demo loop including T1.12 (delivery modal).

---

#### Step 4.8: Extract delivery modal to separate file

**Goal**: Move the delivery modal (~490 lines, 9 functions) from `returns-sidebar-inner.js`
to `returns-sidebar-delivery.js`.

**Precondition**: Step 4.2 (namespace seam) must be complete.

**Extraction boundary** (lines ~839–1338 in current file):

| Function | Lines | Dependencies |
|----------|-------|-------------|
| `showDeliveryModal(order)` | ~46 | `ReclaimSidebar.state.deliveryState`, `ReclaimSidebar.state.deliveryModal`, `renderDeliveryModal()`, `escapeHtml()`, `window.parent.postMessage()` |
| `closeDeliveryModal()` | ~10 | `ReclaimSidebar.state.deliveryModal`, `renderDetailView()` |
| `showDeliveryStatus(delivery)` | ~37 | `ReclaimSidebar.state.*`, `renderDeliveryModal()` |
| `renderDeliveryModal()` | ~54 | `ReclaimSidebar.state.deliveryState`, step renderers |
| `renderAddressStep(content)` | ~77 | `ReclaimSidebar.state`, `escapeHtml()`, `window.parent.postMessage()` |
| `renderLocationsStep(content)` | ~78 | `ReclaimSidebar.state`, `escapeHtml()`, `sanitizeUrl()` |
| `renderQuoteStep(content)` | ~73 | `ReclaimSidebar.state`, `escapeHtml()`, `formatDate()`, `showToast()` |
| `renderConfirmedStep(content)` | ~39 | `ReclaimSidebar.state`, `escapeHtml()`, `formatDate()` |
| `renderStatusStep(content)` | ~78 | `ReclaimSidebar.state`, `escapeHtml()`, `formatDate()` |

**Interface contract**: All delivery functions:
- Read state from `window.ReclaimSidebar.state.*` (available after inner.js creates namespace)
- Call utility functions from `returns-sidebar-inner.js` (available because inner.js loads first)
- Communicate with parent via `window.parent.postMessage()` (always available)
- Are called by `returns-sidebar-inner.js` event handlers (called after all scripts load)

**Changes**:
1. Create `extension/returns-sidebar-delivery.js` with the 9 delivery functions
2. Add module header comment explaining the dependency on `window.ReclaimSidebar`
3. In `returns-sidebar-inner.js`: delete the delivery modal section (lines ~839–1338)
4. In `returns-sidebar.html`: add `<script src="returns-sidebar-delivery.js"></script>`
   **before** the existing `<script src="returns-sidebar-inner.js"></script>`

   Wait — load order matters. Let me be precise:
   ```html
   <!-- Load order: inner.js FIRST (creates namespace + utilities),
        then delivery.js (defines delivery functions using namespace) -->
   <script src="returns-sidebar-inner.js"></script>
   <script src="returns-sidebar-delivery.js"></script>
   ```

   **Correction**: inner.js must load first because it creates `window.ReclaimSidebar` and
   defines utility functions (`escapeHtml`, `showToast`, etc.). Delivery.js defines functions
   that reference these — JavaScript resolves global references at call time, not definition
   time, so this is safe. But inner.js calls delivery functions (e.g., `showDeliveryModal()`)
   only from event handlers, which fire after all scripts have loaded.

5. In `manifest.json`: add `"returns-sidebar-delivery.js"` to `web_accessible_resources`

**MV3 Packaging Check**:
- `extension/returns-sidebar-delivery.js` exists
- `manifest.json` → `web_accessible_resources` includes `"returns-sidebar-delivery.js"`
- `returns-sidebar.html` loads inner.js THEN delivery.js
- Sidebar iframe has no CSP restrictions on additional same-origin scripts

**New files**: `extension/returns-sidebar-delivery.js` (~490 lines)
**Justification**: Delivery modal is a self-contained feature (scheduling return pickups)
with a clear boundary. It has its own state machine (`deliveryState.step`), its own UI
(modal overlay with 5 wizard steps), and communicates exclusively via postMessage. After
extraction, `returns-sidebar-inner.js` drops from ~1756 to ~1266 lines.

**Files touched**: `returns-sidebar-inner.js`, `returns-sidebar.html`, `manifest.json`
**Proof gates**: N/A (code movement, not deletion)
**Rollback**: `git revert`
**Smoke**: T0.6, T0.7, T1.12 (delivery modal)

**Detailed delivery modal verification**:
1. Open sidebar → click an order with a delivery option
2. Delivery modal opens (address step)
3. Navigate through steps (if backend supports delivery)
4. Close modal → returns to detail view
5. No console errors throughout

**Commit**: `refactor: extract delivery modal to returns-sidebar-delivery.js`

---

#### Step 4.9: Verify sidebar line counts and update docs

**Goal**: Confirm the extraction achieved its goals and update documentation.

**Expected results after Steps 4.2 + 4.5 + 4.8**:
| File | Before | After |
|------|--------|-------|
| `returns-sidebar-inner.js` | 1,756 | ~1,266 |
| `returns-sidebar.html` | 1,458 | ~50 |
| `returns-sidebar.css` | (new) | ~1,400 |
| `returns-sidebar-delivery.js` | (new) | ~490 |

**Changes**: Update `docs/FILE_MAP.md`, `docs/ARCHITECTURE.md` sidebar section.
**Commit**: `docs: update FILE_MAP and ARCHITECTURE after sidebar extraction`

---

### Segment 5: Documentation & Module Headers (Steps 4.10–4.11)

**Risk**: Zero. Documentation only.
**Smoke after segment**: Tier 0 (confirm no accidental code changes).

---

#### Step 4.10: Add module headers to large files

**Goal**: Every authored file over 300 lines gets a module header comment (if it doesn't
already have one) describing: purpose, loading mechanism, key exports/functions, and
dependencies.

**Format for JavaScript**:
```javascript
/**
 * Module: <name>
 * Purpose: <one-line description>
 * Loading: <importScripts | webpack | script tag | etc.>
 * Key exports: <list of main functions/classes>
 * Dependencies: <list of modules this depends on>
 */
```

**Format for Python**:
```python
"""
Module: <name>
Purpose: <one-line description>
Key classes: <list>
Dependencies: <list of internal imports>
"""
```

**Files to add headers to** (only if missing or inadequate):
- Extension: `background.js`, `returns-sidebar-inner.js`, `returns-sidebar-delivery.js`,
  `modules/storage/store.js`, `modules/sync/scanner.js`, `modules/gmail/api.js`,
  `modules/pipeline/resolver.js`, `modules/pipeline/extractor.js`,
  `modules/pipeline/lifecycle.js`, `modules/pipeline/filter.js`,
  `modules/returns/api.js`, `modules/enrichment/policy.js`
- Backend: `returns/extractor.py`, `returns/repository.py`, `returns/field_extractor.py`,
  `returns/filters.py`, `returns/types.py`, `returns/filter_data.py`,
  `api/routes/returns.py`, `infrastructure/database.py`

**New files**: None
**Proof gates**: N/A
**Rollback**: `git revert`
**Smoke**: T0.1, T0.3 (ensure no syntax errors in headers)

**Commit**: `docs: add module headers to all files over 300 lines`

---

#### Step 4.11: Complete ARCHITECTURE.md and FILE_MAP.md

**Goal**: Fill in the architecture doc with final accurate content reflecting post-Phase 4
state.

**ARCHITECTURE.md sections**:
1. System Overview (extension ↔ backend ↔ Gmail API ↔ Gemini)
2. Extension Architecture (loading mechanisms, module boundaries, data flow)
3. Backend Architecture (3-stage pipeline, service layer, repository)
4. Build & Deployment (webpack, Chrome load, Cloud Run)
5. Data Models (ReturnCard, Order, key enums)
6. Config System (how config propagates to each context)

**FILE_MAP.md content**:
- Every authored file with: path, purpose, loading mechanism, line count, dependencies
- Organized by directory
- Excludes `node_modules/`, `dist/`, `.git/`, vendored files (`pageWorld.js`)

**New files**: None (updating existing scaffolds from Step 4.0)
**Rollback**: `git revert`
**Smoke**: N/A

**Commit**: `docs: complete ARCHITECTURE.md and FILE_MAP.md`

---

## F) Documentation Update Rules

### Module Header Spec

Every authored file over 300 lines **must** have a module header (added in Step 4.10).
Files under 300 lines **may** have one but it's not required.

Headers must include:
- **Purpose**: One sentence describing what the module does
- **Loading**: How this file gets loaded (importScripts, webpack, script tag, Python import)
- **Key exports**: Main functions or classes (top 3–5)
- **Dependencies**: Internal modules this file imports from

Headers must NOT include:
- Change history (that's git's job)
- Author name
- License text
- Line counts (goes stale)

### FILE_MAP.md Rules

- Updated at the end of each segment (Steps 4.7, 4.9, 4.11)
- One row per authored file (excludes vendored, generated, test fixtures)
- Columns: Path, Purpose, Loading, Lines, Phase 4 Status
- Phase 4 Status values: `unchanged`, `cleaned`, `split-from:<parent>`, `new`, `extracted-to:<child>`

### ARCHITECTURE.md Rules

- High-level diagrams described in text (no image dependencies)
- Updated at end of Phase 4 (Step 4.11)
- Must reflect the actual post-Phase 4 architecture, not aspirational state
- Sections correspond to real module boundaries, not theoretical ones

---

## G) Deferred Work ("Do NOT Refactor Yet")

These items were considered for Phase 4 and explicitly deferred. Each has a reason.

| Item | File(s) | Lines | Why Defer |
|------|---------|-------|-----------|
| **store.js split** | `modules/storage/store.js` | 1,023 | High cohesion — all Chrome Storage operations. Functions are stateless wrappers. Splitting would scatter related operations across files with no cognitive benefit. Add section headers in Step 4.10 instead. |
| **scanner.js split** | `modules/sync/scanner.js` | 808 | Gmail helpers are used exclusively by scan orchestration. Moving them to `gmail/` would create a false abstraction boundary. The file reads linearly. |
| **extractor.py split** | `shopq/returns/extractor.py` | 956 | Pipeline orchestrator. Dedup and cancellation detection are batch-specific but called from the same entry point (`process_email_batch`). types.py seam (Step 4.1) enables a future split without circular imports. |
| **repository.py split** | `shopq/returns/repository.py` | 722 | Pure CRUD. All methods are `@staticmethod` on one class. Splitting "finders" from "writers" would halve the file but double the imports needed everywhere. |
| **returns.py schema extraction** | `shopq/api/routes/returns.py` | 680 | Pydantic models are used only by this router. Moving them to `schemas.py` is cosmetic — no cognitive benefit since you always read routes and schemas together. |
| **database.py pool extraction** | `shopq/infrastructure/database.py` | 615 | Connection pool + helpers are cohesive. The pool class has clear internal boundaries (init, acquire, release, cleanup). Section headers suffice. |
| **field_extractor.py prompt extraction** | `shopq/returns/field_extractor.py` | 594 | The 47-line LLM prompt is a constant inside the file. Extracting to a separate template file creates a new file for 47 lines of text. Not worth the indirection. |
| **content.js further refactoring** | `extension/src/content.js` | 727 | Phase 3 already performed class extraction. Webpack bundles this file. Further splits require webpack config changes — higher risk than reward. |
| **gmail/api.js refactoring** | `extension/modules/gmail/api.js` | ~770 (post dead code) | Label management + email fetching are both Gmail API operations. Splitting by "labels" vs "messages" is arbitrary. Dead code removal (Step 4.3) is sufficient. |
| **Service worker module index** | `extension/background.js` | 459 | A `modules/index.js` barrel file would centralize the `importScripts` list, but Phase 4 doesn't split any SW modules. Create this seam at the start of a future phase that splits service worker modules. |
| **Webpack migration for sidebar** | sidebar files | — | Converting the sidebar to a webpack bundle would solve load-order issues and enable ES module imports. But it changes the build pipeline and the CSP. Save for a dedicated modernization phase. |
| **ES modules for service worker** | `background.js` | — | Chrome MV3 does not support `"type": "module"` for service workers reliably across all Chrome versions. `importScripts` is the stable path. |
| **Naming: shopq → reclaim** | Cross-cutting | — | Module paths use `shopq.*`, config uses `SHOPQ_*`, but the product is "Reclaim." This is a cross-cutting rename affecting imports, env vars, database paths, and deployment config. Needs its own dedicated phase. |
| **Test infrastructure** | — | — | The extension has no automated tests. Adding them is important but orthogonal to cleanup. |
| **Manifest URL mismatch** | `manifest.json` | — | `host_permissions` and CSP reference `shopq-api-488078904670` but the production API may be at `reclaim-api-488078904670`. Verify and fix in a dedicated config audit, not during structural cleanup. |

---

## H) Summary: Expected Post-Phase 4 State

### File Size Changes

| File | Before | After | Change |
|------|--------|-------|--------|
| `returns-sidebar-inner.js` | 1,756 | ~1,266 | -490 (delivery extraction) |
| `returns-sidebar.html` | 1,458 | ~50 | -1,408 (CSS extraction) |
| `returns-sidebar.css` | (new) | ~1,400 | +1,400 |
| `returns-sidebar-delivery.js` | (new) | ~490 | +490 |
| `filters.py` | 589 | ~280 | -309 (constant extraction) |
| `filter_data.py` | (new) | ~320 | +320 |
| `types.py` | (new) | ~80 | +80 |
| `gmail/api.js` | 805 | ~735 | -70 (dead code) |
| `lifecycle.js` | 555 | ~550 | -5 (dead code) |
| `extractor.py` | 956 | ~950 | -6 (dead param) |

**Net lines**: Approximately zero (data and CSS move between files; dead code is ~85 lines removed).

### Files Over 500 Lines (Post-Phase 4)

| File | Lines | Status |
|------|-------|--------|
| `returns-sidebar.css` | ~1,400 | CSS — low cognitive load, no logic |
| `returns-sidebar-inner.js` | ~1,266 | Reduced from 1,756. Further splits deferred. |
| `store.js` | 1,023 | Deferred — high cohesion |
| `extractor.py` | ~950 | Deferred — types seam enables future split |
| `scanner.js` | 808 | Deferred — cohesive orchestrator |
| `api.js` (gmail) | ~735 | Reduced from 805. Further splits deferred. |
| `content.js` | 727 | Deferred — Phase 3 handled |
| `repository.py` | 722 | Deferred — pure CRUD |
| `returns.py` (routes) | 680 | Deferred — thin routes + models |
| `database.py` | 615 | Deferred — cohesive pool |
| `field_extractor.py` | 594 | Deferred |
| `resolver.js` | 590 | Deferred — cohesive |
| `extractor.js` (pipeline) | 587 | Deferred — cohesive |
| `lifecycle.js` | ~550 | Deferred — cohesive |

### Commit Count

| Segment | Steps | Commits | Description |
|---------|-------|---------|-------------|
| 1: Foundations | 4.0–4.2 | 3 | Docs scaffold, types seam, sidebar namespace seam |
| 2: Dead Code | 4.3–4.4 | 2 | Extension dead code, backend dead code |
| 3: Data/CSS | 4.5–4.7 | 3 | CSS extraction, filter constants, docs update |
| 4: Sidebar Split | 4.8–4.9 | 2 | Delivery modal extraction, docs update |
| 5: Documentation | 4.10–4.11 | 2 | Module headers, complete ARCHITECTURE + FILE_MAP |
| **Total** | | **12** | |

---

## I) Progress Tracker

| Step | Status | Commit SHA | Notes |
|------|--------|-----------|-------|
| 4.0 | PENDING | | Docs scaffolding |
| 4.1 | PENDING | | Backend types seam |
| 4.2 | PENDING | | Sidebar namespace seam |
| 4.3 | PENDING | | Extension dead code |
| 4.4 | PENDING | | Backend dead code |
| 4.5 | PENDING | | CSS extraction |
| 4.6 | PENDING | | Filter constants extraction |
| 4.7 | PENDING | | FILE_MAP update |
| 4.8 | PENDING | | Delivery modal extraction |
| 4.9 | PENDING | | Docs update |
| 4.10 | PENDING | | Module headers |
| 4.11 | PENDING | | Complete ARCHITECTURE + FILE_MAP |
