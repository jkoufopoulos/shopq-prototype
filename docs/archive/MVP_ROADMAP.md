# MailQ MVP Roadmap — 95% Accurate, Never Weird

**Goal:** Ship a digest that feels good, is 95% accurate, and won't do anything "very wrong or odd."

**Timeline:** 2 weeks
**Success Criteria:** Critical precision ≥0.95, critical recall ≥0.85, OTP in CRITICAL == 0, event-newsletter noise ≤2%

---

## User-Trust & Permission Model (MVP)

- **Default mode: Read-only.** Onboarding requests only `gmail.readonly`. The digest can run fully in read-only.
- **Optional writes:** If a user enables "Smart labels," we request `gmail.modify` (no send). All writes are reversible.
- **No sending, no drafts (MVP):** MailQ does **not** request `gmail.send`. We won't email anyone on your behalf.
- **Data minimization:** We store message IDs, headers, sender domain, timestamps, and extracted entities — **not** full bodies.
- **Transparency:** Every card shows "Why is this here?" with `{importance, reason, source}`. Overrides apply in one click and can expire.
- **Revocation:** Users can pause syncing anytime and revoke access via Google's "Manage third-party access."

*Goal:* build trust by default, prove value in read-only, and make any writes explicit and reversible.

---

## Completed Milestones

### [DONE 2025-11-10] Phase B0: Type Mapper MVP

**Delivered**: Global deterministic type classifier for calendar events
**Results**:
- Type consistency: 100% calendar match rate (50/50 Google Calendar events)
- False positives: 0.45% (2/444 non-events, both acceptable Resy reservations)
- Performance: <1ms per email
- Cost savings: Zero additional LLM calls for 10% of emails
- Coverage: 10% of gds-1.0 emails (50/500)

**Tests**: 36/36 passing
- Unit tests: 27/27
- Golden dataset regression: 9/9
- Integration tests: 13/15 (2 skipped)

**Reference**: `docs/TYPE_MAPPER_IMPLEMENTATION_SUMMARY.md`

---

### [DONE 2025-11-10] Phase 4: Temporal Decay for Events

**Delivered**: Temporal modulation of importance based on event timing
**Results**:
- Expired events automatically hidden from digest
- Imminent events (±1h) escalated to CRITICAL
- Upcoming events (≤7 days) → COMING UP
- Distant events (>7 days) → WORTH KNOWING
- Grace period (1 hour) handles timezone edge cases

**Tests**: 49/49 passing
- Unit tests: 33/33
- Integration tests: 10/10
- E2E tests: 6/6

**Reference**: `docs/TESTING_COMPLETE_SUMMARY.md`

---

## What to Do Now (Tight, Actionable)

### 1. Lock the Contract & Render Path (No Drift)

**Objective:** Enforce the Pydantic `Classification` contract and produce deterministic digest HTML.

**Tasks:**
- Enforce the Pydantic `Classification` contract (type, importance, optional temporal) and validate at API boundaries
- Render the digest only from a versioned DTO (`digest_dto_v3`) with snapshot tests so the same inputs produce byte-identical HTML
- Wire centralized link builder for all Gmail deep-links

**Acceptance:**
- Contract validation ≥99.5%
- Digest snapshots green
- Use the provided tests in your plan

---

### 2. Ship Bridge Mode (B0) Behind a Shadow Gate

**Status:** ✅ PARTIALLY COMPLETE (Type Mapper phase done, mapper rules pending)

**Objective:** Consume the extension's LLM record and map to importance via rules.

**Completed (2025-11-10):**
- ✅ Type Mapper: Deterministic type classification for calendar events (Phase B0)
- ✅ Integration: Type mapper overrides LLM type predictions
- ✅ Logging: Type mapper matches logged with rule details

**Remaining:**
- [ ] Map extension's LLM output to importance via ≤20 `mapper_rules.yaml` rules
- [ ] Run 3-day shadow against current patterns
- [ ] Log `{llm_mapped vs patterns}` with `model/prompt` pins

