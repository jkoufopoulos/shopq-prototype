# Repo Map — Classification, Rules, Digest, Feedback, Time Math (Nov 2025)

> **⚠️ HISTORICAL REFERENCE**: This document was produced during Phase 0 Bootstrap and contains **OUTDATED PATHS** from before the Nov 2025 restructuring. Many referenced files have been moved or consolidated.
>
> **For current architecture**, see:
> - [shopq/README.md](../../shopq/README.md) - Current 7-directory structure
> - [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Up-to-date file organization
> - [ARCHITECTURE.md](ARCHITECTURE.md) - Current system architecture
>
> This document is preserved for historical context only.


Reference produced during Phase 0 Bootstrap to keep the ShopQ reclassification migration grounded in the current codebase. Paths are relative to repo root.

---

## 1. Entry Points & Pipelines
- `shopq/api.py` — FastAPI application wiring all HTTP endpoints, including `/api/organize`, `/api/context-digest`, `/api/feedback`, and tracking/debug surfaces.
- `shopq/api_organize.py` — Legacy+refactored classification endpoint logic; toggles between `MemoryClassifier` and the refactored pipeline via `shopq/pipeline_wrapper.py`.
- `shopq/pipeline_wrapper.py` — Wraps the new domain pipeline so it can satisfy the `MemoryClassifier` contract; converts API email objects to domain models.
- `usecases/pipeline.py` — High-level orchestrator that runs fetch → parse → dedupe → classify → assemble digest; enforces idempotency and telemetry timing.
- `adapters/api_bridge.py` — Translates FastAPI models to/from `domain.models.*`, ensuring the refactored backend stays schema-compatible with the legacy API.
- `adapters/gmail/*` — Gmail fetchers, parsers, and retry logic used by the pipeline entry point.
- `infra/idempotency.py`, `infra/telemetry.py`, `infra/retry.py` — System-wide helpers for dedupe keys, counters/log events, and resilient retries.

## 2. Classification & Rules Layer
- `shopq/memory_classifier.py` — Legacy orchestration: rules-first via `shopq/rules_engine.py`, then `shopq/vertex_gemini_classifier.py`, plus Gmail label mapping and rule learning.
- `domain/classify.py` & `domain/models.py` — Refactored LLM-first classifier with Pydantic contracts, rules fallback, and deterministic schemas for API compatibility.
- `adapters/llm/client.py` — Vertex/Gemini client abstraction that enforces schema validation and wraps API failures for the domain layer.
- `shopq/vertex_gemini_classifier.py` — Production Gemini integration (few-shot prompt construction, boost heuristics, learning hooks into `FeedbackManager`).
- `shopq/rules_engine.py` & `shopq/rules_manager.py` — SQLite-backed rules storage, learning, and inspection helpers; invoked by both legacy and refactored stacks.
- `config/mapper_rules.yaml`, `config/guardrails.yaml`, `shopq/bridge/*` — Bridge Mode mapper + guardrails that consume extension LLM records before fallback patterns (feature-gated for shadow comparisons).
- `shopq/mapper.py` — Maps semantic classification to Gmail labels using gates from `shopq/config/confidence.py`.
- `shopq/config/confidence.py` & `config/shopq_policy.yaml` — Central confidence/threshold knobs consumed by API, mapper, detectors, and verifier.
- `shopq/api_verify.py` & `extension/modules/verifier.js` — Backend + extension logic for selective second-pass verification on suspicious classifications.
- `shopq/api_debug.py`, `shopq/api_dashboard.py` — Debug surfaces that expose classification summaries, importance groupings, and Gmail search helpers.
- `scripts/diagnose_importance_classifier.py`, `scripts/generate_digest_comparison.py`, `scripts/mailq-db` — Developer utilities to inspect classifier decisions, compare digests, and query tracking DBs.

## 3. Chrome Extension Touchpoints
- `extension/modules/classifier.js` — Runs cache, detectors (`detectors.js`), dedupe, API classification, and wires verifier + logger calls.
- `extension/modules/mapper.js` — Mirrors backend label mapper with client-side heuristics (relationship-aware domain tags, action-required label).
- `extension/modules/detectors.js` — High-precision OTP/receipt/event/etc. detectors that short-circuit API cost and feed the backend confidence model.
- `extension/modules/verifier.js` — Selective verifier trigger calculation and prompt assembly before calling `/api/verify`.
- `extension/modules/context-digest.js` & `extension/modules/summary-email.js` — Frontend drivers for digest generation and display; stream tracking stats back to the CLI.
- `extension/modules/cache.js`, `telemetry.js`, `config-sync.js`, `budget.js`, `auto-organize.js` — Support modules that cache classifications, sync thresholds from backend, enforce budgets, and send telemetry used by backend analytics.

## 4. Importance Classifier & Entity Layer
- `shopq/importance_classifier.py` — Pattern-based critical/time-sensitive/routine classifier used for digest staging, noise summaries, and fallback narratives.
- `shopq/context_digest.py` — Primary context digest generator: filters emails, calls `ImportanceClassifier.classify_batch`, logs/tracks decisions, extracts entities, synthesizes timeline, and renders HTML (fallback + deterministic DTO placeholders).
- `shopq/entity_extractor.py`, `shopq/entities.py`, `shopq/entity_deduplicator.py`, `shopq/span_aware_entity_linker.py` — Rules+LLM entity extraction, dataclasses, dedupe/linking for timeline inputs; every entity carries an `importance`.
- `shopq/context_enricher.py`, `shopq/email_tracker.py`, `shopq/observability.py` — Adds weather/location context, logs classification stats, persists tracking summaries (importance counts, verifier usage, etc.).
- `shopq/importance/learning.py` — Digest feedback learner that turns user actions into importance pattern votes (stored in SQLite under `digest_feedback.db` / `digest_patterns`).

## 5. Digest Assembly, Rendering, & Time Math
- `shopq/timeline_synthesizer.py` — Groups entities by importance, enforces priority scores, and produces featured/noise breakdowns with adaptive word budgets.
- `shopq/digest_categorizer.py`, `shopq/digest_ranker.py`, `shopq/digest_formatter.py`, `shopq/digest_renderer.py`, `shopq/digest_delivery.py` — Learned section assignment, ranking, template formatting, HTML rendering, and outbound delivery helpers; all rely on stable entity importance values.
- `shopq/gmail_link_builder.py`, `shopq/card_renderer.py`, `shopq/natural_opening.py`, `shopq/narrative_generator.py`, `shopq/context_enricher.py` — Deterministic link building, per-card rendering, natural-language openings, narrative blocks, and enrichment services.
- `shopq/location_service.py`, `shopq/weather_service.py`, `shopq/timeline_synthesizer.py`, `shopq/context_digest.py::_fallback_email_summary` — Timezone/math helpers, weather lookups, and fallback narratives that still respect importance ordering.
- `shopq/digest_tracking.html`, `shopq/digest_tracking.*` — Visualization artifacts for digest sessions (used in debugging importance routing).

## 6. Feedback, Corrections, & Learning Loops
- `shopq/api_feedback.py` — HTTP interface for user corrections/feedback, writes to shopq.db, and fans out learning events.
- `shopq/feedback_manager.py` — Persists corrections, learns sender patterns, and exposes few-shot samples for the LLM classifier.
- `shopq/email_tracker.py` — Aggregates session stats (importance counts, extraction coverage, verifier rate) for `/api/tracking/session/:id`.
- `shopq/importance/learning.py` — Learns guardrail patterns (never_surface/force critical/etc.) from digest interactions; writes `digest_feedback` + `digest_patterns`.
- `quality_logs/**`, `quality_monitor.db`, `scripts/quality-monitor/*`, `QUALITY_ISSUES_SUMMARY.md`, `QC_WORKFLOW.md` — Quality monitoring storage and workflows referencing importance drift.

## 7. Config, Data, and Supporting Docs
- `config/shopq_policy.yaml` — Runtime policy for classification/verifier thresholds and quality monitor batch sizes.
- `shopq/config/*` — Central configs (confidence gates, DB settings, feature gates).
- `shopq/data/**` & `archive/**` — Golden datasets, pattern archives, and historical analyses that document importance or digest behavior.
- `docs/CLASSIFICATION_REFACTOR_PLAN.md`, `SHOPQ_REFERENCE.md`, `claude.md`, `AGENTS.md`, `QC_WORKFLOW.md` — Governing documents for the ongoing reclassification migration.

## 8. Tests & Fixtures (importance/digest focused)
- `tests/unit/test_digest_categorizer.py`, `tests/test_natural_opening.py`, `tests/test_debug_endpoints.py`, `shopq/tests/test_entity_linking_digest.py`, `shopq/tests/test_reference_validation.py` — Validate sectioning, narrative openings, debug endpoints, entity linkage, and schema integrity for importance-bearing objects.
- `scripts/quality-monitor/test_nov1_digest.py`, `tests/fixtures/**` (forthcoming Phase 0 `golden_set/`) — Fixture-driven regression tests to freeze current importance routing before the refactor proceeds.

---

This map is exhaustive for modules touching classification, rules, digest generation, feedback, and time math as of Nov 2025. Update alongside new phases so CI guards (importance decider diffs, golden-set replays) stay anchored to real file paths.
