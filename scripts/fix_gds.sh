#!/bin/bash
# GDS Correction Tool - Review and fix GDS labels based on taxonomy analysis
# Usage: ./scripts/fix_gds.sh

cd "$(dirname "$0")/.." || exit 1
PYTHONPATH=. uv run python scripts/evals/tools/gds_correction_tool.py "$@"