**Acceptance:**
- LLM-mapped beats patterns on critical precision without recall collapse
- OTP in CRITICAL == 0
- Event-newsletter noise ≤2%

**Note:** Type Mapper (Phase B0) establishes the foundation for Bridge Mode by providing deterministic type overrides. The importance mapping phase is next.

---

### 3. Move Guardrails to Config with Precedence

**Objective:** Centralize never/force rules and enforce strict precedence.

**Tasks:**
- Create `guardrails.yaml` with:
  - `never_surface` (e.g., OTP/verification codes)
  - `force_critical` (e.g., fraud, phishing, password-reset)
  - `force_non_critical` (e.g., calendar auto-responses, event newsletters)
- Enforce precedence: `never > force_critical > force_non_critical`
- Add table tests for all rules

**Acceptance:**
- Zero behavior drift on golden set
- Precedence tests pass
- CI guard enabled

---

### 4. Make Post-Processing Monotonic (No Surprises)

**Status:** ✅ PARTIALLY COMPLETE (Temporal decay done, mutation guard pending)

**Objective:** Allow only deterministic up-ranks and confidence-based down-ranks.

**Completed (2025-11-10):**
- ✅ Temporal decay: Deterministic up-ranks for events based on timing
  - Imminent events (±1h) → `critical`
  - Upcoming events (≤7 days) → `time_sensitive`
  - Distant events (>7 days) → `routine`
  - Expired events → hidden from digest
- ✅ Tests: 49/49 passing (unit + integration + e2e)

**Remaining:**
- [ ] Implement deadline-based up-ranks (Deadline ≤48h → `time_sensitive`)
- [ ] Implement fraud/phishing up-ranks → `critical`
- [ ] Implement confidence-based down-ranks (confidence < route_threshold → Everything Else)
- [ ] Add CI mutation guard to prevent unauthorized importance changes
- [ ] Forbid any other importance mutation

**Acceptance:**
- Importance distribution stays within ±5pp of baseline
- Mutation guard test passes
- No heuristic "feels urgent" logic

**Note:** Temporal decay (Phase 4) provides deterministic temporal modulation. The remaining tasks focus on deadline/fraud detection and mutation guards.

---

### 5. Freeze the Model/Prompt & Add Rollbacks

**Objective:** Pin model versions and define rollback triggers.

**Tasks:**
- Log `model_name`, `model_version`, `prompt_version` in every classification
- Re-trigger shadow + replay on any model/prompt change
- Define rollback triggers:
  - FP budget exceeded
  - Latency/cost spike
  - Critical precision drop

**Acceptance:**
- Version metadata logged in 100% of classifications
- Rollback runbook documented
- Canary thresholds defined

---

### 6. Instrument a Minimal Overrides Loop (Beta-Safe)

**Objective:** Let users fix mistakes and provide feedback.

**Tasks:**
- Add User Overrides (P5) that apply after LLM/mapper/guardrails and before digest sectioning
- Cap to ≤200 overrides/user with expiry
- Show "Why is this here?" with `{importance, reason, source}`
- Store overrides in `user_overrides` table (thread-level)

**Acceptance:**
- Overrides apply in ≤100ms
- Explainer shown for every card
- Override count enforced per user

---

## Digest UX Rules (Raise Perceived Quality)

### Three Sections (1:1 to Schema)

| Section          | Importance        | Purpose                          |
|------------------|-------------------|----------------------------------|
| **Now**          | `critical`        | Urgent, time-sensitive, actionable |
| **Coming Up**    | `time_sensitive`  | Events, deadlines, reservations   |
| **Everything Else** | `routine`      | FYI, updates, newsletters         |

### Rendering Rules

