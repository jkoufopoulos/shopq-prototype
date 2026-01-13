# Verify-First Strategy - Maximum Accuracy Configuration

**Date**: 2025-11-05
**Objective**: Maximize classification accuracy by verifying nearly all emails
**Trade-off**: Slightly higher cost for significantly higher accuracy

## Strategy Overview

```
Confidence Score → Action
─────────────────────────────────────────────────────────────
0.95 - 1.00      → ✅ Auto-apply (detectors only, skip verifier)
                    Examples: OTP codes, bank alerts
                    Volume: ~5-10% of emails
                    Accuracy: ~98%

0.50 - 0.94      → 🔍 Verifier validates FIRST
                    ↳ Verifier confirms   → ✅ Apply labels
                    ↳ Verifier rejects    → ❌ Mark "Uncategorized"
                    Examples: Rules (0.70-0.85), LLM (0.75-0.90)
                    Volume: ~75-85% of emails
                    Accuracy: ~90-95% (after verification)

< 0.50           → ❌ Mark "Uncategorized" → User organizes
                    Examples: Truly ambiguous emails
                    Volume: ~5-15% of emails
                    Accuracy: 100% (user manual)
```

## Configuration Changes

### Before (High Threshold, Skip Verifier)
```python
TYPE_CONFIDENCE_MIN = 0.92      # 92% required to auto-apply
LABEL_CONFIDENCE_MIN = 0.85     # 85% for individual labels
TYPE_GATE = 0.92                # Mapper gate
VERIFIER_HIGH_CONFIDENCE = 0.90 # Verify only 0.50-0.90
```

**Result**: 100% of rules-based emails → Uncategorized → User organizes manually

### After (Verify-First Strategy)
```python
TYPE_CONFIDENCE_MIN = 0.70      # Lower gate to 70%
LABEL_CONFIDENCE_MIN = 0.70     # Match type threshold
TYPE_GATE = 0.70                # Mapper gate matches
VERIFIER_HIGH_CONFIDENCE = 0.94 # Verify up to 94% (nearly everything)
```

**Result**: 75-85% verified by AI → 90-95% accuracy → Smaller user backlog

## How It Works

### Example 1: GitHub Notification (Rules-Based, 0.70 confidence)

**Old System**:
1. Rules classify: `notification`, confidence: 0.70
2. Backend gate: 0.70 < 0.92 → **REJECT** → Uncategorized
3. User manually organizes

**New System**:
1. Rules classify: `notification`, confidence: 0.70
2. Backend gate: 0.70 >= 0.70 → **PASS**
3. Verifier check: 0.70 in range [0.50, 0.94] → **VERIFY**
4. Verifier validates:
   - ✅ Confirms → Apply `MailQ/Notifications`
   - ❌ Rejects → Mark Uncategorized → User organizes
5. System learns from verifier decision

### Example 2: Amazon Receipt (LLM, 0.80 confidence)

**Old System**:
1. LLM classifies: `receipt`, confidence: 0.80
2. Backend gate: 0.80 < 0.92 → **REJECT** → Uncategorized
3. User manually organizes

**New System**:
1. LLM classifies: `receipt`, confidence: 0.80
2. Backend gate: 0.80 >= 0.70 → **PASS**
3. Verifier check: 0.80 in range [0.50, 0.94] → **VERIFY**
4. Verifier validates:
   - ✅ Confirms → Apply `MailQ/Receipts`, `MailQ/Shopping`
   - ❌ Rejects → Mark Uncategorized → User organizes
5. System learns from verifier decision

### Example 3: Bank Alert (Detector, 0.96 confidence)

**Both Systems**:
1. Detector classifies: `notification`, confidence: 0.96
2. Backend gate: 0.96 >= 0.70 → **PASS**
3. Verifier check: 0.96 > 0.94 → **SKIP VERIFIER**
4. Apply `MailQ/Notifications`, `MailQ/Finance` immediately

## Expected Outcomes

### Accuracy Metrics

| Confidence Range | Volume | Action | Accuracy | Notes |
|-----------------|--------|--------|----------|-------|
| 0.95 - 1.00 | 5-10% | Auto-apply | ~98% | Detectors only |
| 0.70 - 0.94 | 75-85% | Verify first | ~90-95% | Most emails |
| 0.50 - 0.69 | 5-10% | Verify first | ~85-90% | Lower confidence |
| < 0.50 | 5-15% | Uncategorized | 100% | User manual |

**Overall Accuracy**: ~90-95% (weighted average)

### User Experience

**Before**:
- 📬 Inbox: 100 emails
- 🤖 Auto-organized: 0 (all below 0.92 threshold)
- 👤 User organizes: 100 (100%)

**After**:
- 📬 Inbox: 100 emails
- 🤖 Auto-organized: 75-85 (verifier validates)
  - ✅ Correctly labeled: ~70-80 (90-95% accuracy)
  - ❌ Incorrectly labeled: ~5-10 (verifier rejects → Uncategorized)
- 👤 User organizes: 15-25 (verifier rejects + < 0.50)

**Net Result**: 70-80% reduction in manual work with 90-95% accuracy

### Cost Analysis

