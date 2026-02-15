# Phase 2: Extension UI Stabilization

## Doctrine

Same rules as Phase 1:
- **Demo Lock:** Extension loads in Gmail, sidebar shows orders, status changes persist — verified after every commit
- **Seams Before Splits:** Add indirection layers before moving code
- **One Concept Per Commit:** Each commit does exactly one thing
- **No Big-Bang Rewrites:** Incremental changes, never rewrite a file from scratch

---

## Current State

Phase 0 centralized config into `extension/modules/shared/config.js`. Phase 1 consolidated the backend service layer. The extension still has:

1. **Duplicate config file:** `extension/src/config.js` (ES module for webpack) duplicates 4 values from `modules/shared/config.js` — manual sync required
2. **Iframe config mirror:** `returns-sidebar-inner.js` lines 14-18 duplicate 5 constants (iframe has no access to service worker CONFIG)
3. **Minor hardcoded values:** `popup.js` has 3 timeout values, `background.js` has a 10s cleanup interval
4. **Global mutable state:** `returns-sidebar-inner.js` has 12 top-level `let` variables managing UI state
5. **No error boundaries:** Network failures in sidebar show no user feedback
6. **Message passing fragility:** Content script <-> service worker <-> sidebar iframe communication has no timeout/retry

---

## Step-by-Step Plan

### Step 2.0: Remove dead USE_SERVICE_DEDUP flag

**Action:** Delete the `USE_SERVICE_DEDUP` line from `reclaim/config.py` (1-line deletion, zero runtime impact).

**Smoke test:** Backend starts, `curl localhost:8000/health` returns 200.

**Commit:** `chore: remove dead USE_SERVICE_DEDUP flag`

---

### Step 2.1: Eliminate `extension/src/config.js` duplicate

**Problem:** `src/config.js` exports `API_BASE_URL`, `DIGEST_REFRESH_DEBOUNCE_MS`, `SIDEBAR_REFRESH_INTERVAL_MS`, and `LABEL_CACHE_KEY` as ES module exports. `content.js` imports from this file. These must stay in sync with `modules/shared/config.js` manually.

**Action:**
1. In `src/content.js`, replace imports from `./config.js` with direct constant definitions that pull from the same values
2. Since `content.js` is webpack-bundled and can't use `importScripts`, use webpack's `DefinePlugin` to inject CONFIG values at build time from `modules/shared/config.js`
3. If DefinePlugin approach is too invasive: simpler alternative — have the content script read config from `chrome.runtime.sendMessage` on init, or keep `src/config.js` but add a build-time check that values match

**Decision needed:** DefinePlugin injection vs message-based config vs keep-and-lint. The simplest approach that doesn't break the demo is the right one.

**Smoke test (Demo Lock):**
1. `npm run build` succeeds
2. Extension loads in Gmail without console errors
3. Sidebar opens and shows orders
4. Content script correctly sends emails to backend

**Commit:** `refactor: eliminate src/config.js duplication`

---

### Step 2.2: Inject CONFIG into sidebar iframe via postMessage

**Problem:** `returns-sidebar-inner.js` runs in an iframe and cannot access the service worker's `CONFIG` object. It mirrors 5 constants manually (lines 14-18).

**Action:**
1. On sidebar iframe load, have the content script (parent) send a `CONFIG_INIT` message with the relevant values
2. Sidebar iframe stores these in a local `CONFIG` object on receipt
3. Replace the 5 hardcoded constants with references to `CONFIG.*`
4. Keep the current hardcoded values as fallbacks in case `CONFIG_INIT` hasn't arrived yet

**Smoke test (Demo Lock):**
1. Sidebar opens and shows orders (CONFIG_INIT received before render)
2. Toast notifications still appear with correct timing
3. "Expiring soon" threshold still works (7 days)
4. No console errors

**Commit:** `refactor: inject CONFIG into sidebar iframe via postMessage`

---

### Step 2.3: Consolidate sidebar state into a single object

**Problem:** `returns-sidebar-inner.js` has 12 top-level `let` variables (`visibleOrders`, `returnedOrders`, `currentDetailOrder`, `isEnriching`, etc.). This makes it hard to reason about state and easy to introduce inconsistencies.

**Action:**
1. Create a `sidebarState` object at the top of the file containing all 12 variables
2. Update all references from `visibleOrders` to `sidebarState.visibleOrders`, etc.
3. This is a pure rename — no behavioral change

**Smoke test (Demo Lock):**
1. Sidebar opens and shows orders
2. Click a card -> detail view opens
3. Mark returned -> card moves to Returned section
4. Undo -> card returns
5. No console errors

**Commit:** `refactor: consolidate sidebar state into single object`

---

### Step 2.4: Add error feedback for network failures in sidebar

**Problem:** When the backend is unreachable, the sidebar silently fails. The user sees a blank or stale list with no indication of the problem.

**Action:**
1. Wrap `chrome.runtime.sendMessage` calls in the sidebar with a try/catch
2. On network error, show a toast or inline banner: "Could not reach server. Showing cached data."
3. Use the existing `showToast()` function
4. Only show the error once per session (avoid toast spam)

