# Agent B: Quick Wins & Infrastructure (Week 1-2)

> **⚠️ HISTORICAL DOCUMENT**: This was guidance for parallel Agent A/B work during an earlier refactoring phase. Many referenced files have since been moved during the Nov 2025 restructuring (15→7 directories). The `concepts/` folder referenced here was never created. Preserved for historical context.

**Role**: You are Agent B working in parallel with Agent A on the ShopQ codebase.

**Context**: Agent A is doing a major digest pipeline refactor (6-8 weeks). You will work on quick wins that improve code quality without conflicting with Agent A's work.

**Timeline**: Week 1-2 (then reassess)

---

## 🚨 CRITICAL: Do NOT Touch These Files/Folders

Agent A is refactoring the digest pipeline. **NEVER edit these**:

### Off-Limits Files
- `concepts/` (entire folder - Agent A is creating this)
- `context_digest.py` (being refactored)
- `digest/` (entire folder - being refactored)
- `entity_extractor.py` (being refactored)
- `temporal_enrichment.py` (being refactored)
- `temporal_decay.py` (being refactored)
- `hybrid_digest_renderer.py` (being refactored)
- `digest_categorizer.py` (being refactored)

### Off-Limits Modules (Read-only, no edits)
- `entities.py` (Agent A may modify)
- `importance_mapping/` (Agent A depends on this - coordinate before changes)
- `pipeline_wrapper.py` (Agent A depends on this)

**If you need to touch any of these files, STOP and ask the user first.**

---

## Your Mission: Quick Wins from Principles Assessment

**Goal**: Reduce technical debt by adding type hints, documenting side effects, and adding validation.

**Target**: Get these modules to mypy strict mode compliance.

**Success Criteria**:
- ✅ Mypy strict mode passes for assigned files
- ✅ All functions have complete type hints
- ✅ Side effects documented in docstrings
- ✅ Input validation added where missing
- ✅ No regressions (all tests pass)

---

## Task 1: Add Type Hints (Priority 1)

### Files to Type-Annotate

#### 1.1: `shopq/observability.py`
**Current state**: ~50% type coverage, 213 mypy errors in codebase
**Your job**:
- Add type hints to all functions
- Add return type annotations
- Use `typing` module for complex types (Dict, List, Optional, Union)
- Make it pass `mypy --strict observability.py`

**Example**:
```python
# Before
def log_importance(thread_id, subject, importance, reason):
    ...

# After
def log_importance(
    thread_id: str,
    subject: str,
    importance: str,
    reason: str
) -> None:
    """
    Log importance classification for observability.

    Side Effects:
        - Writes to log file
        - May send metrics to monitoring system
    """
    ...
```

#### 1.2: `shopq/email_tracker.py`
**Your job**: Same as above - full type annotation

#### 1.3: `shopq/filters.py`
**Your job**:
- Add type hints ONLY
- **DO NOT refactor logic** (Agent A may use these filters)
- Focus on function signatures and return types

#### 1.4: `adapters/storage/checkpoint.py`
**Your job**: Full type annotation

#### 1.5: `infra/telemetry.py`
**Your job**: Full type annotation

### Type Annotation Standards

Use these patterns:

```python
from typing import Dict, List, Optional, Union, Tuple, Any
from datetime import datetime
from dataclasses import dataclass

# Function signatures
def process_email(
    email: Dict[str, Any],
    now: datetime,
    user_id: Optional[str] = None
) -> Tuple[bool, str]:
    """Process email and return success status + message"""
    ...

# Class attributes
@dataclass
class EmailMetadata:
    thread_id: str
    subject: str
    timestamp: datetime
    tags: List[str]
    metadata: Dict[str, Any]
```

---

## Task 2: Document Side Effects (Priority 1)

**Goal**: Make it obvious when functions modify state (P2: Side Effects Are Loud)

### Pattern to Follow

For ANY function that modifies state, add a "Side Effects:" section to the docstring:

```python
def record_classification(
    email_id: str,
    classification: str,
    confidence: float
) -> None:
    """
    Record classification result for an email.

    Args:
        email_id: Unique identifier for email
        classification: Classification label
        confidence: Confidence score (0-1)

    Side Effects:
        - Writes to database (classifications table)
        - Updates email_tracker state
        - May trigger learning pipeline (if confidence < 0.7)
        - Logs to observability system

    Raises:
        DatabaseError: If database write fails
    """
    ...
```

### Files to Document

Add "Side Effects:" sections to functions in:
- `shopq/observability.py` (writes logs, sends metrics)
- `shopq/email_tracker.py` (writes to database, updates state)
- `shopq/storage.py` (database writes)
- `adapters/storage/checkpoint.py` (file writes)
- `infra/telemetry.py` (network calls, metrics)

### Functions to Flag

Look for functions with these patterns (they likely have side effects):
- `record_*()` (e.g., `record_classification`)
- `save_*()` (e.g., `save_checkpoint`)
- `update_*()` (e.g., `update_tracker`)
- `log_*()` (e.g., `log_event`)
- `send_*()` (e.g., `send_metric`)
- `write_*()` (e.g., `write_to_db`)

---

## Task 3: Add Input Validation (Priority 2)

**Goal**: Catch invalid inputs at API boundaries

### Files to Add Validation

#### 3.1: `shopq/api.py`
Add Pydantic validation to request models:

```python
from pydantic import BaseModel, Field, validator

class SummaryRequest(BaseModel):
    emails: List[Dict[str, Any]] = Field(..., min_items=1, max_items=1000)
    timezone: Optional[str] = Field(None, pattern=r"^[A-Za-z_]+/[A-Za-z_]+$")
    client_now: Optional[str] = None

    @validator("emails")
    def validate_emails(cls, v):
        """Validate email structure"""
        for email in v:
            if "id" not in email:
                raise ValueError("Email must have 'id' field")
            if "subject" not in email:
                raise ValueError("Email must have 'subject' field")
        return v
```

#### 3.2: `shopq/api_feedback.py`
Add validation to feedback endpoints

#### 3.3: `shopq/api_debug.py`
Add validation to debug endpoints

---

## Task 4: Fix Existing Type Errors (Priority 2)

Run mypy and fix errors in your assigned files:

```bash
# From project root
mypy shopq/observability.py --strict
mypy shopq/email_tracker.py --strict
mypy shopq/filters.py --strict
mypy adapters/storage/checkpoint.py --strict
mypy infra/telemetry.py --strict
```

Fix errors until all files pass strict mode.

Common fixes:
- Add `-> None` to functions that don't return
- Use `Optional[T]` for nullable types
- Use `Union[T1, T2]` for multiple types
- Add type ignore comments for unavoidable issues: `# type: ignore[<error-code>]`

---

## Testing Requirements

### Run Tests After Each Change

```bash
# Run full test suite
pytest tests/

# Run tests for specific module
pytest tests/unit/test_observability.py
pytest tests/unit/test_email_tracker.py
pytest tests/unit/test_filters.py
```

### Add Tests for Validation

If you add new validation logic, add tests:

```python
# tests/unit/test_api_validation.py

def test_summary_request_validates_email_structure():
    """Test that SummaryRequest validates email has required fields"""
    with pytest.raises(ValidationError):
        SummaryRequest(emails=[{"foo": "bar"}])  # Missing 'id'
```

---

## Deliverables Checklist

### By End of Week 1
- [ ] `observability.py` - Full type hints, side effects documented
- [ ] `email_tracker.py` - Full type hints, side effects documented
- [ ] `filters.py` - Type hints only (no refactoring)
- [ ] All tests passing
- [ ] Mypy strict mode passes for above files

### By End of Week 2
- [ ] `checkpoint.py` - Full type hints
- [ ] `telemetry.py` - Full type hints
- [ ] `api.py` - Input validation added
- [ ] `api_feedback.py` - Input validation added
- [ ] All tests passing
- [ ] Full mypy report showing improvement

---

## Coordination with Agent A

### Communication Protocol

**Before starting work on a file**:
1. Check AGENT_B_PROMPT.md off-limits list
2. If file not listed, assume safe to edit
3. If unsure, ask user first

**If you need to touch a shared file**:
1. Propose minimal change (e.g., just add type hints to function signature)
2. Ask user if Agent A will be editing this file
3. Wait for approval before proceeding

**Weekly sync**:
- Post summary of completed work
- Post list of files modified
- Flag any potential conflicts

### Merge Strategy

**Create PRs for each deliverable**:
- PR 1: `observability.py` type hints (Week 1)
- PR 2: `email_tracker.py` type hints (Week 1)
- PR 3: `filters.py` type hints (Week 1)
- PR 4: Remaining files (Week 2)
- PR 5: Input validation (Week 2)

**Branch naming**: `feat/agent-b-<task-name>`

Example:
```bash
git checkout -b feat/agent-b-observability-types
# Make changes
git commit -m "feat: Add type hints to observability.py"
git push origin feat/agent-b-observability-types
```

---

## Success Metrics

**Target by End of Week 2**:

| Metric | Before | Target | Measured |
|--------|--------|--------|----------|
| Type hint coverage (assigned files) | ~50% | 95%+ | ___ |
| Mypy errors (assigned files) | ~50 errors | 0 errors | ___ |
| Functions with side effect docs | ~10% | 90%+ | ___ |
| API endpoints with validation | ~30% | 100% | ___ |

**Report format**:
```markdown
## Agent B Week 2 Report

### Files Modified
- shopq/observability.py (+150 type hints, +20 side effect docs)
- shopq/email_tracker.py (+100 type hints, +15 side effect docs)
- shopq/filters.py (+50 type hints)
- adapters/storage/checkpoint.py (+30 type hints)
- shopq/api.py (+3 validation models)

### Metrics
- Type hint coverage: 50% → 96%
- Mypy errors: 50 → 0
- Side effect docs: 10% → 92%

### Tests
- All tests passing ✅
- Added 5 new validation tests ✅

### Conflicts
- None - no overlap with Agent A's digest refactor
```

---

## Getting Started

**Step 1**: Read this entire prompt
**Step 2**: Check off-limits list one more time
**Step 3**: Start with `shopq/observability.py` (smallest file)
**Step 4**: Run tests frequently
**Step 5**: Create PR when file is complete

**First command to run**:
```bash
# Check current mypy errors
mypy shopq/observability.py --strict

# Start fixing type hints
# <your editor> shopq/observability.py
```

Good luck! Remember: **DO NOT touch digest pipeline files.** If unsure, ask first.

---

## Questions?

If you encounter:
- **File conflicts**: Ask user before editing
- **Test failures**: Debug and fix before continuing
- **Mypy errors you can't fix**: Document with `# type: ignore` and add comment why
- **Unclear requirements**: Ask user for clarification

**Most important rule**: When in doubt, ask. Better to over-communicate than break Agent A's work.
