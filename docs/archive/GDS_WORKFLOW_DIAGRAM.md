# GDS Testing Workflow

## The Big Picture

```
┌─────────────────────────────────────────────────────────────┐
│                     gds-1.0.csv                             │
│                   (500 labeled emails)                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ message_id | importance | type | domains | ...      │   │
│  │ email_001  | critical   | task | financial          │   │
│  │ email_002  | routine    | update | newsletters      │   │
│  │ ...        | ...        | ...  | ...                │   │
│  │ email_500  | time_sens. | event | calendar          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ Load emails
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              Your MailQ Classification Pipeline             │
│                                                             │
│  ┌──────────┐   ┌────────────┐   ┌─────────┐   ┌────────┐ │
│  │  Type    │→  │ Guardrails │→  │   LLM   │→  │  Post  │ │
│  │  Mapper  │   │  (never/   │   │ (Gemini)│   │Process │ │
│  │          │   │  force)    │   │         │   │        │ │
│  └──────────┘   └────────────┘   └─────────┘   └────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ Get predictions
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    Test Predictions                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ message_id | predicted | ground_truth | match?     │   │
│  │ email_001  | critical  | critical     | ✅         │   │
│  │ email_002  | routine   | routine      | ✅         │   │
│  │ email_003  | critical  | routine      | ❌ FP!     │   │
│  │ ...        | ...       | ...          | ...         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ Calculate metrics
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    Quality Metrics                          │
│                                                             │
│  Critical Precision:  96.7% (≥95% ✅)                       │
│  Critical Recall:     96.7% (≥85% ✅)                       │
│  OTP in CRITICAL:     0     (==0  ✅)                       │
│  Distribution Drift:  2.1%  (≤5%  ✅)                       │
│                                                             │
│                  ALL QUALITY GATES PASSED ✅                │
└─────────────────────────────────────────────────────────────┘
```

---

## Your Terminal Commands

### Quick Test (10 seconds)

```bash
./scripts/test_against_gds.sh
```

**Output**:
```
╔════════════════════════════════════════════════════════════╗
║  MailQ Golden Dataset Test Suite                          ║
║  Testing against gds-1.0.csv (500 emails)                 ║
╚════════════════════════════════════════════════════════════╝

✅ Found GDS at tests/golden_set/gds-1.0.csv

[1/3] Testing Type Mapper...
✅ Type Mapper tests PASSED

[2/3] Testing Guardrails...
✅ Guardrails tests PASSED

[3/3] Testing Quality Gates (Importance Baseline)...
✅ Quality Gate tests PASSED

╔════════════════════════════════════════════════════════════╗
║  ALL TESTS PASSED ✅                                       ║
╚════════════════════════════════════════════════════════════╝

✨ Ready to ship! All quality gates passed.
```

---

### Verbose Test (see details)

```bash
./scripts/test_against_gds.sh --verbose
```

**Output**:
```
[1/3] Testing Type Mapper...
test_type_mapper_calendar_events_golden_set ... PASSED
  ✅ 50/50 calendar events typed correctly

[2/3] Testing Guardrails...
test_otp_never_in_critical ... PASSED
  ✅ OTP in CRITICAL: 0/15
test_fraud_always_critical ... PASSED
  ✅ Fraud in CRITICAL: 3/3
test_calendar_autoresponse_not_critical ... PASSED
  ✅ Auto-responses in CRITICAL: 0/8

[3/3] Testing Quality Gates...
test_critical_precision ... PASSED
  True Positives: 58
  False Positives: 2
  Precision: 96.7%

test_critical_recall ... PASSED
  True Positives: 58
  False Negatives: 2
  Recall: 96.7%

test_otp_in_critical_equals_zero ... PASSED
  Total OTP emails: 15
  OTP in CRITICAL: 0

test_importance_distribution_stable ... PASSED
  critical:        12.0% → 12.2%  (drift: 0.2%) ✅
  time_sensitive:  28.0% → 28.5%  (drift: 0.5%) ✅
  routine:         60.0% → 59.3%  (drift: 0.7%) ✅

ALL TESTS PASSED ✅
```

---

## What Each Test Does

### 1. Type Mapper Tests (`test_type_mapper_gds.py`)

