# ShopQ Scripts Directory

Utility scripts for development, testing, evaluation, quality monitoring, and data management.

## Categories

Scripts are organized by purpose:

### 🧪 Testing & Evaluation
Scripts for running tests and evaluating classification performance.

### 📊 Data Management
Scripts for building datasets, exports, and database maintenance.

### 🔍 Quality Monitoring
Scripts for automated quality checks and GitHub issue management.

### 🛠️ Development & Debugging
Scripts for development workflow automation.

### 🗄️ Database & Migration
Scripts for database operations and schema migrations.

---

## 🧪 Testing & Evaluation Scripts

### Performance Evaluation

| Script | Purpose | Usage |
|--------|---------|-------|
| **eval_baseline_gds1.py** | Evaluate classification accuracy on Golden Dataset 1.0 | `python scripts/eval_baseline_gds1.py` |
| **eval_bridge_metrics.py** | Evaluate bridge mode metrics (mapper accuracy) | `python scripts/eval_bridge_metrics.py` |
| **check_importance_baseline.py** | Check importance classification baseline accuracy | `python scripts/check_importance_baseline.py` |
| **check_golden_balance.py** | Check Golden Dataset class balance (critical/routine ratio) | `python scripts/check_golden_balance.py` |
| **diagnose_importance_classifier.py** | Debug importance classifier with detailed output | `python scripts/diagnose_importance_classifier.py` |
| **analyze_gds_misclassifications.py** | Analyze misclassifications in Golden Dataset | `python scripts/analyze_gds_misclassifications.py` |

### Test Runners

| Script | Purpose | Usage |
|--------|---------|-------|
| **test_against_gds.sh** | Run full test suite against Golden Dataset | `./scripts/test_against_gds.sh` |
| **test_gds_migration_safe.sh** | Test GDS migration safety (no data loss) | `./scripts/test_gds_migration_safe.sh` |
| **run-full-e2e-tests.sh** | Run complete E2E test suite (Playwright) | `./scripts/run-full-e2e-tests.sh` |

### Comparison & Analysis

| Script | Purpose | Usage |
|--------|---------|-------|
| **compare_actual_vs_ideal.py** | Compare actual digest with ideal (expert-labeled) | `python scripts/compare_actual_vs_ideal.py` |
| **generate_digest_comparison.py** | Generate side-by-side digest comparison | `python scripts/generate_digest_comparison.py` |
| **generate_ideal_digest.py** | Generate expert-labeled "ideal" digest | `python scripts/generate_ideal_digest.py` |

---

## 📊 Data Management Scripts

### Dataset Building

| Script | Purpose | Usage |
|--------|---------|-------|
| **build_golden_dataset.py** | Build Golden Dataset from labeled emails | `python scripts/build_golden_dataset.py` |
| **create_unified_golden_dataset.py** | Merge multiple golden datasets into unified GDS 1.0 | `python scripts/create_unified_golden_dataset.py` |
| **fetch_diverse_emails.py** | Fetch diverse sample of emails for labeling | `python scripts/fetch_diverse_emails.py` |
| **extract_golden_from_db.py** | Extract golden dataset from database | `python scripts/extract_golden_from_db.py` |

### Data Export & Review

| Script | Purpose | Usage |
|--------|---------|-------|
| **export_inbox_for_review.py** | Export inbox emails to CSV for manual review | `python scripts/export_inbox_for_review.py` |
| **create_digest_review_csv.py** | Create CSV for digest quality review | `python scripts/create_digest_review_csv.py` |
| **classify_historical_emails.py** | Classify historical emails and export results | `python scripts/classify_historical_emails.py` |
| **extract_temporal_fields.py** | Extract temporal fields (dates, deadlines) from emails | `python scripts/extract_temporal_fields.py` |

### Database Maintenance

| Script | Purpose | Usage |
|--------|---------|-------|
| **cleanup_old_data.sh** | Clean up old data (exports, logs, test artifacts) | `./scripts/cleanup_old_data.sh` |
| **fix_digest_categorizer_db.py** | Fix digest_rules.db schema issues | `python scripts/fix_digest_categorizer_db.py` |
| **fix_email_tracker_db.py** | Fix email_tracker database schema | `python scripts/fix_email_tracker_db.py` |

---

## 🔍 Quality Monitoring Scripts

ShopQ includes an automated quality monitoring system that continuously checks digest quality and creates GitHub issues for problems.

### Quality System Control

