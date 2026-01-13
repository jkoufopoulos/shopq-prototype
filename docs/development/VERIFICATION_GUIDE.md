# ShopQ System Verification Guide

**Date**: November 6, 2025 @ 4:00 AM EST
**Status**: Ready for testing after extension reload

---

## Quick Start

1. **Reload Chrome Extension**
   - Open Chrome
   - Go to: `chrome://extensions`
   - Find "ShopQ" extension
   - Click reload icon (circular arrow)
   - ✅ Verify no errors in console

2. **Test Classification & Digest**
   - Open Gmail
   - Click "Organize" in ShopQ extension
   - Watch console for logs (see below)
   - Check inbox for digest (should see ONLY ONE)

3. **Run Quality Analysis**
   ```bash
   ./scripts/force-quality-check.sh
   ```

---

## What to Watch For

### ✅ Success Indicators

**Console Logs (Extension)**:
```
✅ OAuth token obtained
📧 Found X unlabeled emails to organize
🤖 Classifying X emails...
✅ Labels applied: ShopQ/Receipts (N), ShopQ/Finance (N), ...
📧 [SUMMARY] Starting summary email generation...
✅ [SUMMARY] Digest generation lock acquired (ID: ..., session: 20251106_040000)
✅ [SUMMARY] Summary email sent successfully! Total time: 2500ms
🔓 [SUMMARY] Digest generation lock released
```

**Gmail Results**:
- Labels appear on emails (ShopQ/Receipts, ShopQ/Finance, etc.)
- ONE digest email arrives in inbox
- No duplicate digests

**Backend Logs** (`/tmp/shopq-api.log`):
```
INFO: 127.0.0.1:xxxxx - "POST /api/classify HTTP/1.1" 200 OK
INFO: 127.0.0.1:xxxxx - "POST /api/context-digest HTTP/1.1" 200 OK
```

**Quality Logs Directory**:
```bash
$ ls -lh quality_logs/
actual_digest_20251106_040000.html    # New digest HTML
input_emails_20251106_040000.json     # Input emails for this session
```

---

### ❌ Failure Indicators (Should NOT See These)

**Mapper Crash (FIXED)**:
```
❌ TypeError: Assignment to constant variable at mapper.js:181
❌ Labels not being applied to emails
```

**Duplicate Digests (FIXED)**:
```
❌ Two digest emails sent within seconds
❌ Second digest nearly empty (1-2 emails)
❌ Multiple "Digest generation lock acquired" messages
```

**Digest HTML Not Found (FIXED)**:
```
❌ Quality monitor: "No digest HTML file found for session"
❌ Timestamp mismatch between session_id and filename
```

---

## Detailed Testing Steps

### Step 1: Extension Reload

```bash
# Open Chrome DevTools before reloading
1. Right-click ShopQ extension icon → Inspect
2. Keep DevTools open during testing
3. Go to chrome://extensions
4. Find ShopQ → Click reload icon
5. Check DevTools console for any errors
```

**Expected**: No errors, extension reloads cleanly

---

### Step 2: Classification Test

```bash
# In Gmail:
1. Click "Organize" button in ShopQ extension
2. Watch console logs in real-time
3. Wait for "Labels applied" message
4. Check emails for ShopQ/* labels
```

**Expected Behavior**:
- ✅ Classification completes without errors
- ✅ All unlabeled emails receive ShopQ labels
- ✅ Console shows: "Labels applied: ShopQ/Receipts (N), ShopQ/Finance (N), ..."

**If It Fails**:
- Check console for "Assignment to constant variable" error
- If error appears, extension reload may have failed
- Try hard-refresh: Disable → Enable extension

---

### Step 3: Digest Generation Test

```bash
# Still watching console:
1. Wait for "Starting summary email generation" message
2. Watch for lock acquisition message
3. Wait for "Summary email sent successfully"
4. Check Gmail inbox for digest
```

**Expected Behavior**:
- ✅ Single "Digest generation lock acquired" message
- ✅ One digest email arrives
- ✅ Console shows session ID (e.g., 20251106_040000)
- ✅ Lock released after digest sent

**If Multiple Digests Appear**:
- Check console for duplicate lock messages
- May indicate extension reload didn't apply fixes
- Check chrome://extensions for any load errors

---

### Step 4: Deduplication Stress Test

```bash
# Test rapid clicks:
1. Click "Organize" button 5 times rapidly
2. Watch console for cooldown messages
3. Check inbox - should see ONLY ONE digest
```

**Expected Console Output**:
```
✅ [SUMMARY] Digest generation lock acquired (first click)
⏱️ [SUMMARY] Digest cooldown active (9s remaining)
⏱️ [SUMMARY] Digest cooldown active (8s remaining)
⏱️ [SUMMARY] Digest cooldown active (7s remaining)
⏱️ [SUMMARY] Digest cooldown active (6s remaining)
```

---

### Step 5: Quality Analysis Test

```bash
# Get the session_id from console logs
# Example: 20251106_040000

# Run quality check
./scripts/force-quality-check.sh

# Watch for these log messages:
# "Found digest HTML file: actual_digest_20251106_040000.html"
# "Running LLM digest analysis for session 20251106_040000"
# "Found N format issues in session 20251106_040000"
```

**Expected Behavior**:
- ✅ Quality monitor finds digest HTML by session_id
- ✅ LLM analysis runs successfully
- ✅ Issues detected and logged (if any)
- ✅ GitHub issues created for problems found

