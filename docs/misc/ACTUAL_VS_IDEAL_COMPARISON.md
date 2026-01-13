# Actual vs Ideal Digest Comparison

**Date**: 2025-11-01 16:00
**Actual**: 9 items featured
**Ideal**: 29 items should be featured
**Gap**: 20 items missing (69% recall failure)

---

## Side-by-Side Comparison

### ACTUAL DIGEST (What system produced)

```
Your Inbox --Saturday, November 01 at 04:00 PM

1. Security alert ✅
2. AutoPay for Brooklinen ❌
3. Time to vote, make every share count ❌
4. Last chance feedback about Vanguard ❌
5. Appointment Midtown Dental (Nov 7, 2:00 PM) ✅
6. J & V Catch-up (Nov 7, 2:05 PM) ✅
7. J & V Catch-up from yesterday (Oct 31, 2 PM) ❌
8. Check out Drawing Hive ❌
9. A meeting has adjourned ❌

Plus, there are 65 routine notifications.
```

**Score**: 3/9 correct (33%), 6/9 wrong (67%)

### IDEAL DIGEST (What it should produce)

```
🚨 CRITICAL (8 emails):
  • Credit Builder statement ready
  • Security alert ← ACTUAL HAS THIS ✅
  • Bill increase alert
  • Deposit to checking account
  • Low balance alert
  • Bank statement
  • Con Edison bill
  • PayPal category selection

📦 TODAY (3 emails):
  • Delivered: Vintage Mesh Top Hat
  • Delivered: Face Body Paint Palette
  • Delivered: Brooklinen package ← ACTUAL SORT OF HAS (as #2 "AutoPay") ⚠️

📅 COMING UP (6 emails):
  • TaskRabbit scheduled Nov 5
  • Dental appointment Nov 7 ← ACTUAL HAS THIS ✅
  • Updates to: General Mounting
  • Your upcoming General Mounting task
  • J & V Catch-up Nov 7 ← ACTUAL HAS THIS ✅
  • P+S event Nov 9

💼 WORTH KNOWING (12 emails):
  • Con Edison bill
  • PayPal Debit category
  • Shipped: Burger Press Tool
  • Shipped: Protein Shake
  • Job Alerts from Aristocrat
  • OnePay AI Product Lead role
  • ... and 6 more

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Everything else (70 emails):
  • 18 promotional ← "vote" and "Vanguard" should be here
  • 12 past events ← "Oct 31", "Drawing Hive", "adjourned" should be here
  • 1 MailQ digest (filtered) ← Phase 1 filtered this ✅
  • 33 updates & notifications
```

---

## Gap Analysis

### ✅ What Actual Got Right (3 items)

1. **Security alert** - ✅ Correctly featured in CRITICAL
2. **Dental appointment Nov 7** - ✅ Correctly featured in COMING UP
3. **J & V Catch-up Nov 7** - ✅ Correctly featured in COMING UP

**Precision**: 3/9 = 33%

### ❌ False Positives (6 items that shouldn't be featured)

1. **"AutoPay for Brooklinen"** - ❌ Should be in RECEIPTS (noise)
   - Why: Receipt for past purchase
   - Ideal: Not featured

2. **"Time to vote, make every share count"** - ❌ Should be in PROMOTIONAL (noise)
   - Subject: "We Need Your Vote! Every Share Counts! Please Vote Now!"
   - Ideal: Listed under "promotional" (18 emails)

3. **"Last chance feedback about Vanguard"** - ❌ Should be in PROMOTIONAL (noise)
   - Subject: "Reminder: Last chance to provide feedback about Vanguard"
   - Ideal: Listed under "promotional"

4. **"J & V Catch-up from yesterday (Oct 31, 2 PM)"** - ❌ Should be FILTERED (past event)
   - Subject: "Notification: J & V Catch-up @ Fri Oct 31, 2025 2pm"
   - Ideal: Listed under "past events (filtered)" (12 emails)

5. **"Check out Drawing Hive"** - ❌ Should be FILTERED (past event)
   - Subject: "Don't forget: Drawing Hive starts in 1 hour" (from Oct 30)
   - Ideal: Listed under "past events (filtered)"

6. **"A meeting has adjourned"** - ❌ Should be FILTERED (past event)
   - Subject: Unknown (likely meeting notification)
   - Ideal: Listed under "past events (filtered)"

