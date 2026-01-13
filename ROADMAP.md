# ShopQ Product Roadmap

**Vision**: A 100% local, privacy-first Gmail assistant powered by SLMs. No cloud, no servers, no data leaving your device. Ever.

**Last Updated**: 2025-11-30

**North Star**:
> Ship a **local-first**, high-precision Gmail assistant that never feels weird. Your emails stay on your device. The AI runs on your machine. Open source, auditable, trustworthy.

---

## Strategic Reality Check

### Why Local-Only?

**Adoption Blocker Analysis**:
- ❌ **Cloud Mode**: Privacy concerns are a dealbreaker, not a feature request
- ✅ **Local Mode**: Eliminates trust barrier entirely. "Your emails never leave your device" is the product.

**Architecture Decision**:
- **Cloud/Gemini = MVP scaffolding** (validation only, NOT a product mode)
- **Local/SLM = The actual product** (ship this, deprecate cloud after migration)

**Implication**: No dual-mode complexity. Cloud is temporary. Focus 100% on making Local Mode excellent.

---

## Success Metrics

| Metric | Cloud Target | Local Target | Status |
|--------|--------------|--------------|--------|
| Critical Precision | ≥95% | ≥90% (SLM tolerance: -5pp) | ✅ On track |
| Critical Recall | ≥85% | ≥80% (SLM tolerance: -5pp) | ✅ On track |
| OTP in CRITICAL | 0 | 0 | ✅ Guardrails complete |
| Event-newsletter noise | ≤2% | ≤2% | ✅ Type Mapper complete |
| User trust | High | **MAXIMUM** (100% local) | 🟡 Local Mode pending |
| Install time | N/A | ≤10 min | 🔴 Not started |
| Memory footprint | N/A | ≤4GB RAM | 🔴 Not started |

---

## Phase Overview

```
Phase 0: Cloud MVP Validation      → Validate UX, collect Golden Dataset
Phase 0.5: Architecture Cleanup    → Fix issues before SLM migration
Phase 1: SLM Migration             → Replace Gemini with local SLM
Phase 2: Local Daemon              → Package as installable daemon
Phase 2b: Story Engine             → Unified inbox narrative
Phase 3: Private Beta              → 5-10 privacy-conscious users
Phase 4: Public Launch             → HN, GitHub, privacy communities
Phase 5: Gmail Drawer UI           → Live agentic inbox view
```

---

## Phase 0: Cloud MVP Validation (NOW) - 95% Complete

**Goal**: Validate UX + collect data for SLM migration. Nothing more.

**Duration**: 1-2 weeks remaining

**Why Keep Cloud Temporarily**:
1. Faster iteration (Gemini gives instant feedback)
2. Baseline metrics (establish quality bar before SLM)
3. Golden Dataset (collect examples for SLM training)
4. UX validation (ensure digest/sectioning/temporal decay works)

### ✅ COMPLETED (13/14 items)

1. ✅ **Type Mapper MVP** - Deterministic calendar event classification (100% accuracy)
2. ✅ **Centralized Guardrails** - OTP suppression, force_critical/force_non_critical rules
3. ✅ **Temporal Decay** - Event timing, OTP expiry, package delivery scoring (48/48 tests)
4. ✅ **Database Consolidation** - Single SQLite DB, 2,008 rows migrated
5. ✅ **Multi-User Tenancy** - `user_id` column on all tables
6. ✅ **Deterministic Digest Rendering** - Pydantic validation, zero LLM prose
7. ✅ **Golden Dataset v1.0** - 500 emails, 105 tests
8. ✅ **Model/Prompt Versioning** - Central versioning, rollback runbook
9. ✅ **Privacy & Retention** - 14-day retention (Cloud only)
10. ✅ **Database Fixes Deployment** - Connection pool, WAL checkpoints
11. ✅ **Architecture Improvements** - Principles score: 39/50 → 45/50
12. ✅ **Template-Based Digest Cleanup** - V2 pipeline complete, deprecated files removed (-2,397 lines)
13. ✅ **Importance System Consolidation** - ImportanceClassifier deleted, BridgeImportanceMapper simplified to guardrails-only, TYPE_FRIENDLY_NAMES centralized in `shopq/shared/constants.py`

### 🟡 REMAINING (1 item)

#### 1. Classification Accuracy Validation
**Status**: 🟡 Ready to validate | **Effort**: 1-2 days

**Context**: Importance system has been consolidated:
- Gemini now outputs importance directly (T0 classification)
- ImportanceClassifier pattern-based system deleted
- BridgeImportanceMapper simplified to guardrails-only
- TYPE_FRIENDLY_NAMES centralized

