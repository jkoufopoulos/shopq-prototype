# GDS Temporal Context Issue

## The Problem

**GDS labels were created with temporal awareness**:

```
From GDS_SCHEMA_v1.0.md (line 79):
"Type: event
 Importance: Based on proximity (today → critical, this week → time_sensitive)"
```

But **GDS tests compare WITHOUT temporal decay**:

```python
# Current test (test_importance_baseline_gds.py)
result = classifier.classify(subject, snippet, from_field)
# ↑ Returns stored_importance (NO temporal decay)

predicted = result.get('importance')  # e.g., "time_sensitive"
ground_truth = gds_row['importance']  # e.g., "routine" (was labeled with temporal context)

# MISMATCH!
```

---

## Evidence

### Example 1: Expired Event

```
Email: "Meeting @ Sun Nov 9, 2025 4pm"
Created: Nov 9, 2025
Tested: Nov 11, 2025 (2 days later)

GDS label: "routine" (labeled when event was imminent/current)
Classifier: "time_sensitive" (classifies without temporal decay)

Result: MISMATCH (but both are arguably correct!)
```

### Example 2: Imminent Event

```
Email: "Flight tomorrow"
Created: Nov 9, 2025
Tested: Nov 11, 2025

GDS label: "critical" (flight was tomorrow when labeled)
Classifier: "time_sensitive" (flight is now in the past)

Result: MISMATCH
```

---

## Why This Causes Test Failures

### Critical Precision Failure

```
test_critical_precision FAILED
  Precision: 87.5% (expected ≥95%)

Likely cause: Temporal mismatch
  - Emails labeled "critical" when urgent (Nov 9)
  - Now expired/distant (Nov 11)
  - Classifier says "routine" (correct for today)
  - GDS says "critical" (correct when labeled)
  - Counted as False Positive
```

### Distribution Drift Failure

```
test_importance_distribution_stable FAILED
  Critical: 12% → 18% (drift: 6pp)

Likely cause:
  - GDS labels reflect state on Nov 9
  - Classification reflects state on Nov 11
  - Events moved between categories due to time passing
```

---

## Solutions

### Option 1: Snapshot Testing (Freeze Time)

Test with **same timestamp** as when GDS was created:

```python
# Test as if it's Nov 9, 2025 (when GDS was labeled)
from datetime import datetime, timezone

GDS_CREATION_DATE = datetime(2025, 11, 9, tzinfo=timezone.utc)

def test_critical_precision_snapshot(predictions):
    """Test precision as of GDS creation date"""

    # Apply temporal decay with frozen time
    for email in gds:
        stored_importance = classifier.classify(...)

        # Apply temporal decay with GDS creation date
        entity = create_entity(email, stored_importance)
        enriched = enrich_with_temporal_decay(entity, now=GDS_CREATION_DATE)

        # NOW compare resolved_importance to GDS label
        assert enriched.resolved_importance == email['importance']
```

**Pros**: Tests match GDS labeling context
**Cons**: Doesn't test current behavior

---

### Option 2: Separate Stored vs Resolved Tests

Test both concepts separately:

```python
def test_stored_importance_baseline():
    """
    Test stored_importance (context-independent)

    Compare classifier output to:
    - What importance WOULD be without temporal context
    """
    # Need new GDS labels: stored_importance (always the same)

def test_resolved_importance_baseline():
    """
    Test resolved_importance (time-dependent)

    Compare full pipeline to:
    - What importance IS considering current time
    """
    # Use current GDS labels: resolved_importance (changes over time)
```

**Pros**: Clear separation of concerns
**Cons**: Need to re-label GDS with both stored & resolved

---

### Option 3: Accept Lower Thresholds (Quick Fix)

Acknowledge that temporal mismatch causes noise:

```python
# tests/test_importance_baseline_gds.py

# OLD threshold
assert precision >= 0.95

# NEW threshold (accounting for temporal noise)
assert precision >= 0.85  # Lower due to temporal mismatch

# Add comment explaining why
# "Note: Precision lower due to temporal context mismatch
#  between GDS labeling (Nov 9) and testing (Nov 11)"
```

**Pros**: Quick fix, tests still valuable
**Cons**: Masks real issues

---

### Option 4: Re-label GDS (Most Accurate)

Create two importance columns:

```csv
message_id, stored_importance, resolved_importance, temporal_start
email_001,  time_sensitive,    routine,            2025-11-09T16:00:00Z
```

- `stored_importance`: What LLM should return (context-independent)
- `resolved_importance`: What digest should show (after temporal decay)

**Pros**: Most accurate testing
**Cons**: Requires relabeling 500 emails

---

## Recommendation

### For NOW (Immediate)

**Use Option 1: Snapshot Testing**

Test GDS as of its creation date (Nov 9, 2025):

