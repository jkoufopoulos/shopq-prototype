# ShopQ Architecture Evaluation Report

**Date:** November 2025
**Scope:** Full codebase review against documented architecture and Core Principles
**Overall Grade:** B+ (85/100) → **A- (90/100)** after Phase 0.5 fixes

---

## Executive Summary

The ShopQ codebase demonstrates **solid architectural discipline** with excellent infrastructure (database, configuration, error handling) and good separation of concerns. The 4-tier classification system is properly implemented, and the single-database policy is exemplary. Main weaknesses are in **orchestrator complexity** (large files) and **features spread across too many files**.

### Quick Assessment

| Area | Grade | Notes |
|------|-------|-------|
| Database Policy | A | Single DB enforced, connection pooling, pre-commit hooks |
| Classification Pipeline | A- | 4-tier system working; orchestration slightly scattered |
| Error Handling | A | Circuit breakers, fallbacks, graceful degradation |
| Test Coverage | A- | 83 test files; comprehensive unit/integration/e2e |
| Configuration | A- | Centralized in YAML, threshold conflict resolved ✅ |
| Code Organization | B | Some god objects; features span too many files |
| Type Safety | B+ | LLM outputs now validated on all paths ✅ |

---

## 1. Code Organization

### Documented vs. Actual Structure

**Documented (CLAUDE.md):** 7 modules
**Actual:** 14 modules (deliberate expansion)

```
shopq/
├── api/               FastAPI endpoints
├── classification/    Email categorization (21 files, ~5,900 LOC)
├── concepts/          Feedback, preferences, A/B testing
├── contracts/         Type definitions
├── data/              SQLite database
├── digest/            Digest generation (19 files, ~6,500 LOC)
├── gmail/             Gmail API & OAuth
├── infrastructure/    Database, auth, settings
├── llm/               Prompts & LLM abstraction
├── observability/     Logging, telemetry, confidence
├── runtime/           Feature flags, gates, thresholds
├── shared/            Pipeline orchestration
├── storage/           Database access layer
└── utils/             Email, versioning, redaction utilities
```

**Assessment:** The additional modules (infrastructure, observability, runtime, concepts, contracts) represent thoughtful decomposition that improves modularity. This exceeds documentation but is a positive evolution.

### P1 Compliance: Concepts Are Rooms, Not Hallways

**Violations Found:**

1. **Digest pipeline scattered across 6 files:**
   - `context_digest.py` (1,523 LOC) - orchestrator
   - `digest_stages_v2.py` (898 LOC) - stage definitions
   - `card_renderer.py` (918 LOC) - rendering
   - `temporal.py` (751 LOC) - temporal decay
   - `support.py` (614 LOC) - helpers
   - `categorizer.py` (439 LOC) - categorization

2. **Classification orchestration across 3 files:**
   - `memory_classifier.py` (283 LOC)
   - `vertex_gemini_classifier.py` (884 LOC)
   - `rules_engine.py` (393 LOC)

**Impact:** Understanding core features requires reading 3-6 files instead of 1-2.

---

## 2. Classification Pipeline

### 4-Tier Architecture Implementation

The documented 4-tier system is **fully implemented**:

```
T0 (Free)     → Type Mapper (type_mapper.py, ~255 LOC)
                Config-driven from type_mapper_rules.yaml
                   ↓
T0 (Free)     → Rules Engine (rules_engine.py, ~393 LOC)
                User-learned patterns from SQLite
                   ↓
T3 (~$0.0001) → Gemini Classifier (vertex_gemini_classifier.py)
                Prompts from shopq/llm/prompts/
                   ↓
T3 (~$0.0001) → Verifier (selective 2nd pass)
```

**Strengths:**
- Type Mapper: Singleton pattern, config-driven, 95%+ precision
- Rules Engine: Centralized DB, retry decorator for lock contention
- LLM Classifier: External prompts, circuit breaker, input sanitization
- Orchestration: Clear 6-step flow in `memory_classifier.py`

**Issues:**
- ~~Vertex AI project ID hardcoded~~ ✅ Fixed in Phase 0.5

---

## 3. Principle Compliance

### P2: Side Effects Are Loud

**Status: GOOD**

Well-marked examples:
```python
RulesEngine.classify()           # "Side Effects: - Increments use_count..."
FeedbackManager.record_correction()  # "Side Effects: - Writes to corrections table"
```

