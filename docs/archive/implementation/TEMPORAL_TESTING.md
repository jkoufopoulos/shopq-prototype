# Temporal Decay Testing Framework

Comprehensive test suite for validating temporal decay logic across digest sections.

## Overview

This framework tests how emails transition between digest sections (CRITICAL, TODAY, COMING UP, WORTH KNOWING, etc.) as time advances. Uses a **fixed cohort** of 50 real emails + 10 synthetic edge cases to track section transitions and validate temporal decay behavior.

## Why Fixed Cohort?

- **Track per-email transitions**: See exactly how "Bill due tomorrow" (T0: CRITICAL) → "Bill due today" (T1: TODAY) → "Overdue bill" (T2: SKIP)
- **Clean attribution**: Section changes are due to time advancement, not dataset variation
- **Seed isolation**: Uses `seed=50` (different from 100-email test `seed=42`) to avoid overfitting

## Pass/Fail Criteria

### T0 (Just Received)
| Metric | Threshold | Description |
|--------|-----------|-------------|
| **Overall Accuracy** | ≥ 70% | Correct section assignment |
| **Critical Precision** | ≥ 80% | Avoid showing stale urgencies |
| **TODAY Recall** | ≥ 75% | Catch everything happening today |
| **Receipt Stability** | ≥ 90% | Receipts stay in WORTH_KNOWING |

### T1 (+24 Hours)
| Metric | Threshold | Description |
|--------|-----------|-------------|
| **Overall Accuracy** | ≥ 70% | Account for temporal decay |
| **Critical → TODAY Transitions** | ≥ 80% | Bills/deadlines downgrade correctly |
| **TODAY → SKIP Transitions** | ≥ 85% | Delivered/past items expire |
| **Receipt Stability** | ≥ 90% | Receipts remain stable |

### T2 (+168 Hours / 1 Week)
| Metric | Threshold | Description |
|--------|-----------|-------------|
| **Overall Accuracy** | ≥ 70% | Most items should be expired |
| **SKIP Rate** | ≥ 70% | Maximum decay for time-sensitive items (1 week old) |
| **Receipt Stability** | ≥ 90% | Receipts still in WORTH_KNOWING |
| **Noise Hygiene** | ≥ 95% | Old items in EVERYTHING_ELSE/SKIP |

## Dataset Composition

### 50 Real Emails (GDS, seed=50)
- Random sample from Golden Dataset v1.0
- Distribution:
  - 6 critical (OTPs, security alerts)
  - 44 routine (receipts, events, notifications)

### 10 Synthetic Edge Cases
| ID | Description | Tests |
|----|-------------|-------|
| edge_001 | Event in 59 minutes | TODAY cutoff (≤ 1 hour) |
| edge_002 | Event in 61 minutes | COMING_UP boundary |
| edge_003 | Event at 11:55pm today | Day boundary (end) |
| edge_004 | Event at 12:05am tomorrow | Day boundary (start) |
| edge_005 | Bill due in 24h | Critical downgrade timing |
| edge_006 | Package out for delivery | TODAY → SKIP delivery |
| edge_007 | Starbucks receipt | Receipt stability (all timepoints) |
| edge_008 | Event in 7 days | COMING_UP window edge |
| edge_009 | OTP code | Critical → SKIP expiration |
| edge_010 | Promotional email | EVERYTHING_ELSE stability |

## Workflow

### Step 1: Setup Dataset

```bash
make temporal-setup
```

Generates:
- `reports/temporal_digest_review_50_emails.csv` (50 real emails)
- `reports/temporal_edge_cases_10_emails.csv` (10 edge cases)

### Step 2: Manual Labeling

```bash
make temporal-label
```

Interactive terminal tool guides you through:

1. **T0 Labeling** (Just Received)
   - Assume all emails just arrived "now"
   - Mark which section each belongs in
   - Add temporal hints (e.g., "event tomorrow", "bill due Friday")

2. **T1 Labeling** (+24 hours later)
   - Re-label **same emails** as if 24 hours passed
   - Events "tomorrow" → might be "today"
   - Deadlines "today" → might be expired

3. **T2 Labeling** (+168 hours / 1 week later)
   - Re-label **same emails** as if 1 week passed
   - Most time-sensitive → should be SKIP
   - Receipts → still WORTH_KNOWING

**Keyboard Shortcuts:**
- `[1]` = CRITICAL
- `[2]` = TODAY
- `[3]` = COMING UP
- `[4]` = WORTH KNOWING
- `[5]` = EVERYTHING ELSE
- `[6]` = SKIP
- `[t]` = Add temporal hint
- `[n]` = Add note
- `[s]` = Switch timepoint
- `[q]` = Save and quit

Progress auto-saves every 10 emails.

### Step 3: Evaluate System

```bash
make temporal-eval
```

Runs digest generation at T0, T1, T2 and compares system predictions to your manual labels.

Outputs:
- Accuracy metrics by timepoint
- Confusion matrices
- Misclassification reports

### Step 4: Generate Report

```bash
make temporal-report
```

Creates comprehensive markdown report:
- `reports/temporal_decay_evaluation.md` (summary + visualizations)
- `reports/temporal_evaluation_results.csv` (detailed results)

Report includes:
- ✅/❌ Pass/fail for each criterion
- Confusion matrices with visual heatmaps
- Section transition analysis (T0 → T1 → T2)
- Top misclassifications with recommendations

