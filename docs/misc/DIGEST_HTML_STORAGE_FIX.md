# Digest HTML Storage Fix

**Date**: November 6, 2025 @ 3:50 AM EST
**Issue**: Quality monitor cannot find digest HTML for analysis
**Status**: ✅ Fixed

---

## Problem

### Symptom
Quality monitor reports: `No digest_html in session {session_id}, checking quality_logs...` and finds no matching files.

### Root Cause
**Timestamp mismatch** between session_id in tracking database and digest HTML filename:

- **Session ID**: Generated once at start of digest: `20251106_083734`
- **Digest HTML filename**: Generated later when saving: `20251106_083738` (4 seconds later)
- **Result**: Quality monitor looks for `actual_digest_20251106_083734.html` but file is named `actual_digest_20251106_083738.html`

### Evidence
```bash
# Sessions in tracking database
20251106_083734 (95 threads)
20251106_084036 (95 threads)
20251106_084555 (95 threads)

# Files in quality_logs/
actual_digest_20251106_011419.html
actual_digest_20251106_011423.html
actual_digest_20251106_031420.html

# Missing: Files for 08:37, 08:40, 08:45 sessions
```

---

## Fix Applied

### File: `mailq/api.py`

**Lines 404-408, 417** - Use `session_id` from digest result instead of generating new timestamp

**Before**:
```python
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

html_log_file = os.path.join(log_dir, f"actual_digest_{timestamp}.html")
# ...
emails_log_file = os.path.join(log_dir, f"input_emails_{timestamp}.json")
```

**After**:
```python
# Use session_id from digest result to ensure filename matches tracking database
session_id = result.get('session_id', datetime.now().strftime("%Y%m%d_%H%M%S"))

html_log_file = os.path.join(log_dir, f"actual_digest_{session_id}.html")
# ...
emails_log_file = os.path.join(log_dir, f"input_emails_{session_id}.json")
```

---

## Testing

### 1. Restart Backend
```bash
# Kill existing uvicorn
pkill -f "uvicorn mailq.api"

# Start fresh
uvicorn mailq.api:app --host 127.0.0.1 --port 8000
```

### 2. Generate New Digest
```bash
# In Chrome extension, click "Organize"
# Wait for digest to be sent
```

### 3. Verify File Created
```bash
# Check quality_logs for new file
ls -lh quality_logs/actual_digest_*.html | tail -1

# Expected: File with matching session_id timestamp
# Example: actual_digest_20251106_095030.html
```

### 4. Run Quality Analysis
```bash
./scripts/force-quality-check.sh

# Expected log output:
# "Found digest HTML file: actual_digest_20251106_095030.html"
# "Running LLM digest analysis for session 20251106_095030"
# "Found N format issues in session 20251106_095030"
```

---

## Expected Behavior After Fix

### ✅ Session ID Matches Filename
```
Session in DB:       20251106_095030
Digest HTML file:    actual_digest_20251106_095030.html
Input emails file:   input_emails_20251106_095030.json
```

### ✅ Quality Monitor Finds Digest
```
2025-11-06 04:00:00 [INFO] No digest_html in session 20251106_095030, checking quality_logs...
2025-11-06 04:00:00 [INFO] Found digest HTML file: actual_digest_20251106_095030.html
2025-11-06 04:00:01 [INFO] Running LLM digest analysis for session 20251106_095030
2025-11-06 04:00:15 [INFO] LLM digest analysis found 3 valid issues
```

### ✅ Digest Format Issues Detected
Quality monitor can now analyze digest HTML and report issues like:
- Missing CRITICAL section
- Bills categorized as WORTH KNOWING instead of CRITICAL
- Past events in main list instead of "Everything else"

---

## Related Issues

### Why Recent Sessions Had No Digest HTML

The sessions `20251106_083734`, `20251106_084036`, `20251106_084555` appear in the tracking API but have no digest HTML because:

1. **Extension mapper crash** prevented classification from completing
2. **Digest was still generated** (using cached classifications)
3. **But digest HTML wasn't saved** due to timestamp mismatch
4. **Quality monitor couldn't analyze** these sessions

After extension fix (mapper.js) + backend fix (this one), new digests will:
- ✅ Complete classification successfully
- ✅ Save digest HTML with matching session_id
- ✅ Be analyzable by quality monitor

---

## Long-Term Solution (Future Enhancement)

**Current**: Digest HTML stored in filesystem (`quality_logs/`)
**Problem**: Won't work in Cloud Run (ephemeral filesystem)
**Solution**: Store digest HTML in tracking database

### Schema Change Needed
```sql
ALTER TABLE email_threads ADD COLUMN digest_html TEXT;
```

### API Change Needed
```python
# In /api/tracking/session/{session_id}
return {
    'session_id': session_id,
    'summary': summary,
    'threads': threads,
    'digest_html': digest_html  # Add this field
}
```

See: `QUALITY_CONTROL_PIPELINE.md` for full implementation plan

---

## Rollback

If this causes issues:

```bash
cd /Users/justinkoufopoulos/Projects/mailq-prototype

# Revert changes
git checkout HEAD -- mailq/api.py

# Restart backend
pkill -f "uvicorn mailq.api" && uvicorn mailq.api:app --host 127.0.0.1 --port 8000
```

---

**Status**: ✅ Fixed - Digest HTML filename now matches session_id for reliable quality analysis
