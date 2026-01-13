# Archived Scripts

Historical scripts kept for reference. These are **not actively maintained** and may have broken imports/paths.

## Structure

```
scripts/archive/
├── dev_tools/      # Development iteration & debugging scripts
├── generators/     # Data generation scripts
├── legacy_gds/     # Old GDS (Golden Dataset) scripts - superseded by scripts/evals/
├── migrations/     # One-time migration scripts
└── one_off/        # One-time experiments, fixes, tests
```

## Why Archived?

- **legacy_gds/**: Replaced by `scripts/evals/` evaluation infrastructure
- **one_off/**: Scripts written for specific experiments/fixes, not reusable
- **dev_tools/**: Development helpers that may be useful for debugging
- **generators/**: Data generation scripts, occasionally useful
- **migrations/**: Historical schema/data migrations

## Using Archived Scripts

1. Paths are likely outdated (e.g., `data/gds/` → `data/evals/classification/`)
2. Imports may be broken due to refactoring
3. Test on a copy of data, not production

## Active Scripts Location

Current evaluation scripts are in `scripts/evals/`:
- `classification_accuracy.py` - Main classification eval
- `digest_comparison.py` - Digest quality eval
- `verifier_accuracy.py` - Verifier eval
- `tools/` - Labeling and correction tools

## Cleanup Policy

Scripts are moved here when:
- Superseded by a better implementation
- One-time use completed
- No longer compatible with current codebase

Delete archived scripts after 6 months if not referenced.