**Next Steps**:
- [ ] Run evaluation against GDS to validate accuracy
- [ ] Update GDS if needed based on Gemini importance output
- [ ] Confirm classification accuracy targets met

### Phase 0 Exit Criteria

- [ ] Classification accuracy targets met (type ≥85%, importance ≥80%)
- [x] Template-based digest cleanup complete ✅
- [ ] You use digest daily for ≥2 weeks
- [ ] Golden Dataset expanded to 700-1,000 emails
- [ ] Quality baseline: Precision ≥95%, Recall ≥85%

**If PASS → Phase 0.5 (Architecture Cleanup)**
**If FAIL → Iterate on digest UX before SLM investment**

---

## Phase 0.5: Architecture Cleanup (BEFORE SLM) - ✅ COMPLETE

**Goal**: Fix architecture issues identified in evaluation before SLM migration
**Duration**: 1-2 weeks
**Reference**: [`reports/ARCHITECTURE_EVALUATION_2025-11.md`](reports/ARCHITECTURE_EVALUATION_2025-11.md) (Grade: B+ 85/100 → **A- 90/100**)

### Why Before SLM?

SLM migration will touch `vertex_gemini_classifier.py` and the LLM pipeline. These files have issues that will compound during migration:
1. ~~Hardcoded Vertex AI config blocks easy swapping~~ ✅ Fixed
2. ~~Threshold conflicts will cause debugging headaches~~ ✅ Fixed
3. ~~Missing LLM output validation = silent failures with new model~~ ✅ Fixed

### ✅ High Priority (Completed)

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 1 | **Move Vertex AI config to env vars** | ✅ Done | `VERTEX_AI_PROJECT_ID`, `VERTEX_AI_LOCATION` |
| 2 | **Resolve threshold conflict** | ✅ Done | `config/shopq_policy.yaml` is single source of truth |
| 3 | **Add LLM output validation to all paths** | ✅ Done | Type mapper, rules, and LLM paths validated |

### ✅ Medium Priority (Completed)

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 5 | Audit/remove unused prompt versions | ✅ Done | 10 prompts archived to `prompts/archive/` |
| 6 | Extract hardcoded confidence values from `patterns.py` | ✅ Done | `PATTERN_CONFIDENCE` dict using `DETECTOR_CONFIDENCE` |
| 7 | Add `ClassificationResult` TypedDict | ✅ Done | `ClassificationContract` already provides this |

### ✅ All Issues Resolved

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 4 | **Split `context_digest.py`** | ✅ Done | V2 pipeline already built: `digest_pipeline.py` + `digest_stages_v2.py` (7 modular stages) |
| 8 | **Consolidate T0/T1 documentation** | ✅ Done | 3 docs aligned, 1 archived |

### ❌ Removed (Not Needed)

| # | Issue | Reason |
|---|-------|--------|
| 9 | ~~Merge duplicate temporal systems~~ | **Not duplicates.** `classification/temporal.py` modulates T0 importance; `digest/temporal.py` assigns T1 sections. These are complementary layers by design. |

### Documentation Inconsistencies Found ✅ RESOLVED

Three docs previously had conflicting terminology. Now aligned:
- `docs/features/T0_T1_IMPORTANCE_CLASSIFICATION.md` - ✅ Canonical reference for T0/T1 system
- `docs/architecture/T0_T1_TEMPORAL_ARCHITECTURE.md` - ✅ Updated with correct terminology
- `docs/archive/importance_deciders_DEPRECATED_2025-11.md` - 📦 Archived (referenced deprecated components)

### Exit Criteria ✅ ALL MET

- [x] Vertex AI config externalized (env vars) ✅
- [x] Single threshold source of truth ✅
- [x] LLM outputs validated on all code paths ✅
- [x] No files >1,000 LOC in critical path ✅ (V2 pipeline: `digest_pipeline.py` + `digest_stages_v2.py`)
- [x] T0/T1 docs consolidated (single terminology) ✅
- [x] Architecture score: B+ → A- (target: 90/100) ✅

**Status: Phase 0.5 COMPLETE. Ready for Phase 1 (SLM Migration).**

**If PASS → Phase 1 (SLM Migration)**

---

## Phase 1: SLM Migration (NEXT) - 0% Complete

**Goal**: Replace Gemini with local SLM, maintain quality within tolerance

**Duration**: 4 weeks

### Week 1: SLM Selection & Setup

