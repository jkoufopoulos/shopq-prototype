# Evaluation Datasets

This directory contains ground truth datasets for evaluating MailQ's classification and digest generation.

## Structure

```
data/evals/
├── classification/          # Email classification evaluation
│   ├── gds-2.0.csv          # 500 manually-labeled emails
│   └── backups/             # Historical backups
└── digests/                 # Digest generation evaluation
    ├── dataset3/            # Nov 5-7, 2025 (68 emails)
    │   ├── emails.csv       # Source emails
    │   └── golden.html      # Expected digest output (hand-crafted)
    ├── dataset4/            # Oct 27-29, 2025 (55 emails)
    │   ├── emails.csv
    │   └── golden.html      # Hand-crafted
    ├── dataset6/            # Nov 21-22, 2025 (21 emails) - newsletter/promo heavy
    │   └── emails.csv       # No golden yet
    └── dataset7/            # Oct 19, 2025 (14 emails) - receipt heavy, single day
        └── emails.csv       # No golden yet
```

## Two Evaluation Tracks

### 1. Classification Accuracy (`classification/`)

Tests whether the classifier correctly labels individual emails.

**Dataset:** `gds-2.0.csv` - 500 manually-reviewed emails with ground truth labels

**Labels evaluated:**
- `email_type`: otp, notification, event, newsletter, promotion, message, receipt
- `importance`: critical, time_sensitive, routine
- `client_label`: action-required, receipts, messages, everything-else

**Run evaluation:**
```bash
uv run python scripts/evals/classification_accuracy.py --save-results --name "experiment_name"
```

### 2. Digest Quality (`digests/`)

Tests whether the digest pipeline produces correct HTML summaries for a set of emails.

**Datasets:** Each subdirectory contains emails from a specific date range that form a coherent "day of email"

**Structure:**
- `emails.csv` - Source emails for the digest period
- `golden.html` - Hand-crafted expected digest output

**Run evaluation:**
```bash
uv run python scripts/evals/digest_comparison.py --dataset dataset3
uv run python scripts/evals/digest_comparison.py --all
```

## Why Two Separate Tracks?

**Classification** needs broad coverage across email types - a random sample works well.

**Digest** needs emails that make sense *together* as a daily summary. You can't substitute random emails because the golden digest is crafted for that specific email set.

## Adding New Datasets

### Classification
Edit `classification/gds-2.0.csv` directly or use the labeling tool:
```bash
uv run python scripts/evals/tools/manual_label.py --input data/evals/classification/gds-2.0.csv
```

### Digests
1. Create a new directory: `digests/dataset6/`
2. Export emails from a date range to `emails.csv`
3. Generate and manually refine the golden digest as `golden.html`

## Results

Evaluation results are saved to `reports/experiments/` with timestamps:
- `YYYYMMDD_HHMMSS_experiment_name.json` - Full metrics
- `YYYYMMDD_HHMMSS_experiment_name.md` - Human-readable summary
