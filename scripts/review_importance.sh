#!/bin/bash
# Quick wrapper to review importance classification errors
#
# Usage:
#   ./scripts/review_importance.sh          # Review errors from latest eval
#   ./scripts/review_importance.sh --fresh  # Run fresh eval first, then review
#   ./scripts/review_importance.sh --apply  # Apply saved decisions to GDS

set -e
cd "$(dirname "$0")/.."

# Auto-commit function for eval data changes
auto_commit_eval_data() {
  # Check if there are changes to eval data files
  if git diff --quiet data/evals/classification/gds-2.0.csv data/evals/classification/importance_review_decisions.csv 2>/dev/null; then
    return 0  # No changes
  fi

  echo ""
  echo "📝 Saving review session to git..."
  git add data/evals/classification/gds-2.0.csv data/evals/classification/importance_review_decisions.csv

  # Count new decisions
  local decisions=$(git diff --cached --numstat data/evals/classification/importance_review_decisions.csv | awk '{print $1}')
  local msg="data: Update importance review decisions"
  if [ -n "$decisions" ] && [ "$decisions" -gt 0 ]; then
    msg="data: Add $decisions importance review decisions"
  fi

  git commit -m "$msg" --no-verify
  echo "✅ Changes committed: $msg"
}

apply_corrections_if_pending() {
  # Check if there are unapplied corrections
  local pending=$(python3 scripts/evals/tools/apply_importance_corrections.py --dry-run 2>&1 | grep "would be updated" | grep -oE "[0-9]+" || echo "0")
  if [ "$pending" -gt 0 ]; then
    echo ""
    echo "📋 Applying $pending pending corrections to GDS..."
    python3 scripts/evals/tools/apply_importance_corrections.py
  fi
}

case "${1:-}" in
  --fresh)
    echo "Running fresh classification eval..."
    PYTHONPATH=. SHOPQ_USE_LLM=true uv run python3 scripts/evals/classification_accuracy.py \
      --name "importance_review_$(date +%Y%m%d)" --save-results
    echo ""
    echo "Starting importance review tool..."
    python3 scripts/evals/tools/importance_review_tool.py
    apply_corrections_if_pending
    auto_commit_eval_data
    ;;
  --apply)
    echo "Applying saved importance corrections to GDS..."
    python3 scripts/evals/tools/apply_importance_corrections.py
    auto_commit_eval_data
    ;;
  --dry-run)
    echo "Preview importance corrections (dry run)..."
    python3 scripts/evals/tools/apply_importance_corrections.py --dry-run
    ;;
  *)
    echo "Starting importance review tool..."
    python3 scripts/evals/tools/importance_review_tool.py
    apply_corrections_if_pending
    auto_commit_eval_data
    ;;
esac