1. Evaluate 3 SLM candidates:
   - **Phi-3.5-mini** (3.8B) - Strong reasoning
   - **Gemma-2-2B** (2B) - Lightweight, fast
   - **Qwen2.5-3B** (3B) - Strong instruction following
2. Setup Ollama locally
3. Export Golden Dataset benchmark

### Week 2-3: Prompt Engineering & Evaluation

4. Build harness script (`scripts/evaluate_slm.py`)
5. Iterate on prompts (few-shot, chain-of-thought)
6. Log metrics: precision/recall, latency, RAM/CPU
7. Target: ≥90% precision, ≥80% recall, <30s per 50-email batch

### Week 4: Integration & Testing

8. Create `shopq/llm/ollama_client.py`
9. Feature flag: `LLM_BACKEND = "gemini" | "ollama"`
10. Run full pipeline on your inbox (SLM mode)
11. Update Golden Dataset tests for SLM

### Decision Gate (dg_2_slm_feasibility)

- [ ] SLM precision ≥90%, recall ≥80%
- [ ] Latency <30s per 50-email batch
- [ ] Memory ≤4GB RAM
- [ ] You trust the classifications

**If PASS → Phase 2 (Local Daemon)**
**If FAIL → Iterate on prompts/model, or reconsider timing**

---

## Phase 2: Local Daemon (LATER) - 0% Complete

**Goal**: Package SLM + classification pipeline as localhost daemon

**Duration**: 4 weeks

### Architecture

```
┌─────────────────────────────────────┐
│ Chrome Extension                    │
│  • Points to localhost:8080         │
│  • Fetches emails from Gmail API    │
│  • Sends to local daemon            │
│  • Applies labels to Gmail          │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ Local Daemon (Python/FastAPI)       │
│  • HTTP server (localhost:8080)     │
│  • Ollama SLM client                │
│  • Classification pipeline          │
│  • SQLite DB (~/.shopq/shopq.db)    │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ Ollama (local LLM server)           │
│  • localhost:11434                  │
│  • 3-4GB model in RAM               │
└─────────────────────────────────────┘
```

### Tasks

**Week 1-2: Daemon Core**
- Create `shopq_daemon/` package (FastAPI, reuse existing pipeline)
- API endpoints: `/api/classify`, `/api/organize`, `/api/digest`, `/health`
- Launcher script with dependency checks

**Week 3: Extension Integration**
- Update extension to use localhost:8080
- Add daemon health check
- End-to-end flow: Gmail → Extension → Daemon → Labels

**Week 4: Packaging**
- One-liner installer (`curl -sSL https://shopq.ai/install.sh | bash`)
- Dogfood full system for 1 week
- Performance tuning

---

## Phase 2b: Story Engine (LATER) - 0% Complete

**Goal**: Unified semantic representation of inbox for digest + drawer

**Duration**: 3-4 weeks (parallel with Phase 2)

### Story Engine Responsibilities

**Inputs**:
- `last_active_in_gmail_at` (when user last opened Gmail)
- `last_digest_sent_at`
- Classified emails

**Outputs**:
- `story_state.json` with temporal buckets:
  - `happened_while_away`: Critical events user missed
  - `still_relevant`: Time-sensitive items that still matter
  - `coming_up_next`: Future events/deadlines
  - `noise_summary`: Low-priority aggregated

### Tasks

**Week 1-2**: Create `concepts/story_engine.py`, add DB fields
**Week 3**: Refactor digest to consume story_state
**Week 4**: Add "While You Were Away" section, snapshot tests

---

## Phase 3: Private Beta (LATER) - 0% Complete

**Goal**: 5-10 privacy-conscious users validate install + trust

**Duration**: 4 weeks

### Tasks

**Week 1-2: Documentation**
- `LOCAL_MODE_GUIDE.md` - What runs locally, privacy guarantees
- `INSTALL.md` - Prerequisites, one-liner, troubleshooting
- `ARCHITECTURE.md` - System diagram, data flow

**Week 2-3: Beta Cohort**
- Recruit 5-10 users (HN crowd, security researchers, self-hosters)
- 1:1 onboarding calls
- Private support channel

**Week 3-4: Iteration**
- Analyze feedback, fix install friction
- Improve error messages, add FAQ

### Decision Gate (dg_3_beta_viability)

- [ ] ≥5 users install in ≤15 minutes
- [ ] ≥80% say "I trust this"
- [ ] Zero data-loss bugs
- [ ] Daemon stability: <1 crash/week/user

---

## Phase 4: Public Launch (LATER) - 0% Complete