```python
# In test fixtures
GDS_TIMESTAMP = datetime(2025, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

def test_importance_with_temporal_snapshot(gds):
    """Test with temporal decay frozen to GDS creation date"""

    for email in gds:
        # Classify
        result = classifier.classify(...)

        # Apply temporal decay with FROZEN time
        if email['email_type'] == 'event' and pd.notna(email['temporal_start']):
            entity = EventEntity(
                importance=result['importance'],
                event_time=pd.to_datetime(email['temporal_start'])
            )
            enriched = enrich_entity_with_temporal_decay(
                entity,
                now=GDS_TIMESTAMP  # ← Freeze time to GDS creation
            )
            predicted = enriched.resolved_importance
        else:
            predicted = result['importance']

        # NOW compare to GDS label (should match!)
        assert predicted == email['importance']
```

This will make tests pass because we're comparing apples-to-apples.

---

### For LATER (Future GDS v2.0)

**Use Option 4: Dual Labels**

When creating GDS v2.0:
- Label both `stored_importance` and `resolved_importance`
- Test both separately
- Clear separation of temporal vs non-temporal

---

## Impact on Your Current Test Failures

Your failures are likely **NOT bugs**, but **temporal mismatch**:

```
✅ Type Mapper: Works perfectly (9/9 tests pass)
✅ OTP Filtering: Works perfectly (0 OTPs in critical)
✅ Classification: Works (100% success rate)

❌ Precision/Recall: Failed due to temporal mismatch
❌ Distribution: Failed due to temporal mismatch
❌ Fraud detection: May be real issue, or temporal mismatch

Next: Apply snapshot testing to see if failures disappear
```

---

## Quick Test: Does Snapshot Fix It?

Run this to confirm:

```python
from datetime import datetime, timezone

GDS_CREATION = datetime(2025, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

# Test one expired event
email = "Meeting @ Nov 9, 2025 4pm"

# Without snapshot (current)
result = classify(email)  # → "time_sensitive"
# GDS says: "routine" (was labeled after event passed)
# MISMATCH!

# With snapshot
result_with_time = classify_with_temporal(email, now=GDS_CREATION)
# → "time_sensitive" (event was upcoming on Nov 9)
# GDS says: "time_sensitive" (was labeled on Nov 9)
# MATCH! ✅
```

---

## ✅ SOLUTION IMPLEMENTED (2025-11-11)

### What We Built

**File**: `tests/test_temporal_gds_scenarios.py`

**Approach**: Option B - Parameterized Tests with Time Snapshots

This test file validates both stages of importance classification:

1. **Stage 1 (At Receipt)**: Confirms GDS labels = stored_importance
2. **Stage 2 (Temporal Decay)**: Tests real GDS emails at multiple time snapshots

### Test Coverage

| Test Class | Tests | What It Validates |
|------------|-------|-------------------|
| TestStage1Documentation | 1 | GDS labels represent stored_importance (at receipt) |
| TestStage2TemporalDecay | 7 | Temporal decay with time snapshots (imminent, expired, upcoming, distant) |
| TestDeadlineTemporal | 2 | Deadline expiration and escalation (skipped - no deadlines in GDS) |
| TestAuditTrail | 1 | Audit fields populated (stored vs resolved importance) |
| TestNonTemporalEmails | 1 | Non-temporal emails unaffected by temporal decay |

**Total**: 11 passing, 2 skipped (no deadlines in GDS v1.0)

### Key Insights from Testing

1. **GDS labels ARE stored_importance** (confirmed by test results)
2. **Temporal decay works correctly**:
   - Events 30 min before → escalate to critical ✅
   - Events 2h after end → downgrade to routine + hidden ✅
   - Events 3 days before → escalate to time_sensitive ✅
   - Events 10 days before → downgrade to routine ✅
3. **Non-temporal emails pass through unchanged** ✅
4. **Audit trail preserved** (stored vs resolved importance) ✅

### What This Means for Previous Test Failures

The original test failures in `test_importance_baseline_gds.py` were **NOT** due to temporal context mismatch!

**Evidence**:
- GDS labels represent stored_importance (Stage 1)
- Current baseline tests correctly compare stored_importance
- Temporal decay tests pass with real GDS emails

**Conclusion**: The precision/recall failures in baseline tests are likely:
1. Real issues with classification (LLM schema errors observed)
2. Distribution drift from actual behavior changes
3. Edge cases in guardrail rules

**Next Steps**: Focus on fixing actual classification issues, not temporal testing strategy.

### Running the Tests

```bash
# Run temporal GDS scenarios
pytest tests/test_temporal_gds_scenarios.py -v

# Run full GDS suite (Stage 1 + Stage 2)
pytest tests/test_*_gds.py -v

# Run all tests
pytest tests/ -v
```

### Future Work

1. **Add deadlines to GDS v2.0**: Current GDS has no deadline emails (tests skipped)
2. **Parameterize time offsets**: Test more time snapshots (6h, 12h, 24h, 5d, 14d)
3. **Add OTP/shipping temporal tests**: Test notification subtype temporal decay
4. **Integration with digest**: Test full pipeline from classification → temporal decay → digest rendering

---

**Status**: ✅ COMPLETE - Two-stage testing strategy implemented and validated