Database transactions use clear context managers:
```python
with db_transaction() as conn:   # Clear write intent
with get_db_connection() as conn:  # Clear read intent
```

**Gap:** Module-level initialization side effects not documented (e.g., `validate_thresholds()` called on import in `confidence.py`).

### P3: Compiler Is Your Senior Engineer

**Status: GOOD (with gaps)**

- 37 files import `Any` type (32% of 113 files) - moderate usage
- 14 functions use `: Any` parameters/returns - acceptable

**Gaps:**
1. `user_prefs: dict[str, Any]` should be typed dataclass
2. ~~LLM outputs are untyped dicts~~ ✅ ClassificationContract validates all outputs
3. ~~No schema validation for all LLM outputs~~ ✅ Fixed in Phase 0.5

### P4: Synchronizations Are Explicit

**Status: GOOD**

- DB transactions explicit
- Pipeline stages have clear ordering in `memory_classifier.py`
- No circular dependencies detected

### P5: Production Complexity Is Tuning

**Status: GOOD**

Present:
- Connection pooling (`DatabaseConnectionPool`)
- Circuit breakers (`InvalidJSONCircuitBreaker`)
- Graceful degradation (fallbacks in digest pipeline)
- Rate limiting infrastructure

---

## 4. Issues Found

### High Priority

#### Issue #1: Hardcoded Vertex AI Configuration ✅ FIXED

**Location:** `shopq/classification/vertex_gemini_classifier.py:114-115`

```python
# Now uses environment variables with defaults
project_id = os.getenv("VERTEX_AI_PROJECT_ID", "mailq-467118")
location = os.getenv("VERTEX_AI_LOCATION", "us-central1")
```

**Status:** Fixed in Phase 0.5. `.env.example` updated with new variables.

#### Issue #2: Threshold Value Conflict ✅ FIXED

**Resolution:**
- `config/shopq_policy.yaml` is now single source of truth
- `shopq/observability/confidence.py` loads values from YAML
- All thresholds unified at 0.70 (verify-first strategy)

**Status:** Fixed in Phase 0.5. YAML is canonical.

#### Issue #3: God Object - context_digest.py (1,523 LOC)

**Location:** `shopq/digest/context_digest.py`

Orchestrates: extraction, classification, enrichment, synthesis, verification, rendering

**Risk:** Hard to test, maintain, and understand.
**Fix:** Split into per-stage classes with clear interfaces.

**Status:** Pending (1-2 day refactor, separate PR recommended)

#### Issue #4: Incomplete LLM Output Validation ✅ FIXED

**Location:** `shopq/classification/memory_classifier.py`

Validation now called on all paths:
- Line 76: Type mapper path
- Line 100: Rules path
- Line 118: LLM path (already existed)

**Status:** Fixed in Phase 0.5.

### Medium Priority

#### Issue #5: Stale Prompt File Versions ✅ FIXED

**Location:** `shopq/llm/prompts/`

**Resolution:** Archived 10 unused prompt files to `prompts/archive/`:
- `narrative_prompt_v1_original.txt` → archive
- `narrative_prompt_v2_grouped.txt` → archive
- `classifier_prompt_improved.txt` → archive
- (and 7 more)

**Status:** Fixed in Phase 0.5. Only 3 active prompts remain.

#### Issue #6: Hardcoded Confidence in patterns.py ✅ FIXED

**Location:** `shopq/classification/patterns.py`

```python
# Now references centralized config
from shopq.observability.confidence import DETECTOR_CONFIDENCE
PATTERN_CONFIDENCE = {
    "otp": DETECTOR_CONFIDENCE["otp"]["type_conf"],
    "receipt": DETECTOR_CONFIDENCE["receipt"]["type_conf"],
    ...
}
```

**Status:** Fixed in Phase 0.5.

### Low Priority

#### Issue #7: Inconsistent Logging Levels

Some failures log as `info()`, others as `warning()`. No consistent severity pattern.

#### Issue #8: Stale Comments

References to deprecated databases in comments:
- `tracking.py`: "Old database (data/shopq_tracking.db) is deprecated"
- `formatting.py`: mentions "digest_rules.db"

---

## 5. Strengths

### Database Policy (Exemplary)