**Goal**: Public launch on HN, privacy-focused communities

**Duration**: 2-3 weeks

### Landing Page

```
┌────────────────────────────────────────────┐
│ ShopQ: Your AI Gmail Assistant             │
│ 100% Local. 100% Private. 100% Yours.      │
├────────────────────────────────────────────┤
│                                            │
│ ✓ Emails never leave your device           │
│ ✓ AI runs on your machine                  │
│ ✓ Open source, auditable                   │
│ ✓ No servers, no tracking, no BS           │
│                                            │
│ [Download for macOS] [View on GitHub]      │
└────────────────────────────────────────────┘
```

### Launch Channels

- **Primary**: Hacker News, Reddit (/r/privacy, /r/selfhosted, /r/locallama)
- **Secondary**: Product Hunt, Indie Hackers, Dev.to

### Success Metrics (Month 1)

- 100+ GitHub stars
- 20-50 active users
- <5% install failure rate
- ≥80% user trust score

---

## Phase 5: Gmail Drawer UI (LATER) - 0% Complete

**Goal**: Persistent drawer showing live inbox story

**Duration**: 4-6 weeks

### Features

1. Inject drawer UI in Gmail DOM (right sidebar)
2. Background polling of `/api/story` (every 5 min)
3. Sections: Jarvis Summary, Critical Items, While You Were Away, Coming Up, Noise Summary
4. Smooth transitions when returning from absence

---

## Timeline Summary

```
┌───────────────────────────────────────────────────────────────┐
│ Phase 0: Cloud MVP Validation (NOW)                           │
│ 🟡 95% complete | 1-2 weeks remaining                         │
├───────────────────────────────────────────────────────────────┤
│ Phase 0.5: Architecture Cleanup                               │
│ ✅ COMPLETE | All exit criteria met                           │
├───────────────────────────────────────────────────────────────┤
│ Phase 1: SLM Migration | 4 weeks                              │
├───────────────────────────────────────────────────────────────┤
│ Phase 2: Local Daemon | 4 weeks                               │
├───────────────────────────────────────────────────────────────┤
│ Phase 2b: Story Engine | 3-4 weeks (parallel)                 │
├───────────────────────────────────────────────────────────────┤
│ Phase 3: Private Beta | 4 weeks                               │
├───────────────────────────────────────────────────────────────┤
│ Phase 4: Public Launch | 2-3 weeks                            │
├───────────────────────────────────────────────────────────────┤
│ Phase 5: Gmail Drawer UI | 4-6 weeks                          │
└───────────────────────────────────────────────────────────────┘

Total: ~22 weeks to public launch
```

---

## Core Principles Compliance

All phases follow the 5 Core Principles from `docs/CORE_PRINCIPLES.md`:

| Principle | Application |
|-----------|-------------|
| **P1: Concepts Are Rooms** | 90% code reuse - same `concepts/` modules for Cloud + Local |
| **P2: Side Effects Are Loud** | Local daemon side effects documented, auditable via logs |
| **P3: Compiler Is Senior Engineer** | Same contracts (ClassificationContract, DigestDTOv3) for both modes |
| **P4: Explicit Contracts** | Extension doesn't know/care if backend is Gemini or SLM |
| **P5: Tuning Not Rewrites** | SLM migration swaps LLM backend only, <10% code changes |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| SLM accuracy worse than Gemini | Keep Cloud as fallback; hybrid mode for ambiguous cases |
| Story Engine drift across modes | Single `story_state.json` contract; snapshot tests |
| Daemon install too complex | Offer to power users first; simplify over time |

---

## Immediate Next Steps

### This Week

1. ✅ **Type Consolidation Complete** - EmailType and EntityType unified
2. ✅ **Importance System Consolidated** - Gemini outputs importance, pattern-based classifier deleted

### Next Steps

3. **Validate classification accuracy** (1 day)
   - Run evaluation against GDS
   - Confirm type ≥85%, importance ≥80%

4. **Dogfood daily for 2 weeks**
5. **Expand Golden Dataset to 700-1,000 emails**

**Target**: Phase 0 complete, ready for Phase 0.5 (Architecture Cleanup)

---

## Maintenance

**Review Cadence**:
- Weekly: Update progress, unblock issues
- After each phase: Review metrics, decision gates
- Monthly: Review SLM landscape, user feedback

**Last Updated**: 2025-11-30

---

**Remember**: Cloud/Gemini is scaffolding. Local/SLM is the product. Validate UX fast, migrate to local, ship to users who care about privacy.