```
gds-1.0.csv
  ↓ Filter to calendar events
  ↓ (50 emails with type=event)
  ↓
Run through type_mapper.py
  ↓
Check: Did type mapper match ≥95%?
  ↓
✅ PASS: 50/50 matched (100%)
```

---

### 2. Guardrail Tests (`test_guardrails_gds.py`)

```
gds-1.0.csv
  ↓ Filter to OTP emails (15 emails)
  ↓
Run through full pipeline
  ↓
Check: Are any OTP emails in CRITICAL?
  ↓
✅ PASS: 0/15 in CRITICAL
```

```
gds-1.0.csv
  ↓ Filter to fraud emails (3 emails)
  ↓
Run through full pipeline
  ↓
Check: Are all fraud emails in CRITICAL?
  ↓
✅ PASS: 3/3 in CRITICAL
```

---

### 3. Baseline Tests (`test_importance_baseline_gds.py`)

```
gds-1.0.csv (all 500 emails)
  ↓
Run through full pipeline
  ↓
Compare predictions vs ground truth
  ↓
Calculate:
  - Precision (how many predicted criticals are correct?)
  - Recall (how many actual criticals did we catch?)
  - Distribution (did % critical/time_sensitive/routine drift?)
  - OTP in CRITICAL (quality gate)
  ↓
Check all metrics against thresholds
  ↓
✅ PASS: All quality gates met
```

---

## Development Workflow

### Before You Start (Baseline)

```bash
./scripts/test_against_gds.sh
# Output: ALL TESTS PASSED ✅
# Good! You have a clean baseline
```

---

### Implement Feature (e.g., Guardrails)

```bash
# Edit code
vim mailq/bridge/guardrails.py

# Test your feature
pytest tests/test_guardrails_gds.py -v
# Output: ✅ All guardrail tests pass

# Full regression check
./scripts/test_against_gds.sh
# Output: ✅ ALL TESTS PASSED

# Mark complete
/complete US-005
```

---

### Handle Test Failure

```bash
./scripts/test_against_gds.sh
# Output: ❌ FAILED test_critical_precision

# Debug: What failed?
pytest tests/test_importance_baseline_gds.py::test_critical_precision -v
# Output shows:
#   False Positives: 8 emails
#   Precision: 87.3% < 95%

# Fix the issue
vim mailq/bridge/guardrails.py

# Re-test
./scripts/test_against_gds.sh
# Output: ✅ ALL TESTS PASSED

# Now safe to ship!
```

---

## Files You Created

```
tests/
├── test_guardrails_gds.py           ← Tests guardrail rules
├── test_importance_baseline_gds.py  ← Tests quality gates
├── GDS_TESTING_GUIDE.md             ← Full documentation
└── GDS_WORKFLOW_DIAGRAM.md          ← This file

scripts/
└── test_against_gds.sh              ← Convenience runner
```

---

## The Mental Model

**Think of GDS as your "regression test database"**

```
┌─────────────────────────────────────────┐
│  GDS = 500 Known-Good Email Labels     │
│                                         │
│  Like unit tests, but for ML           │
│  Like golden master testing             │
│  Like visual regression testing         │
│                                         │
│  Every code change must pass GDS        │
└─────────────────────────────────────────┘
```

**Two failure modes**:

1. **Regression**: "This calendar event used to work, now it's broken"
   - Type mapper stopped matching Google Calendar emails
   - Fix: Check type_mapper.py logic

2. **Drift**: "Too many emails moved to CRITICAL"
   - Distribution changed from 12% → 18% critical
   - Fix: Check if guardrails are too loose or LLM prompt changed

---

## Quick Reference Card

```
┌───────────────────────────────────────────────────────────┐
│  COMMAND                    │  PURPOSE                    │
├─────────────────────────────┼─────────────────────────────┤
│  ./scripts/test_against_    │  Run all tests (quick)      │
│    gds.sh                   │                             │
│                             │                             │
│  ./scripts/test_against_    │  Run with details           │
│    gds.sh --verbose         │                             │
│                             │                             │
│  pytest tests/ -k "gds" -v  │  Run all GDS tests          │
│                             │                             │
│  pytest tests/test_         │  Run specific test file     │
│    guardrails_gds.py -v     │                             │
└─────────────────────────────┴─────────────────────────────┘
```

---

**Next**: Read `GDS_TESTING_GUIDE.md` for full details and examples.
