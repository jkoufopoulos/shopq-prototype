# Principles Violations Analysis Report

**Generated:** 2025-12-05
**Validator:** `scripts/validate_principles.py`
**Scope:** `mailq/` (production) + `scripts/` (dev tools)

---

## Executive Summary

| Metric | Count |
|--------|-------|
| **Total Violations** | 748 |
| **P2 (Side Effects)** | 236 |
| **P3 (Type Hints)** | 512 |
| **Files Affected** | 143 of 204 |

### By Area

| Area | Violations | Priority |
|------|------------|----------|
| `mailq/` (production) | 230 | HIGH |
| `scripts/` (dev tools) | 518 | LOWER |

---

## P3: Type Hints (512 violations)

### Breakdown

| Type | Count | % |
|------|-------|---|
| Missing return type | 333 | 65% |
| Missing parameter type | 133 | 26% |
| Bare dict/list (not parameterized) | 46 | 9% |

### Top Offenders (mailq/ only)

1. `mailq/infrastructure/database.py` - 24 violations
2. `mailq/api/routes/debug.py` - 15 violations
3. `mailq/api/app.py` - 11 violations
4. `mailq/storage/__init__.py` - 9 violations
5. `mailq/observability/structured.py` - 9 violations

### Action Required

```python
# Before (violation)
def get_stats():
    return {"count": 10}

# After (compliant)
def get_stats() -> dict[str, int]:
    return {"count": 10}
```

---

## P2: Side Effects (236 violations)

### Breakdown

| Type | Count | Notes |
|------|-------|-------|
| Missing docs: state mutations | 94 | Real issue |
| **FALSE POSITIVE**: name suggests side effects | 74 | Validator bug |
| Missing docs: database writes | 34 | Real issue |
| Missing docstring entirely | 34 | Real issue |

### False Positive Patterns (74 violations)

The validator incorrectly flags these pure functions because their names contain keywords like "reset", "clear", "set":

| Pattern | Count |
|---------|-------|
| `clear_*` (cache clear methods) | 9 |
| `put` (cache put, in-memory) | 7 |
| `__post_init__` (dataclass hook) | 6 |
| `reset_*` (state reset, often in-memory) | 5 |
| `compute_*` (pure computation) | 5 |
| `send_*` (stub/mock methods) | 4 |
| `record_*` (in-memory only) | 4 |
| `set_*` (dependency injection setters) | 3 |
| `validate_*` (pure validators) | 2 |
| `dispatch` (middleware, no side effects) | 2 |
| Other | 27 |

### Real P2 Issues (~162 violations)

Functions that actually modify state but don't document it:

```python
# Before (violation)
def save_to_db(self, data):
    """Save data."""
    self.conn.execute("INSERT INTO table VALUES (?)", (data,))

# After (compliant)
def save_to_db(self, data):
    """Save data to database.

    Side Effects:
        - Writes to 'table' in SQLite database
    """
    self.conn.execute("INSERT INTO table VALUES (?)", (data,))
```

---

## Scripts Breakdown

Most `scripts/` violations are in archived/legacy code:

| Directory | Violations |
|-----------|------------|
| `scripts/archive/legacy_gds/` | 138 |
| `scripts/archive/one_off/` | 117 |
| `scripts/evals/tools/` | 57 |
| `scripts/archive/generators/` | 49 |
| `scripts/archive/dev_tools/` | 45 |
| `scripts/quality-monitor/` | 36 |
| `scripts/database/` | 28 |

**Recommendation:** Consider exempting `scripts/archive/` from validation since these are legacy/one-off tools.

---

## Recommendations

### 1. Fix Validator False Positives (Priority: HIGH)

Update `scripts/validate_principles.py` to exclude these patterns from P2 side-effect detection:

```python
# Exclude from SIDE_EFFECT_KEYWORDS or add to allowlist
FALSE_POSITIVE_PATTERNS = {
    "__post_init__",  # dataclass hook, not a side effect
    "validate_",      # pure validators
    "compute_",       # pure computation
    "dispatch",       # middleware routing
}
```

This would eliminate ~74 false positives.

### 2. Add Type Hints to Production Code (Priority: HIGH)

Focus on `mailq/` files with most violations:

| File | Missing |
|------|---------|
| `mailq/infrastructure/database.py` | 24 type hints |
| `mailq/api/routes/debug.py` | 15 type hints |
| `mailq/api/app.py` | 11 type hints |
| `mailq/storage/__init__.py` | 9 type hints |
| `mailq/observability/structured.py` | 9 type hints |

### 3. Document Real Side Effects (Priority: MEDIUM)

Add `Side Effects:` sections to functions that:
- Write to database (INSERT, UPDATE, DELETE)
- Call external APIs
- Mutate global/shared state

### 4. Consider Exempting Scripts (Priority: LOW)

Option A: Exclude `scripts/archive/` from default validation
```python
if not args.paths:
    args.paths = [Path("mailq"), Path("scripts")]
    # Exclude archived scripts
```

Option B: Add `--strict` flag for production-only validation
```bash
python scripts/validate_principles.py --strict  # Only mailq/
python scripts/validate_principles.py           # mailq/ + scripts/
```

---

## Appendix: Subdirectory Breakdown

| Subdirectory | Violations |
|--------------|------------|
| scripts/archive | 349 |
| mailq/api | 86 |
| scripts/evals | 79 |
| scripts/quality-monitor | 36 |
| mailq/infrastructure | 33 |
| mailq/classification | 32 |
| scripts/database | 28 |
| mailq/digest | 21 |
| mailq/storage | 20 |
| mailq/observability | 11 |
| mailq/gmail | 11 |
| mailq/concepts | 6 |
| mailq/llm | 4 |
| mailq/runtime | 3 |
| mailq/shared | 2 |
