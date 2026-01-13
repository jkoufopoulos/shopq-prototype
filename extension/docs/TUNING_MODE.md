# MailQ Test/Tuning Mode

## Quick Start

When actively tuning the classifier, enable test mode to ensure fresh classifications.

**IMPORTANT:** Test mode is now **unified** - change ONE value in the backend and it syncs to extension automatically.

### 1. Enable Test Mode (Single Source of Truth)

In `mailq/feature_gates.py`, set:

```python
'test_mode': True,  # Change from False to True
```

Then deploy backend:

```bash
./deploy.sh
```

Then reload the extension (chrome://extensions → reload) - it will fetch test mode status from backend

### 2. What Test Mode Does

**Backend (`mailq/feature_gates.py` → `test_mode: True`):**
- ✅ **Disables rules engine** - All emails go to LLM (no stale rules)
- ✅ **Disables feedback learning** - No automatic rule creation
- ✅ **Skips rule learning** - Prevents pattern memorization

**Frontend (synced from backend via `/api/test/mode`):**
- ✅ **Disables cache** - All emails freshly classified (no stale cache)
- ✅ **Logs test mode** - Console shows "🧪 Test mode ENABLED"
- ✅ **Forces fresh classifications** - Every run uses latest backend logic

### 3. Manual Cache Control (from DevTools Console)

Open background page console (chrome://extensions → MailQ → "Inspect views: background page")

```javascript
// Check cache stats
getCacheStats().then(stats => console.log(stats));
// Output: { total: 118, fresh: 118, stale: 0, oldestAge: 2, newestAge: 0 }

// Clear cache manually
clearCache();
// Output: ✅ Classification cache cleared
```

### 4. When to Use Tuning Mode

**Enable when:**
- ✅ Tweaking classifier prompts
- ✅ Adjusting confidence thresholds
- ✅ Testing verifier logic changes
- ✅ Evaluating backend updates
- ✅ Debugging classification issues

**Disable when:**
- ❌ Done tuning (for production use)
- ❌ Cost-sensitive testing (cache saves API calls)
- ❌ Testing cache behavior itself

### 5. Cost Implications

**With cache (TUNING_MODE: false):**
- 100 emails → ~10-30 API calls (70-90% cache hit)
- Cost: ~$0.01-0.03

**Without cache (TUNING_MODE: true):**
- 100 emails → 100 API calls (0% cache hit)
- Cost: ~$0.10

**Recommendation:** Enable tuning mode ONLY during active development, disable for daily use.

### 6. Unified Workflow (Single Source of Truth)

```bash
# 1. Enable test mode in backend
vim mailq/feature_gates.py  # Set 'test_mode': True
./deploy.sh  # Deploy to Cloud Run

# 2. Reload extension (fetches test mode from backend)
# chrome://extensions → MailQ → Reload

# 3. Make classifier changes
vim mailq/classifier.py  # Edit classifier logic
./deploy.sh  # Deploy updates

# 4. Test with fresh classifications
# Click MailQ icon → all emails freshly classified
# Console shows: "🧪 Test mode ENABLED - cache disabled, rules skipped"

# 5. When stable, disable test mode
vim mailq/feature_gates.py  # Set 'test_mode': False
./deploy.sh  # Deploy
# Reload extension → syncs to normal mode
```

### 7. Test Mode Status Check

**On extension load, console should show:**

```
🚀 Initializing config sync...
🔄 Fetching confidence thresholds from backend: https://...
🧪 Test mode ENABLED - cache disabled, rules skipped, no learning
✅ Config sync initialized
```

**During classification:**

```
🧪 TUNING MODE: Cache disabled - all emails will be freshly classified
🤖 Classifying emails...
📊 Cache hit: 0.0%  ← Should always be 0% in test mode
🔄 Classifying 100/100 new emails
```

**Backend logs should show:**

```
🧪 Test mode enabled - skipping rules engine
🧪 Test mode enabled - skipping rule learning
```

If you see cache hits > 0% or rules matching, test mode is NOT active - reload extension.
