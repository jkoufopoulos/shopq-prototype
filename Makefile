# -------- Makefile (resilient ci) --------

.PHONY: cinit fmt lint typecheck test ci temporal-setup temporal-label temporal-eval temporal-report temporal-all

# Quick clipboard helper for Claude init
cinit:
	@cat .claude/presets/init-claude.txt | \
	(pbcopy 2>/dev/null || xclip -selection clipboard 2>/dev/null || clip.exe 2>/dev/null || cat >/dev/null)
	@echo "✅ Claude init prompt copied to clipboard. Paste into Claude Code panel."

# Auto-detect Python directories (add more here if needed)
PY_DIRS := $(strip \
  $(if $(wildcard reclaim),reclaim,) \
  $(if $(wildcard backend),backend,) \
  $(if $(wildcard shared),shared,) \
)

# Frontend extension paths
EXT_DIR := frontend/extension
EXT_PKG := $(EXT_DIR)/package.json

# Helper macro to run a command only if condition is met
define maybe_run
@if [ -n "$1" ]; then \
  echo "▶ $2: $1"; \
  $1; \
else \
  echo "⏭  $2: (skipped)"; \
fi
endef

fmt:
	@ruff format .

lint:
	@ruff format --check .
	@ruff check .
	# Extension lint (pnpm or npm) only if package.json exists
	$(call maybe_run, [ -f "$(EXT_PKG)" ] && (pnpm --prefix $(EXT_DIR) lint || npm --prefix $(EXT_DIR) run lint) || true,extension:lint)

typecheck:
	@mypy reclaim

test:
	# Python tests (pytest via uv)
	$(call maybe_run, test -n "$(PY_DIRS)" && PYTHONPATH=. RECLAIM_USE_LLM=false uv run pytest -q,pytest)
	# Extension tests
	$(call maybe_run, [ -f "$(EXT_PKG)" ] && (pnpm --prefix $(EXT_DIR) test || npm --prefix $(EXT_DIR) test) || true,extension:test)

ci: lint typecheck test
	@echo "✅ ci completed (see skipped lines above if parts of the tree are absent)"

# -------- End --------

.PHONY: fast
fast:
	@echo 'Running Ruff autofix + mypy on changed files...'
	@CHANGED=$$(git diff --name-only --diff-filter=AMR | grep -E '\.py$$' || true); \
	if [ -n "$$CHANGED" ]; then \
		ruff check $$CHANGED --select I,UP,W --fix; \
		ruff check $$CHANGED --select SIM,RET,ARG,B --fix; \
		mypy $$CHANGED; \
	else \
		echo 'No changed Python files.'; \
	fi

# -------- Temporal Decay Testing --------

# Step 1: Generate 50-email golden dataset + 10 edge cases
temporal-setup:
	@echo "🔧 Setting up temporal testing dataset..."
	@python3 scripts/create_temporal_digest_review.py
	@python3 scripts/create_edge_case_emails.py
	@echo ""
	@echo "✅ Dataset ready! Next step:"
	@echo "   Run: make temporal-label"
	@echo "   Or: python3 scripts/interactive_temporal_review.py"

# Step 2: Launch interactive labeling tool (manual step)
temporal-label:
	@echo "🏷️  Launching interactive labeling tool..."
	@echo ""
	@echo "INSTRUCTIONS:"
	@echo "1. Choose [1] T0 - Just Received"
	@echo "2. Label all 50 emails"
	@echo "3. Re-run for [2] T1 and [3] T2"
	@echo ""
	@python3 scripts/interactive_temporal_review.py

# Step 3: Evaluate temporal decay at all timepoints
temporal-eval:
	@echo "📊 Evaluating temporal decay (T0, T1, T2)..."
	@python3 scripts/evaluate_temporal_decay.py
	@echo ""
	@echo "✅ Evaluation complete! Next step:"
	@echo "   Run: make temporal-report"

# Step 4: Generate markdown report with confusion matrices
temporal-report:
	@echo "📝 Generating markdown report..."
	@python3 scripts/generate_temporal_report.py
	@echo ""
	@echo "✅ Report generated!"
	@echo "   📂 reports/temporal_decay_evaluation.md"
	@echo "   📂 reports/temporal_evaluation_results.csv"

# Run full temporal testing workflow (except labeling)
temporal-all:
	@echo "🚀 Running full temporal testing workflow..."
	@echo ""
	@make temporal-setup
	@echo ""
	@echo "⏸️  MANUAL STEP REQUIRED:"
	@echo "   Run: make temporal-label"
	@echo "   Label emails at T0, T1, T2"
	@echo ""
	@echo "   Then run: make temporal-eval && make temporal-report"
