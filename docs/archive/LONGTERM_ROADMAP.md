# ShopQ Roadmap — Now / Next / Later

**Last Updated**: 2025-11-10

---

## Completed Work (Archive)

### ✅ [DONE 2025-11-10] Type Mapper MVP (Phase B0)

**Delivered**: Global deterministic type classifier for calendar events
- 100% calendar match rate (50/50 Google Calendar events)
- 0.45% false positive rate (2/444 non-events)
- <1ms per email, zero LLM calls
- 10% email coverage (50/500 from gds-1.0)
- 36/36 tests passing

**Reference**: `docs/TYPE_MAPPER_IMPLEMENTATION_SUMMARY.md`

### ✅ [DONE 2025-11-10] Temporal Decay for Events (Phase 4)

**Delivered**: Temporal modulation of importance based on event timing
- Expired events hidden automatically
- Imminent events (±1h) → CRITICAL
- Upcoming events (≤7 days) → COMING UP
- Distant events (>7 days) → WORTH KNOWING
- 49/49 tests passing (unit + integration + e2e)

**Reference**: `docs/TESTING_COMPLETE_SUMMARY.md`

---

## NOW (lock safety + measurement for 20–40 user MVP)

* **Finish P0 (golden set + baseline)** ✅ DONE (2025-11-10)
  * ✅ build v1 dataset (500 emails - gds-1.0)
  * ✅ compute precision/recall/cost/latency
  * ✅ store results in comprehensive testing docs
  * **Reference**: `tests/golden_set/`, `docs/TESTING_COMPLETE_SUMMARY.md`

* **Run B0 shadow while labeling** ⚠️ PARTIALLY COMPLETE
  * ✅ Type mapper implemented and tested (Phase B0)
  * [ ] 3 day shadow period (mapper rules phase)
  * [ ] log {current vs llm} with version pins
  * [ ] inspect weekday/weekend drift

* **P4 monotonic post-process guard (CI + code)** ⚠️ PARTIALLY COMPLETE
  * ✅ Temporal decay: deterministic up-ranks for events (Phase 4)
  * [ ] add failing CI test for illegal downstream mutation
  * [ ] restrict to up-rank rules + confidence down-rank only
  * **Reference**: `shopq/temporal_decay.py`, `docs/TESTING_COMPLETE_SUMMARY.md`

* **Freeze model/prompt policy**
  * pin model_name, model_version, prompt_version in logs
  * treat changes as deploys (shadow + replay required)

* **Template-based digest only**
  * enforce template renderer
  * disable LLM narrative formatting

* **Gmail reality tests in CI**
  * add labeling test to CI
  * fail CI if Gmail label not actually applied

* **Add user_id to DB tables for rules/feedback/corrections/fewshot/tracking**
  * add NOT NULL user_id to listed tables; create composite keys (e.g., (user_id, thread_id))
  * backfill existing rows with owner user; write migration script
  * add tenancy guards in every query + unit tests for cross-tenant leakage
  * index (user_id, updated_at) in tracking tables for fast per-user scans

* **Digest QA privacy switches + retention**
  * anonymize/truncate artifacts for non-owner (mask sender/subject; drop bodies)
  * add retention policy (e.g., 14 days) + cleanup job

* **Write rollback conditions**
  * document exact thresholds (OTP in CRITICAL > 0, −5pp critical precision, p95 latency/cost caps, invalid JSON rate)
  * runbook: which flags to flip, how to revert model/prompt versions, and how to re-enable once green

* **Granular OAuth scopes**
  * MVP ships `gmail.readonly` only; `gmail.modify` is opt-in for Smart labels (no `gmail.send`).

* **Transparency UI**
  * Onboarding modal explains scopes and storage; each card has "Why is this here?" (source + reason).

* **Tenancy & retention**
  * Per-user scoping on all tables; add retention for tracking artifacts (e.g., 14 days).

## NEXT (stabilize cohort, prep for a few hundred)

* Ship P5 overrides (thread-level importance/type)
* Add exponential backoff + jitter, add small queue if needed
* LLM extraction back-pressure
* Define SQLite→Postgres flip point (threshold)
* Nightly golden-set replay + drift alarms
* Agent v0: Suggested Next Steps (advice-only) from entities + calendar read

* **Encryption at rest (NEXT)**
  * Enable DB and backup encryption (SQLite SEE or envelope encryption + Fernet for secrets).
  * Secrets management and key rotation plan.

## LATER (scale, canary, agentization)

* P6 canary + auto-rollback (10→50→100%)
* Postgres + worker tier
* Agent v1: follow-ups (suggest bump on silence)
* Agent v2: opt-in write scopes (calendar write / draft emails)
* P7 cleanup & docs
* Agent v3: human-feeling/JARVIS layer on top of deterministic core
  * micro-enrichment (1 sentence rewrite inside cards)
  * digest opening line (contextual top-of-digest sentence)
  * conversational surface for "what should I do next?" queries
