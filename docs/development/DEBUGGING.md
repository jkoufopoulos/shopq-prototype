# ShopQ Debugging Guide

Complete guide to debugging digest generation, classification, and visual output quality.

## Quick Start

```bash
# Automated watch mode (recommended)
./scripts/watch-and-debug.sh

# Single validation run
./scripts/validate-digest.sh

# Debug specific aspects
./scripts/mailq-debug featured    # Featured selection
./scripts/mailq-debug labels      # Label counts
./scripts/mailq-debug snapshot    # Complete snapshot
```

---

## Table of Contents

- [Automated Debugging (Watch Mode)](#automated-debugging-watch-mode)
- [Visual Digest Validation](#visual-digest-validation)
- [Debug Endpoints](#debug-endpoints)
- [Common Issues](#common-issues)
- [Debugging Tips](#debugging-tips)
- [CLI Tool Usage](#cli-tool-usage)

---

## Automated Debugging (Watch Mode)

### The Problem

Every digest needs manual checking:
- Are all emails represented?
- Do age markers appear for old emails?
- Is weather enrichment working?
- Are entity numbers correct?

### The Solution

**Watch mode** - Set it and forget it. Automatically validates every digest as it's generated.

### Quick Start

**One-time setup (30 seconds):**

```bash
# 1. Show setup instructions
./scripts/reset-for-debug.sh

# 2. Follow the 4 steps (reload extension, clear data, reload Gmail, wait 10 sec)

# 3. Start watch mode
./scripts/watch-and-debug.sh
```

That's it! Now it runs forever, automatically checking every digest.

### What Happens

**Watch Mode Running:**

```
👁️  Watch Mode - Automated Digest Debugging
===========================================
Monitoring for new digest sessions every 5s...

.........  ← Waiting for new digest

🆕 NEW DIGEST DETECTED - Session: 20251031_120345

📊 Quick Stats:
   Total: 25 emails
   Featured: 8
   Orphaned: 2
   Noise: 15

✅ Timestamps: Real email timestamps
✅ Coverage: All 25 emails represented
✅ Temporal awareness: Age markers found
✅ Weather: Present

🎉 ALL VALIDATIONS PASSED!
```

**When Issues Detected:**

```
🆕 NEW DIGEST DETECTED - Session: 20251031_120456

📊 Quick Stats:
   Total: 30 emails
   Featured: 5
   Orphaned: 0
   Noise: 10

❌ Timestamps: Using current time (ISO format)
❌ Coverage: 15/30 emails (gap: 15)
❌ Temporal awareness: No age markers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ ISSUES DETECTED - Running full debug analysis...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 Fixing: TIMESTAMP_MISSING
  → Adding emailTimestamp to logger.js ✅
  → Updating api.py ✅

⚠️  CODE CHANGES MADE - Manual steps required:
  1. Reload extension
  2. Clear data in Gmail
  3. Wait for new digest

Watch mode will auto-validate the new digest when it appears.
```

**After Manual Steps:**

```
.........  ← Waiting

🆕 NEW DIGEST DETECTED - Session: 20251031_120512

✅ Timestamps: Real email timestamps  ← Fixed!
✅ Coverage: All 30 emails represented  ← Fixed!
✅ Temporal awareness: Age markers found  ← Fixed!

🎉 ALL VALIDATIONS PASSED!

Continuing to watch for more digests...
```

### What It Checks

Every digest is automatically validated for:

**✅ Real Timestamps**
- **Bad**: `2025-10-31T18:07:25` (current time when logged)
- **Good**: `1730398645000` (Gmail's internalDate in milliseconds)

**✅ Complete Coverage**
- Featured + Orphaned + Noise = Total emails
- No emails left out of the digest

**✅ Temporal Awareness**
- Age markers like `[5 days old]` appear for old emails
- Users can see email age at a glance

**✅ Weather Enrichment**
- Location-aware weather in digest greeting
- Example: "cloudy 55° in Brooklyn"

**✅ Entity Numbers**
- Continuous numbering (1, 2, 3, ... no gaps)
- All featured entities have references

### Output Files

All validation results saved to `test-results/watch-mode/`:

```
test-results/watch-mode/
├── iteration-1/
│   ├── session.csv          ← Session data
│   ├── digest.txt           ← Digest content
│   └── debug-output.log     ← Debug run (if issues found)
├── iteration-2/
│   └── ...
├── iteration-N/
│   └── ...
└── summary.csv              ← All iterations summary
```

**View summary:**
```bash
cat test-results/watch-mode/summary.csv
```

Output:
```
iteration,session_id,total,featured,orphaned,noise,real_timestamps,all_passed
1,20251031_120345,25,8,2,15,1,1
2,20251031_120456,30,5,0,10,0,0
3,20251031_120512,30,8,2,20,1,1
```

### Success Criteria

Watch mode reports `🎉 ALL VALIDATIONS PASSED` when:

- ✅ Real email timestamps used (not current time)
- ✅ All emails represented (featured + orphaned + noise = total)
- ✅ Age markers present for old emails
- ✅ Weather enrichment working

### Options

```bash
./scripts/watch-and-debug.sh      # Check every 5 seconds (default)
./scripts/watch-and-debug.sh 10   # Check every 10 seconds
```

**Running in background:**
```bash
# Start in background
./scripts/watch-and-debug.sh > /tmp/watch-mode.log 2>&1 &

# Check output
tail -f /tmp/watch-mode.log

# Stop
pkill -f watch-and-debug.sh
```

---

## Visual Digest Validation

### What This Does

**Validates that the digest email accurately represents what was classified/organized.**

Cross-references 3 data sources:
1. **Extension logger** (what was classified)
2. **Backend tracking** (what was processed)
3. **Visual digest** (what user sees)

### Quick Start

```bash
# 1. Clear old data first (in Gmail console F12)
indexedDB.deleteDatabase('ShopQLogger');
await chrome.storage.local.clear();
location.reload();

# 2. Run validation
./scripts/validate-digest.sh
```

### What Gets Validated

**✅ Entity Numbers Match**
- Backend says: 6 featured entities
- Digest shows: (1), (2), (3), (4), (5), (6)
- **Check**: All numbers present and continuous

**✅ Noise Summary Accurate**
- Backend says: 15 routine emails
- Digest shows: "15 notifications (10 promos, 5 receipts)"
- **Check**: Count matches, categories correct

**✅ Weather Enrichment**
- Digest shows: "cloudy 55° in Brooklyn"
- **Check**: Weather info present

**✅ Temporal Awareness**
- Emails from 5 days ago
- Digest shows: "[5 days old] Job opportunity..."
- **Check**: Age markers present for old emails

**✅ Coverage Complete**
- Classified: 20 emails
- Featured: 6, Orphaned: 2, Noise: 12
- **Check**: 6 + 2 + 12 = 20 (all accounted for)

### Output Files

After running `./scripts/validate-digest.sh`, you get:

```
test-results/validation-{timestamp}/
├── CLAUDE_ANALYSIS.md          ← Read this first!
├── summary.md                  ← Human-readable report
├── report.json                 ← Full structured data
├── classified-emails.json      ← What extension classified
├── backend-tracking.json       ← What backend processed
├── digest-text.txt             ← Plain text digest
├── digest-html.html            ← HTML digest
├── 01-inbox-before-organize.png
├── 02-after-organize.png
└── 03-digest-opened.png
```

### Claude Code Workflow

**1. Run Test**
```bash
./scripts/validate-digest.sh
```

**2. Read Analysis**
```bash
cat test-results/validation-*/CLAUDE_ANALYSIS.md
```

Sample output:
```markdown
# Claude Code Analysis

## Quick Summary
- Total Issues: 2
- Errors: 2
- Status: ❌ FAIL

## Issues Requiring Fixes

### Issue 1: TEMPORAL_AWARENESS_MISSING
**Root Cause**: emailTimestamp not being logged

**Files to Check**:
- extension/modules/logger.js
- shopq/api.py
- shopq/entity_extractor.py

**Recommended Fix**:
Add emailTimestamp field to logger
```

**3. View Evidence**
```bash
# View screenshots
open test-results/validation-*/03-digest-opened.png

# Compare data
cat test-results/validation-*/classified-emails.json
cat test-results/validation-*/backend-tracking.json
cat test-results/validation-*/digest-text.txt
```

**4. Make Fix**

Based on analysis, edit the right files:
```javascript
// extension/modules/logger.js
const entry = {
  // ... existing fields
  emailTimestamp: email.timestamp  // ← Add this
};
```

**5. Re-test**
```bash
# Clear old data (in Gmail console)
indexedDB.deleteDatabase('ShopQLogger');
await chrome.storage.local.clear();
location.reload();

# Re-run validation
./scripts/validate-digest.sh
```

**6. Verify**

Check that issue is resolved in new `CLAUDE_ANALYSIS.md`

---

## Debug Endpoints

### 1. `/api/debug/featured-selection`

**Purpose**: Introspect the selection pipeline and understand why items were featured.

**Response**:
```json
{
  "total_ranked": 25,
  "filtered_remaining": 20,
  "featured": [
    {
      "id": "msg_123",
      "threadId": "msg_123",
      "subject": "Flight AA123 to Los Angeles",
      "from": "N/A",
      "attention_score": 1.0,
      "contextual_score": 0.95,
      "labels": ["ShopQ-Critical"],
      "reason": "critical importance, confidence=0.95"
    }
  ],
  "top15_candidates": [...]
}
```

**What it tells you**:
- How many entities were ranked
- Why specific items made it to "Featured"
- Attention score (based on importance: critical=1.0, time_sensitive=0.7, routine=0.3)
- Contextual score (priority_score = importance × confidence)
- Top 15 candidates for comparison

### 2. `/api/debug/category-summary`

**Purpose**: Show which emails fell into each importance category (critical, time_sensitive, routine).

**Query Parameters**:
- `newer_than_days` (default: 1) - Time window to analyze

**Response**:
```json
{
  "categories": [
    {
      "key": "critical",
      "count": 5,
      "sample_subjects": [
        "Your flight departs soon",
        "Bill due tomorrow"
      ],
      "sample_threadIds": ["msg_1", "msg_2"],
      "gmail_search_query": "label:ShopQ-Critical in:anywhere newer_than:1d"
    }
  ]
}
```

**What it tells you**:
- How many emails in each category
- Sample subjects to verify categorization
- Exact Gmail query used in digest footer links

### 3. `/api/debug/label-counts`

**Purpose**: Compare digest summary counts vs computed counts.

**Query Parameters**:
- `labels` - Comma-separated list of labels to check
- `newer_than_days` (default: 1)

**Response**:
```json
{
  "computed_at": "2025-10-28T12:00:00",
  "gmail_counts": [
    {
      "label": "ShopQ-Uncategorized",
      "query": "label:ShopQ-Uncategorized in:anywhere newer_than:1d",
      "count": 12
    }
  ],
  "digest_reported_total": 12,
  "discrepancy": 0,
  "note": "Live Gmail API integration required for accurate discrepancy detection"
}
```

**What it tells you**:
- Whether digest counts match computed counts
- Any discrepancies between reported and actual counts
- Gmail queries used for verification

**Known limitations**:
- Currently uses computed counts from the same data source
- For true live verification, Gmail API integration is needed
- Gmail may lag 30-90 seconds in applying labels

### 4. `/api/debug/missed-featured`

**Purpose**: Identify high-scoring emails that weren't selected for Featured section.

**Query Parameters**:
- `k` (default: 15) - Number of top candidates to check

**Response**:
```json
{
  "cutoff_contextual_score": 0.65,
  "featured_ids": ["msg_1", "msg_2"],
  "missed": [
    {
      "id": "msg_3",
      "subject": "Newsletter: Industry Updates",
      "contextual_score": 0.27,
      "reason_excluded": "hard_filter:routine_importance"
    }
  ]
}
```

**What it tells you**:
- Minimum score needed to be featured
- Why high-scoring emails were excluded
- Possible exclusion reasons:
  - `hard_filter:routine_importance` - Routine emails are filtered out
  - `below_cutoff_score` - Score too low
  - `diversity_balance` - Removed for diversity/balance

### 5. `/api/debug/digest-snapshot`

**Purpose**: Single comprehensive payload for auditing a digest run.

**Query Parameters**:
- `batch_id` (optional) - Identifier for specific digest run

**Response**:
```json
{
  "header": {
    "day": "Monday, October 28, 2025",
    "generated_at": "2025-10-28T12:00:00",
    "batch_id": "digest_2025-10-28T12:00:00"
  },
  "featured": [...],
  "bottom_links": {
    "reported_counts": {
      "critical": 5,
      "time_sensitive": 10,
      "routine": 15
    },
    "live_counts": [...],
    "discrepancy": 0
  },
  "categories": [...],
  "notes": [
    "Total emails processed: 30",
    "Entities extracted: 25",
    "Featured entities: 5"
  ]
}
```

**What it tells you**:
- Complete state of a digest generation run
- All data needed to audit and debug
- Can be saved to file for later analysis

---

## Common Issues

### Issue: ENTITY_COUNT_MISMATCH

**What**: Digest shows 4 entity refs but backend has 6 featured

**Root Cause**: Entity linking broken or timeline selection wrong

**Files to Check**:
- `shopq/card_renderer.py` - Entity linking logic
- `shopq/timeline_synthesizer.py` - Selection logic
- `shopq/narrative_generator.py` - Prompt generation

**Fix**:
```python
# Check that all featured entities get numbered
featured = timeline.featured
for i, entity in enumerate(featured, start=1):
    # Entity should be linkable with number i
```

### Issue: TEMPORAL_AWARENESS_MISSING

**What**: No "[5 days old]" markers despite old emails

**Root Cause**: Timestamps not flowing through system

**Files to Check**:
- `extension/modules/logger.js` - Must save `emailTimestamp`
- `shopq/api.py` - Must extract `emailTimestamp`
- `shopq/entity_extractor.py` - Must parse timestamp
- `shopq/timeline_synthesizer.py` - Must add age markers

**Fix**:
```javascript
// logger.js
emailTimestamp: email.timestamp  // Add this field
```

```python
# api.py
'timestamp': item.get('emailTimestamp', '')  # Extract it
```

### Issue: NOISE_COUNT_MISMATCH

**What**: Digest shows "10 notifications" but backend has 15

**Root Cause**: Noise summary generation wrong

**Files to Check**:
- `shopq/importance_classifier.py` (`categorize_routine()`)
- `shopq/narrative_generator.py` - Noise section

**Fix**:
```python
# Check that categorize_routine counts threads correctly
noise_breakdown = classifier.categorize_routine(routine_emails)
total = sum(noise_breakdown.values())
# Should equal len(routine_emails)
```

### Issue: WEATHER_MISSING

**What**: No weather in digest

**Root Cause**: Weather API failing or not enriched

**Files to Check**:
- `shopq/weather_enrichment.py` - API calls
- `shopq/narrative_generator.py` - Weather prompt

**Fix**:
```python
# Check weather API logs
# Look for "Weather enrichment complete" in backend logs
```

### Issue: COVERAGE_GAP

**What**: 20 emails classified but only 18 in digest

**Root Cause**: Some emails not featured, orphaned, or noise

**Files to Check**:
- `shopq/entity_extractor.py` - Extraction failures
- `shopq/timeline_synthesizer.py` - Selection logic

**Fix**:
```python
# Check entity extraction success rate
# Verify all importance levels get included
```

---

## Debugging Tips

### Check if timestamps are logged

```javascript
// In Gmail console
const db = await new Promise(r => {
  const req = indexedDB.open('ShopQLogger', 1);
  req.onsuccess = () => r(req.result);
});

const tx = db.transaction(['classifications'], 'readonly');
const all = await new Promise(r => {
  const req = tx.objectStore('classifications').getAll();
  req.onsuccess = () => r(req.result);
});

console.log('Sample entry:', all[0]);
console.log('Has emailTimestamp?', 'emailTimestamp' in all[0]);
```

### Check backend receives timestamps

```bash
# Watch backend logs
tail -f /tmp/mailq-backend.log | grep "📅"
```

### Check entity timestamps

```bash
# View backend tracking
curl -s http://localhost:8000/api/tracking/session/latest | \
  jq '.threads[] | {subject, timestamp}'
```

### Force fresh classification

```javascript
// Clear everything in Gmail console
indexedDB.deleteDatabase('ShopQLogger');
await chrome.storage.local.clear();
location.reload();
```

### Gmail Label Lag

**Issue**: Digest shows 19 emails, but Gmail search only shows 15.

**Cause**: Gmail may take 30-90 seconds to index labels after they're applied.

**Solution**:
1. Wait 90 seconds after digest generation
2. Re-run the Gmail search
3. If still mismatched, use `/api/debug/label-counts` to investigate

### Archived Emails Not Found

**Issue**: Gmail search doesn't find emails shown in digest footer counts.

**Cause**: ShopQ archives emails after organizing. Gmail search must include `in:anywhere`.

**Solution**: All digest footer links now include `in:anywhere` in queries:
```
label:ShopQ-Notifications in:anywhere newer_than:1d
```

### Featured Selection Seems Wrong

**Issue**: Important email wasn't featured, or unimportant email was featured.

**Debug Steps**:
1. Run `./scripts/mailq-debug featured` to see scores
2. Check `attention_score` (importance level)
3. Check `contextual_score` (importance × confidence)
4. Run `./scripts/mailq-debug missed --k 20` to see what didn't make the cut
5. Check `reason_excluded` for explanation

**Common Reasons**:
- Low confidence score (< 0.8)
- Routine importance (automatically filtered)
- Below diversity threshold

---

## CLI Tool Usage

### Installation

The `mailq-debug` CLI tool is in the scripts directory:

```bash
chmod +x scripts/mailq-debug
./scripts/mailq-debug --help
```

### Commands

#### `mailq-debug featured`

Show featured selection details in a formatted table.

```bash
./scripts/mailq-debug featured
```

**Output**:
```
Pipeline Summary
━━━━━━━━━━━━━━━━━━━━
Total ranked: 25
Featured: 5
Filtered out: 20

✨ Featured Entities
┌──────────────────────┬───────────┬─────────────┬──────────────────┐
│ Subject              │ Attention │ Contextual  │ Reason           │
├──────────────────────┼───────────┼─────────────┼──────────────────┤
│ Flight AA123 to LA   │ 1.000     │ 0.950       │ critical, 0.95   │
└──────────────────────┴───────────┴─────────────┴──────────────────┘
```

#### `mailq-debug labels`

Check label counts and look for discrepancies.

```bash
# Check specific labels
./scripts/mailq-debug labels --labels ShopQ-Uncategorized,ShopQ-Notifications

# Check labels from last 3 days
./scripts/mailq-debug labels --labels ShopQ-Newsletters --days 3
```

#### `mailq-debug snapshot`

Get complete snapshot and save to file.

```bash
# Save latest snapshot
./scripts/mailq-debug snapshot

# Save specific batch
./scripts/mailq-debug snapshot --batch digest_2025-10-28
```

**Output**:
```
✓ Snapshot saved to /tmp/shopq_snapshot_latest.json

Header
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Day: Monday, October 28, 2025
Generated: 2025-10-28T12:00:00
Batch ID: digest_2025-10-28T12:00:00
```

#### `mailq-debug categories`

Show category breakdown.

```bash
./scripts/mailq-debug categories
```

#### `mailq-debug missed`

Check for missed high-priority emails.

```bash
# Check top 15 candidates
./scripts/mailq-debug missed

# Check top 30 candidates
./scripts/mailq-debug missed --k 30
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEBUG_FEATURED` | `false` | Enable inline [score, reason] hints in digest |
| `SHOPQ_API_URL` | `http://localhost:8000` | API URL for CLI tool |

**Enable debug hints:**
```bash
export DEBUG_FEATURED=true
```

When enabled, featured items in the digest will show:
```
Your flight AA123 [score=0.95, critical, conf=0.95] departs at 10:00 AM.
```

---

## Implementation Details

### Pipeline Flow

1. **Stage 1**: ImportanceClassifier → critical/time_sensitive/routine
2. **Stage 2**: EntityExtractor → extract entities from critical + time_sensitive
3. **Stage 3**: Deduplicator → deduplicate entities
4. **Stage 4**: TimelineSynthesizer → select featured entities
   - ALWAYS includes ALL critical entities
   - Fills remaining slots with top time_sensitive entities
   - Adaptive selection: 3-10 entities based on volume
5. **Stage 5+**: Enrichment, narrative generation, verification, rendering

### Priority Score Calculation

```python
priority_score = importance_weight × confidence

# Importance weights:
# - critical: 1.0
# - time_sensitive: 0.7
# - routine: 0.3
```

**Example**:
- Critical flight with 0.95 confidence → priority_score = 1.0 × 0.95 = 0.95
- Time-sensitive event with 0.9 confidence → priority_score = 0.7 × 0.9 = 0.63
- Routine newsletter with 0.9 confidence → priority_score = 0.3 × 0.9 = 0.27 (filtered)

### Debug Data Storage

Debug data is stored in-memory in `shopq.api_debug.last_digest_store`:

```python
{
    "timestamp": "2025-10-28T12:00:00",
    "total_ranked": 25,
    "filtered_remaining": 20,
    "featured": [Entity, ...],
    "all_entities": [Entity, ...],
    "importance_groups": {
        "critical": [...],
        "time_sensitive": [...],
        "routine": [...]
    },
    "all_emails": [...],
    "noise_breakdown": {...}
}
```

Updated automatically when digest is generated via `context_digest._store_debug_data()`.

---

## Testing

Run the debug endpoint tests:

```bash
pytest shopq/tests/test_debug_endpoints.py -v
```

**Tests include**:
- `test_set_last_digest` - Verify debug data storage
- `test_get_entity_title_flight` - Entity title extraction
- `test_inline_debug_hidden_by_default` - Debug hints disabled by default
- `test_inline_debug_shown_when_enabled` - Debug hints when DEBUG_FEATURED=true

---

## Related Documentation

- [TESTING.md](TESTING.md) - Testing procedures
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design details
- [QUICKSTART.md](../QUICKSTART.md) - Basic setup and usage
- [SHOPQ_REFERENCE.md](../SHOPQ_REFERENCE.md) - AI assistant guide

---

**Last Updated**: 2025-11-01
