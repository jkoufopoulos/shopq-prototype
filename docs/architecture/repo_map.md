# Repo Map — Classification, Rules, Digest, Feedback, Time Math (Nov 2025)

> **⚠️ HISTORICAL REFERENCE**: This document was produced during Phase 0 Bootstrap and contains **OUTDATED PATHS** from before the Nov 2025 restructuring. Many referenced files have been moved or consolidated.
>
> **For current architecture**, see:
> - [mailq/README.md](../../mailq/README.md) - Current 7-directory structure
> - [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Up-to-date file organization
> - [ARCHITECTURE.md](ARCHITECTURE.md) - Current system architecture
>
> This document is preserved for historical context only.


Reference produced during Phase 0 Bootstrap to keep the MailQ reclassification migration grounded in the current codebase. Paths are relative to repo root.

---

## 1. Entry Points & Pipelines
- `mailq/api.py` — FastAPI application wiring all HTTP endpoints, including `/api/organize`, `/api/context-digest`, `/api/feedback`, and tracking/debug surfaces.
- `mailq/api_organize.py` — Legacy+refactored classification endpoint logic; toggles between `MemoryClassifier` and the refactored pipeline via `mailq/pipeline_wrapper.py`.
- `mailq/pipeline_wrapper.py` — Wraps the new domain pipeline so it can satisfy the `MemoryClassifier` contract; converts API email objects to domain models.
- `usecases/pipeline.py` — High-level orchestrator that runs fetch → parse → dedupe → classify → assemble digest; enforces idempotency and telemetry timing.
- `adapters/api_bridge.py` — Translates FastAPI models to/from `domain.models.*`, ensuring the refactored backend stays schema-compatible with the legacy API.
- `adapters/gmail/*` — Gmail fetchers, parsers, and retry logic used by the pipeline entry point.
- `infra/idempotency.py`, `infra/telemetry.py`, `infra/retry.py` — System-wide helpers for dedupe keys, counters/log events, and resilient retries.

## 2. Classification & Rules Layer
- `mailq/memory_classifier.py` — Legacy orchestration: rules-first via `mailq/rules_engine.py`, then `mailq/vertex_gemini_classifier.py`, plus Gmail label mapping and rule learning.
- `domain/classify.py` & `domain/models.py` — Refactored LLM-first classifier with Pydantic contracts, rules fallback, and deterministic schemas for API compatibility.
- `adapters/llm/client.py` — Vertex/Gemini client abstraction that enforces schema validation and wraps API failures for the domain layer.
- `mailq/vertex_gemini_classifier.py` — Production Gemini integration (few-shot prompt construction, boost heuristics, learning hooks into `FeedbackManager`).
- `mailq/rules_engine.py` & `mailq/rules_manager.py` — SQLite-backed rules storage, learning, and inspection helpers; invoked by both legacy and refactored stacks.
- `config/mapper_rules.yaml`, `config/guardrails.yaml`, `mailq/bridge/*` — Bridge Mode mapper + guardrails that consume extension LLM records before fallback patterns (feature-gated for shadow comparisons).
- `mailq/mapper.py` — Maps semantic classification to Gmail labels using gates from `mailq/config/confidence.py`.
- `mailq/config/confidence.py` & `config/mailq_policy.yaml` — Central confidence/threshold knobs consumed by API, mapper, detectors, and verifier.
- `mailq/api_verify.py` & `extension/modules/verifier.js` — Backend + extension logic for selective second-pass verification on suspicious classifications.
- `mailq/api_debug.py`, `mailq/api_dashboard.py` — Debug surfaces that expose classification summaries, importance groupings, and Gmail search helpers.
- `scripts/diagnose_importance_classifier.py`, `scripts/generate_digest_comparison.py`, `scripts/mailq-db` — Developer utilities to inspect classifier decisions, compare digests, and query tracking DBs.

## 3. Chrome Extension Touchpoints
- `extension/modules/classifier.js` — Runs cache, detectors (`detectors.js`), dedupe, API classification, and wires verifier + logger calls.
- `extension/modules/mapper.js` — Mirrors backend label mapper with client-side heuristics (relationship-aware domain tags, action-required label).
- `extension/modules/detectors.js` — High-precision OTP/receipt/event/etc. detectors that short-circuit API cost and feed the backend confidence model.
- `extension/modules/verifier.js` — Selective verifier trigger calculation and prompt assembly before calling `/api/verify`.
- `extension/modules/context-digest.js` & `extension/modules/summary-email.js` — Frontend drivers for digest generation and display; stream tracking stats back to the CLI.
- `extension/modules/cache.js`, `telemetry.js`, `config-sync.js`, `budget.js`, `auto-organize.js` — Support modules that cache classifications, sync thresholds from backend, enforce budgets, and send telemetry used by backend analytics.

## 4. Importance Classifier & Entity Layer
- `mailq/importance_classifier.py` — Pattern-based critical/time-sensitive/routine classifier used for digest staging, noise summaries, and fallback narratives.
- `mailq/context_digest.py` — Primary context digest generator: filters emails, calls `ImportanceClassifier.classify_batch`, logs/tracks decisions, extracts entities, synthesizes timeline, and renders HTML (fallback + deterministic DTO placeholders).
- `mailq/entity_extractor.py`, `mailq/entities.py`, `mailq/entity_deduplicator.py`, `mailq/span_aware_entity_linker.py` — Rules+LLM entity extraction, dataclasses, dedupe/linking for timeline inputs; every entity carries an `importance`.
- `mailq/context_enricher.py`, `mailq/email_tracker.py`, `mailq/observability.py` — Adds weather/location context, logs classification stats, persists tracking summaries (importance counts, verifier usage, etc.).
- `mailq/importance/learning.py` — Digest feedback learner that turns user actions into importance pattern votes (stored in SQLite under `digest_feedback.db` / `digest_patterns`).

## 5. Digest Assembly, Rendering, & Time Math
- `mailq/timeline_synthesizer.py` — Groups entities by importance, enforces priority scores, and produces featured/noise breakdowns with adaptive word budgets.
- `mailq/digest_categorizer.py`, `mailq/digest_ranker.py`, `mailq/digest_formatter.py`, `mailq/digest_renderer.py`, `mailq/digest_delivery.py` — Learned section assignment, ranking, template formatting, HTML rendering, and outbound delivery helpers; all rely on stable entity importance values.
- `mailq/gmail_link_builder.py`, `mailq/card_renderer.py`, `mailq/natural_opening.py`, `mailq/narrative_generator.py`, `mailq/context_enricher.py` — Deterministic link building, per-card rendering, natural-language openings, narrative blocks, and enrichment services.
- `mailq/location_service.py`, `mailq/weather_service.py`, `mailq/timeline_synthesizer.py`, `mailq/context_digest.py::_fallback_email_summary` — Timezone/math helpers, weather lookups, and fallback narratives that still respect importance ordering.
- `mailq/digest_tracking.html`, `mailq/digest_tracking.*` — Visualization artifacts for digest sessions (used in debugging importance routing).

## 6. Feedback, Corrections, & Learning Loops
- `mailq/api_feedback.py` — HTTP interface for user corrections/feedback, writes to mailq.db, and fans out learning events.
- `mailq/feedback_manager.py` — Persists corrections, learns sender patterns, and exposes few-shot samples for the LLM classifier.
- `mailq/email_tracker.py` — Aggregates session stats (importance counts, extraction coverage, verifier rate) for `/api/tracking/session/:id`.
- `mailq/importance/learning.py` — Learns guardrail patterns (never_surface/force critical/etc.) from digest interactions; writes `digest_feedback` + `digest_patterns`.
- `quality_logs/**`, `quality_monitor.db`, `scripts/quality-monitor/*`, `QUALITY_ISSUES_SUMMARY.md`, `QC_WORKFLOW.md` — Quality monitoring storage and workflows referencing importance drift.

## 7. Config, Data, and Supporting Docs
- `config/mailq_policy.yaml` — Runtime policy for classification/verifier thresholds and quality monitor batch sizes.
- `mailq/config/*` — Central configs (confidence gates, DB settings, feature gates).
- `mailq/data/**` & `archive/**` — Golden datasets, pattern archives, and historical analyses that document importance or digest behavior.
- `docs/CLASSIFICATION_REFACTOR_PLAN.md`, `MAILQ_REFERENCE.md`, `claude.md`, `AGENTS.md`, `QC_WORKFLOW.md` — Governing documents for the ongoing reclassification migration.

## 8. Tests & Fixtures (importance/digest focused)
- `tests/unit/test_digest_categorizer.py`, `tests/test_natural_opening.py`, `tests/test_debug_endpoints.py`, `mailq/tests/test_entity_linking_digest.py`, `mailq/tests/test_reference_validation.py` — Validate sectioning, narrative openings, debug endpoints, entity linkage, and schema integrity for importance-bearing objects.
- `scripts/quality-monitor/test_nov1_digest.py`, `tests/fixtures/**` (forthcoming Phase 0 `golden_set/`) — Fixture-driven regression tests to freeze current importance routing before the refactor proceeds.

---

This map is exhaustive for modules touching classification, rules, digest generation, feedback, and time math as of Nov 2025. Update alongside new phases so CI guards (importance decider diffs, golden-set replays) stay anchored to real file paths.
