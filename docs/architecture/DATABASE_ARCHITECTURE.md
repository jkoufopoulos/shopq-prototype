# ShopQ Database Architecture

**Status**: Database Consolidation Complete ✅
**Last Updated**: 2025-11-12
**Owner**: Architecture Team

---

## Executive Summary

ShopQ uses a **single SQLite database** architecture to ensure data consistency, enable cross-domain queries, and prevent database proliferation. All features MUST add tables to the central `shopq/data/shopq.db` database.

**Policy**: Creating new `.db` files is **FORBIDDEN** without explicit architectural review.

---

## Database Policy (Enforced)

### Single Database Rule

**ShopQ uses ONE SQLite database: `shopq/data/shopq.db`**

- All new tables MUST be added to this database
- Scripts MUST connect to central database via `shopq/config/database.py`
- Creating new `.db` files is FORBIDDEN without architectural review
- Pre-commit hook enforces this policy (blocks commits with new .db files)

### Why Single Database?

**Benefits**:
- ✅ Single backup/restore point
- ✅ JOIN queries across domains (rules + feedback + classifications)
- ✅ Connection pooling (5x performance improvement)
- ✅ Multi-tenancy ready with `user_id` scoping
- ✅ ACID transactions span all data

**Problems with Multiple Databases**:
- ❌ No cross-database JOINs in SQLite
- ❌ 10+ files to backup/restore
- ❌ Connection management nightmare
- ❌ Multi-tenancy impossible (data scattered)
- ❌ Schema drift (each database evolves separately)

---

## Current State (2025-11-12)

### Central Database (Consolidation Complete ✅)

```
shopq/data/shopq.db
├─ Classification
│  ├─ rules - User classification rules
│  ├─ pending_rules - Candidate rules from learning
│  ├─ categories - Classification categories
│  └─ learned_patterns - Patterns from feedback
│
├─ Feedback & Learning
│  ├─ feedback - User corrections
│  ├─ corrections - Detailed correction tracking
│  ├─ fewshot_examples - Few-shot learning examples
│  ├─ digest_feedback - User feedback on digest quality
│  └─ digest_patterns - Learned digest importance patterns
│
└─ Tracking & Observability
   ├─ email_threads - Email classification history
   ├─ digest_sessions - Digest generation tracking
   └─ confidence_logs - Confidence score monitoring
```

**All tracking, digest, and quality monitoring tables are now in the central database.**

### External Tools (Keep Separate)

| Database | Purpose | Status |
|----------|---------|--------|
| **scripts/quality-monitor/quality_monitor.db** | Quality analysis state, GitHub issues | ✅ **INTENTIONALLY SEPARATE** |

Quality monitoring keeps its own database to avoid coupling monitoring tools to production schema.

---

## Connection Management (Enforced Singleton)

### How to Connect to Database

All code MUST use the singleton pattern from `shopq/config/database.py`:

```python
from shopq.config.database import get_db_connection, db_transaction

# ✅ CORRECT: Read query
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rules WHERE user_id = ?", (user_id,))
    results = cursor.fetchall()
    # Connection automatically returned to pool

# ✅ CORRECT: Write with transaction
with db_transaction() as conn:
    conn.execute("INSERT INTO rules (...) VALUES (?)", (values,))
    conn.execute("UPDATE categories SET ...")
    # Auto-commits on success, rolls back on error

# ❌ WRONG: Direct sqlite3.connect() bypasses singleton
import sqlite3
conn = sqlite3.connect("some_database.db")  # FORBIDDEN!
```

### Connection Pool Features

- **Pooling**: 5 pre-created connections (reused for performance)
- **WAL mode**: Write-Ahead Logging for concurrent reads
- **Foreign keys**: Enabled by default (SQLite disables them otherwise)
- **Row factory**: Results returned as dictionaries (`Row` objects)
- **Thread-safe**: `check_same_thread=False` with proper locking
- **Automatic cleanup**: Connections closed on program exit

---

## Schema Design Principles

### Multi-Tenancy Preparation

All tables MUST include `user_id` for future multi-tenant support:

