# Agent B: Phase 3 - Principles Compliance & Code Quality

**Role**: You are Agent B working in parallel with Agent A on the MailQ codebase.

**Context**: Agent A has completed the digest pipeline refactor (Phase 1-2). Now we're in Phase 3, focused on:
- Agent A: Dataset 2 validation and old code removal
- Agent B (you): Principles compliance and code quality improvements

**Timeline**: Week 7-8 of refactor (final phase)

---

## 🎯 Your Mission: Get MailQ to 46/50 Principles Score

**Current Score**: 33/50 (66%) - Grade C+
**Target Score**: 46/50 (92%) - Grade A

**Your Goal**: Fix P1, P2, P3 violations across the codebase

---

## 🚨 CRITICAL: Do NOT Touch These Files/Folders (Agent A Territory)

Agent A is working on Dataset 2 validation and code removal. **NEVER edit these**:

### Off-Limits Files (Logic Changes)
- `concepts/digest_pipeline.py` - **READ-ONLY for logic** (you can add type hints/docstrings only)
- `concepts/digest_stages.py` - **READ-ONLY for logic** (you can add type hints/docstrings only)
- `concepts/temporal_extraction.py` - **READ-ONLY for logic** (you can add type hints/docstrings only)
- `concepts/section_assignment.py` - **READ-ONLY for logic** (you can add type hints/docstrings only)
- `context_digest.py` - **READ-ONLY for logic** (you can add type hints/docstrings only)
- Any scripts in `scripts/evaluate_*.py` (Agent A creating these)

### What You CAN Do in concepts/
✅ Add type hints to function signatures
✅ Add "Side Effects:" sections to docstrings
✅ Fix mypy errors (add type ignores if needed)
✅ Add missing return type annotations

### What You CANNOT Do in concepts/
❌ Change any function logic
❌ Rename functions or classes
❌ Change function signatures (except adding types)
❌ Refactor or reorganize code

**Rule of thumb**: If it changes behavior, ask Agent A first.

---

## 📋 Your Task List (Priority Order)

### Phase 3A: Complete Original Tasks (Week 7, Days 1-2)

These are from your original AGENT_B_PROMPT.md - finish them first:

#### ✅ Task 1: Type Hints (Priority 1)
**Files to complete**:
- [ ] `mailq/observability.py` - Full type hints
- [ ] `mailq/email_tracker.py` - Full type hints
- [ ] `mailq/filters.py` - Type hints only (no refactoring)
- [ ] `adapters/storage/checkpoint.py` - Full type hints
- [ ] `infra/telemetry.py` - Full type hints

**Standard**: Every function must have:
```python
def function_name(
    param1: Type1,
    param2: Type2 | None = None
) -> ReturnType:
    """Docstring with Side Effects section if applicable"""
```

#### ✅ Task 2: Document Side Effects (Priority 1)
**Files to complete**:
- [ ] `mailq/observability.py` - Add "Side Effects:" to docstrings
- [ ] `mailq/email_tracker.py` - Add "Side Effects:" to docstrings
- [ ] `mailq/storage.py` - Add "Side Effects:" to docstrings
- [ ] `adapters/storage/checkpoint.py` - Add "Side Effects:" to docstrings

**Pattern**:
```python
def record_classification(email_id: str, classification: str) -> None:
    """
    Record classification for an email.

    Args:
        email_id: Email identifier
        classification: Classification result

    Side Effects:
        - Writes to database (classifications table)
        - Updates email_tracker state
        - Logs to observability system

    Raises:
        DatabaseError: If database write fails
    """
```

#### ✅ Task 3: Input Validation (Priority 2)
- [ ] `mailq/api.py` - Add Pydantic validation to request models
- [ ] `mailq/api_feedback.py` - Add validation to feedback endpoints
- [ ] `mailq/api_debug.py` - Add validation to debug endpoints

---

### Phase 3B: NEW - Concepts Module Annotations (Week 7, Days 3-4)

Now that Agent A has created the refactored pipeline, add type hints and docstrings:

#### ✅ Task 4: Type Hints for concepts/ (Priority 1)

**Files to annotate** (READ-ONLY for logic, annotations only):

1. **`concepts/digest_pipeline.py`**
   - [ ] Add type hints to all methods
   - [ ] Fix any mypy errors
   - [ ] Ensure all dataclasses are fully typed

2. **`concepts/digest_stages.py`**
   - [ ] Add type hints to all stage methods
   - [ ] Type hint helper methods (e.g., `_extract_entities_from_email`)
   - [ ] Fix mypy errors

3. **`concepts/temporal_extraction.py`**
   - [ ] Add type hints to all helper functions
   - [ ] Ensure datetime types are explicit
   - [ ] Fix mypy errors

4. **`concepts/section_assignment.py`**
   - [ ] Add type hints to all helper functions
   - [ ] Fix mypy errors

