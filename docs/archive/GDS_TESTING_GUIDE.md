# Golden Dataset Testing Guide

**Purpose**: Test MailQ against 500 labeled emails to catch regressions and drift

**Last Updated**: 2025-11-10

---

## Quick Start

### Run All Tests

```bash
# Simple (quiet output)
./scripts/test_against_gds.sh

# Verbose (see each test)
./scripts/test_against_gds.sh --verbose

# Generate HTML report
./scripts/test_against_gds.sh --report
```

### Run Specific Tests

```bash
# Just guardrails
pytest tests/test_guardrails_gds.py -v

# Just quality gates
pytest tests/test_importance_baseline_gds.py -v

# Just type mapper
pytest tests/test_type_mapper_gds.py -v

# Run all GDS tests
pytest tests/ -k "gds" -v
```

---

## What These Tests Do

### 1. `test_guardrails_gds.py` - Feature Validation

**Tests specific guardrail rules against GDS**

```bash
pytest tests/test_guardrails_gds.py -v
```

**What it checks**:
- ✅ OTP codes never in CRITICAL (Quality Gate: must be 0)
- ✅ Fraud/phishing always in CRITICAL
- ✅ Calendar auto-responses not in CRITICAL
- ✅ Guardrail precedence rules work

**Output**:
```
test_otp_never_in_critical ... PASSED
  ✅ OTP in CRITICAL: 0/15
test_fraud_always_critical ... PASSED
  ✅ Fraud in CRITICAL: 3/3
test_calendar_autoresponse_not_critical ... PASSED
  ✅ Auto-responses in CRITICAL: 0/8
```

---

### 2. `test_importance_baseline_gds.py` - Quality Gates

**Tests MVP quality gates from ROADMAP.md**

```bash
pytest tests/test_importance_baseline_gds.py -v
```

**What it checks**:
- ✅ **Critical precision ≥95%** (How many predicted criticals are actually critical)
- ✅ **Critical recall ≥85%** (How many actual criticals are we catching)
- ✅ **OTP in CRITICAL == 0** (Hard constraint, no exceptions)
- ✅ **Event-newsletter noise ≤2%** (Event newsletters not in COMING UP)
- ✅ **Importance distribution stable** (±5pp drift limit)

**Output**:
```
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
  critical:        12.0% → 12.2%  (drift: 0.2%)
  time_sensitive:  28.0% → 28.5%  (drift: 0.5%)
  routine:         60.0% → 59.3%  (drift: 0.7%)
```

---

### 3. `test_type_mapper_gds.py` - Regression Testing

**Tests type mapper against known calendar events** (you already have this)

```bash
pytest tests/test_type_mapper_gds.py -v
```

**What it checks**:
- ✅ Calendar events correctly typed as 'event'
- ✅ Type mapper hit rate (% of emails matched)
- ✅ False positive rate <1%

---

## Your Daily Workflow

### Before Starting Work

```bash
# Establish baseline (all should pass)
./scripts/test_against_gds.sh

# Output:
# [1/3] Testing Type Mapper...
# ✅ Type Mapper tests PASSED
# [2/3] Testing Guardrails...
# ✅ Guardrails tests PASSED
# [3/3] Testing Quality Gates...
# ✅ Quality Gate tests PASSED
#
# ALL TESTS PASSED ✅
```

If tests fail before you start, something is already broken!

---

### While Developing

```bash
# After each code change, run relevant tests
pytest tests/test_guardrails_gds.py -v

# Fast feedback loop (5-10 seconds)
```

---

### Before Marking Feature Complete

```bash
# Run full suite
./scripts/test_against_gds.sh --verbose

# All passing? Safe to ship!
/complete US-005
```

---

## Understanding Test Failures

### Example: OTP in CRITICAL Failure

```
FAILED test_otp_in_critical_equals_zero

❌ OTP emails incorrectly in CRITICAL:
  - Your verification code is 123456 (message_id: abc123)
  - Amazon OTP: 456789 (message_id: def456)

AssertionError: Found 2 OTP emails in CRITICAL (must be 0)
```

**What to do**:
1. Check `config/guardrails.yaml` - is `never_surface` configured correctly?
2. Check `mailq/bridge/guardrails.py` - are rules being applied?
3. Debug the specific emails that failed
4. Fix the issue
5. Re-run tests

---

### Example: Critical Precision Failure

```
FAILED test_critical_precision

True Positives: 55
False Positives: 8
Precision: 87.3%

⚠️  False Positive examples:
  - Newsletter: Events near you (actually routine)
  - Promotional email from Amazon (actually routine)

AssertionError: Critical precision 87.3% < 95%
```

**What to do**:
1. Review false positive examples
2. Check if guardrails should have filtered these
3. Check if LLM prompt needs adjustment
4. Fix the issue
5. Re-run tests

---

### Example: Distribution Drift