```sql
CREATE TABLE rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT DEFAULT 'default',  -- Required for multi-tenancy!
    pattern_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    category TEXT NOT NULL,
    confidence INTEGER DEFAULT 85,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    use_count INTEGER DEFAULT 0,
    UNIQUE(user_id, pattern_type, pattern, category)  -- Composite key with user_id
);

-- Index for efficient user-scoped queries
CREATE INDEX idx_rules_user_pattern ON rules(user_id, pattern_type, pattern);
```

### Adding New Tables

When you need to add a table:

1. **Update `shopq/config/database.py::init_database()`**:
   ```python
   conn.executescript("""
       CREATE TABLE IF NOT EXISTS your_new_table (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           user_id TEXT DEFAULT 'default',  -- Required!
           your_column TEXT NOT NULL,
           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
       );

       CREATE INDEX IF NOT EXISTS idx_your_table_user
       ON your_new_table(user_id);
   """)
   ```

2. **Add to `validate_schema()`**:
   ```python
   required_tables = {
       "your_new_table": ["id", "user_id", "your_column"],
       # ... existing tables
   }
   ```

3. **Create migration script** (if production DB exists):
   ```python
   # shopq/scripts/migrations/YYYYMMDD_add_your_table.py
   def migrate():
       with db_transaction() as conn:
           conn.execute("ALTER TABLE ... ADD COLUMN ...")
   ```

4. **Update this documentation** with table purpose

---

## Migration Roadmap

### Phase 1: Foundation ✅ COMPLETE (2025-11-10)

**Goals**: Establish governance and prevent future proliferation

**Completed**:
- ✅ Database singleton pattern enforced in `shopq/config/database.py`
- ✅ Policy added to `CLAUDE.md` section 8
- ✅ Pre-commit hook created: `scripts/hooks/check-no-new-databases.sh`
- ✅ Hook integrated into `.pre-commit-config.yaml`
- ✅ Documentation created (`DATABASE_ARCHITECTURE.md`)

**Impact**: New `.db` files now blocked by pre-commit hook

---

### Phase 2: Consolidation ✅ COMPLETE (2025-11-12)

**Completed**: Merged with feat/bridge-mode-ingestion branch

**What was done**:

1. ✅ **Migrated tracking tables** to central database:
   - `email_threads` - Email classification history
   - `digest_sessions` - Digest generation tracking
   - All tracking code now uses `get_db_connection()`

2. ✅ **Migrated digest tables** to central database:
   - `digest_feedback` - User feedback on digests
   - `digest_patterns` - Learned importance patterns
   - Digest code updated to use central connection pool

3. ✅ **Updated all code** to use singleton pattern:
   - `shopq/email_tracker.py` → uses `get_db_connection()`
   - `shopq/confidence_logger.py` → uses `get_db_connection()`
   - All new code must use `get_db_connection()` (enforced by policy)

4. ✅ **Added automatic initialization**:
   - API startup calls `init_database()` to create core tables
   - `EmailThreadTracker()` creates tracking tables on first use
   - All schema creation is idempotent (CREATE TABLE IF NOT EXISTS)

5. ✅ **Production deployment**:
   - Database schema initialized automatically on Cloud Run startup
   - All endpoints now use central database
   - No manual migration needed for new deployments

**Note**: Quality monitor (`scripts/quality-monitor/quality_monitor.db`) intentionally kept separate to avoid coupling monitoring tools to production schema.

---

### Phase 3: Multi-Tenancy (Planned: Week of 2025-11-25)

**Timing**: Aligns with Classification Phase 5 (User Overrides)

**Why aligned?**: Both need `user_id` schema changes

**Tasks**:

1. **Verify user_id columns exist** in all tables
2. **Create composite indexes**: `(user_id, key_column)`
3. **Implement tenancy guards**:
   ```python
   from shopq.tenancy import enforce_tenancy

   @enforce_tenancy
   def get_user_rules(user_id: str):
       # Automatically validates user_id matches auth context
       with get_db_connection() as conn:
           return conn.execute(
               "SELECT * FROM rules WHERE user_id = ?",
               (user_id,)
           ).fetchall()
   ```

4. **Add cross-tenant leakage tests**:
   ```python
   def test_user_cannot_see_other_user_rules():
       create_rule(user_id="alice@example.com", pattern="*@bank.com")
       rules = get_rules(user_id="bob@example.com")
       assert len(rules) == 0  # Bob should NOT see Alice's rules
   ```

5. **Backfill existing rows**: `user_id = 'default'`

**Duration**: 2-3 weeks