**Example**:
```python
# Before
def _extract_entities_from_email(self, extractor, email):
    """Extract entities from email"""
    ...

# After
def _extract_entities_from_email(
    self,
    extractor: HybridExtractor,
    email: dict[str, Any],
) -> list[Entity]:
    """Extract entities from email using HybridExtractor"""
    ...
```

#### ✅ Task 5: Document Side Effects in concepts/ (Priority 1)

Add "Side Effects:" sections to ALL stage `process()` methods:

**Example**:
```python
@dataclass
class TemporalContextExtractionStage:
    """Extract temporal context from emails"""

    name: str = "extract_temporal_context"
    depends_on: list[str] = field(default_factory=lambda: ["filter_expired"])

    def process(self, context: DigestContext) -> StageResult:
        """
        Extract temporal context from all filtered emails.

        Args:
            context: Digest context with filtered emails

        Returns:
            StageResult with extraction metrics

        Side Effects:
            - Populates context.temporal_contexts dict
            - Maps email_id -> temporal context
            - No external I/O or database writes
        """
        ...
```

**Files to update**:
- [ ] All stage classes in `concepts/digest_stages.py` (7 stages)
- [ ] Helper functions in `concepts/temporal_extraction.py`
- [ ] Helper functions in `concepts/section_assignment.py`

---

### Phase 3C: Mypy Cleanup (Week 7, Day 5)

#### ✅ Task 6: Run mypy and Fix Errors

**Commands**:
```bash
# Check concepts/ modules
mypy concepts/digest_pipeline.py --strict
mypy concepts/digest_stages.py --strict
mypy concepts/temporal_extraction.py --strict
mypy concepts/section_assignment.py --strict

# Check your assigned files
mypy mailq/observability.py --strict
mypy mailq/email_tracker.py --strict
mypy mailq/filters.py --strict
mypy adapters/storage/checkpoint.py --strict
mypy infra/telemetry.py --strict
```

**Target**: All files pass `mypy --strict` with zero errors

**Common fixes**:
- Add `-> None` for functions without return
- Use `Optional[T]` for nullable params
- Use `dict[str, Any]` instead of `dict`
- Add `# type: ignore[error-code]` for unavoidable issues

---

### Phase 3D: Testing & Validation (Week 8, Days 1-2)

#### ✅ Task 7: Ensure Tests Pass

After your changes, run tests:

```bash
# Run all tests
pytest tests/

# Run specific test suites
pytest tests/unit/test_observability.py
pytest tests/unit/test_email_tracker.py
pytest tests/unit/test_filters.py

# Run concepts tests (Agent A's tests)
pytest tests/unit/test_digest_pipeline.py
pytest tests/unit/test_temporal_extraction.py
pytest tests/unit/test_section_assignment.py
pytest tests/integration/test_digest_pipeline_integration.py
```

**Requirement**: All tests must pass after your changes

#### ✅ Task 8: Add Tests for Validation Logic

If you added Pydantic validation, add tests:

```python
# tests/unit/test_api_validation.py

def test_summary_request_validates_email_structure():
    """Test that SummaryRequest validates email has required fields"""
    with pytest.raises(ValidationError):
        SummaryRequest(emails=[{"foo": "bar"}])  # Missing 'id'

def test_summary_request_validates_email_count():
    """Test that SummaryRequest validates email count limits"""
    with pytest.raises(ValidationError):
        SummaryRequest(emails=[])  # Too few emails
```

---

## 📊 Success Metrics

### Target by End of Phase 3 (Week 8)

| Metric | Before | Target | Your Contribution |
|--------|--------|--------|-------------------|
| **P1: Concepts Are Rooms** | 5/10 | 9/10 | +0 (Agent A handles) |
| **P2: Side Effects Loud** | 4/10 | 9/10 | +5 (you document 12+ functions) |
| **P3: Compiler Is Senior** | 6/10 | 9/10 | +3 (you add type hints) |
| **P4: Synchronizations** | 8/10 | 9/10 | +0 (Agent A already fixed) |
| **P5: Debt vs Complexity** | 10/10 | 10/10 | +0 (already perfect) |
| **Total** | 33/50 | 46/50 | +8 points |

### Code Quality Metrics

| Metric | Before | Target |
|--------|--------|--------|
| Type hint coverage (assigned files) | ~50% | 95%+ |
| Type hint coverage (concepts/) | ~80% | 95%+ |
| Mypy errors (assigned files) | ~50 | 0 |
| Mypy errors (concepts/) | ~10 | 0 |
| Functions with side effect docs | ~10% | 90%+ |
| API endpoints with validation | ~30% | 100% |

---

## 🔄 Coordination with Agent A

### Daily Sync Protocol

**Every day, before starting work**:
1. Check if Agent A has pushed changes to `concepts/`
2. Pull latest changes: `git pull origin main`
3. If conflicts in `concepts/`, ask user for resolution

