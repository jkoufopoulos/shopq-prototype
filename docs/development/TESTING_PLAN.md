# Importance Classification System - Testing Plan

**Created**: 2025-11-10
**Status**: Ready to Execute
**Context**: Post type-mapper migration, validating full classification pipeline

---

## Overview

You've successfully implemented **Phase B0 (Type Mapper)** and have a **temporal decay system** (Phase 4) in place. Now you need to validate the **entire importance classification pipeline** end-to-end.

### Your Classification Pipeline (Current State)

```
Email → Type Mapper → RulesEngine → LLM Classifier → Temporal Decay → Digest
         (Phase B0)                  (ImportanceClassifier)  (Phase 4)
```

**Key Components**:
1. **Type Mapper** (NEW) - Deterministic type rules (calendar events)
2. **ImportanceClassifier** - LLM-based classification (Gemini 2.0 Flash)
3. **Temporal Decay** - Time-based importance adjustment
4. **Digest Renderer** - Final HTML output

---

## Testing Strategy (Layered Validation)

### Layer 1: Unit Tests (Components in Isolation)
**Goal**: Verify each component works correctly independently
**Time**: 5-10 minutes

### Layer 2: Integration Tests (Component Interactions)
**Goal**: Verify components work together correctly
**Time**: 10-15 minutes

### Layer 3: End-to-End Tests (Full Pipeline)
**Goal**: Verify complete flow from email → digest HTML
**Time**: 10-15 minutes

### Layer 4: Golden Dataset Regression (Production Reality)
**Goal**: Verify accuracy on real-world emails
**Time**: 20-30 minutes

### Layer 5: Manual Validation (Real Inbox)
**Goal**: Smoke test on actual Gmail data
**Time**: 30-60 minutes

---

## Detailed Test Plan

### ✅ Layer 1: Unit Tests (Already Passing)

**Type Mapper** (27/27 passed):
```bash
PYTHONPATH=. pytest tests/test_type_mapper.py -v
```
- ✅ Domain matching (Google Calendar, Outlook, etc.)
- ✅ Subject pattern matching (regex)
- ✅ Body phrase matching (Google Meet, Zoom)
- ✅ ICS attachment detection
- ✅ Fallback to None for non-matches

**Temporal Decay** (33 tests):
```bash
PYTHONPATH=. pytest tests/test_temporal_decay.py -v
```
**Expected Coverage**:
- [ ] Expired events → routine (with 1h grace period)
- [ ] Active events (±1h) → critical
- [ ] Upcoming events (≤7 days) → time_sensitive
- [ ] Distant events (>7 days) → routine
- [ ] Non-temporal types → unchanged
- [ ] Digest section mapping (NOW/COMING_UP/WORTH_KNOWING)

**What to look for**:
- All tests should pass
- Check for any deprecation warnings
- Note any skipped tests (understand why)

---

### ⚠️ Layer 2: Integration Tests

**Type Mapper + MemoryClassifier** (13/15 passed):
```bash
PYTHONPATH=. pytest tests/test_memory_classifier_integration.py -v
```
**Already validated** ✅

**Temporal Enrichment** (needs verification):
```bash
PYTHONPATH=. pytest tests/test_temporal_integration.py -v
```
**Expected Coverage**:
- [ ] Entity extraction → temporal decay → digest categorization
- [ ] Expired events filtered from digest
- [ ] Temporal stats collection (escalated/downgraded counters)
- [ ] Digest section grouping (NOW/COMING_UP/WORTH_KNOWING)

**What to check**:
- Does `enrich_entities_with_temporal_decay()` work correctly?
- Are `stored_importance` and `resolved_importance` both populated?
- Are expired events correctly filtered out?
- Do telemetry counters update correctly?

---

### 🔥 Layer 3: End-to-End Tests (Critical Path)

**Full Pipeline** (needs verification):
```bash
PYTHONPATH=. pytest tests/test_temporal_e2e.py -v
```
**Expected Coverage**:
- [ ] Email → extraction → classification → temporal decay → digest HTML
- [ ] Expired event hidden from digest
- [ ] Imminent event appears in CRITICAL section
- [ ] Upcoming event appears in COMING_UP section
- [ ] Mixed entity types render in correct order