---

## Governance & Enforcement

### Pre-commit Hook

**Location**: `scripts/hooks/check-no-new-databases.sh`

**Whitelist**:
- `shopq/data/shopq.db` (central database)
- `shopq/data/shopq_test.db` (test database)

**Behavior**: Rejects commits with new `.db` files:

```bash
❌ ERROR: New SQLite database file detected: scripts/new_feature.db

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATABASE POLICY VIOLATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ShopQ uses ONE SQLite database: shopq/data/shopq.db

Creating new .db files is FORBIDDEN without architectural review.

What to do instead:
  1. Add your tables to shopq/data/shopq.db
  2. Use shopq/config/database.py::get_db_connection()
  3. Update shopq/config/database.py::init_database() with your schema
```

### CLAUDE.md Policy (Section 8)

```markdown
* **Database Policy:** ShopQ uses ONE SQLite database: `shopq/data/shopq.db`
  * All new tables MUST be added to this database via `shopq/config/database.py`
  * Creating new `.db` files is **FORBIDDEN** without explicit architectural review
  * All code MUST use `get_db_connection()` from `shopq/config/database.py`
  * Scripts MUST connect to central database, not create their own
  * Pre-commit hook will reject commits with new `.db` files
```

---

## Database File Locations

### Allowed ✅

```
shopq/data/
├─ shopq.db          ✅ Central database (THE database)
└─ shopq_test.db     ✅ Test database (isolated from production)
```

### Forbidden ❌

```
❌ scripts/*/some_feature.db        # Scripts creating own DBs
❌ shopq/some_module/feature.db     # Modules creating own DBs
❌ data/some_feature_tracking.db    # Feature-specific DBs
❌ *.db (anywhere else)             # Any other location
```

---

## Future: Postgres Migration

### When to Migrate

**Migration Triggers** (monitor monthly):

| Metric | Current | Postgres Threshold | Timeline Estimate |
|--------|---------|-------------------|-------------------|
| **Database size** | 756KB | >50MB | 12-18 months |
| **Concurrent users** | 1 | >50 | 6-12 months |
| **Write lock contention** | <1% | >10% failures | 6-9 months |

### Migration Plan

**Phase 1 (6-12 months)**: Postgres Prep
- Set up Cloud SQL (Postgres 15)
- Write Alembic migration scripts
- Test with production data snapshot

**Phase 2 (12+ months)**: Migration Execution
- Gradual rollout (10% → 50% → 100%)
- Dual-write period (1 week validation)
- Keep SQLite as fallback (2 weeks)

**Cost**: $25-50/month for Cloud SQL db-f1-micro (100 users)

### Why Postgres (Not Firebase)

✅ **Postgres**:
- Drop-in replacement (same SQL)
- Migration effort: 2-3 weeks
- Cost: $25-50/month
- Supports JOINs, transactions, complex queries

❌ **Firebase/Firestore**:
- Architectural mismatch (NoSQL, no JOINs)
- Migration effort: 2-3 months (complete rewrite)
- Cost: $100-200/month (expensive for your query patterns)

---

## Troubleshooting

### "Database not found" error

```python
FileNotFoundError: Database not found: shopq/data/shopq.db
Run: python shopq/scripts/consolidate_databases.py
```

**Solution**:
```bash
python -c "from shopq.config.database import init_database; init_database()"
```

### "Database locked" error

```
sqlite3.OperationalError: database is locked
```

**Solution**: Connection pool with WAL mode handles this automatically. If it persists:
1. Check for long-running transactions
2. Increase timeout in `DatabaseConnectionPool._create_connection()`
3. Consider Postgres if concurrent writes >10/sec

### Schema validation failed

```
ValueError: Database missing tables: {'your_table'}
```

**Solution**:
```bash
python -c "from shopq.config.database import init_database; init_database()"
```

---

## References

- **Root Cause Analysis**: Architecture-advisor report (2025-11-10)
- **CLAUDE.md Section 8**: Database Policy governance
- **Pre-commit Hook**: `scripts/hooks/check-no-new-databases.sh`
- **Connection Pool**: `shopq/config/database.py`
- **Migration Script**: `shopq/scripts/consolidate_databases.py` (Phase 2)

---

**Maintenance**: Review quarterly. Update when schema changes or migration triggers hit.
