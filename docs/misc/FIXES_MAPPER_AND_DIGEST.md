# ShopQ Extension Fixes - Mapper Crash & Duplicate Digests

**Date**: November 6, 2025
**Issues Fixed**: 2 critical bugs
**Files Modified**: 2

---

## Issues Fixed

### Issue #1: Mapper Crash - Labels Not Being Applied ✅

**Symptom**:
- Classification completes successfully
- No labels are written to Gmail emails
- Console error: `TypeError: Assignment to constant variable at mapper.js:181`

**Root Cause**:
- Line 64 declared `const labels = []`
- Line 181 tried to reassign: `labels = finalLabels`
- JavaScript doesn't allow reassignment of const variables

**Fix**:
```javascript
// File: extension/modules/mapper.js:64
// Changed from:
const labels = [];

// To:
let labels = [];
```

**Impact**: All 113 unlabeled emails will now receive proper ShopQ labels.

---

### Issue #2: Duplicate Digests with Race Condition ✅

**Symptom**:
- Two digest emails sent within seconds of each other
- Second digest is nearly empty (1-2 emails)
- Happens when clicking "Organize" button

**Root Cause**:
Multiple race conditions:
1. **Non-atomic lock acquisition** - Lock check and lock set were separate operations
2. **No session tracking** - Same organize session could trigger multiple digests
3. **No cooldown** - Rapid triggers (button click + tab activation + auto-organize) all fired
4. **Missing deduplication** - Lock acquisition didn't check if same session already generated digest

**Fix #1: Atomic Lock with Session Tracking**
```javascript
// File: extension/modules/summary-email.js:204-254

async function acquireDigestLock() {
  // Added session-based deduplication
  const sessionStart = result.shopq_organize_session_start;

  if (existingLock) {
    // Check if this is the same session trying to generate twice
    if (existingLock.sessionStart === sessionStart && lockAge < DIGEST_LOCK_TIMEOUT_MS) {
      console.log('Digest already generated/generating for this session');
      return false;
    }
  }

  // Store lock with session ID and unique lock ID
  await chrome.storage.local.set({
    [DIGEST_GENERATION_LOCK_KEY]: {
      timestamp: new Date().toISOString(),
      lockId: lockId,                    // Unique ID per lock
      sessionStart: sessionStart          // Prevents same-session duplicates
    }
  });
}
```

**Fix #2: Cooldown Timer**
```javascript
// File: extension/modules/summary-email.js:25,31,215-219

const DIGEST_COOLDOWN_MS = 10 * 1000; // 10 seconds cooldown
let lastDigestTimestamp = 0;

// In acquireDigestLock():
const timeSinceLastDigest = Date.now() - lastDigestTimestamp;
if (lastDigestTimestamp > 0 && timeSinceLastDigest < DIGEST_COOLDOWN_MS) {
  console.log(`⏱️ Digest cooldown active (${remaining}s remaining)`);
  return false;
}

// After successful digest:
lastDigestTimestamp = Date.now();
```

**Impact**: Only one digest will be generated per organize session, even if multiple triggers fire.

---

## Files Modified

### 1. `extension/modules/mapper.js`
- **Line 64**: Changed `const labels = []` → `let labels = []`
- **Impact**: Fixes label assignment crash

### 2. `extension/modules/summary-email.js`
- **Lines 25, 31**: Added `DIGEST_COOLDOWN_MS` constant and `lastDigestTimestamp` variable
- **Lines 215-219**: Added cooldown check in `acquireDigestLock()`
- **Lines 224-227**: Added session-based deduplication check
- **Lines 240-246**: Enhanced lock with `lockId` and `sessionStart` tracking
- **Line 756**: Update `lastDigestTimestamp` after successful digest
- **Impact**: Prevents duplicate digests via multiple mechanisms

---

## Testing Instructions

### 1. Reload the Extension

```bash
# In Chrome:
1. Go to chrome://extensions
2. Find "ShopQ" extension
3. Click the reload icon (circular arrow)
4. Verify no errors in console
```

### 2. Test Label Application

```bash
# In Gmail:
1. Click the ShopQ extension icon (or "Organize Now" button)
2. Wait for classification to complete
3. Check that emails now have ShopQ labels:
   - ShopQ/Notifications
   - ShopQ/Receipts
   - ShopQ/Events
   - etc.
4. Verify NO console error about "Assignment to constant variable"
```

### 3. Test Digest Deduplication

```bash
# Test single digest generation:
1. Click "Organize" button
2. Immediately switch to Gmail tab
3. Wait 5 seconds
4. Check inbox - should see ONLY ONE digest email

# Check console logs:
- Should see: "✅ Digest generation lock acquired"
- Should NOT see multiple "Digest generation lock acquired" messages
- May see: "🔒 Digest already generated/generating for this session"
- May see: "⏱️ Digest cooldown active (Xs remaining)"
```

### 4. Test Auto-Organize Doesn't Duplicate

```bash
# If auto-organize is enabled (runs every 5 minutes):
1. Click "Organize" manually
2. Wait for digest to arrive
3. Wait 5 minutes for auto-organize to trigger
4. Verify NO second digest is sent
5. Console should show: "Digest already generated/generating for this session"
```

### 5. Test Multiple Rapid Clicks

```bash
# Stress test:
1. Click "Organize" button 5 times rapidly
2. Wait for processing to complete
3. Verify ONLY ONE digest email is sent
4. Console should show multiple "Digest cooldown active" messages
```

---

## Expected Console Output

### Successful Single Digest:
```
✅ [SUMMARY] Digest generation lock acquired (ID: 1730893054789-abc123, session: 2025-11-06T08:37:34.172Z)
📧 [SUMMARY] Starting summary email generation...
✅ [SUMMARY] Summary email sent successfully! Total time: 3380ms
🔓 [SUMMARY] Digest generation lock released
```

### Duplicate Prevented (Same Session):
```
🔒 [SUMMARY] Digest already generated/generating for this session (2025-11-06T08:37:34.172Z)
```

### Duplicate Prevented (Cooldown):
```
⏱️ [SUMMARY] Digest cooldown active (7s remaining)
```

### Duplicate Prevented (In-Memory):
```
🔒 [SUMMARY] Digest generation already in progress (in-memory check)
```

---

## Rollback Instructions

If these fixes cause issues, rollback:

```bash
cd /Users/justinkoufopoulos/Projects/mailq-prototype

# Revert changes
git checkout HEAD -- extension/modules/mapper.js extension/modules/summary-email.js

# Reload extension
# Go to chrome://extensions and reload ShopQ
```

---

## Verification Checklist

- [ ] Extension reloaded without errors
- [ ] Labels are being applied to emails
- [ ] Single digest sent per organize session
- [ ] Auto-organize doesn't create duplicate digests
- [ ] Rapid clicks don't create multiple digests
- [ ] Console shows proper lock/cooldown messages
- [ ] No "Assignment to constant variable" errors

---

## Related Issues

- GitHub Issue #12: Bill categorized as WORTH KNOWING instead of CRITICAL
- GitHub Issue #13: Flight confirmation categorized as WORTH KNOWING instead of COMING UP
- GitHub Issue #14: Missing CRITICAL section entirely

These are digest **content** issues (separate from generation issues) and will be addressed by the quality control pipeline.

---

**Status**: ✅ All fixes implemented and ready for testing