**Check Quality Monitor Logs**:
```bash
tail -f scripts/quality-monitor/quality_monitor.log
```

---

### Step 6: Verify File Storage

```bash
# After digest generation, check files match session_id
SESSION_ID="20251106_040000"  # Replace with actual session_id from console

ls -lh quality_logs/actual_digest_${SESSION_ID}.html
ls -lh quality_logs/input_emails_${SESSION_ID}.json

# Both files should exist with same timestamp
```

**Expected**: Files exist with matching session_id

---

## Common Issues & Solutions

### Issue: Labels Still Not Applied

**Symptom**: Classification completes but no labels appear on emails

**Possible Causes**:
1. Extension reload didn't apply mapper.js fix
2. Browser cache holding old code

**Solution**:
```bash
# Hard refresh extension:
1. chrome://extensions → Disable ShopQ
2. Wait 5 seconds
3. chrome://extensions → Enable ShopQ
4. Clear browser cache (Ctrl+Shift+Delete)
5. Reload Gmail tab
6. Try "Organize" again
```

---

### Issue: Still Getting Duplicate Digests

**Symptom**: Two digests sent, one nearly empty

**Possible Causes**:
1. Extension reload didn't apply summary-email.js fix
2. Old lock data in chrome.storage

**Solution**:
```bash
# Clear extension storage:
1. Right-click ShopQ icon → Inspect
2. In DevTools console:
   chrome.storage.local.clear(() => console.log('Storage cleared'))
3. Reload extension
4. Try "Organize" again
```

---

### Issue: Quality Monitor Can't Find Digest

**Symptom**: "No digest HTML file found for session" in quality monitor logs

**Possible Causes**:
1. Backend not restarted (still using old code)
2. Session tracking not working

**Solution**:
```bash
# Verify backend is running with new code:
ps aux | grep uvicorn | grep 23712

# If PID is different or not found:
pkill -f "uvicorn shopq.api"
nohup uvicorn shopq.api:app --host 127.0.0.1 --port 8000 > /tmp/shopq-api.log 2>&1 &

# Get new PID:
ps aux | grep uvicorn | grep -v grep
```

---

### Issue: Console Shows Old Errors

**Symptom**: Still seeing "Assignment to constant variable" or old lock messages

**Possible Causes**:
1. Browser cached old extension code
2. Service worker not restarted

**Solution**:
```bash
# Force service worker restart:
1. chrome://extensions → ShopQ → "service worker" link
2. In DevTools: Right-click "Reload" → Hard Reload
3. Or: chrome://serviceworker-internals
4. Find ShopQ → Click "Unregister"
5. Reload extension
```

---

## Rollback Instructions

If any fixes cause new issues:

### Backend Rollback
```bash
# Stop current server
kill 23712

# Revert changes
git checkout HEAD -- shopq/api.py

# Restart with old code
uvicorn shopq.api:app --host 127.0.0.1 --port 8000
```

### Extension Rollback
```bash
# Revert extension changes
git checkout HEAD -- extension/modules/mapper.js extension/modules/summary-email.js

# Reload extension in Chrome
# Go to chrome://extensions → Reload ShopQ
```

---

## Success Criteria Checklist

After testing, verify ALL of these:

- [ ] Extension reloaded without errors
- [ ] DevTools console shows no errors
- [ ] Labels applied to all unlabeled emails
- [ ] Console shows proper ShopQ/* label names
- [ ] Single digest email sent (not two)
- [ ] Console shows lock acquisition with session_id
- [ ] Console shows lock release after digest sent
- [ ] Rapid clicks show cooldown messages
- [ ] No "Assignment to constant variable" error
- [ ] Quality monitor finds digest HTML
- [ ] Files exist: `actual_digest_{session_id}.html`
- [ ] Files exist: `input_emails_{session_id}.json`
- [ ] Quality analysis runs successfully
- [ ] GitHub issues created (if problems found)

---

## Next Steps After Successful Verification

1. **Review Quality Issues**
   ```bash
   # View issues found in latest digest
   ./scripts/view-quality-issues.sh

   # Or check GitHub:
   # https://github.com/jkoufopoulos/mailq-prototype/issues?q=is:issue+label:quality
   ```

2. **Monitor Ongoing Sessions**
   ```bash
   # Quality monitor runs every 5 minutes
   # Watch real-time logs:
   tail -f scripts/quality-monitor/quality_monitor.log
   ```

3. **Address Quality Issues**
   - Review GitHub issues created by quality monitor
   - Prioritize CRITICAL issues (e.g., bills misclassified)
   - Use quality feedback to improve classification rules

---

## Useful Commands

```bash
# Check backend health
curl http://127.0.0.1:8000/health

# View recent backend logs
tail -20 /tmp/shopq-api.log

# Check quality monitor status
./scripts/quality-system-status.sh

# Force quality check on latest session
./scripts/force-quality-check.sh

# View all quality issues
./scripts/view-quality-issues.sh

# List recent digest files
ls -lht quality_logs/actual_digest_*.html | head -5

# Check database for recent sessions
sqlite3 quality_control.db "SELECT session_id, timestamp, thread_count FROM sessions ORDER BY timestamp DESC LIMIT 5;"
```

---

**Ready to Test!** Follow the steps above after reloading your Chrome extension.
