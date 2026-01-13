# MailQ Refactoring Roadmap

**Last Updated:** 2025-01-13
**Current Principles Score:** 33/50 (66%) - Grade C+
**Target Score:** 48/50 (96%) - Grade A
**Timeline:** 6-8 weeks

---

## Executive Summary

This document consolidates all known refactoring needs across the MailQ codebase, prioritized by impact and aligned with the 5 Core Principles. All issues are categorized as either **Architecture Debt** (requires code restructuring) or **Production Complexity** (requires tuning/configuration).

**Quick Stats:**
- **3 Critical Violations** requiring immediate attention
- **12 Functions** missing side effect documentation
- **4 Modules** fragmented across the codebase
- **13 Files** with no type hints
- **Expected Improvement:** +15 points (33/50 → 48/50) over 6-8 weeks

---

## Table of Contents

1. [Critical Violations (P1 Priority)](#critical-violations-p1-priority)
2. [High Priority Refactoring (P2 Priority)](#high-priority-refactoring-p2-priority)
3. [Medium Priority Improvements (P3 Priority)](#medium-priority-improvements-p3-priority)
4. [Quick Wins (Low Effort, High Impact)](#quick-wins-low-effort-high-impact)
5. [Production Complexity (Tuning, Not Refactoring)](#production-complexity-tuning-not-refactoring)
6. [Migration Progress Tracking](#migration-progress-tracking)
7. [Detailed Implementation Plans](#detailed-implementation-plans)

---

## Critical Violations (P1 Priority)

### 1. Feedback/Learning Fragmentation (P1 Violation)

**Status:** ❌ NOT STARTED
**Category:** Architecture Debt
**Impact:** HIGH - Changes require editing 4 files
**Effort:** 5-7 days
**Score Impact:** +8 points (33/50 → 41/50)

#### Current State

**Concept:** "User corrections improve system through pattern learning"

**Actual Implementation:** Fragmented across 4 modules

| File | Lines | Responsibility | Problem |
|------|-------|----------------|---------|
| `mailq/feedback_manager.py` | 31-196 | Records corrections, triggers learning | Hidden side effect: calls `_learn_from_correction()` |
| `mailq/rules_manager.py` | 34-142 | CRUD operations for rules | No awareness of feedback lifecycle |
| `mailq/rules_engine.py` | 59-341 | Applies rules, learns from classification | Duplicates some feedback logic |
| `mailq/api_feedback.py` | - | HTTP endpoints | Doesn't understand full lifecycle |

#### Impact

**Onboarding Time:** 15+ minutes (vs 15 minutes ideal)
**Change Amplification:** 4 files to modify per feature change
**Testing Complexity:** Must mock 4 modules for end-to-end tests

#### Target State

**Single Module:** `concepts/feedback_learning.py`

```python
class FeedbackLearning:
    """User Feedback → Pattern Learning → Rule Creation → Rule Application

    Single conceptual home for entire feedback lifecycle.

    Side Effects:
        - Writes to corrections table
        - Writes to learned_patterns table
        - Writes to rules table
        - Modifies future classification behavior
    """

    def record_correction(self, ...) -> int:
        """Record user correction. Returns correction_id."""

    def learn_patterns_from_correction(self, correction_id: int) -> None:
        """Learn patterns from correction. Explicit, not hidden."""

    def create_rule_from_pattern(self, pattern: dict) -> int:
        """Create rule from learned pattern. Returns rule_id."""

    def apply_rules_to_email(self, email: dict) -> dict:
        """Apply all learned rules to classify email."""

    def get_feedback_stats(self) -> dict:
        """Get correction and rule statistics."""
```

#### Migration Plan

1. **Week 1, Days 1-2:** Create `concepts/feedback_learning.py` with full API
2. **Week 1, Days 3-4:** Add feature flag `USE_CONSOLIDATED_FEEDBACK`
3. **Week 1, Day 5:** Dual implementation (old + new) with 10% rollout
4. **Week 2, Days 1-3:** Migrate callers to new API
5. **Week 2, Days 4-5:** Increase rollout to 100%, remove old implementation

#### Files to Modify

- ✅ **Create:** `concepts/feedback_learning.py` (~300 lines)
- 🔄 **Refactor:** `mailq/feedback_manager.py` → wrapper over concept
- 🔄 **Refactor:** `mailq/rules_manager.py` → wrapper over concept
- 🔄 **Refactor:** `mailq/rules_engine.py` → move learning logic
- 🔄 **Update:** `mailq/api_feedback.py` → call concept module
- ✅ **Tests:** `tests/unit/test_feedback_learning.py` (~200 lines)

#### Success Metrics

- [ ] Entire feedback feature understandable in 1 file
- [ ] Changes touch 1 module, not 4
- [ ] Testing requires mocking DB only, not 4 modules
- [ ] Onboarding time < 15 minutes

---

### 2. Digest Pipeline Orchestration (P1 Violation)

**Status:** 🔄 IN PROGRESS (V2 built, not deployed)
**Category:** Architecture Debt
**Impact:** HIGH - Cannot understand digest invariants without reading 13 files
**Effort:** 3-5 days (mostly complete, needs deployment)
**Score Impact:** +4 points (already built, needs migration)

#### Current State

**Concept:** "Generate intelligent daily digest from raw emails"

**V1 Implementation (Production):** Imperative orchestration across 13+ modules

| File | Responsibility | Lines |
|------|----------------|-------|
| `mailq/context_digest.py` | Orchestrator - wires 13 dependencies | 509-1200 |
| `mailq/entity_extractor.py` | Stage 1: Entity extraction | ~300 |
| `mailq/importance_classifier.py` | Stage 2: Classification | ~200 |
| `mailq/temporal_enrichment.py` | Stage 3: Temporal decay | ~250 |
| `mailq/digest/categorizer.py` | Stage 4: Categorization | ~150 |
| `mailq/digest/card_renderer.py` | Stage 5: Rendering | ~200 |
| ...and 8 more modules | Various stages | ~400 |

**Problem:** No declarative specification of "what is a digest"

#### Target State (V2 - Already Built!)

**V2 Implementation:** Declarative pipeline in `concepts/` directory

| File | Responsibility | Status |
|------|----------------|--------|
| `concepts/digest_pipeline.py` | Declarative orchestrator with dependency validation | ✅ Built |
| `concepts/digest_stages.py` | 7 stage classes with explicit `depends_on` | ✅ Built |
| `concepts/temporal_extraction.py` | Helper functions | ✅ Built |
| `concepts/section_assignment.py` | Helper functions | ✅ Built |

**Benefits:**
- Explicit pipeline dependencies (`depends_on=["classify"]`)
- Self-documenting stages with "Side Effects:" sections
- 44 tests passing
- Runtime dependency validation

#### Migration Status

**Infrastructure Complete:**
- ✅ Feature flags system (`DIGEST_V2_ROLLOUT_PERCENTAGE`)
- ✅ A/B testing infrastructure (runs both pipelines, compares metrics)
- ✅ V2 pipeline fully tested

**Current Rollout:** 0% (feature flag at 0%)

**Next Steps:**
1. Enable A/B testing mode (`AB_TEST_ENABLED=true`) for 1 week
2. Collect comparison metrics (latency, entity count, quality)
3. Gradual rollout: 10% → 50% → 100%
4. After 2 weeks at 100%, deprecate V1

#### Success Metrics

- [ ] A/B tests show V2 wins >60% of comparisons
- [ ] V2 latency within 200ms of V1
- [ ] V2 entity extraction equal or better than V1
- [ ] Zero production incidents during rollout
- [ ] V1 code removed after 2 weeks at 100%

---

### 3. Importance Classification Fragmentation (P1 Violation)

**Status:** ⚠️ PARTIALLY ADDRESSED
**Category:** Architecture Debt
**Impact:** MEDIUM - Logic distributed across 3 layers
**Effort:** 1-2 days
**Score Impact:** +2 points

#### Current State

**Concept:** "What makes an email important?"

**Files Involved:**

| File | Lines | Responsibility |
|------|-------|----------------|
| `mailq/importance_classifier.py` | ~200 | Pattern-based rules |
| `mailq/bridge/mapper.py` | ~150 | LLM → importance mapping |
| `mailq/bridge/guardrails.py` | ~100 | Override rules |

**Problem:** Cannot answer "what is important" without reading 3 files

#### Target State

**Option 1:** Consolidate into `concepts/importance_resolution.py`
**Option 2:** Rename `mailq/bridge/` → `mailq/importance_mapping/` and merge mapper + guardrails

**Recommendation:** Option 2 (lower risk, 1 day effort)

#### Migration Plan

1. Rename `mailq/bridge/` → `mailq/importance_mapping/`
2. Merge `mapper.py` + `guardrails.py` into `importance_resolver.py`
3. Update imports across codebase
4. Add comprehensive module docstring

#### Files to Modify

- 🔄 **Rename:** `mailq/bridge/` → `mailq/importance_mapping/`
- 🔄 **Merge:** `mapper.py` + `guardrails.py` → `importance_resolver.py`
- 🔄 **Update:** All imports (6 files)
- ✅ **Tests:** No new tests needed (existing tests still valid)

---

## High Priority Refactoring (P2 Priority)

### 4. Hidden Side Effects (P2 Violation)

**Status:** ❌ NOT STARTED
**Category:** Architecture Debt
**Impact:** HIGH - Production surprises, 2-3x debugging time
**Effort:** 2-3 days
**Score Impact:** +5 points (33/50 → 38/50)

#### Critical Examples

##### Example 1: `record_correction()` - Hidden Learning

**File:** `mailq/feedback_manager.py:31-100`

```python
# Current (misleading)
def record_correction(self, email_id: str, ...) -> int:
    """Record a user correction. Returns correction_id."""
    # Hidden: Also learns patterns!
    self._learn_from_correction(...)  # ❌ Not visible in name/docstring
```

**Side Effects:**
- ✅ **Documented:** Writes to `corrections` table
- ❌ **HIDDEN:** Writes to `learned_patterns` table
- ❌ **HIDDEN:** Updates support_count if pattern exists
- ❌ **HIDDEN:** Modifies future classification behavior

**Fix:**

```python
# Option 1: Rename to reveal side effect
def record_and_learn_from_correction(self, email_id: str, ...) -> int:
    """
    Record user correction and learn patterns.

    Side Effects:
        - Writes to corrections table
        - Writes to learned_patterns table (or updates support_count)
        - Modifies future classification behavior via learned rules

    Returns:
        correction_id
    """

# Option 2: Split into explicit steps
def record_correction(self, email_id: str, ...) -> int:
    """Record correction. Returns correction_id."""

def learn_patterns_from_correction(self, correction_id: int) -> None:
    """Learn patterns from correction (explicit call)."""
```

##### Example 2: `classify()` - Hidden Use Count Increment

**File:** `mailq/rules_engine.py:59-101`

```python
# Current (misleading)
def classify(self, subject: str, ...) -> dict:
    """Classify email using learned rules."""
    # Hidden: Updates database!
    with db_transaction() as conn:
        conn.execute("UPDATE rules SET use_count = use_count + 1 WHERE id = ?")
```

**Fix:**

```python
def classify_and_track_usage(self, subject: str, ...) -> dict:
    """
    Classify email using learned rules and track usage.

    Side Effects:
        - Reads from rules table
        - Writes to rules table (increments use_count)

    Returns:
        Classification result
    """
```

#### Functions Missing "Side Effects:" Documentation

**Total:** 15 functions across 4 files

| File | Functions | Side Effects |
|------|-----------|--------------|
| `mailq/feedback_manager.py` | 3 | DB writes, pattern learning |
| `mailq/rules_engine.py` | 4 | DB writes, use count tracking |
| `mailq/rules_manager.py` | 5 | DB CRUD operations |
| `mailq/context_digest.py` | 2 | Global state mutation, debug storage |
| `mailq/observability.py` | 1 | Logging, metrics collection |

#### Implementation Plan

**Week 1:**
1. **Day 1:** Add "Side Effects:" docstrings to all 15 functions
2. **Day 2:** Create deprecation plan for function renames
3. **Day 3:** Add new functions with explicit names (keep old for compatibility)
4. **Day 4:** Update callers to use new functions
5. **Day 5:** Add deprecation warnings to old functions

**Week 2:**
1. **Day 1-2:** Monitor for deprecation warnings in production
2. **Day 3-4:** Remove deprecated functions after 1 week
3. **Day 5:** Verify all side effects documented

#### Success Metrics

- [ ] 100% of functions with side effects have "Side Effects:" section
- [ ] Function names reveal side effects (no surprises)
- [ ] Testing mocks only documented side effects
- [ ] Zero production bugs from hidden side effects

---

### 5. No Pipeline Type Enforcement (P3 Violation)

**Status:** ❌ NOT STARTED
**Category:** Architecture Debt
**Impact:** HIGH - Runtime errors instead of compile-time
**Effort:** 3-5 days
**Score Impact:** +3 points

#### Current State

**Problem:** All pipeline stages return `list[Entity]` but each adds different fields

```python
# Current state - no type safety
entities = extractor.extract(emails)        # Returns list[Entity]
classified = classifier.classify(entities)  # Returns list[Entity] (same type!)
enriched = enricher.enrich(classified)      # Returns list[Entity] (still same!)

# Stage 4 expects resolved_importance but type system doesn't enforce it
categorized = categorizer.categorize(enriched)
# Uses getattr(entity, "resolved_importance", None) - runtime check!
```

**Impact:**
- Pipeline stages fail at runtime if called out of order
- IDE autocomplete doesn't work
- Refactoring is risky (no compile-time safety)

#### Target State

**Typed Pipeline Stages:**

```python
# concepts/pipeline_types.py
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

@dataclass
class ExtractedEntity:
    """Stage 1 output: Entity with source metadata"""
    source_email_id: str
    source_subject: str
    source_snippet: str
    timestamp: datetime
    confidence: float
    type: str

@dataclass
class ClassifiedEntity(ExtractedEntity):
    """Stage 2 output: Entity with importance classification"""
    importance: Literal["critical", "time_sensitive", "routine"]
    classification_reason: str

@dataclass
class EnrichedEntity(ClassifiedEntity):
    """Stage 3 output: Entity with temporal decay applied"""
    resolved_importance: Literal["critical", "time_sensitive", "routine"]
    decay_reason: str
    was_modified: bool
    hide_in_digest: bool

@dataclass
class CategorizedEntity(EnrichedEntity):
    """Stage 4 output: Entity with digest section assigned"""
    digest_section: Literal["critical", "today", "coming_up", "worth_knowing", "skip"]
```

**Updated Stage Signatures:**

```python
class EntityExtractor:
    def extract(self, emails: list[dict]) -> list[ExtractedEntity]: ...

class ImportanceClassifier:
    def classify(self, entities: list[ExtractedEntity]) -> list[ClassifiedEntity]: ...

class TemporalEnricher:
    def enrich(self, entities: list[ClassifiedEntity]) -> list[EnrichedEntity]: ...

class DigestCategorizer:
    def categorize(self, entity: EnrichedEntity) -> CategorizedEntity: ...
```

**Benefits:**
- ✅ Type checker enforces pipeline ordering
- ✅ IDE autocomplete shows available fields
- ✅ Compile-time errors for wrong stage order
- ✅ Self-documenting pipeline

#### Implementation Plan

**Week 1:**
1. Create `concepts/pipeline_types.py`
2. Update `concepts/digest_stages.py` signatures
3. Update tests to use typed entities
4. Run mypy --strict, fix all errors

**Week 2:**
1. Update V1 pipeline to use typed entities
2. Verify all tests pass
3. Deploy with feature flag
4. Monitor for type-related issues

#### Files to Modify

- ✅ **Create:** `concepts/pipeline_types.py`
- 🔄 **Update:** `concepts/digest_stages.py` (7 stage classes)
- 🔄 **Update:** `mailq/entities.py` (deprecate old Entity class)
- 🔄 **Update:** All tests using Entity class
- 🔄 **Update:** `mailq/context_digest.py` (V1 pipeline)

---

### 6. Implicit Pipeline Dependencies (P4 Violation)

**Status:** ✅ COMPLETE IN V2, 🔄 NEEDS DEPLOYMENT
**Category:** Architecture Debt
**Impact:** MEDIUM - Integration bugs at runtime
**Effort:** 0 days (already complete in V2)
**Score Impact:** +2 points (when V2 deployed)

#### Current State (V1)

**Problem:** Pipeline ordering dependencies are implicit

```python
# mailq/context_digest.py:509-1200
def generate(self, emails: list[dict], ...) -> dict:
    # Stage 1: Extract entities
    entities = self.entity_extractor.extract(emails)

    # Stage 2: Classify importance
    classified = self.importance_classifier.classify(entities)

    # Stage 3: Temporal enrichment
    enriched = self.temporal_enricher.enrich_timeline(classified, current_time)

    # Stage 4: Categorize (depends on resolved_importance!)
    for entity in enriched:
        section = self.categorizer.categorize(entity)
```

**Problems:**
- ❌ Ordering dependencies implicit (no `depends_on` declarations)
- ❌ If you reorder stages, no compile-time warning
- ❌ If stage B expects field from stage A, no validation
- ❌ Pipeline structure invisible without reading code

#### Target State (V2 - Already Built!)

```python
# concepts/digest_pipeline.py
@dataclass
class ExpiredEmailFilterStage:
    name: str = "filter_expired"
    depends_on: list[str] = field(default_factory=list)  # No dependencies

@dataclass
class TemporalContextExtractionStage:
    name: str = "extract_temporal_context"
    depends_on: list[str] = field(default_factory=lambda: ["filter_expired"])

@dataclass
class ImportanceClassificationStage:
    name: str = "classify_importance"
    depends_on: list[str] = field(default_factory=lambda: ["extract_temporal_context"])
```

**Benefits:**
- ✅ Dependencies visible at a glance
- ✅ Runtime validation of dependency graph
- ✅ Can generate dependency diagrams automatically
- ✅ Easier to test (mock individual stages)
- ✅ Reordering stages caught by validation

#### Next Steps

**Already complete!** Just needs V2 deployment (see Critical Violation #2)

---

## Quick Wins (Low Effort, High Impact)

### Quick Win #1: Add "Side Effects:" Docstrings

**Status:** ❌ NOT STARTED
**Effort:** 4 hours
**Impact:** +2 points (P2: 4/10 → 6/10)
**Category:** Documentation

#### Scope

**15 functions** across 4 files need "Side Effects:" sections

**Template:**

```python
def function_with_side_effects(self, ...) -> ReturnType:
    """
    Short description of what the function does.

    Args:
        param1: Description
        param2: Description

    Side Effects:
        - Writes to database (table_name)
        - Calls external API (service_name)
        - Modifies global state (variable_name)
        - Logs telemetry events

    Returns:
        Description of return value

    Raises:
        ExceptionType: When this happens
    """
```

#### Files to Update

| File | Functions | Estimated Time |
|------|-----------|----------------|
| `mailq/feedback_manager.py` | 3 | 45 min |
| `mailq/rules_engine.py` | 4 | 1 hour |
| `mailq/rules_manager.py` | 5 | 1 hour |
| `mailq/context_digest.py` | 2 | 30 min |
| `mailq/observability.py` | 1 | 15 min |

**Total:** 4 hours

#### Success Criteria

- [ ] All 15 functions have "Side Effects:" section
- [ ] All database writes documented
- [ ] All API calls documented
- [ ] All state mutations documented

---

### Quick Win #2: Rename Ambiguous Modules

**Status:** ❌ NOT STARTED
**Effort:** 2 hours
**Impact:** +1 point (P1: 5/10 → 6/10)
**Category:** Code Organization

#### Changes

| Current Path | New Path | Reason |
|--------------|----------|--------|
| `mailq/bridge/` | `mailq/importance_mapping/` | "bridge" is too generic |
| `mailq/bridge/shadow_logger.py` | `mailq/decision_audit_logger.py` | "shadow" is unclear |

#### Implementation

1. Rename directories (git mv)
2. Update imports (6 files)
3. Update references in documentation
4. Run all tests

**Estimated Time:** 2 hours

---

### Quick Win #3: Add Module Docstrings

**Status:** ❌ NOT STARTED
**Effort:** 2 hours
**Impact:** +1 point (P1: 5/10 → 6/10)
**Category:** Documentation

#### Scope

**20 modules** missing comprehensive docstrings

**Template:**

```python
"""
Module: mailq/feedback_manager.py

Purpose: Records user corrections and learns patterns

What it does:
    - Stores user corrections in database
    - Triggers pattern learning from corrections
    - Provides correction statistics and analytics

How it works:
    - User submits correction via API
    - Correction stored in corrections table
    - Pattern learning triggered automatically
    - New rules created from patterns

Side Effects:
    - Writes to corrections table
    - Writes to learned_patterns table
    - May create new rules

Dependencies:
    - mailq.config.database (database access)
    - mailq.rules_engine (rule creation)
"""
```

#### Files to Update

- `mailq/feedback_manager.py`
- `mailq/rules_engine.py`
- `mailq/rules_manager.py`
- `mailq/importance_classifier.py`
- `mailq/entity_extractor.py`
- `mailq/temporal_enrichment.py`
- `mailq/digest/categorizer.py`
- `mailq/digest/card_renderer.py`
- ...and 12 more modules

**Estimated Time:** 2 hours (6 minutes per module)

---

### Quick Win #4: Extract PII Redaction to Central Module

**Status:** ❌ NOT STARTED
**Effort:** 1 hour
**Impact:** +0 points (code quality, not principles)
**Category:** Production Complexity (Tuning)

#### Current State

**Problem:** PII redaction logic duplicated in 2 places

| File | Lines | Logic |
|------|-------|-------|
| `mailq/logging_utils.py` | ~50 | Email/subject redaction for logs |
| `adapters/llm/client.py` | ~30 | Email/subject redaction for LLM calls |

#### Target State

**Single Module:** `infra/pii.py`

```python
"""PII Redaction Utilities

Centralized PII redaction for emails, subjects, and sensitive data.
"""

def redact_email(email: str) -> str:
    """Redact email address (show domain only)."""
    # user@example.com → ***@example.com

def redact_subject(subject: str) -> str:
    """Redact email subject (show first 20 chars only)."""

def redact_snippet(snippet: str) -> str:
    """Redact email snippet (show first 50 chars only)."""
```

#### Files to Modify

- ✅ **Create:** `infra/pii.py`
- 🔄 **Update:** `mailq/logging_utils.py` (use infra/pii)
- 🔄 **Update:** `adapters/llm/client.py` (use infra/pii)
- ✅ **Tests:** `tests/unit/test_pii.py`

---

## Production Complexity (Tuning, Not Refactoring)

These are NOT architecture debt - they can be fixed with configuration/tuning:

### 1. Missing Database Indexes

**Status:** ⚠️ PARTIALLY ADDRESSED
**Category:** Production Complexity
**Effort:** 1 day
**Impact:** Query performance

#### Missing Indexes

| Table | Column | Query Pattern | Impact |
|-------|--------|---------------|--------|
| `corrections` | `user_id` | Lookup by user | Slow user stats |
| `corrections` | `created_at` | Recent corrections | Slow analytics |
| `learned_patterns` | `support_count` | Top patterns | Slow pattern ranking |
| `rules` | `use_count` | Most used rules | Slow rule analytics |

#### Implementation

```sql
CREATE INDEX idx_corrections_user_id ON corrections(user_id);
CREATE INDEX idx_corrections_created_at ON corrections(created_at);
CREATE INDEX idx_learned_patterns_support ON learned_patterns(support_count DESC);
CREATE INDEX idx_rules_use_count ON rules(use_count DESC);
```

**Estimated Time:** 4 hours (testing + validation)

---

### 2. In-Memory Cache Limiting Scale

**Status:** ⚠️ ACCEPTABLE FOR NOW
**Category:** Production Complexity
**Effort:** 2 days (when needed)
**Impact:** Scale beyond 10K users

#### Current State

- LRU cache in `mailq/llm_client.py`
- Singleton pattern limits to single process
- No cache invalidation across instances

#### Future State (when needed)

- Redis cache with TTL
- Cross-instance cache sharing
- Cache invalidation events

**Note:** Not needed until 10K+ users. Current in-memory cache is acceptable.

---

### 3. Connection Pool Size Tuning

**Status:** ✅ COMPLETE
**Category:** Production Complexity
**Effort:** 1 day (already done)

Connection pooling already implemented in `mailq/config/database.py`

---

## Migration Progress Tracking

### V1 to V2 Digest Pipeline Migration

| Stage | Status | Rollout % | Notes |
|-------|--------|-----------|-------|
| Build V2 Pipeline | ✅ Complete | - | 44 tests passing |
| Feature Flags System | ✅ Complete | 0% | Ready to enable |
| A/B Testing Infrastructure | ✅ Complete | - | Ready to use |
| Enable A/B Testing | ⏳ Planned | - | Week 1 |
| Analyze A/B Results | ⏳ Planned | - | Week 2 |
| Gradual Rollout (10%) | ⏳ Planned | 10% | Week 3 |
| Gradual Rollout (50%) | ⏳ Planned | 50% | Week 4 |
| Full Rollout (100%) | ⏳ Planned | 100% | Week 5 |
| Deprecate V1 | ⏳ Planned | - | Week 7 |
| Remove V1 Code | ⏳ Planned | - | Week 8 |

### Principles Score Progress

| Week | Completed Work | Expected Score | Grade |
|------|----------------|----------------|-------|
| **Baseline** | - | 33/50 (66%) | C+ |
| Week 1 | Quick Wins (#1-3) | 37/50 (74%) | C+ |
| Week 2-3 | Hidden Side Effects (#4) | 38/50 (76%) | C+ |
| Week 4-5 | Feedback Consolidation (#1) | 41/50 (82%) | B |
| Week 6-7 | Pipeline Type Safety (#5) | 44/50 (88%) | B+ |
| Week 8 | V2 Deployment (#2) | 48/50 (96%) | A |

---

## Detailed Implementation Plans

### Week 1: Quick Wins

**Goal:** +4 points (33/50 → 37/50)

#### Monday
- [ ] Add "Side Effects:" docstrings (15 functions, 4 hours)
- [ ] Create PR for review

#### Tuesday
- [ ] Rename ambiguous modules (2 hours)
- [ ] Update imports and documentation
- [ ] Run all tests

#### Wednesday
- [ ] Add module docstrings (20 modules, 2 hours)
- [ ] Create PR for review

#### Thursday
- [ ] Extract PII redaction to central module (1 hour)
- [ ] Add tests for PII module
- [ ] Create PR for review

#### Friday
- [ ] Review and merge all PRs
- [ ] Verify all tests pass
- [ ] Update ROADMAP.md with progress

**Deliverables:**
- 15 functions with "Side Effects:" documentation
- 20 modules with comprehensive docstrings
- Clearer module naming
- Centralized PII redaction

---

### Week 2-3: Hidden Side Effects

**Goal:** +5 points (37/50 → 42/50, includes feedback consolidation start)

#### Week 2, Monday-Tuesday
- [ ] Create new function signatures with explicit names
- [ ] Add deprecation warnings to old functions
- [ ] Update documentation

#### Week 2, Wednesday-Friday
- [ ] Update all callers to use new functions
- [ ] Monitor deprecation warnings in logs
- [ ] Verify no production issues

#### Week 3, Monday-Wednesday
- [ ] Start `concepts/feedback_learning.py` implementation
- [ ] Add feature flag `USE_CONSOLIDATED_FEEDBACK`
- [ ] Write comprehensive tests

#### Week 3, Thursday-Friday
- [ ] Enable dual implementation (old + new)
- [ ] 10% rollout with feature flag
- [ ] Monitor for issues

**Deliverables:**
- All functions with explicit side effect names
- 100% side effect documentation
- Feedback consolidation started

---

### Week 4-5: Feedback Consolidation

**Goal:** +8 points total (33/50 → 41/50)

#### Week 4, Monday-Tuesday
- [ ] Complete `concepts/feedback_learning.py`
- [ ] Migrate callers to new API
- [ ] Comprehensive integration tests

#### Week 4, Wednesday-Friday
- [ ] Increase rollout to 50%
- [ ] Monitor metrics (latency, correctness)
- [ ] Fix any issues found

#### Week 5, Monday-Wednesday
- [ ] Increase rollout to 100%
- [ ] Monitor for 48 hours
- [ ] Verify all metrics stable

#### Week 5, Thursday-Friday
- [ ] Remove old implementation
- [ ] Clean up deprecated code
- [ ] Update documentation

**Deliverables:**
- Feedback concept consolidated into 1 file
- 100% rollout complete
- Old code removed
- Onboarding time < 15 minutes

---

### Week 6-7: Pipeline Type Safety

**Goal:** +3 points (41/50 → 44/50)

#### Week 6, Monday-Tuesday
- [ ] Create `concepts/pipeline_types.py`
- [ ] Define typed entity classes
- [ ] Update V2 pipeline signatures

#### Week 6, Wednesday-Friday
- [ ] Update all stage signatures
- [ ] Fix mypy errors
- [ ] Update tests to use typed entities

#### Week 7, Monday-Wednesday
- [ ] Update V1 pipeline to use typed entities
- [ ] Run comprehensive test suite
- [ ] Verify type safety works

#### Week 7, Thursday-Friday
- [ ] Deploy with feature flag
- [ ] Monitor for type-related issues
- [ ] Document type hierarchy

**Deliverables:**
- Typed pipeline stages
- Compile-time type checking
- IDE autocomplete works
- Zero AttributeErrors from missing fields

---

### Week 8: V2 Deployment & Cleanup

**Goal:** +4 points (44/50 → 48/50)

#### Monday-Tuesday
- [ ] V2 at 100% rollout for 2 weeks
- [ ] Verify all metrics stable
- [ ] Zero production incidents

#### Wednesday-Thursday
- [ ] Mark `mailq/context_digest.py` as deprecated
- [ ] Update all documentation to reference V2
- [ ] Create migration guide for external users

#### Friday
- [ ] Remove V1 code after 2 weeks at 100%
- [ ] Clean up old imports
- [ ] Final principles assessment
- [ ] Celebrate reaching Grade A! 🎉

**Deliverables:**
- V1 code removed
- Documentation updated
- Principles score: 48/50 (96%) - Grade A
- Comprehensive migration complete

---

## Success Criteria

### Overall

- [ ] Principles score: 48/50 (96%) - Grade A
- [ ] All critical violations resolved
- [ ] All quick wins implemented
- [ ] V2 pipeline deployed to production
- [ ] Zero regression bugs from refactoring

### P1: Concepts Are Rooms (Target: 9/10)

- [ ] Feedback concept consolidated into 1 file
- [ ] Digest concept in declarative pipeline (V2)
- [ ] Importance mapping in clear module structure
- [ ] Onboarding time < 30 minutes per feature

### P2: Side Effects Are Loud (Target: 9/10)

- [ ] 100% of functions with side effects documented
- [ ] Function names reveal side effects
- [ ] No hidden database writes
- [ ] No hidden state mutations

### P3: Compiler Is Senior Engineer (Target: 9/10)

- [ ] Typed pipeline stages
- [ ] mypy --strict passes on all core modules
- [ ] IDE autocomplete works
- [ ] Compile-time errors for wrong stage order

### P4: Synchronizations Are Explicit (Target: 9/10)

- [ ] Pipeline dependencies declared (`depends_on`)
- [ ] Runtime validation of dependencies
- [ ] Can generate dependency diagrams
- [ ] No implicit state contracts

### P5: Debt vs Complexity (Target: 10/10)

- [ ] All issues correctly categorized
- [ ] Architecture debt register maintained
- [ ] Quarterly architecture reviews scheduled
- [ ] Team alignment on debt vs complexity

---

## Risk Mitigation

### Risk 1: Breaking Changes During Refactoring

**Mitigation:**
- Feature flags for all major changes
- Dual implementations during migration
- Comprehensive test coverage
- Gradual rollout (10% → 50% → 100%)
- Instant rollback capability

### Risk 2: Timeline Slippage

**Mitigation:**
- Quick wins first (build momentum)
- Weekly progress reviews
- Defer low-priority items if needed
- Focus on high-impact changes

### Risk 3: Production Incidents

**Mitigation:**
- A/B testing before full rollout
- Monitor all key metrics
- Alert on latency/error rate changes
- Keep old code until 100% confident

---

## Notes

**Last Updated:** 2025-01-13
**Next Review:** 2025-01-20 (weekly)
**Owner:** Development Team
**Status:** In Progress

**Questions or Issues?**
Create a GitHub issue with label `refactoring` or `principles-compliance`