| Script | Purpose | Usage |
|--------|---------|-------|
| **start-quality-system.sh** | Start full quality monitoring system (background) | `./scripts/start-quality-system.sh` |
| **stop-quality-system.sh** | Stop quality monitoring system | `./scripts/stop-quality-system.sh` |
| **quality-system-status.sh** | Check quality system status (processes, last run) | `./scripts/quality-system-status.sh` |
| **force-quality-check.sh** | Force immediate quality check (bypass schedule) | `./scripts/force-quality-check.sh` |

### Quality Pipeline

| Script | Purpose | Usage |
|--------|---------|-------|
| **run-quality-pipeline.sh** | Run quality analysis pipeline manually | `./scripts/run-quality-pipeline.sh` |
| **quality-monitor-status.sh** | Show quality monitor detailed status | `./scripts/quality-monitor-status.sh` |

### GitHub Issue Management

| Script | Purpose | Usage |
|--------|---------|-------|
| **create_quality_issues.sh** | Create GitHub issues from quality analysis results | `./scripts/create_quality_issues.sh` |
| **close_quality_issues.sh** | Close resolved quality issues | `./scripts/close_quality_issues.sh` |

**Note**: Quality monitoring requires:
- `GITHUB_TOKEN` environment variable set
- Backend API running
- `quality-monitor/` subdirectory with Python scripts

See: `scripts/quality-monitor/README.md` for details.

---

## 🛠️ Development & Debugging Scripts

### Development Workflow

| Script | Purpose | Usage |
|--------|---------|-------|
| **load-env.sh** | Load environment variables from .env | `source scripts/load-env.sh` |
| **reset-for-debug.sh** | Reset state for clean debugging session | `./scripts/reset-for-debug.sh` |
| **fetch-logs.sh** | Fetch logs from Cloud Run production | `./scripts/fetch-logs.sh` |

### Automated Debugging

| Script | Purpose | Usage |
|--------|---------|-------|
| **auto-debug-digest.sh** | Auto-debug digest generation issues | `./scripts/auto-debug-digest.sh` |
| **auto-fix-tests.sh** | Auto-fix common test failures | `./scripts/auto-fix-tests.sh` |
| **claude-iterate-digest.sh** | Use Claude to iterate on digest improvements | `./scripts/claude-iterate-digest.sh` |

**Warning**: Automated debugging scripts use Claude API and may incur costs.

### Diagnostics

| Script | Purpose | Usage |
|--------|---------|-------|
| **check_importance_mutators.py** | Check which mutators affect importance scoring | `python scripts/check_importance_mutators.py` |

---

## 🗄️ Database & Migration Scripts

Database-related scripts are located in `shopq/scripts/` (package-level):

| Script | Purpose | Location |
|--------|---------|----------|
| **consolidate_databases.py** | Consolidate multiple .db files into single database | `shopq/scripts/` |
| **inspect_databases.py** | Inspect database schema and contents | `shopq/scripts/` |
| **migrate_pending_rules.py** | Migrate pending digest rules | `shopq/scripts/` |
| **clear_rules.py** | Clear cached rules | `shopq/scripts/` |

**Important**: Always use `shopq/config/database.py:get_db_connection()` for database access.

---

## Subdirectories

### quality-monitor/

Standalone quality monitoring system with its own Python scripts:

```
scripts/quality-monitor/
├── README.md                  # Quality monitor documentation
├── quality_analyzer.py        # Core analysis logic
├── github_reporter.py         # GitHub issue creation
├── quality_monitor.py         # Main monitor orchestrator
└── prompts/                   # LLM prompts for analysis
```

See: `scripts/quality-monitor/README.md` for details.

### hooks/

Git hooks for pre-commit checks:

```
scripts/hooks/
├── check-no-new-databases.sh  # Prevent new .db files (database policy)
└── [other pre-commit hooks]
```

**Note**: Hooks are installed via `.pre-commit-config.yaml`.

---

## Common Workflows

### 1. Evaluate Classification Accuracy

```bash
# Check baseline accuracy on Golden Dataset
python scripts/check_importance_baseline.py

# Detailed evaluation with metrics
python scripts/eval_baseline_gds1.py

# Analyze misclassifications
python scripts/analyze_gds_misclassifications.py
```

**Output**: Precision, recall, F1 score, confusion matrix.

### 2. Build New Golden Dataset

```bash
# 1. Fetch diverse sample
python scripts/fetch_diverse_emails.py --count 500

# 2. Export for manual labeling
python scripts/export_inbox_for_review.py

# 3. Label in CSV (manually)

# 4. Build golden dataset
python scripts/build_golden_dataset.py --input labeled.csv

# 5. Check class balance
python scripts/check_golden_balance.py
```