- **Render from DTO:** Use `card_renderer` + `digest_renderer` only
- **Keep copy deterministic:** No LLM phrasing in templates for MVP
- **Cap oddities:**
  - Limit per-sender card count (e.g., ≤3 cards/sender)
  - Always show `message` + Gmail deep-link
  - Use centralized link builder

---

## Quality Gates for "95% Accurate & Never Weird"

Ship **only** when these hold on golden + rolling traffic:

| Metric                          | Threshold           |
|---------------------------------|---------------------|
| Critical precision              | ≥0.95               |
| Critical recall                 | ≥0.85               |
| OTP in CRITICAL                 | == 0                |
| Event newsletters in Coming Up  | ≤2%                 |
| Invalid-JSON                    | <1% (circuit breaker) |
| P95 latency                     | Within NOW budget   |
| P95 cost/email                  | Within NOW budget   |

---

## Operationalize the Loop (Iterate Safely)

### Nightly Validation

- Run golden-set replay
- Drift alarms (importance distribution ±5pp)
- Fail CI if Gmail labels aren't applied (Gmail reality test)

### Watch Scripts

Use the provided scripts:
- `scripts/watch_digest_quality.sh` — Monitor live digest quality
- `scripts/validate_guardrails.sh` — Test guardrail precedence

---

## Architecture Boundaries (Keep Clean)

### Extension (Frontend)
- Fetch visible message IDs
- Request projection: `{type, importance, temporal}`
- Render digest UI
- **Not** source-of-truth

### Backend (Source-of-Truth)
- Owns schema, guardrails, post-process
- Digest assembly and delivery
- Contract validation

---

## Concrete 2-Week Execution Plan

### Week 1 (Stability & Shadow)

**Days 1-2:**
- Implement `guardrails.yaml` + precedence tests
- Migrate any regexes
- Enable CI mutation guard

**Days 3-4:**
- Finalize `digest_dto_v3`
- Add snapshot tests
- Wire deterministic link builder

**Days 5-7:**
- Turn on Bridge Mode shadow
- Log `{llm_mapped vs patterns}` with model/prompt pins
- Run 3-day shadow comparison

---

### Week 2 (Flip with Brakes)

**Days 8-10:**
- Add monotonic post-process gates
- Implement confidence down-rank
- Test importance distribution stability

**Days 11-12:**
- Ship minimal overrides (thread-level)
- Add "Why is this here?" explainer
- Test override expiry and caps

**Days 13-14:**
- Canary flip: 10% → 50% → 100%
- Monitor rollback thresholds
- Finalize golden-set validation

---

## Beta-Friendly Guardrails (Avoid "Very Wrong or Very Odd")

### Never Elevate to CRITICAL
- Verification codes / OTP
- Calendar auto-responses
- Event newsletters (unless explicit fraud/phishing signal)

### Only Deterministic Time Windows Can Up-Rank
- Deadline ≤48h → `time_sensitive`
- Event ≤7d → `time_sensitive`
- No heuristic "feels urgent" logic

### Keep Copy/Template Static
- No LLM prose in digest body for MVP
- Use deterministic message extraction from DTO

### Safe Default on Low Confidence
- If `confidence < route_threshold` → down-rank to Everything Else

---

## How This Balances Your Tension

| Tension                  | Solution                                                                 |
|--------------------------|--------------------------------------------------------------------------|
| **Consistent experience** | Deterministic DTO + snapshot rendering = digest feels the same day to day |
| **Future-proof**          | Schema + monotonic gates + overrides map cleanly to agent actions later  |
| **MVP feedback**          | B0 shadow + overrides give real-inbox signals and fast fix loop          |

---

## Next Steps

1. Draft `guardrails.yaml` (OTP, calendar auto-responses, fraud, deadline windows)
2. Draft `mapper_rules.yaml` (≤20 rules) matching success criteria
3. Run 3-day shadow and validate against golden set
4. Ship canary with rollback thresholds

---

**Maintenance:** Review this roadmap weekly; update based on observed issues and metrics.
