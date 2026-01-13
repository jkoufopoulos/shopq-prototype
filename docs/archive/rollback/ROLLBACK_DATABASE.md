# Database Rollback Procedure

**Last Updated**: 2025-11-12
**Owner**: Infrastructure Team
**Purpose**: Emergency rollback procedure for database-related deployments

---

## When to Rollback

Trigger rollback if you observe:

1. **Critical Failures**:
   - Application fails to start (database init errors)
   - Database schema validation fails on startup
   - Connection pool exhaustion (> 80% usage sustained)
   - WAL file growing unbounded (> 100MB in Cloud Run)

2. **Data Loss Indicators**:
   - Missing records in email_threads table
   - Digest sessions not being saved
   - Tracking data incomplete

3. **Performance Degradation**:
   - Database lock errors (> 5% of requests)
   - Query timeouts (> 30s)
   - API response time > 5s

---

## Rollback Steps

### Step 1: Identify Target Version

```bash
# View recent commits
git log --oneline -10

# Identify the last known good commit (before database changes)
# Example: If rolling back database consolidation, target the commit before it
```

### Step 2: Rollback Cloud Run Deployment

```bash
# Option A: Rollback to previous revision
gcloud run services update-traffic shopq-api \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region=us-central1

# Option B: Deploy specific commit
git checkout <last-good-commit>
./deploy.sh

# Verify rollback
gcloud run services describe shopq-api --region=us-central1 | grep "Revision:"
```

### Step 3: Verify Application Health

```bash
# Check if API is responding
curl https://shopq-api-<project-id>.run.app/health

# Check database health
curl https://shopq-api-<project-id>.run.app/health/db

# Expected response:
# {
#   "status": "healthy",
#   "pool": {
#     "pool_size": 5,
#     "available": 4,
#     "in_use": 1,
#     "usage_percent": 20.0,
#     "closed": false
#   }
# }
```

### Step 4: Monitor for Issues

```bash
# Tail Cloud Run logs
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=shopq-api" --format=json

# Look for:
# - "Database initialization complete" (should appear within 5s of startup)
# - No "Database schema validation failed" errors
# - No "Connection pool exhausted" errors
```

### Step 5: Restore Database (If Needed)

⚠️ **ONLY if data loss occurred and you have backups**

```bash
# Stop the application first
gcloud run services delete shopq-api --region=us-central1

# Restore database from backup (if using Cloud SQL)
gcloud sql backups restore <backup-id> --instance=<instance-name>

# Or restore from local backup (if using SQLite)
gsutil cp gs://mailq-backups/mailq-<timestamp>.db /app/shopq/data/shopq.db

# Redeploy application
./deploy.sh
```

---

## Database Schema Rollback

If schema changes were made (new tables/columns), you may need to:

### Option 1: Keep New Schema (Recommended)

- New tables are created with `CREATE TABLE IF NOT EXISTS`
- Application code checks for columns before using them
- **No manual schema rollback needed** - old code will ignore new tables

### Option 2: Manual Schema Rollback (If Necessary)

⚠️ **Only if Option 1 doesn't work**

```python
# Connect to production database
import sqlite3
conn = sqlite3.connect("/app/shopq/data/shopq.db")

# Drop new tables (example - adjust as needed)
conn.execute("DROP TABLE IF EXISTS new_table_name")

# Remove new columns (SQLite doesn't support DROP COLUMN - need to recreate)
# 1. Create backup table
conn.execute("CREATE TABLE rules_backup AS SELECT id, pattern_type, pattern, category FROM rules")

# 2. Drop original table
conn.execute("DROP TABLE rules")

# 3. Rename backup
conn.execute("ALTER TABLE rules_backup RENAME TO rules")

conn.commit()
conn.close()
```

---

## Rollback Validation Checklist

After rollback, verify:

- [ ] Application starts successfully (no startup errors in logs)
- [ ] `/health` endpoint returns 200 OK
- [ ] `/health/db` shows healthy pool status
- [ ] Email classification works (test with /api/classify endpoint)
- [ ] Digest generation works (test with /api/summary endpoint)
- [ ] No database lock errors in logs (check for 15 minutes)
- [ ] Connection pool usage < 50% (check /health/db)

---

## Specific Rollback Scenarios

### Scenario 1: Database Consolidation Rollback

**What Changed**: Migrated from 10+ databases to single shopq.db

**Rollback Target**: Commit before feat/bridge-mode-ingestion merge

```bash
# Find the merge commit
git log --grep="merge.*bridge-mode" --oneline

# Rollback to commit before merge
git checkout <commit-before-merge>
./deploy.sh
```

**Database Actions**: None needed - old code still works with new schema

---

### Scenario 2: Connection Pool Changes Rollback

**What Changed**: Added WAL checkpointing, fixed race conditions, added retry logic

**Rollback Target**: Commit before "feat(performance): Add WAL checkpointing"

```bash
git checkout <commit-before-pool-changes>
./deploy.sh
```

**Database Actions**: None needed - schema unchanged

**Post-Rollback**: May see database lock errors return (this is expected)

---

### Scenario 3: Schema Validation Moved to Startup

**What Changed**: Validation now runs at startup instead of import time

**Rollback Target**: Commit before validation changes

**Post-Rollback**: Application may start even with invalid schema (less safe)

---

## Emergency Contacts

If rollback fails or data loss is critical:

1. **Justin** (Product Owner): [contact details]
2. **Architecture Team**: [contact details]
3. **Google Cloud Support**: Open P1 ticket if Cloud Run issues

---

## Post-Rollback Actions

After successful rollback:

1. **Create Incident Report**: Document what went wrong, impact, rollback time
2. **Root Cause Analysis**: Why did the deployment fail? What tests missed it?
3. **Update Monitoring**: Add alerts for the failure condition
4. **Fix Forward Plan**: Create a plan to re-deploy the changes safely
5. **Update This Doc**: Add lessons learned to prevent future issues

---

## Prevention Checklist (Use Before Deploy)

Before deploying database changes, verify:

- [ ] All tests pass locally (unit + integration)
- [ ] Schema changes are backward compatible (old code can ignore new tables)
- [ ] Database initialization is idempotent (safe to run multiple times)
- [ ] Startup validation fails fast (doesn't let bad deploys run)
- [ ] Monitoring is in place (/health/db endpoint works)
- [ ] Backup exists (if using Cloud SQL) or database is small enough to rebuild
- [ ] Rollback procedure tested in staging (if available)

---

## Appendix: Useful Commands

### Check Database Size

```bash
# In Cloud Run container
ls -lh /app/shopq/data/shopq.db*

# Expected:
# shopq.db      - main database (< 50MB is normal)
# shopq.db-wal  - write-ahead log (< 10MB is normal)
# shopq.db-shm  - shared memory (< 1MB is normal)
```

### Force WAL Checkpoint

```bash
# In Python shell (inside Cloud Run container)
from shopq.config.database import checkpoint_wal
stats = checkpoint_wal()
print(f"Freed {stats['bytes_freed'] / 1024 / 1024:.1f} MB")
```

### Check Connection Pool Stats

```bash
# Via API
curl https://shopq-api-<project-id>.run.app/health/db

# In Python shell
from shopq.config.database import get_pool_stats
print(get_pool_stats())
```

---

**Maintenance**: Review quarterly. Update after each database-related incident or rollback.