### 3. Run Quality Monitoring

```bash
# Start quality system (background)
./scripts/start-quality-system.sh

# Check status
./scripts/quality-system-status.sh

# Force immediate check
./scripts/force-quality-check.sh

# View issues created
# → Go to GitHub Issues with `quality` label
```

### 4. Debug Digest Generation

```bash
# Manual debugging
python scripts/generate_ideal_digest.py

# Automated debugging with Claude
./scripts/auto-debug-digest.sh

# Compare actual vs ideal
python scripts/compare_actual_vs_ideal.py
```

### 5. Database Maintenance

```bash
# Consolidate databases (if policy violated)
python shopq/scripts/consolidate_databases.py

# Inspect database
python shopq/scripts/inspect_databases.py

# Clean up old data
./scripts/cleanup_old_data.sh
```

---

## Environment Variables

Many scripts require environment variables. Load them:

```bash
source scripts/load-env.sh
```

**Required variables**:
- `ANTHROPIC_API_KEY` - For Claude API (debugging, quality monitoring)
- `GOOGLE_API_KEY` - For Gemini API (classification)
- `GITHUB_TOKEN` - For GitHub issue creation (quality monitoring)
- `SHOPQ_API_URL` - Backend API URL (default: http://localhost:8000)

See: `.env.example` for full list.

---

## Script Conventions

### Python Scripts

**Naming**: `verb_noun.py` (e.g., `build_golden_dataset.py`)

**Structure**:
```python
#!/usr/bin/env python3
"""
Brief description of what this script does.

Usage:
    python scripts/script_name.py [options]

Example:
    python scripts/script_name.py --input data.csv --output results.json
"""

import argparse
# ... imports ...

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # ... argument parsing ...
    # ... script logic ...

if __name__ == "__main__":
    main()
```

### Shell Scripts

**Naming**: `verb-noun.sh` (e.g., `start-quality-system.sh`)

**Structure**:
```bash
#!/bin/bash
# Brief description of what this script does

set -e  # Exit on error

# Script logic...
```

**Exit codes**:
- `0` - Success
- `1` - General error
- `2` - Usage error (missing arguments)

---

## Adding New Scripts

### 1. Choose Category
Place script in appropriate category (testing, data, quality, etc.)

### 2. Follow Naming Convention
- Python: `verb_noun.py`
- Shell: `verb-noun.sh`

### 3. Add Documentation
- Docstring (Python) or header comment (Shell)
- Usage examples
- Environment variable requirements

### 4. Update This README
Add entry to appropriate table with:
- Script name (linked if possible)
- Purpose (one sentence)
- Usage example

### 5. Make Executable (Shell scripts)
```bash
chmod +x scripts/your-script.sh
```

---

## Troubleshooting

### Script Fails with "Module not found"

**Cause**: Python path not set.

**Fix**:
```bash
export PYTHONPATH=/path/to/mailq-prototype
python scripts/your_script.py
```

Or add to script:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### Script Fails with "Database locked"

**Cause**: Multiple processes accessing database.

**Fix**:
1. Check running processes: `ps aux | grep python`
2. Stop conflicting processes
3. Use `shopq/config/database.py:get_db_connection()` (has retry logic)

### Quality Monitor Not Running

**Cause**: Process crashed or not started.

**Fix**:
```bash
# Check status
./scripts/quality-system-status.sh

# Stop and restart
./scripts/stop-quality-system.sh
./scripts/start-quality-system.sh
```

### GitHub Issues Not Created

**Cause**: `GITHUB_TOKEN` not set or invalid.

**Fix**:
```bash
# Check token
echo $GITHUB_TOKEN

# Set token (get from GitHub Settings → Developer settings → Personal access tokens)
export GITHUB_TOKEN="ghp_your_token_here"

# Or add to .env
echo "GITHUB_TOKEN=ghp_your_token_here" >> .env
source scripts/load-env.sh
```

---

## Related Documentation

- **Quality Monitoring**: `scripts/quality-monitor/README.md`
- **Database Policy**: `shopq/config/database.py` (docstring)
- **Testing Guide**: `/docs/TESTING.md`
- **Development Workflow**: `/CONTRIBUTING.md`

---

## Script Statistics

- **Python scripts**: 40+ evaluation, data, and quality scripts
- **Shell scripts**: 20+ automation and workflow scripts
- **Quality monitor**: 5 Python modules in `quality-monitor/`
- **Git hooks**: 2+ pre-commit hooks in `hooks/`

---

**Last Updated**: November 2025
**Maintained by**: See `/CONTRIBUTING.md`
