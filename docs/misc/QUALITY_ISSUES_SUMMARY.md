# ShopQ Quality Issues Summary
**Generated**: 2025-11-06 01:32 AM
**Status**: 16 issues identified, 0 created on GitHub

## Executive Summary

Quality monitoring system identified **16 critical issues** across classification, importance scoring, and digest generation:

- **8 High Severity** - Core functionality broken
- **8 Medium/Low Severity** - Classification accuracy issues

### Most Critical Issues

1. ️**All confidence scores = 0.0** (HIGH)
   - No confidence scoring implemented
   - Affects: Classification reliability, verifier triggers

2. ️**Verifier never triggered** (HIGH)
   - 0% trigger rate despite 100% unknown senders
   - Affects: Quality control, misclassification detection

3. ️**Empty from_email field** (HIGH)
   - Email parser not extracting sender
   - Affects: Sender-based rules, relationship classification

4. ️**Financial statements misclassified as critical** (HIGH)
   - "eStatement available" treated as urgent
   - Affects: Digest quality, notification priority

---

## High Severity Issues (8)

### 1. All confidence scores are exactly 0.0
**Pattern**: No confidence scoring implemented
**Evidence**: All 30 sample emails show `type_confidence=0.0`, `entity_confidence=0.0`
**Impact**:
- Cannot determine classification reliability
- Verifier triggers disabled
- No quality metrics

**Fix**:
```python
# Implement pattern-based confidence scoring
if matched_exact_domain:
    confidence = 0.95
elif matched_keyword_pattern:
    confidence = 0.70
else:
    confidence = 0.50
```

**Priority**: P0 - Blocks verifier system

---

### 2. Verifier never triggered despite unknown relationships
**Pattern**: Verifier activation logic broken
**Evidence**: 0/289 emails triggered verifier (0.0%), but all show `relationship='from_unknown'`
**Impact**:
- No quality control on classifications
- Misclassifications go undetected
- Learning system cannot provide feedback

**Root Cause**: Verifier trigger conditions require confidence scores (which are all 0.0)

**Fix**:
```python
# Trigger verifier when:
if confidence < 0.85 or relationship == 'from_unknown':
    run_verifier()
```

**Priority**: P0 - Core quality control broken

---

### 3. Empty from_email field for all emails
**Pattern**: Email parser failing to extract sender
**Evidence**: All 40 emails show `from_email: ''` (empty string)
**Impact**:
- Sender-based rules don't work
- Relationship classification unreliable
- Cannot learn sender patterns

**Root Cause**: Email processing pipeline not extracting 'From' header

**Fix**:
```python
# In email parser:
from_email = email_data.get('from', '')
# Extract email from "Name <email@domain.com>" format
if '<' in from_email:
    from_email = from_email.split('<')[1].split('>')[0]
```

**Priority**: P0 - Blocks sender-based classification

---

### 4. Financial statement notifications misclassified as critical
**Pattern**: Generic "statement" keyword triggers critical classification
**Evidence**:
- 6/10 critical samples are routine statements
- Examples: "eStatement available", "monthly statement ready"

**Impact**:
- Digest flooded with non-urgent notifications
- User trust in "critical" label decreases

**Fix**:
```python
# Only treat as critical if:
- "statement" + "action required"
- "statement" + deadline mention
- NOT "statement available/ready"
```

**Priority**: P1 - Major digest quality issue

---

### 5. Statistics show 0% for all importance categories
**Pattern**: Aggregation query broken
**Evidence**: Overall stats show Critical: 0%, Time-sensitive: 0%, Routine: 0%
**Impact**: Cannot measure system performance

**Fix**: Debug SQL aggregation query in analytics module

**Priority**: P2 - Metrics only

---

## Medium Severity Issues (6)

### 6. Shipment notifications over-classified as time-sensitive
**Pattern**: "Shipped", "Delivered" treated as urgent
**Evidence**: 4/10 time-sensitive emails are routine shipment updates
**Fix**: Only classify as time-sensitive if shipment has issues (delayed, failed)
**Priority**: P1 - Digest quality

---

### 7. Low entity extraction rate (32.9%)
**Pattern**: Only 1/3 of emails have entities extracted
**Evidence**: 95/289 emails (32.9%) have entities
**Fix**: Expand entity extraction to all email types
**Priority**: P2 - Digest richness

---

### 8. Delivery notifications over-classified as critical
**Pattern**: "Out for delivery" treated as urgent
**Evidence**: 2/10 critical samples are routine delivery updates
**Fix**: Downgrade to time-sensitive unless delayed/issue
**Priority**: P1 - Digest quality

---

### 9. Policy update misclassified using medical_claims pattern
**Pattern**: Generic patterns matching unrelated content
**Evidence**: Meta privacy policy classified as medical claim
**Fix**: Add domain context requirements to pattern matching
**Priority**: P2 - Classification accuracy

---

### 10. Promotional emails with action_required elevated to time-sensitive
**Pattern**: action_required flag auto-escalates importance
**Evidence**: "Holiday Season Essentials" marked time-sensitive
**Fix**: Don't auto-elevate promotions based on action_required
**Priority**: P2 - Digest quality

---

## Low Severity Issues (2)

### 11. GitHub issue notifications misclassified
**Pattern**: Issue titles containing keywords trigger wrong classification
**Fix**: Add sender pre-filtering for known domains
**Priority**: P3 - Edge case

---

### 12. Generic all-event time-sensitive classification
**Pattern**: All events marked time-sensitive without date checking
**Fix**: Parse event dates, only mark upcoming events as time-sensitive
**Priority**: P2 - Over-classification

---

## Recommendations

### Immediate Actions (P0)
1. **Implement confidence scoring** (Issue #1)
   - Add pattern-based confidence calculation
   - Update all classification outputs

2. **Fix from_email extraction** (Issue #3)
   - Update email parser
   - Test with real Gmail data

3. **Enable verifier triggers** (Issue #2)
   - Update trigger logic to use confidence + relationship
   - Test with low-confidence samples

### Short-term (P1)
4. **Fix financial statement classification** (Issue #4)
   - Add context-aware pattern matching
   - Test with bank/investment emails

5. **Fix shipment notification classification** (Issue #6)
   - Only elevate if delivery issue exists
   - Test with Amazon/shipping emails

### Medium-term (P2)
6. **Improve entity extraction** (Issue #7)
   - Expand to all email types
   - Add receipt parsing

7. **Fix statistics aggregation** (Issue #5)
   - Debug SQL query
   - Add unit tests

---

## Next Steps

1. **Review and prioritize** these issues
2. **Create GitHub issues** for P0/P1 items
3. **Fix P0 issues** first (confidence, from_email, verifier)
4. **Test with real data** after each fix
5. **Re-run quality pipeline** to verify improvements

---

## Data Sources

- Quality Monitor Database: `scripts/quality-monitor/quality_monitor.db`
- Sessions Analyzed: 4 recent sessions
- Sample Emails: 289 total
- Issues Found: 16 unique patterns