**Smoke test (Demo Lock):**
1. With backend running: sidebar works normally
2. Stop backend, reload Gmail: sidebar shows error toast, then displays cached data
3. Restart backend, click refresh: sidebar recovers

**Commit:** `feat: show error feedback on sidebar network failures`

---

### Step 2.5: Add timeout to chrome.runtime.sendMessage calls

**Problem:** Message passing between content script <-> service worker has no timeout. If the service worker is suspended (MV3 lifecycle), messages can hang indefinitely.

**Action:**
1. Create a `sendMessageWithTimeout(message, timeoutMs = 10000)` helper
2. Returns a Promise that rejects after `timeoutMs` if no response received
3. Replace bare `chrome.runtime.sendMessage` calls in content script and sidebar with this helper
4. On timeout, treat as network error (show cached data)

**Smoke test (Demo Lock):**
1. Normal operation: sidebar loads, messages resolve quickly
2. No console errors or unhandled promise rejections

**Commit:** `feat: add timeout to chrome.runtime.sendMessage calls`

---

### Step 2.6: Clean up intervals and observers on sidebar teardown

**Problem:** `returns-sidebar-inner.js` creates a `setInterval` for date refresh (line 49) and may create MutationObservers. If the sidebar iframe is destroyed and recreated (Gmail navigation), these are never cleaned up.

**Action:**
1. Add a `cleanup()` function that clears `dateRefreshInterval` and any other timers/observers
2. Call `cleanup()` on `beforeunload` event (iframe about to be destroyed)
3. Guard `startDateRefreshTimer()` to be idempotent (already done, line 49 checks `if (dateRefreshInterval)`)

**Smoke test (Demo Lock):**
1. Open sidebar, navigate away from Gmail, come back
2. Sidebar still works, no duplicate intervals
3. No console errors about accessing destroyed contexts

**Commit:** `fix: clean up intervals on sidebar teardown`

---

### Step 2.7: Harden popup.js timeout values

**Problem:** `popup.js` has 3 hardcoded timeout values (3000ms, 2000ms, 500ms) used for UI transitions.

**Action:**
1. Add `POPUP_SCAN_FEEDBACK_MS: 3000`, `POPUP_SCAN_DELAY_MS: 2000`, `POPUP_INIT_DELAY_MS: 500` to CONFIG
2. Replace hardcoded values in `popup.js` with `CONFIG.*` references
3. `popup.js` loads CONFIG via `<script src="modules/shared/config.js">` in `popup.html` — already works

**Smoke test:**
1. Click extension icon -> popup opens
2. Click "Scan Now" -> shows feedback, then resets
3. Badge count displays correctly

**Commit:** `refactor: popup.js timing constants use CONFIG`

---

### Step 2.8: Add background.js cleanup interval to CONFIG

**Problem:** `background.js` line 122 has a hardcoded 10-second cleanup interval.

**Action:**
1. Add `CLEANUP_INTERVAL_MS: 10000` to CONFIG
2. Replace hardcoded value in `background.js`

**Smoke test:**
1. Extension loads without errors
2. Background service worker responds to messages

**Commit:** `refactor: background.js cleanup interval uses CONFIG`

---

## Summary

| Step | Files Changed | Risk | Description |
|------|--------------|------|-------------|
| 2.0 | 1 | None | Remove dead flag |
| 2.1 | 2-3 | Medium | Eliminate src/config.js duplication |
| 2.2 | 2 | Medium | Inject CONFIG into sidebar iframe |
| 2.3 | 1 | Low | Consolidate sidebar state object |
| 2.4 | 1 | Low | Error feedback for network failures |
| 2.5 | 2-3 | Medium | Message timeout helper |
| 2.6 | 1 | Low | Interval cleanup on teardown |
| 2.7 | 2 | Low | Popup timing constants |
| 2.8 | 2 | Low | Background cleanup interval |

**Total commits:** 9
**Net new files:** 0 (all edits to existing files)
**Risk profile:** Steps 2.1, 2.2, and 2.5 require extra care (build system + message passing). All others are low-risk refactors.

---

## Demo Lock Checklist (run after every commit)

1. `npm run build` succeeds (no webpack errors)
2. Extension loads in Gmail without console errors
3. Sidebar opens and shows existing orders
4. Click a card -> detail view opens with merchant, dates, links
5. "Mark Returned" -> card moves to Returned section
6. Page reload -> state persists (returned cards still returned)

Steps 1-3 are mandatory for every commit. Steps 4-6 are mandatory for commits that touch sidebar, content script, or message passing.

---

## Out of Scope for Phase 2

These are real issues found during research but belong in later phases:

- **InboxSDK upgrade:** `pageWorld.js` is 20,650 lines of external library. Updating it is a separate task.
- **XSS hardening:** innerHTML usage in sidebar is already escaped via `escapeHtml()`. Full CSP/Trusted Types is a Phase 3 security task.
- **Service worker lifecycle:** MV3 service worker suspension/wake is a broader architectural concern. Step 2.5 adds a timeout as a band-aid; full resilience (message queue, retry with backoff) is Phase 3+.
- **Webpack -> ES module migration:** Converting the extension to pure ES modules would eliminate the src/config.js problem entirely, but it's a large migration.
- **Test infrastructure:** The extension has no automated tests. Adding them is important but orthogonal to stabilization.