```
FAILED test_importance_distribution_stable

  critical:        12.0% → 18.2%  (drift: 6.2%) ❌
  time_sensitive:  28.0% → 25.8%  (drift: 2.2%) ✅
  routine:         60.0% → 56.0%  (drift: 4.0%) ✅

AssertionError: critical drifted by 6.2% (>5pp limit)
```

**What to do**:
1. Check if this drift is **intentional** (new feature up-ranks emails)
2. If intentional, update the baseline in `test_importance_baseline_gds.py`
3. If unintentional (bug), investigate why too many emails are critical
4. Fix the issue
5. Re-run tests

---

## Updating Baselines (When Drift is Expected)

If you **intentionally** change the distribution (e.g., temporal decay up-ranks events), update the baseline:

```python
# tests/test_importance_baseline_gds.py

# OLD baseline (before temporal decay)
baseline_dist = {
    'critical': 0.12,
    'time_sensitive': 0.28,
    'routine': 0.60
}

# NEW baseline (after temporal decay)
baseline_dist = {
    'critical': 0.12,
    'time_sensitive': 0.32,  # +4pp from temporal up-ranks ✅
    'routine': 0.56
}
```

Then re-run tests to verify the new baseline is stable.

---

## Advanced Usage

### Generate HTML Report

```bash
# Create HTML report
./scripts/test_against_gds.sh --report

# Open report
open reports/gds_test_report.html
```

### Run Specific Test Functions

```bash
# Just OTP test
pytest tests/test_guardrails_gds.py::test_otp_never_in_critical -v

# Just precision test
pytest tests/test_importance_baseline_gds.py::test_critical_precision -v
```

### Debug Mode

```bash
# Run with print statements visible
pytest tests/test_guardrails_gds.py -v -s

# Run with debugger on failure
pytest tests/test_guardrails_gds.py -v --pdb
```

### Save Test Results

```bash
# Save to JSON
pytest tests/ -k "gds" --json-report --json-report-file=test_results.json

# Compare baseline vs current
python scripts/compare_test_results.py baseline.json test_results.json
```

---

## Integration with CI

### GitHub Actions (Example)

```yaml
# .github/workflows/gds-validation.yml
name: GDS Validation

on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run GDS tests
        run: ./scripts/test_against_gds.sh --verbose
```

### Pre-commit Hook (Local)

```bash
# .git/hooks/pre-commit
#!/bin/bash
echo "Running GDS tests before commit..."
./scripts/test_against_gds.sh || {
    echo "❌ GDS tests failed! Commit aborted."
    exit 1
}
```

---

## File Structure

```
tests/
├── golden_set/
│   └── gds-1.0.csv                      # 500 labeled emails
│
├── test_type_mapper_gds.py               # Type mapper regression tests
├── test_guardrails_gds.py                # Guardrail feature tests
├── test_importance_baseline_gds.py       # Quality gate tests
└── GDS_TESTING_GUIDE.md                  # This file

scripts/
└── test_against_gds.sh                   # Convenience test runner
```

---

## FAQ

### Q: How long do tests take?

**A**: ~10-30 seconds total (500 emails × 3 test files)

---

### Q: What if I don't have guardrails implemented yet?

**A**: Tests will be skipped automatically. Implement the feature, then tests will run.

```python
# tests/test_guardrails_gds.py
try:
    from mailq.bridge.guardrails import GuardrailMatcher
except ImportError:
    pytest.skip("Guardrails not implemented yet")
```

---

### Q: Can I test on a subset of GDS?

**A**: Yes, filter in the test:

```python
@pytest.fixture
def gds_subset(gds):
    """Test on first 100 emails only"""
    return gds.head(100)
```

---

### Q: How do I add new quality gates?

**A**: Add a new test function to `test_importance_baseline_gds.py`:

```python
def test_my_new_quality_gate(predictions):
    """My new quality gate description"""
    # Your test logic here
    assert some_metric >= threshold
```

---

## Troubleshooting

### Tests fail with "MemoryClassifier not found"

```bash
# Check imports
python -c "from mailq.memory_classifier import MemoryClassifier"

# If fails, check PYTHONPATH
export PYTHONPATH=/path/to/mailq-prototype:$PYTHONPATH
```

### Tests fail with "GDS not found"

```bash
# Check if GDS exists
ls -lh tests/golden_set/gds-1.0.csv

# If missing, check documentation on how to create GDS
```

### All tests skip

```bash
# Check pytest output for skip reasons
pytest tests/test_guardrails_gds.py -v -rs

# -rs shows skip reasons
```

---

## Next Steps

1. **Run the tests now**: `./scripts/test_against_gds.sh`
2. **Fix any failures**: Debug and iterate
3. **Integrate into workflow**: Run before `/complete US-XXX`
4. **Add to CI**: Run on every PR
5. **Expand GDS**: Add more emails over time (target: 1000-2000)

---

**Questions?** See `/ROADMAP.md` for overall testing strategy or `docs/ROADMAP_AUTOMATION.md` for automation details.
