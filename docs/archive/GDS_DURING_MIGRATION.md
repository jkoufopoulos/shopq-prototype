# GDS Testing During Database Migration

**TL;DR**: GDS tests use your database (via RulesEngine). During DB migration, some tests might fail. Use the migration-safe test script instead.

---

## The Issue

Your MemoryClassifier uses the database:

```python
# mailq/memory_classifier.py
class MemoryClassifier:
    def __init__(self):
        self.rules = RulesEngine()  # ← Uses mailq.db
        self.type_mapper = get_type_mapper()  # ← Uses config (YAML)
        self.llm_classifier = VertexGeminiClassifier()  # ← Uses Gemini API
```

**During database migration**:
- ✅ Type Mapper works (uses YAML config)
- ✅ LLM Classifier works (uses Gemini API)
- ❌ **Rules Engine might fail** (uses database)

---

## What Breaks During Migration

### Scenario 1: Schema Changes

```sql
-- Old schema
CREATE TABLE rules (
    id INTEGER PRIMARY KEY,
    pattern TEXT,
    category TEXT
);

-- New schema (after migration)
CREATE TABLE rules (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,  -- ← NEW COLUMN
    pattern TEXT,
    category TEXT,
    confidence REAL
);
```

**Impact**:
```python
# RulesEngine queries with new schema
SELECT * FROM rules WHERE user_id = ?
                          ↑
                    Error: no such column

→ MemoryClassifier initialization fails
→ GDS tests error: "Could not initialize classifier"
```

---

### Scenario 2: Empty Rules Table

```sql
-- During migration
DELETE FROM rules;  -- Temporarily empty
-- ... migration logic ...
INSERT INTO rules VALUES (...);  -- Restore
```

**Impact**:
```python
# RulesEngine finds no rules
→ All emails fall through to LLM
→ Tests still pass, but classification might differ
→ Slower (every email uses LLM, not cached rules)
```

---

### Scenario 3: Database Locked

```bash
# Migration script holds write lock
BEGIN EXCLUSIVE TRANSACTION;
ALTER TABLE rules ...;
```

**Impact**:
```python
# RulesEngine tries to query
→ Error: database is locked

→ GDS tests timeout or error
```

---

## Solutions

### Option 1: Skip GDS Tests During Migration (Simplest)

Just don't run GDS tests while migrating:

```bash
# During migration
git commit -m "WIP: Database migration in progress" --no-verify

# After migration complete
./scripts/test_against_gds.sh  # Now run GDS tests
```

---

### Option 2: Use Migration-Safe Test Script

Run tests that don't depend on database:

```bash
# During migration
./scripts/test_gds_migration_safe.sh

# Output:
# ╔════════════════════════════════════════════════════════╗
# ║  MailQ GDS Tests (DB Migration Safe Mode)             ║
# ║  Running tests that don't depend on database          ║
# ╚════════════════════════════════════════════════════════╝
#
# ⚠️  NOTE: Database-dependent tests will be skipped
#    (Rules engine, user overrides, few-shot examples)
#
# [1/2] Testing Type Mapper (no DB dependency)...
# ✅ Type Mapper tests PASSED
#
# [2/2] Testing Basic Classification (LLM + Type Mapper only)...
# ⚠️  Skipping: Rules engine, guardrails (DB-dependent)
```

This runs:
- ✅ Type Mapper tests (no DB)
- ❌ Skips Rules Engine tests
- ❌ Skips Guardrails tests (if they use DB)

---

### Option 3: Mock the Database

Create a test database that won't change:

```bash
# Before migration: Copy current DB
cp mailq/data/mailq.db mailq/data/mailq_test.db

# During migration: Use test DB for GDS tests
export MAILQ_TEST_DB=mailq/data/mailq_test.db
pytest tests/test_*_gds.py -v

# After migration: Delete test DB
rm mailq/data/mailq_test.db
```

---

## Testing Workflow During Migration

### Before Migration

```bash
# 1. Run full GDS tests (establish baseline)
./scripts/test_against_gds.sh
# Output: ALL TESTS PASSED ✅

# 2. Save test results
pytest tests/ -k "gds" --json-report --json-report-file=baseline_before_migration.json
```

---

### During Migration

```bash
# Option A: Skip GDS tests entirely
# (Just focus on migration, test after)

# Option B: Run migration-safe tests
./scripts/test_gds_migration_safe.sh
# (Only tests type mapper, skips rules/guardrails)
```