- Single database: `shopq/data/shopq.db`
- Connection pooling with `DatabaseConnectionPool`
- Pre-commit hooks block new `.db` files
- All code uses `get_db_connection()` from centralized location
- WAL mode for concurrent reads
- Foreign keys enabled

### Error Handling (Robust)

```python
# Circuit breaker for LLM failures
self.circuit_breaker = InvalidJSONCircuitBreaker()

# Graceful degradation in digest
if not validate_classification_result(semantic_result):
    logger.warning("Schema validation failed, using fallback")
    semantic_result = self._fallback_semantic(from_field)
```

### Test Coverage (Comprehensive)

```
tests/
├── unit/        30+ files
├── integration/ 34+ files
├── e2e/         14+ files
├── manual/      11+ files
├── evals/       GDS evaluation scripts
└── snapshots/   Digest golden samples
```

Key areas covered: rules engine, mapper, deduplication, digest pipeline, retention, circuit breaker, connection pool.

### Prompt Externalization (Correct)

- 3 active prompt files in `shopq/llm/prompts/` (10 archived in Phase 0.5)
- PromptLoader pattern with caching
- Not hardcoded in Python

---

## 6. Recommendations

### Phase 0.5 Completed ✅

| # | Action | Status | Notes |
|---|--------|--------|-------|
| 1 | Move Vertex AI config to env vars | ✅ Done | `VERTEX_AI_PROJECT_ID`, `VERTEX_AI_LOCATION` |
| 2 | Resolve threshold conflict | ✅ Done | YAML is single source of truth |
| 3 | Add LLM output validation to all paths | ✅ Done | 3 paths now validated |
| 5 | Audit and remove unused prompt versions | ✅ Done | 10 files archived |
| 6 | Extract hardcoded confidence values | ✅ Done | `PATTERN_CONFIDENCE` dict |
| 7 | Add `ClassificationResult` TypedDict | ✅ Done | ClassificationContract used |

### Remaining (Separate PR)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 4 | Split `context_digest.py` into stages | 1-2 days | Improves maintainability |
| 8 | Consolidate classification orchestration | 1 day | Improves P1 compliance |

---

## 7. Conclusion

ShopQ's architecture is **production-ready** with strong fundamentals:

- **What works:** Database discipline, 4-tier classification, error handling, test coverage
- **What needs work:** Large orchestrator files (`context_digest.py`), scattered features

**Phase 0.5 Progress:** Resolved 6/7 high and medium priority issues. Configuration is now centralized in YAML, LLM outputs validated on all paths, and unused prompts archived.

The main remaining risk is **complexity growth** in `context_digest.py` (1,523 LOC). Address this before SLM migration.

### Next Review

Schedule architecture review after:
- Any file exceeds 800 LOC
- New major feature (multi-tenancy, new LLM provider)
- 3 months elapsed

---

## Appendix: File Size Analysis

Files exceeding 500 LOC (potential complexity):

| File | LOC | Assessment |
|------|-----|------------|
| `digest/context_digest.py` | 1,523 | **Split required** |
| `api/app.py` | 1,445 | Expected for FastAPI app |
| `digest/card_renderer.py` | 918 | Could split by card type |
| `digest/digest_stages_v2.py` | 898 | Should be separate stage files |
| `classification/vertex_gemini_classifier.py` | 884 | Mixing concerns |
| `infrastructure/database.py` | 764 | Core infrastructure, acceptable |
| `digest/temporal.py` | 751 | Core feature, acceptable |
| `observability/tracking.py` | 739 | Core feature, acceptable |
| `classification/extractor.py` | 740 | Core feature, acceptable |
| `classification/importance_classifier.py` | 673 | Core feature, acceptable |

---

## Comparison to Previous Audit

| Metric | Jan 2025 (ARCHITECTURE_AUDIT.md) | Nov 2025 (This Report) |
|--------|----------------------------------|------------------------|
| Overall Score | 78/100 (B+) | 85/100 (B+) |
| Database Policy | Good | Excellent (improved) |
| Test Coverage | ~60 files | 83 files (improved) |
| God Objects | Multiple identified | `context_digest.py` main concern |
| Circular Deps | None | None |

**Progress:** Architecture has improved since January 2025 audit. Database consolidation complete. Test coverage expanded. Main remaining concern is digest orchestrator complexity.