**What this validates**:
- The ENTIRE pipeline works end-to-end
- No integration bugs between components
- Digest HTML renders correctly with temporal data

**If tests fail**, this tells you:
- Where the integration is broken
- Which component is not wired correctly
- What data is being lost between stages

---

### 📊 Layer 4: Golden Dataset Regression

**Type Mapper on gds-1.0** (9/9 passed) ✅:
```bash
PYTHONPATH=. pytest tests/test_type_mapper_gds.py -v
```

**Importance Classification Baseline** (needs verification):
```bash
PYTHONPATH=. pytest tests/test_importance_baseline.py -v
```
**Expected Metrics**:
- [ ] Critical precision ≥ 0.95
- [ ] Critical recall ≥ 0.85
- [ ] Time-sensitive accuracy ≥ 0.80
- [ ] OTP false positives = 0
- [ ] Type consistency (calendar → event) ≥ 95%

**What to check**:
- Are you meeting your acceptance criteria?
- Where are the main error patterns?
- Are there specific senders causing issues?

**Golden Dataset Files**:
- `gds-1.0.csv` - Full dataset (500 emails)
- `gds-1.0_train.csv` - Training set
- `gds-1.0_test.csv` - Test set
- `gds-1.0_regression.csv` - Regression checks
- `gds-1.0_dev.csv` - Development scratch space

---

### 🧪 Layer 5: Manual Validation Plan

**5.1 Setup Test Environment**
```bash
# Ensure you're on the right branch
git status

# Ensure all dependencies installed
pip install -r requirements.txt  # or use uv

# Set environment variables
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account.json"
export ANTHROPIC_API_KEY="your-key"  # if using Claude
```

**5.2 Test on Sample Emails** (start small!)
```bash
# Test type mapper on a few emails from your inbox
# Use the extension or API to classify 5-10 recent emails
```

**What to check**:
1. **Calendar invites** → type=event, decider=type_mapper ✅
2. **Bills/invoices** → type=deadline or receipt, appropriate importance
3. **Newsletters** → type=notification or other, importance=routine
4. **Time-sensitive emails** → correct temporal decay applied
5. **Expired events** → hidden from digest

**5.3 Full Digest Test**
```bash
# Generate a digest from your last 24h of emails
# Check:
# - Are events in the right section (NOW/COMING_UP/WORTH_KNOWING)?
# - Are expired events hidden?
# - Are imminent events in CRITICAL?
# - Is the HTML rendering correctly?
```

**5.4 Edge Cases to Test Manually**

| Scenario | Expected Behavior |
|----------|-------------------|
| Calendar invite for meeting in 30 min | type=event, importance=critical, section=NOW |
| Event that ended 2 hours ago | type=event, hidden from digest |
| Bill due tomorrow | type=deadline, importance=time_sensitive, section=COMING_UP |
| Newsletter | type=notification, importance=routine, section=WORTH_KNOWING |
| Amazon receipt | type=receipt, importance=routine |
| Security alert | type=notification, importance=critical |
| Meeting in 5 days | type=event, importance=time_sensitive, section=COMING_UP |
| OTP code | type=notification, importance=routine (NOT critical) |

---

## Test Execution Order (Recommended)

### Phase 1: Verify Existing Tests Still Pass (5 min)
```bash
# Type mapper (already passing)
PYTHONPATH=. pytest tests/test_type_mapper.py -v

# Type mapper golden dataset (already passing)
PYTHONPATH=. pytest tests/test_type_mapper_gds.py -v
```
**Expected**: All green ✅

### Phase 2: Run Temporal Unit Tests (5 min)
```bash
PYTHONPATH=. pytest tests/test_temporal_decay.py -v
```
**Expected**: Should pass (temporal logic is deterministic)
**If failures**: Check config/mailq_policy.yaml temporal_decay settings

### Phase 3: Run Integration Tests (10 min)
```bash
PYTHONPATH=. pytest tests/test_temporal_integration.py -v
PYTHONPATH=. pytest tests/test_memory_classifier_integration.py -v
```
**Expected**: Most should pass
**If failures**: Integration wiring issues - need to fix

### Phase 4: Run End-to-End Tests (10 min)
```bash
PYTHONPATH=. pytest tests/test_temporal_e2e.py -v
```
**Expected**: Should pass if integration tests passed
**If failures**: Full pipeline issues - serious debugging needed

