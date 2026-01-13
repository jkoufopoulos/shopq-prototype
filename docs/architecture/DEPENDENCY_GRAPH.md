# Dependency Graph Overview

_Generated during Phase 0 as a baseline for future refactors._

## High-level Findings

- **`mailq/context_digest.py`** currently imports 10+ modules spanning entity extraction, importance classification, enrichment, rendering, and observability. This file is the primary hotspot and violates the desired layered architecture (domain + usecases separation).
- **`extension/background.js`** aggregates utility modules (logger, classifier, summary-email, auto-organize). It mixes orchestration with adapter details and should be decomposed into usecases vs adapters.
- **`extension/modules/summary-email.js`** depends on logger, config, and Gmail API helpers—indicating tight coupling between telemetry and delivery logic.
- **`mailq/digest_formatter.py`** pulls domain logic plus contextual helpers, but remains relatively isolated from mailq.adapters.
- Shared utilities such as `mailq/importances_classifier.py`, `mailq/context_digest.py`, and `mailq/entity_extractor.py` create a broad dependency fan-out that will need re-homing under `domain/` and `adapters/`.

## Notable Cycles (Manual Inspection)

1. `mailq/context_digest.py → mailq.timeline_synthesizer → mailq.importance_classifier → mailq.context_digest.py` (implicit through shared imports).
   - **Mitigation**: split domain models into `domain/` and pass data via pure functions.

2. `extension/background.js → modules/auto-organize.js → modules/summary-email.js → background.js` (registration side effects).
   - **Mitigation**: re-export orchestration helpers from `usecases/` namespace; background worker should import orchestrators only.

## TODOs

- // TODO(clarify): Generate full dependency graph via `pydeps mailq --noshow --show-deps` and store as `docs/deps.svg`. The tool is not available in the current environment; schedule for Phase 1 setup.
- // TODO(clarify): For front-end scripts, run `npx madge extension --image docs/deps.svg` once Node tooling is confirmed.