**False Positive Breakdown**:
- 3 promotional items featured (should be noise)
- 3 past events featured (should be filtered)

### ❌ False Negatives (26 items missing)

#### CRITICAL Missing (7 of 8):

1. ❌ "Credit Builder statement ready"
2. ✅ "Security alert" - FEATURED
3. ❌ "Bill increase alert"
4. ❌ "Deposit to checking account"
5. ❌ "Low balance alert"
6. ❌ "Bank statement"
7. ❌ "Con Edison bill"
8. ❌ "PayPal category selection"

**Missing**: 7/8 = 87.5%

#### TODAY Missing (2 of 3):

1. ❌ "Delivered: Vintage Mesh Top Hat"
2. ❌ "Delivered: Face Body Paint Palette"
3. ⚠️ "Delivered: Brooklinen package" - Featured but as "AutoPay" (wrong framing)

**Missing**: 2/3 = 67%

#### COMING UP Missing (3 of 6):

1. ❌ "TaskRabbit scheduled Nov 5"
2. ✅ "Dental appointment Nov 7" - FEATURED
3. ❌ "Updates to: General Mounting"
4. ❌ "Your upcoming General Mounting task"
5. ✅ "J & V Catch-up Nov 7" - FEATURED
6. ❌ "P+S event Nov 9"

**Missing**: 3/6 = 50%

#### WORTH KNOWING Missing (12 of 12):

1. ❌ "Con Edison bill"
2. ❌ "PayPal Debit category"
3. ❌ "Shipped: Burger Press Tool"
4. ❌ "Shipped: Protein Shake"
5. ❌ "Job Alerts from Aristocrat"
6. ❌ "OnePay AI Product Lead role"
7. ❌ ... and 6 more

**Missing**: 12/12 = 100%

---

## Performance Metrics

### Actual System Performance

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Precision** | 33% (3/9) | ≥75% | ❌ FAIL |
| **Recall** | 10% (3/29) | ≥70% | ❌ FAIL |
| **Noise Filtered** | 67% (6/9 wrong) | ≤25% | ❌ FAIL |
| **Phase 1 Filter** | 6/99 (6.1%) | 5-10% | ✅ PASS |

### Breakdown by Category

| Category | Should Feature | Actually Featured | Recall |
|----------|----------------|-------------------|--------|
| Critical | 8 | 1 | 12.5% ❌ |
| Today | 3 | 0 (1 wrong framing) | 0% ❌ |
| Coming Up | 6 | 2 | 33% ❌ |
| Worth Knowing | 12 | 0 | 0% ❌ |
| **TOTAL** | **29** | **3** | **10%** ❌ |

### False Positive Analysis

| Type | Count | Examples |
|------|-------|----------|
| Promotional | 2 | "vote", "Vanguard survey" |
| Past Events | 3 | "Oct 31", "Drawing Hive", "adjourned" |
| Receipts | 1 | "AutoPay Brooklinen" |
| **TOTAL** | **6** | 67% of featured items |

---

## Root Cause Analysis

### Issue 1: Importance Classification Broken (Primary Issue)

**Symptom**: 26 important emails not featured

**Evidence**:
- 7/8 critical items missing (bills, statements, alerts)
- 2/3 deliveries missing
- 12/12 "worth knowing" missing (jobs, shipments, personal)

**Root Cause**: ImportanceClassifier is not prioritizing correctly

**Where**: `mailq/importance_classifier.py`

**Impact**: MASSIVE - 90% recall failure

---

### Issue 2: Phase 1 Filters Missing Patterns (Secondary Issue)

**Symptom**: 3 past events still featured

**Evidence**:
1. "J & V Catch-up from yesterday (Oct 31)" - Pattern: "Updated invitation with note"
2. "Drawing Hive" - No date in subject
3. "Meeting adjourned" - Semantic understanding needed

**Root Cause**: Time-decay filter only catches 3 specific patterns

**Where**: `mailq/filters/time_decay.py`

**Impact**: MODERATE - 33% of featured items are noise

---

### Issue 3: Wrong Items Prioritized (Tertiary Issue)

**Symptom**: Promotional surveys featured instead of bills/deliveries

**Evidence**:
- "Vote" promo featured
- "Vanguard survey" featured
- Meanwhile, Con Edison bill NOT featured