### Phase 5: Golden Dataset Baseline (20 min)
```bash
PYTHONPATH=. pytest tests/test_importance_baseline.py -v -s
```
**Expected**: See metrics report
**If failures**: LLM classification not meeting targets - may need prompt tuning

### Phase 6: Manual Validation (30-60 min)
- Test on 10-20 real emails from your inbox
- Generate a full digest
- Verify edge cases from table above

---

## Success Criteria (Must Pass Before Production)

### Automated Tests
- ✅ All unit tests passing (type mapper, temporal decay)
- ✅ All integration tests passing (enrichment, classification)
- ✅ All e2e tests passing (full pipeline)
- ⚠️ Golden dataset metrics meet thresholds:
  - Critical precision ≥ 0.95
  - Critical recall ≥ 0.85
  - Type consistency ≥ 95%

### Manual Validation
- [ ] Calendar invites classified correctly
- [ ] Temporal decay working (expired events hidden)
- [ ] Digest sections correct (NOW/COMING_UP/WORTH_KNOWING)
- [ ] No obvious false positives (newsletters in CRITICAL)
- [ ] Edge cases handled correctly

---

## Common Issues & Debugging

### Issue: Type mapper not being used
**Symptoms**: All emails show `decider=gemini` instead of `decider=type_mapper`
**Check**:
- Is `type_mapper.py` imported in `memory_classifier.py`?
- Is `get_type_mapper()` called in `__init__`?
- Are sender emails being normalized correctly?

### Issue: Temporal decay not applying
**Symptoms**: Expired events still showing in digest, importance unchanged
**Check**:
- Is `temporal_enrichment.py` being called?
- Are temporal fields (`temporal_start`, `temporal_end`) populated?
- Check `config/mailq_policy.yaml` for correct settings

### Issue: Tests failing with "module not found"
**Solution**: Always use `PYTHONPATH=. pytest` or `PYTHONPATH=/full/path`

### Issue: Integration tests timing out
**Solution**:
- Check if LLM API keys are set
- Verify network connectivity
- Check rate limits

### Issue: Golden dataset metrics below threshold
**Solution**:
- Review error patterns in test output
- Check prompt templates in LLM classifier
- Verify temporal decay rules are correct
- May need to tune thresholds in `config/mailq_policy.yaml`

---

## Quick Start (Copy-Paste Commands)

```bash
# Set working directory
cd /Users/justinkoufopoulos/Projects/mailq-prototype

# Phase 1: Verify type mapper (already passing)
PYTHONPATH=. pytest tests/test_type_mapper.py tests/test_type_mapper_gds.py -v

# Phase 2: Test temporal decay
PYTHONPATH=. pytest tests/test_temporal_decay.py -v

# Phase 3: Test integration
PYTHONPATH=. pytest tests/test_temporal_integration.py -v

# Phase 4: Test end-to-end
PYTHONPATH=. pytest tests/test_temporal_e2e.py -v

# Phase 5: Golden dataset baseline
PYTHONPATH=. pytest tests/test_importance_baseline.py -v -s

# Run ALL classification tests at once
PYTHONPATH=. pytest tests/test_type_mapper*.py tests/test_temporal*.py tests/test_importance*.py -v
```

---

## Next Steps After Testing

1. **If all tests pass**:
   - Update NEXT_STEPS.md to mark testing complete
   - Move to manual validation on real inbox
   - Consider deploying to staging/production

2. **If tests fail**:
   - Identify which layer is failing
   - Fix integration issues first (bottom-up)
   - Re-run tests after each fix
   - Document failures in NEXT_STEPS.md

3. **If golden dataset metrics are low**:
   - Analyze error patterns
   - Review LLM prompts
   - Check temporal decay rules
   - Consider expanding type mapper rules
   - May need to tune confidence thresholds

---

## References

- Type Mapper: `docs/TYPE_MAPPER_IMPLEMENTATION_SUMMARY.md`
- Temporal Decay: `docs/PHASE_4_TEMPORAL_DECAY.md` (if exists)
- Golden Dataset: `tests/golden_set/GDS_SCHEMA_v1.0.md`
- Classification Plan: `docs/CLASSIFICATION_REFACTOR_PLAN.md`
- Action Items: `NEXT_STEPS.md`
