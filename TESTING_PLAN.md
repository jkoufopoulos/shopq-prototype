# Testing Plan: Onboarding → First Scan

Manual QA checklist for the end-to-end flow from fresh install through first scan results.

---

## Prerequisites

- [ ] Backend is running and healthy
  ```bash
  curl -s https://reclaim-api-142227390702.us-central1.run.app/health | python3 -m json.tool
  # Expected: "status": "healthy"
  ```
- [ ] Extension is built: `cd extension && npm run build`
- [ ] Test Gmail account has purchase emails from the last 14 days
- [ ] Chrome DevTools ready (you'll need service worker inspector)

---

## 1. Fresh Install

**Goal**: Verify `onInstalled` fires with `reason='install'` and onboarding opens.

- [ ] Fully remove any existing Reclaim extension from `chrome://extensions`
- [ ] Load unpacked: `chrome://extensions` → Developer mode → Load unpacked → select `extension/`
- [ ] **Verify**: `onboarding.html` opens automatically in a new tab
- [ ] **Verify**: Service worker console shows `🎉 Reclaim installed`

**If onboarding doesn't open**: Extension wasn't fully removed (Chrome fired `update` instead of `install`). Remove again, restart Chrome, re-load.

---

## 2. Onboarding Page

**Goal**: Verify content renders correctly and CTA works.

- [ ] Page renders with Reclaim logo, 3-step explainer, privacy section
- [ ] Privacy section mentions Gemini AI processing and local storage
- [ ] Click **"Open Gmail to get started"**
- [ ] **Verify**: Gmail tab opens (or existing one focuses)
- [ ] **Verify**: Onboarding tab closes

---

## 3. OAuth Consent

**Goal**: First-time auth flow completes without errors.

- [ ] Open service worker DevTools: `chrome://extensions` → Reclaim → "Inspect views: service worker"
- [ ] Navigate to Gmail (if not already there)
- [ ] **Verify**: OAuth consent popup appears requesting Gmail read-only + profile
- [ ] Approve access
- [ ] **Verify**: No `No auth token available` error in service worker console

**If OAuth popup doesn't appear**: The OAuth client ID in `manifest.json` must match a GCP OAuth app that has the extension's ID as an authorized origin. Check `chrome://extensions` for the extension ID, then verify in [GCP Console](https://console.cloud.google.com/apis/credentials).

---

## 4. First Scan Triggers

**Goal**: Gmail tab load triggers automatic full scan.

Service worker console should show this sequence:

- [ ] `[ReturnWatch:Refresh] INITIALIZING`
- [ ] `[ReturnWatch:Refresh] INITIALIZED`
- [ ] `[ReturnWatch:Refresh] ON_GMAIL_LOAD`
- [ ] `[ReturnWatch:Scanner] SCAN_START window=14d, incremental=true`
- [ ] `[ReturnWatch:Scanner] SEARCH category:purchases ...`
- [ ] `[ReturnWatch:Scanner] FOUND N messages` (N > 0 if test account has purchases)
- [ ] `[ReturnWatch:Scanner] COLLECT_COMPLETE X emails ready for batch processing`
- [ ] `[ReturnWatch:Scanner] BATCH_SEND X emails in Y chunks`
- [ ] `[ReturnWatch:Scanner] SCAN_COMPLETE` with stats summary

**Timing**: First scan with ~50 emails takes 30-90 seconds depending on backend response time.

**If scan doesn't trigger**: `isLastScanStale()` returns `true` only when `lastScanEnd === 0` (never scanned) or >6h stale. Check that `handleTabUpdated` fires for the Gmail tab.

---

## 5. Sidebar Populates

**Goal**: Return cards appear in the Gmail sidebar after scan completes.

- [ ] InboxSDK sidebar icon appears in Gmail
- [ ] Click sidebar icon to open
- [ ] **Verify**: Return cards are displayed (merchant name, item, deadline)
- [ ] **Verify**: Cards show correct status badges (Active, Expiring Soon, etc.)
- [ ] **Verify**: No console errors in the Gmail page DevTools

**If sidebar is empty after scan**: Check service worker for `SCAN_COMPLETE_NOTIFICATION` being sent. Check Gmail page console for the message being received. Verify `upsertOrder()` calls succeeded.

---

## 6. Card Interactions

**Goal**: Verify basic CRUD operations on return cards.

- [ ] Click a card → detail view opens with full info
- [ ] Mark an item as "Returned" → status updates, card moves to Returned section
- [ ] Dismiss a card → card moves to Dismissed section
- [ ] Click refresh button → manual scan triggers (`ON_MANUAL_REFRESH` in console)

---

## 7. Popup

**Goal**: Extension popup shows correct state.

- [ ] Click extension icon in toolbar
- [ ] **Verify**: Badge count matches active returns
- [ ] **Verify**: "Scan now" button triggers a scan
- [ ] **Verify**: Privacy policy link works

---

## 8. Subsequent Visits

**Goal**: Incremental scanning works correctly on return visits.

- [ ] Close Gmail tab
- [ ] Reopen Gmail
- [ ] **Verify**: `ON_GMAIL_LOAD` fires, but scan is skipped if <6h since last scan (`SKIP scan not stale`)
- [ ] Wait 10+ minutes, switch to another tab, switch back to Gmail
- [ ] **Verify**: `ON_TAB_FOCUS` fires, focus scan triggers with 7-day window

---

## 9. Theme / Dark Mode

- [ ] Toggle Gmail to dark mode (Settings → Theme → Dark)
- [ ] **Verify**: Sidebar respects dark theme (no white flash, readable text)
- [ ] Toggle back to light mode
- [ ] **Verify**: Sidebar updates to light theme

---

## Troubleshooting Quick Reference

| Symptom | Likely Cause | Fix |
|---|---|---|
| Onboarding doesn't open | `update` event instead of `install` | Fully remove extension, restart Chrome |
| OAuth popup missing | Extension ID doesn't match GCP OAuth config | Add extension ID to authorized origins in GCP |
| `No auth token available` | OAuth consent not granted or token expired | Re-authorize in `chrome://extensions` |
| Scan runs but 0 results | No purchase emails in 14-day window | Send a test order confirmation to the Gmail account |
| Sidebar doesn't update | `SCAN_COMPLETE_NOTIFICATION` not reaching content script | Check content.js message listener in Gmail page DevTools |
| Backend returns 500 | Gemini API key invalid or quota exceeded | Check `GOOGLE_API_KEY` env var on Cloud Run |

---

## Resetting for Re-Test

```javascript
// In service worker DevTools console:
chrome.storage.local.clear(() => console.log('Storage cleared'));
// Then click "Update" on chrome://extensions to restart service worker
```

For full fresh-install test, remove and re-load the extension.
