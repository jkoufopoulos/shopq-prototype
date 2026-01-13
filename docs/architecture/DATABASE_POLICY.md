# Database Policy (Updated Nov 2025)

## Decision: Single Central Database Architecture

**Decision Date**: November 11, 2025
**Status**: ✅ Implemented

### Architecture

ShopQ uses **ONE** central SQLite database for all application data:

```
shopq/data/shopq.db (PRIMARY - 756 KB)
├── Application tables (email_threads, rules, feedback)
├── Digest tables (digest_feedback, digest_sessions)
├── Quality monitoring (quality_issues, analyzed_sessions)
├── User preferences (pending_rules, learned_patterns)
└── Observability (llm_usage_tracking, confidence_logs)
```

### Rationale

**Why single database?**
1. **Simplicity**: Single source of truth, single backup strategy
2. **SQLite strengths**: Handles our scale (< 100 users) with ease
3. **Atomic transactions**: Cross-domain queries work seamlessly
4. **Already implemented**: Recent consolidation (Nov 2025) merged all tables

**Scale limits**:
- Current: 1 user, 756 KB database
- Comfortable: Up to 500 users (~375 MB)
- SQLite limit: 100+ req/sec with WAL mode

**Migration trigger**: When reaching 500+ users, migrate to Cloud SQL (Postgres).

### Tables in Central Database

```sql
-- Application Core
email_threads          -- Processed emails
rules                  -- Classification rules
feedback               -- User feedback
corrections            -- User corrections

-- Digest System
digest_feedback        -- User feedback on digests
digest_sessions        -- Generated digest sessions
digest_patterns        -- Learned digest patterns
digest_emails          -- Sent digests

-- Quality & Learning
quality_issues         -- Identified quality problems
analyzed_sessions      -- Quality analysis results
learned_patterns       -- ML-learned patterns
fewshot_examples       -- Few-shot examples for LLM
pending_rules          -- Rules awaiting approval

-- Observability
llm_usage_tracking     -- LLM API call tracking
confidence_logs        -- Classification confidence logs

-- Configuration
categories             -- Email categories
```

### Connection Management

All code MUST use the centralized connection pool:

```python
from shopq.config.database import get_db_connection, db_transaction

# Read operations
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rules")

# Write operations (automatic commit/rollback)
with db_transaction() as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO rules (...) VALUES (...)")
```

### Policy Enforcement

**Creating new `.db` files is FORBIDDEN** without architectural review.

**Pre-commit hook** (`scripts/hooks/check-no-new-databases.sh`):
- Blocks commits with new `*.db` files
- Allows `shopq/data/shopq.db` (central database)
- Allows test fixtures (`tests/fixtures/*.db`)

**Git ignore pattern**:
```gitignore
# Ignore all databases
*.db
*.sqlite
*.sqlite3

# Exception: Test fixtures
!shopq/tests/fixtures/*.db
```

### What Changed (Nov 2025)

**Before consolidation**:
```
shopq/digest_rules.db (40 KB)          → Deleted (deprecated, unused)
data/shopq_tracking.db (88 KB)         → Merged into shopq/data/shopq.db
scripts/quality-monitor/quality_monitor.db (0 KB) → Deleted (unused)
```

**After consolidation**:
```
shopq/data/shopq.db (756 KB) ✅ ONLY database
```

**Migration details**:
- Date: November 11, 2025
- Script: `shopq/scripts/consolidate_databases.py`
- Verification: All tables present, data intact
- Archives deleted: `data/archived_dbs/` removed

### Backup Strategy

**Development**: No automatic backups (git-tracked database)

**Production**:
1. **WAL mode**: Enabled by default (crash-safe, concurrent reads)
2. **Periodic snapshots**: Cloud Run persistent disk snapshots (daily)
3. **Export backups**: Manual exports to Cloud Storage (weekly)
4. **Retention**: 30 days rolling backups

### Multi-Tenancy Preparation

Database is **multi-tenant ready**:

```sql
-- All tables have user_id column
CREATE TABLE rules (
    id INTEGER PRIMARY KEY,
    user_id TEXT DEFAULT 'default',  -- ✅ Multi-tenant ready
    pattern TEXT NOT NULL,
    ...
);
```

**Next steps for multi-user**:
1. Replace `user_id='default'` with actual user IDs
2. Add `user_id` indexes to all queries
3. Add tenant isolation tests

See: `P0.3: Multi-tenancy preparation` in roadmap.

### Scalability Roadmap

| Users | Database | Action Required |
|-------|----------|-----------------|
| 1-100 | SQLite | ✅ Current architecture (no changes) |
| 100-500 | SQLite | Monitor query performance, add indexes |
| 500-5000 | Cloud SQL (Postgres) | Migrate to managed database |
| 5000+ | Cloud SQL + Read Replicas | Horizontal scaling |

**Migration path** (when needed):
```python
# config/database.py - Add Postgres support
def get_db_connection():
    if os.getenv("DATABASE_URL"):  # Cloud SQL
        return psycopg2.connect(os.getenv("DATABASE_URL"))
    else:  # Local SQLite (development)
        return sqlite3.connect(DB_PATH)
```

### Alternative Considered: 3-Database Architecture

**Considered approach** (from architecture advisor):
1. `shopq/data/shopq.db` - Application database
2. `scripts/quality-monitor/quality_monitor.db` - Observability
3. `shopq/data/shopq_test.db` - Testing

**Why rejected**:
- **Recent consolidation**: Just completed database merge (Nov 2025)
- **Simplicity wins**: Single database is easier to manage, backup, query
- **No performance issues**: SQLite handles our current scale with ease
- **Quality tables fit well**: Observability is part of application lifecycle

**When to reconsider**: If quality monitoring becomes separate microservice.

### Related Documentation

- **Database Architecture**: `/docs/DATABASE_ARCHITECTURE.md` (schema reference)
- **Connection Pool**: `shopq/config/database.py` (implementation)
- **Database Guardrails**: `/claude.md` (section 8: Database Policy)
- **Consolidation Script**: `shopq/scripts/consolidate_databases.py`

### Troubleshooting

**Issue**: "Database is locked" error

**Cause**: Multiple processes writing simultaneously

**Fix**:
1. Ensure using `get_db_connection()` (has retry logic)
2. Enable WAL mode: `PRAGMA journal_mode=WAL;`
3. Close connections promptly (use context managers)

**Issue**: Slow queries

**Cause**: Missing indexes, large table scans

**Fix**:
```sql
-- Add index on frequently queried columns
CREATE INDEX idx_email_threads_user_id ON email_threads(user_id, timestamp DESC);
CREATE INDEX idx_rules_user_id ON rules(user_id, active);
```

**Issue**: Database file growing quickly

**Cause**: No VACUUM, deleted rows not reclaimed

**Fix**:
```bash
# Manual VACUUM (reclaims space)
sqlite3 shopq/data/shopq.db "VACUUM;"

# Auto-vacuum (automatic space reclamation)
sqlite3 shopq/data/shopq.db "PRAGMA auto_vacuum = FULL;"
```

---

**Last Updated**: November 11, 2025
**Decision Owner**: See `/CONTRIBUTING.md`
**Review Schedule**: Quarterly or when approaching 500 users