**If you need to touch a file Agent A is working on**:
1. Ask user first: "Agent A is working on X, can I add type hints?"
2. Wait for approval
3. Only add annotations, don't change logic

**When you're done with a file**:
1. Commit with clear message: `feat: Add type hints to observability.py`
2. Push to your branch: `git push origin feat/agent-b-phase3-typing`
3. Create PR for review

---

## 📦 Deliverables Checklist

### Week 7
- [ ] All original files typed (observability.py, email_tracker.py, filters.py, checkpoint.py, telemetry.py)
- [ ] All original files have side effect docs
- [ ] concepts/ modules fully typed
- [ ] concepts/ modules have side effect docs
- [ ] All mypy errors fixed
- [ ] All tests passing

### Week 8
- [ ] API validation added (api.py, api_feedback.py, api_debug.py)
- [ ] Validation tests added
- [ ] Final mypy report showing improvement
- [ ] PR created with all changes
- [ ] Final principles score: 40+/50

---

## 🎯 Quick Start Guide

**Day 1 - Get oriented**:
```bash
# Pull latest code
git pull origin main

# Create your branch
git checkout -b feat/agent-b-phase3-typing

# Check current mypy status
mypy mailq/observability.py --strict
mypy concepts/digest_pipeline.py --strict

# Start with smallest file
code mailq/observability.py
```

**Day 2 - Type hints**:
- Complete observability.py, email_tracker.py
- Run tests after each file
- Commit after each file

**Day 3 - concepts/ typing**:
- Add type hints to concepts/digest_pipeline.py
- Add type hints to concepts/digest_stages.py
- Run mypy, fix errors

**Day 4 - Side effects**:
- Add "Side Effects:" sections to all your files
- Add "Side Effects:" to concepts/ stages

**Day 5 - Mypy cleanup**:
- Run mypy on all files
- Fix all errors
- Get to zero mypy errors

**Day 6-7 - API validation**:
- Add Pydantic models to api.py
- Add validation to endpoints
- Write validation tests

**Day 8 - Final check**:
- Run all tests
- Generate mypy report
- Create PR
- Celebrate! 🎉

---

## ❓ Questions & Troubleshooting

### Q: Can I refactor code in concepts/ if I see issues?
**A**: No. Only add type hints and docstrings. If you see logic issues, report to Agent A or user.

### Q: What if mypy errors are unfixable?
**A**: Add `# type: ignore[error-code]` with a comment explaining why. Example:
```python
# type: ignore[arg-type] - HybridExtractor has dynamic method resolution
```

### Q: What if tests fail after my changes?
**A**:
1. Check if you accidentally changed logic (revert if so)
2. Check if type hints are too strict (use Union or Any if needed)
3. Ask user for help if stuck

### Q: What if Agent A pushes changes that conflict with mine?
**A**:
1. Pull their changes: `git pull origin main`
2. Resolve conflicts (keep their logic, add your annotations)
3. Ask user if unsure

### Q: Can I create new files?
**A**: Only for tests (e.g., `tests/unit/test_api_validation.py`). No new production code without approval.

---

## 📚 Reference Materials

### Type Hint Patterns

```python
# Basic types
def process(x: int, y: str) -> bool:
    ...

# Optional/nullable
def get_user(user_id: str | None = None) -> User | None:
    ...

# Collections
def process_emails(emails: list[dict[str, Any]]) -> list[Entity]:
    ...

# Complex unions
def parse(data: str | dict | bytes) -> ParsedData:
    ...

# Protocols
from typing import Protocol

class Extractor(Protocol):
    def extract(self, email: dict) -> list[Entity]:
        ...
```

### Side Effects Documentation Pattern

```python
def write_to_database(
    table: str,
    data: dict[str, Any]
) -> None:
    """
    Write data to database table.

    Args:
        table: Table name
        data: Row data to insert

    Side Effects:
        - Writes to database (specified table)
        - Creates transaction log entry
        - Updates last_modified timestamp
        - May trigger database webhooks

    Raises:
        DatabaseError: If write fails
        ValidationError: If data is invalid
    """
    ...
```

---

## 🎯 Most Important Rules

1. **DO NOT change logic in concepts/** - Only add type hints and docstrings
2. **RUN TESTS after every change** - Don't break Agent A's work
3. **ASK if unsure** - Better to over-communicate than break things
4. **COMMIT frequently** - Small commits are easier to review
5. **FOCUS on principles** - Your goal is P2 and P3 compliance

**Your success = MailQ gets to 46/50 principles score**

Good luck! 🚀

---

## 📞 Getting Help

If you encounter:
- **File conflicts**: Ask user before editing
- **Test failures**: Debug and fix before continuing
- **Mypy errors you can't fix**: Document with `# type: ignore` and add comment
- **Unclear requirements**: Ask user for clarification
- **Logic bugs in concepts/**: Report to Agent A, don't fix yourself

**Most important rule**: When in doubt, ask. Better to over-communicate than break Agent A's work.