**Root Cause**: Importance classifier sees "last chance" and treats as time-sensitive

**Where**: `mailq/importance_classifier.py` - time-sensitive patterns

**Impact**: HIGH - User sees noise instead of important info

---

## Action Plan (Priority Order)

### 🔥 URGENT: Fix Importance Classification (Issue #1)

**Problem**: 26 important emails missing

**Investigation needed**:
1. Check why bills/statements not classified as "critical"
2. Check why deliveries not classified as "time_sensitive"
3. Check why jobs/shipments not featured at all

**Files to inspect**:
- `mailq/importance_classifier.py`
- `mailq/context_digest.py` (Stage 1: Classify importance)

**Expected fix**:
- Add explicit patterns for bills: "bill", "statement", "balance"
- Add patterns for deliveries: "delivered:", "delivery confirmation"
- Add patterns for jobs: "job alert", "hiring"

**Impact**: Should boost recall from 10% → 70%+

---

### ⚠️ HIGH: Expand Phase 1 Filter Patterns (Issue #2)

**Problem**: 3 past events still appearing

**Quick wins** (5-10 min each):

1. **Expand calendar patterns**:
```python
# mailq/filters/time_decay.py:70
if any(kw in subject for kw in [
    'notification:',
    'updated invitation:',
    'invitation with note:',
    'calendar:'
]):
    event_date = _extract_event_date_from_notification(subject)
```

2. **Add "yesterday" keyword**:
```python
if 'yesterday' in subject or 'from yesterday' in subject:
    return True  # Yesterday is always past
```

3. **Add "adjourned" keyword** (conservative):
```python
if 'adjourned' in subject or 'has adjourned' in snippet:
    return True  # Meeting already happened
```

**Impact**: Filter 3 more items, boost precision from 33% → 100%

---

### 📊 MEDIUM: Fix Promotional Detection (Issue #3)

**Problem**: "Vote" and "Vanguard" featured, but Con Edison bill not featured

**Investigation**:
- Why does "last chance" trigger time_sensitive?
- Should promotional surveys be time_sensitive?
- Add promotional keywords: "vote", "survey", "feedback"

**Expected fix**:
```python
# Detect promotional even if has urgency keywords
if any(kw in subject for kw in ['vote', 'survey', 'feedback', 'share counts']):
    return 'routine'  # Override time_sensitive
```

**Impact**: Prevent 2 noise items from being featured

---

## Recommended Next Steps

### Step 1: Debug Importance Classification (NOW)

Run diagnosis:
```bash
# Check how emails are classified
python3 -c "
from mailq.importance_classifier import ImportanceClassifier
import csv

classifier = ImportanceClassifier()

# Load ground truth
with open('inbox_review_with notes - inbox_review.csv') as f:
    emails = list(csv.DictReader(f))

# Classify critical emails
critical_should_be = [e for e in emails if 'bill' in e.get('subject', '').lower() or 'statement' in e.get('subject', '').lower()]

print(f'Emails with bills/statements: {len(critical_should_be)}')

for email in critical_should_be[:5]:
    text = f\"{email['subject']} {email.get('snippet', '')}\"
    classification = classifier.classify(text)
    print(f\"Subject: {email['subject'][:50]}\")
    print(f\"Classification: {classification}\")
    print()
"
```

### Step 2: Implement Fixes

Priority 1: Importance classification
Priority 2: Phase 1 pattern expansion
Priority 3: Promotional detection

### Step 3: Re-test

Generate new digest and compare to ideal.

Target metrics:
- Precision: ≥75% (currently 33%)
- Recall: ≥70% (currently 10%)
- Noise: ≤25% (currently 67%)

---

## Summary

### Current State
- ✅ Phase 1 filters working (6 emails filtered)
- ❌ Importance classification broken (90% recall failure)
- ❌ 3 past events slipping through Phase 1
- ❌ Promotional noise prioritized over bills

### Critical Path
1. **Fix importance classification** (biggest impact)
2. Expand Phase 1 patterns (quick wins)
3. Fix promotional detection
4. Re-test and iterate

### Expected Improvement
After fixes:
- Featured: 9 → 25-30 items
- Precision: 33% → 80%+
- Recall: 10% → 75%+

**Status**: Phase 1 partially working, but importance classification is the bottleneck.