---

### After Migration

```bash
# 1. Run full GDS tests
./scripts/test_against_gds.sh

# 2. Compare to baseline
pytest tests/ -k "gds" --json-report --json-report-file=baseline_after_migration.json

# 3. Check for regressions
python scripts/compare_test_results.py \
    baseline_before_migration.json \
    baseline_after_migration.json
```

**Expected**: Tests should pass with similar metrics (precision, recall, distribution)

---

## Common Migration Errors

### Error 1: "no such column: user_id"

```
FAILED tests/test_guardrails_gds.py - Error: no such column: user_id
```

**Cause**: RulesEngine queries using new schema, but DB still has old schema

**Fix**: Complete the migration, then run tests

---

### Error 2: "database is locked"

```
FAILED tests/test_guardrails_gds.py - Error: database is locked
```

**Cause**: Migration script holds exclusive lock

**Fix**: Wait for migration to complete, or use test DB (Option 3)

---

### Error 3: "Could not initialize classifier"

```
SKIPPED tests/test_guardrails_gds.py - Could not initialize classifier (DB migration?)
```

**Cause**: MemoryClassifier.__init__() failed (probably RulesEngine)

**Fix**: This is expected during migration. Tests will auto-skip.

---

## FAQ

### Q: Can I run GDS tests during migration?

**A**: Depends on the migration:
- **Schema-only** (add column): Probably safe
- **Data migration** (empty/refill tables): Risky, might get inconsistent results
- **Major refactor** (multi-table changes): Skip tests until done

**Recommendation**: Wait until migration is complete, then run full GDS tests.

---

### Q: What if GDS tests fail after migration?

**A**: Compare metrics before vs after:

```bash
# Before migration
Critical precision: 96.7%
OTP in CRITICAL: 0

# After migration
Critical precision: 87.2%  ❌ REGRESSION!
OTP in CRITICAL: 3         ❌ REGRESSION!
```

**Likely causes**:
1. **Rules lost during migration** (check rules table)
2. **Schema mismatch** (RulesEngine queries wrong columns)
3. **User ID scoping** (rules not associated with test user_id)

---

### Q: Should I update GDS baseline after migration?

**A**: **Only if migration intentionally changes behavior**

**Example - Should update**:
```
Migration: Add user_id column, split rules per user

Before: 1 global rule matches 50 emails
After:  10 user-specific rules match 45 emails

→ Update baseline (expected behavior change)
```

**Example - Should NOT update**:
```
Migration: Just add user_id column, don't change logic

Before: Rules match 50 emails
After:  Rules match 50 emails

→ Don't update baseline (no behavior change expected)
```

---

## Checklist: Testing Around Migrations

**Before Migration**:
- [ ] Run `./scripts/test_against_gds.sh` (establish baseline)
- [ ] Save results: `pytest tests/ -k "gds" --json-report --json-report-file=baseline_before.json`
- [ ] Commit: `git add baseline_before.json && git commit -m "GDS baseline before migration"`

**During Migration**:
- [ ] Option: Skip GDS tests (focus on migration)
- [ ] Option: Run `./scripts/test_gds_migration_safe.sh` (partial testing)
- [ ] Don't worry if tests fail - expected during migration

**After Migration**:
- [ ] Run `./scripts/test_against_gds.sh` (full test suite)
- [ ] Compare: `python scripts/compare_test_results.py baseline_before.json baseline_after.json`
- [ ] Investigate any regressions (rules lost? schema mismatch?)
- [ ] If behavior intentionally changed, update test baselines
- [ ] Mark migration complete: `/complete US-XXX`

---

## Summary

**The short version**:

1. **GDS tests use database** (via RulesEngine)
2. **During migration, tests might fail** (database locked, schema mismatch, empty tables)
3. **Two options**:
   - Skip tests during migration, run after ✅ (recommended)
   - Use migration-safe script (partial testing)
4. **After migration, run full GDS tests** to catch regressions
5. **Compare before/after** to ensure no unexpected behavior changes

**Quick commands**:
```bash
# Before migration
./scripts/test_against_gds.sh

# During migration (optional)
./scripts/test_gds_migration_safe.sh

# After migration (required)
./scripts/test_against_gds.sh
```

---

**Questions?** See `GDS_TESTING_GUIDE.md` for general testing workflow or `/ROADMAP.md` for overall testing strategy.
