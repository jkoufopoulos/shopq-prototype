#!/bin/bash
# Quick launcher for manual GDS review tool
# Automatically resumes from session file (tracks completed message_ids)
# Reviews remaining emails with GPT-5 pre-fills + pattern overrides

PYTHONPATH=/Users/justinkoufopoulos/Projects/mailq-prototype uv run python scripts/manual_label_gds.py \
    --input data/gds/gds-2.0-manually-reviewed.csv \
    --output data/gds/gds-2.0-manually-reviewed.csv \
    --use-existing-labels
