# Evaluation Scripts

Scripts for evaluating ShopQ's classification accuracy and digest quality.

## Quick Start

```bash
# Classification accuracy (500 emails, ~15-17 min)
uv run python scripts/evals/classification_accuracy.py --save-results --name "baseline"

# Digest comparison
uv run python scripts/evals/digest_comparison.py --all

# Verifier accuracy
uv run python scripts/evals/verifier_accuracy.py --limit 100
```

## Scripts

### `classification_accuracy.py`
Main classification evaluation script. Compares classifier predictions against GDS ground truth.

**Usage:**
```bash
# Full evaluation (500 emails)
uv run python scripts/evals/classification_accuracy.py --save-results --name "experiment_name"

# Quick test (first 50 emails)
uv run python scripts/evals/classification_accuracy.py --limit 50

# With notes
uv run python scripts/evals/classification_accuracy.py --save-results --name "v2" --notes "Testing new prompt"
```

**Output:**
- Accuracy metrics for type, importance, client_label
- Confusion matrices
- Top error patterns
- JSON/MD reports in `reports/experiments/`
- CSV error files for detailed analysis

### `digest_comparison.py`
Compares generated digests against golden reference HTMLs.

**Usage:**
```bash
# List available datasets
uv run python scripts/evals/digest_comparison.py --list

# Evaluate specific dataset
uv run python scripts/evals/digest_comparison.py --dataset dataset3

# Evaluate all datasets with golden digests
uv run python scripts/evals/digest_comparison.py --all

# Save generated output for inspection
uv run python scripts/evals/digest_comparison.py --dataset dataset3 --save-output
```

**Comparison approach:**
- Section presence (Today/Urgent, Coming Up, Worth Knowing)
- Item counts per section
- Email coverage (which emails are mentioned)
- Similarity score (0-100%)

### `verifier_accuracy.py`
Evaluates the verifier system that cross-checks classifier outputs.

**Usage:**
```bash
uv run python scripts/evals/verifier_accuracy.py --limit 100 --verbose
```

## Tools

### `tools/manual_label.py`
Interactive CLI for labeling emails in the GDS.

```bash
uv run python scripts/evals/tools/manual_label.py \
    --input data/evals/classification/gds-2.0.csv \
    --output data/evals/classification/gds-2.0.csv \
    --use-existing-labels
```

### `tools/apply_corrections.py`
Apply batch corrections to the GDS (creates backup first).

### `tools/review_corrections.py`
Review potential labeling issues in the GDS.

## Data Locations

| Data | Location |
|------|----------|
| Classification GDS | `data/evals/classification/gds-2.0.csv` |
| Digest datasets | `data/evals/digests/dataset{N}/` |
| Results | `reports/experiments/` |

## Typical Workflow

1. **Establish baseline:**
   ```bash
   uv run python scripts/evals/classification_accuracy.py --save-results --name "baseline"
   ```

2. **Make prompt/model changes**

3. **Run comparison:**
   ```bash
   uv run python scripts/evals/classification_accuracy.py --save-results --name "v2_changes"
   ```

4. **Analyze errors:**
   - Check `reports/experiments/YYYYMMDD_*_type_errors.csv`
   - Look for systematic patterns
   - Update prompt or add few-shot examples

5. **Repeat until accuracy target met**

## Target Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Type Accuracy | ≥85% | Current: ~84.6% |
| Importance Accuracy | ≥80% | Current: ~81.4% |
| Client Label Accuracy | ≥80% | Current: ~80.8% |