**Verifier Cost**: ~$0.0001 per email (Gemini 2.0 Flash)

**Monthly Cost** (1000 emails/month):
- Old: $0.10 (10% LLM classification only)
- New: $0.10 + $0.08 (80% verifier) = **$0.18/month**

**Increase**: +$0.08/month (+80%) for 70-80% less manual work

## Learning Benefits

### Old System (0.92 threshold)
- ❌ Rules never applied → No learning from patterns
- ❌ User corrects manually → Slow feedback loop
- ❌ System can't improve confidence scores

### New System (Verify-First)
- ✅ Verifier corrections train the system
- ✅ Successful verifications reinforce patterns
- ✅ Failed verifications create negative examples
- ✅ Confidence scores improve over time
- ✅ Eventually more emails hit 0.95+ → Skip verifier

## Monitoring

### Key Metrics to Track

1. **Verifier Usage Rate**: Should be 75-85%
   - Too high (>90%) → Thresholds may be too low
   - Too low (<60%) → Thresholds may be too high

2. **Verifier Rejection Rate**: Should be 5-15%
   - Too high (>20%) → Rules need improvement
   - Too low (<5%) → System is learning well

3. **User Corrections**: Should decrease over time
   - More user corrections → Adjust patterns
   - Fewer corrections → System learning successfully

4. **Confidence Score Distribution**: Should shift right over time
   - More emails reaching 0.85-0.95 range
   - Fewer emails below 0.70

### Dashboard Queries

```sql
-- Verifier usage over time
SELECT
  DATE(timestamp) as date,
  COUNT(*) as total_emails,
  SUM(CASE WHEN verifier_used = 1 THEN 1 ELSE 0 END) as verified,
  ROUND(100.0 * SUM(CASE WHEN verifier_used = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) as verify_rate
FROM classifications
GROUP BY DATE(timestamp)
ORDER BY date DESC;

-- Verifier rejection rate
SELECT
  DATE(timestamp) as date,
  SUM(CASE WHEN verifier_used = 1 THEN 1 ELSE 0 END) as verified,
  SUM(CASE WHEN verifier_verdict = 'reject' THEN 1 ELSE 0 END) as rejected,
  ROUND(100.0 * SUM(CASE WHEN verifier_verdict = 'reject' THEN 1 ELSE 0 END) /
        SUM(CASE WHEN verifier_used = 1 THEN 1 ELSE 0 END), 1) as reject_rate
FROM classifications
WHERE verifier_used = 1
GROUP BY DATE(timestamp)
ORDER BY date DESC;

-- Confidence score distribution
SELECT
  CASE
    WHEN type_confidence >= 0.95 THEN '0.95-1.00 (Auto)'
    WHEN type_confidence >= 0.70 THEN '0.70-0.94 (Verify)'
    WHEN type_confidence >= 0.50 THEN '0.50-0.69 (Verify)'
    ELSE '<0.50 (Skip)'
  END as confidence_bucket,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) as percentage
FROM classifications
WHERE DATE(timestamp) = DATE('now')
GROUP BY confidence_bucket
ORDER BY confidence_bucket;
```

## Rollback Plan

If accuracy is not meeting expectations (< 85%), rollback:

```python
# Revert to strict thresholds
TYPE_CONFIDENCE_MIN = 0.92
LABEL_CONFIDENCE_MIN = 0.85
TYPE_GATE = 0.92
VERIFIER_HIGH_CONFIDENCE = 0.90
```

This returns to 100% user manual organization (safe but high effort).

## Success Criteria

**After 1 Week**:
- ✅ Verifier usage: 75-85%
- ✅ Verifier rejection: 10-20% (initial learning phase)
- ✅ User corrections: < 10% of auto-labeled emails
- ✅ No increase in mis-labeled emails in wrong folders

**After 1 Month**:
- ✅ Verifier usage: 70-80% (should decrease as confidence improves)
- ✅ Verifier rejection: 5-15% (system learning)
- ✅ User corrections: < 5% of auto-labeled emails
- ✅ More emails reaching 0.85-0.95 confidence range

**After 3 Months**:
- ✅ Verifier usage: 60-70% (more emails hitting 0.95+)
- ✅ Verifier rejection: < 10%
- ✅ User corrections: < 3% of auto-labeled emails
- ✅ System confidently handling 80-90% of emails

## Files Changed

1. `mailq/config/confidence.py` - Lowered thresholds to 0.70, widened verifier range
2. `domain/models.py` - Added dimension-specific confidence fields
3. `domain/classify.py` - Populate confidence scores from rules
4. `adapters/api_bridge.py` - Use dimension-specific confidence in API

## Next Steps

1. ✅ **Commit confidence scoring fix** (this PR)
2. ✅ **Commit threshold changes** (this PR)
3. ⏭️ **Deploy to production**
4. ⏭️ **Monitor verifier usage** (should be 75-85%)
5. ⏭️ **Track accuracy metrics** (should be 90-95%)
6. ⏭️ **Collect user feedback** (is backlog smaller?)

---

**Status**: ✅ READY TO DEPLOY
**Risk**: LOW (can rollback immediately if needed)
**Expected Impact**: 70-80% reduction in manual work with 90-95% accuracy