## Example Temporal Flow

| Email | T0 (Just Received) | T1 (+24h) | T2 (+1 week) | Rationale |
|-------|-------------------|-----------|--------------|-----------|
| "Bill due tomorrow" | CRITICAL | TODAY | SKIP | Deadline approaches, passes, expires |
| "Event this weekend" | COMING UP | COMING UP | SKIP | Future event → past event |
| "Receipt: Order #123" | WORTH KNOWING | WORTH KNOWING | WORTH KNOWING | Time-insensitive |
| "Package out for delivery" | TODAY | SKIP | SKIP | Delivery happens, becomes stale |
| "OTP code: 123456" | CRITICAL | SKIP | SKIP | Expires after 10 minutes |
| "50% off sale" | EVERYTHING ELSE | EVERYTHING ELSE | EVERYTHING ELSE | Promotional noise |

## Interpreting Results

### High Accuracy (✅ PASS)
- Temporal decay windows are correctly calibrated
- Categorizer rules align with user expectations
- Entity extraction + temporal enrichment working

### Low Critical Precision (❌ FAIL)
- **Issue**: Showing stale urgent items (bills after deadline)
- **Fix**: Review temporal decay downgrade timing
- **Check**: `mailq/temporal_enrichment.py` windows

### Low TODAY Recall (❌ FAIL)
- **Issue**: Missing items happening today (< 1 hour)
- **Fix**: Expand TODAY cutoff or temporal keyword detection
- **Check**: `mailq/digest/categorizer.py` temporal logic

### Low Receipt Stability (❌ FAIL)
- **Issue**: Receipts jumping between sections
- **Fix**: Add receipt stability rules (time-insensitive)
- **Check**: `config/guardrails.yaml` or categorizer

### Poor Noise Hygiene (❌ FAIL)
- **Issue**: Old promotions/newsletters still surfacing
- **Fix**: Increase skip rate for routine items after 1 week
- **Check**: Temporal decay rules for routine importance

## Optional Enhancements

### K-Fold Temporal Validation

To guard against seed-lucky results:

```bash
# Generate 3 additional datasets with different seeds
for seed in 51 52 53; do
  python3 scripts/create_temporal_digest_review.py --seed $seed
done

# Label all datasets at T0, T1, T2
# Evaluate all datasets
# Calculate mean ± stdev for metrics
```

This shows whether results generalize or are specific to seed-50 cohort.

### Edge Case Density Increase

Add more boundary cases for specific windows:
- Events at exactly 59, 60, 61 minutes
- Bills due at 23h, 24h, 25h
- Day boundaries: 11:59pm, 12:00am, 12:01am

Modify `scripts/create_edge_case_emails.py` to generate additional cases.

## Files

### Scripts
- `scripts/create_temporal_digest_review.py` - Generate 50-email dataset
- `scripts/create_edge_case_emails.py` - Generate 10 edge cases
- `scripts/merge_edge_cases_to_dataset.py` - Combine datasets
- `scripts/interactive_temporal_review.py` - Interactive labeling tool
- `scripts/evaluate_temporal_decay.py` - Run system evaluation
- `scripts/generate_temporal_report.py` - Generate markdown report

### Outputs
- `reports/temporal_digest_review_50_emails.csv` - Main dataset
- `reports/temporal_edge_cases_10_emails.csv` - Edge cases
- `reports/temporal_digest_review_60_emails.csv` - Combined (optional)
- `reports/temporal_evaluation_results.csv` - Detailed results
- `reports/temporal_decay_evaluation.md` - Summary report

### Configuration
- `config/guardrails.yaml` - Filtering rules
- `mailq/digest/categorizer.py` - Section assignment logic
- `mailq/temporal_enrichment.py` - Decay windows

## Troubleshooting

**Q: Labels not saving**
- Check CSV file permissions
- Progress auto-saves every 10 emails + on quit
- Look for success message: "✅ Progress saved!"

**Q: System predictions all wrong**
- Verify temporal enrichment is enabled
- Check `mailq.db` has temporal keyword rules (22 entries)
- Review logs for entity extraction failures

**Q: Edge cases not included**
- Run `merge_edge_cases_to_dataset.py` to combine
- OR manually append edge case CSV rows to main CSV
- Update interactive tool path if using 60-email combined CSV

**Q: Confusion matrix hard to read**
- Open markdown report in GitHub/VS Code for table rendering
- Or convert to HTML: `pandoc -s temporal_decay_evaluation.md -o report.html`

## Next Steps After Results

1. **All Pass**: ✅ Temporal decay is working correctly! Ship it.

2. **Some Fail**: Review top error patterns in report:
   - Adjust temporal decay windows in `temporal_enrichment.py`
   - Add/modify rules in `config/guardrails.yaml`
   - Enhance temporal keyword database
   - Re-run evaluation to validate fixes

3. **Major Fail**: Deep dive needed:
   - Check entity extraction success rate
   - Verify importance classification (Stage 1)
   - Review categorizer logic (Stage 4.5)
   - Consider adding more training data

## References

- [CLAUDE.md](CLAUDE.md) - Development guardrails
- [MAILQ_REFERENCE.md](MAILQ_REFERENCE.md) - Architecture reference
- [config/guardrails.yaml](config/guardrails.yaml) - Filtering rules
- [mailq/temporal_enrichment.py](mailq/temporal_enrichment.py) - Decay logic
