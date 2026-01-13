# GDS Migration Scripts Archive

This directory contains one-time scripts used during the GDS-2.0 migration (Nov 2025).

These scripts have already been executed and are kept for historical reference only.

## Archived Scripts

### `ai_label_gds2.py`
**Purpose**: Pre-label GDS-2.0 emails with GPT-5-mini
**Status**: ✅ Complete (364 emails pre-labeled)
**Output**: `gds-2.0-gpt5-prelabeled.csv`

### `apply_ai_labels_to_gds2.py`
**Purpose**: Apply AI labels to GDS-2.0 dataset
**Status**: ✅ Complete
**Output**: `gds-2.0-labeled.csv`

### `add_client_labels_gpt5.py`
**Purpose**: Add client_label field using GPT-5
**Status**: ✅ Complete
**Output**: `gds-2.0-with-client-labels.csv`

### `manual_label_golden_set.py`
**Purpose**: Manual labeling tool for GDS-1.0
**Status**: ⚠️ Deprecated (replaced by `manual_label_gds.py`)
**Replacement**: `../manual_label_gds.py` (with resume + pattern overrides)

## Do Not Use These Scripts

These scripts were designed for one-time migrations and should not be run again.
They may overwrite current labeling progress.

If you need to re-run any migration, consult the team first.

---

**Archived**: Nov 17, 2025
**Migration**: GDS-1.0 → GDS-2.0 with manual review support
