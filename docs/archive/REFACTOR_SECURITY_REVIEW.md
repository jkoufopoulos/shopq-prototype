# Security Review: Refactored Files
**Date:** 2025-12-07
**Reviewer:** Claude Security Agent
**Scope:** Recent refactoring of 4 files extracted from larger modules
**Status:** ✅ PASS - No critical or high-severity issues found

---

## Executive Summary

Reviewed 4 recently refactored files for security vulnerabilities:
- `shopq/api/routes/debug_ab_testing.py` - A/B testing debug endpoints
- `shopq/infrastructure/database_schema.py` - Database schema initialization
- `shopq/classification/extractor_patterns.py` - Pattern matching helpers
- `shopq/observability/tracking_reports.py` - Reporting and GCS sync

**Findings:**
- ✅ **SQL Injection:** All queries use parameterized queries correctly
- ✅ **Input Validation:** Proper validation at boundaries (FastAPI schemas, type hints)
- ⚠️ **Authentication:** Debug endpoints lack authentication (MEDIUM priority)
- ⚠️ **PII Logging:** Some subject lines logged (MEDIUM priority)
- ✅ **Connection Management:** Proper use of context managers
- ✅ **Error Handling:** No sensitive information leakage in errors

**Summary:** 0 Critical, 0 High, 2 Medium findings

---

## Detailed Findings

### Medium Priority

#### [M1] Debug Endpoints Lack Authentication
**Severity:** Medium
**Location:** `shopq/api/routes/debug_ab_testing.py` (all endpoints)
**Files Affected:**
- `shopq/api/routes/debug_ab_testing.py:17-42` (get_ab_testing_summary)
- `shopq/api/routes/debug_ab_testing.py:45-102` (get_recent_ab_tests)
- `shopq/api/routes/debug_ab_testing.py:105-193` (get_ab_test_details)

**Evidence:**
```python
@router.get("/ab-testing/summary")
async def get_ab_testing_summary(limit: int = Query(default=100)) -> dict[str, Any]:
    # No authentication dependency - anyone can call this
```

**Risk:**
Debug endpoints expose internal system metrics and A/B test results without authentication. While these don't contain direct PII, they reveal:
- System architecture details (pipeline versions, latency metrics)
- Feature rollout strategy (winner selection algorithms)
- Test volume and success rates

In production, unauthorized access could enable competitive intelligence gathering or inform targeted attacks on the classification pipeline.

**Impact:** Medium - Information disclosure, not direct data breach

**Exploitation Scenario:**
1. Attacker discovers debug endpoint via port scanning or documentation
2. Calls `/api/debug/ab-testing/summary` without authentication
3. Learns about pipeline architecture and performance characteristics
4. Uses information to craft more effective prompt injection attacks

**Fix:**
Add authentication to debug endpoints using existing `require_admin_auth` dependency:

```diff
# shopq/api/routes/debug_ab_testing.py
from fastapi import APIRouter, Query, Depends
+from shopq.api.middleware.auth import require_admin_auth

 @router.get("/ab-testing/summary")
 async def get_ab_testing_summary(
-    limit: int = Query(default=100)
+    limit: int = Query(default=100),
+    _authenticated: bool = Depends(require_admin_auth),
 ) -> dict[str, Any]:

 @router.get("/ab-testing/recent")
 async def get_recent_ab_tests(
-    limit: int = Query(default=20)
+    limit: int = Query(default=20),
+    _authenticated: bool = Depends(require_admin_auth),
 ) -> dict[str, Any]:

 @router.get("/ab-testing/{test_id}")
-async def get_ab_test_details(test_id: str) -> dict[str, Any]:
+async def get_ab_test_details(
+    test_id: str,
+    _authenticated: bool = Depends(require_admin_auth),
+) -> dict[str, Any]:
```

**Recommendation:**
Apply authentication to all `/api/debug/*` endpoints. Consider creating a shared decorator in claude.md's standard practices.

---

#### [M2] PII Exposure in Log Messages
**Severity:** Medium
**Locations:**
- `shopq/observability/tracking_reports.py:92-96` (Entity extraction failures)
- `shopq/observability/tracking_reports.py:103-104` (Unlinked summaries)
- `shopq/classification/extractor_patterns.py:280,302,312,317` (Metadata recovery)
- `shopq/observability/validation.py:112,146-149` (Importance/entity logging)

**Evidence:**
```python
# tracking_reports.py:92-96
for thread in no_entity_critical[:5]:
    logger.warning(
        "  - %s: %s",
        thread["importance"],
        thread["subject"][:60],  # ⚠️ Subject line contains PII
    )

# tracking_reports.py:103-104
for item in unlinked[:5]:
    logger.error("  - %s", item["subject"][:60])  # ⚠️ Subject line
    logger.error("    Summary: %s", item["summary_line"][:80])  # ⚠️ Summary

# extractor_patterns.py:280
logger.warning("   Subject: %s", entity.source_subject[:60])  # ⚠️ Subject

# extractor_patterns.py:312
logger.warning("   Current: '%s'", entity.source_subject)  # ⚠️ Full subject!
```

**Risk:**
Email subject lines can contain PII (names, account numbers, addresses, medical info). Logging subjects exposes this data to:
- Cloud logging systems (Cloud Run → Cloud Logging)
- Log aggregation tools (external SIEM)
- Developers with log access
- Potential log file leaks if misconfigured

Examples of PII in subjects:
- "Your appointment with Dr. Smith on Monday"
- "Payment confirmation for account #12345"
- "Re: Sarah Johnson's performance review"

**Impact:** Medium - Privacy violation, potential GDPR/CCPA breach

**Exploitation Scenario:**
1. Attacker gains read access to Cloud Logging (e.g., stolen service account key)
2. Searches logs for subject lines using pattern matching
3. Extracts PII from log messages
4. Correlates subjects across sessions to build user profiles

**Fix:**
Replace subject line logging with pseudonymous identifiers:

```diff
# tracking_reports.py
 for thread in no_entity_critical[:5]:
     logger.warning(
-        "  - %s: %s",
+        "  - %s: thread_id=%s",
         thread["importance"],
-        thread["subject"][:60],
+        thread.get("thread_id", "unknown")[:20],
     )

# extractor_patterns.py
-logger.warning("   Subject: %s", entity.source_subject[:60])
+logger.warning("   thread_id: %s", entity.source_thread_id[:20])

-logger.warning("   Current: '%s'", entity.source_subject)
+logger.warning("   Current subject length: %d chars", len(entity.source_subject or ""))
```

**Recommendation:**
1. Audit all `logger.info/warning/error` calls for subject/from/snippet logging
2. Replace with non-PII identifiers (thread_id, email_id)
3. Add pre-commit hook to block `logger.*subject` patterns
4. Update claude.md to forbid PII in logs

**Note on Verbose Mode:**
Some PII logging occurs only in `DEBUG=true` mode (validation.py:108-114). While this reduces production exposure, debug logs may still reach production via:
- Emergency debugging sessions
- Misconfigured environment variables
- Local dev → cloud log sync

Recommendation: Remove PII from debug logs entirely, or implement log scrubbing.

---

## Positive Security Findings

### ✅ SQL Injection Prevention

All database queries use parameterized queries correctly:

**Evidence:**
```python
# database_schema.py:192 - Safe parameterized query
cursor.execute(f"PRAGMA table_info({table})")  # ✅ Schema identifier validated at line 187

# Line 187-188: Validation prevents injection
if not table.replace("_", "").isalnum():
    raise ValueError(f"Invalid table name: {table}")

# debug_ab_testing.py:65-77 - Parameterized query
cursor.execute(
    """
    SELECT ... FROM ab_test_runs
    ORDER BY timestamp DESC
    LIMIT ?
    """,
    (limit,),  # ✅ Parameter passed safely
)

# debug_ab_testing.py:133-135 - Parameterized WHERE clause
cursor.execute(
    "SELECT ... FROM ab_test_runs WHERE test_id = ?",
    (test_id,),  # ✅ User input parameterized
)
```

**Note on Schema Identifiers:**
`database_schema.py:192` uses string formatting for table names (`f"PRAGMA table_info({table})"`), which is safe because:
1. Table names come from hardcoded dict (line 165-171)
2. Validated to be alphanumeric + underscore only (line 187-188)
3. SQLite doesn't support parameterized schema identifiers (by design)

**Verdict:** ✅ No SQL injection vulnerabilities

---

### ✅ Connection Management

All database operations use proper context managers:

**Evidence:**
```python
# debug_ab_testing.py:62-79
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    rows = cursor.fetchall()
# ✅ Connection automatically returned to pool

# tracking_reports.py:152-156
with open(output_path, "w", newline="") as f:
    writer = csv.DictWriter(f, ...)
    writer.writeheader()
    writer.writerows(threads)
# ✅ File handle properly closed
```

Connection pooling (from `database.py:122-318`) ensures:
- Connections reused (lines 198-268)
- Temporary connections tracked and limited (line 221-268)
- Pool exhaustion prevents resource leaks (line 224-239)

**Verdict:** ✅ No connection leaks

---

### ✅ Input Validation

FastAPI's type system and Pydantic schemas enforce validation at API boundaries:

**Evidence:**
```python
# debug_ab_testing.py:18,46 - Type-validated inputs
async def get_ab_testing_summary(limit: int = Query(default=100)):
    # FastAPI enforces int type, default value

async def get_ab_test_details(test_id: str):
    # FastAPI enforces string type
```

**Additional Validation:**
- `database_schema.py:187-188` - Alphanumeric table name validation
- `extractor_patterns.py:100-104` - Importance level whitelist

**Verdict:** ✅ Proper input validation

---

### ✅ Error Handling

Error messages don't leak sensitive information:

**Evidence:**
```python
# debug_ab_testing.py:138-139
if not run_row:
    return {"error": f"Test {test_id} not found"}
    # ✅ Generic error, no stack trace or internal state

# database_schema.py:196-197
if missing_cols:
    raise ValueError(f"Table '{table}' missing columns: {missing_cols}")
    # ✅ Schema validation error, no secrets
```

Exception handling in `tracking_reports.py:218-220`:
```python
except Exception as e:
    logger.error("Failed to sync %s to GCS: %s", session_id, e)
    return False
    # ✅ Logs error but doesn't expose secrets
```

**Verdict:** ✅ Safe error handling

---

## Non-Issues (Considered but Dismissed)

### Schema Validation Uses f-strings (NOT A VULNERABILITY)
**Location:** `database_schema.py:192`
**Why Not Vulnerable:**
- Table names from hardcoded dict (not user input)
- Validated alphanumeric + underscore only (line 187-188)
- SQLite PRAGMA doesn't support parameterized identifiers
- Standard practice for schema introspection

---

### Pattern Regex Complexity (NOT A VULNERABILITY)
**Location:** `extractor_patterns.py:18-56`
**Why Not Vulnerable:**
- Patterns compiled at module load (not per-request)
- No user-controlled regex patterns
- Used for extraction, not validation
- ReDoS prevention in `validation.py:32-55` via length limits

---

### GCS Session ID in Path (LOW RISK)
**Location:** `tracking_reports.py:193`
**Code:** `storage_client.upload_session_db(session_id, str(get_db_path()))`
**Why Low Risk:**
- Session IDs are timestamps (`20251108_143022`), not secrets
- GCS bucket requires authentication (Cloud IAM)
- No path traversal risk (session_id validated upstream)
- Standard practice for object storage

---

## Authentication Context

**Current State:**
- Admin endpoints use `require_admin_auth` dependency (rules.py:56,100,137)
- API key from `SHOPQ_ADMIN_API_KEY` environment variable
- Timing-safe comparison with `secrets.compare_digest()` (auth.py:60)
- Optional in development (auth.py:34-35)

**Gap:**
Debug endpoints (`/api/debug/ab-testing/*`) don't use authentication, allowing unauthenticated access to internal metrics.

**Production Configuration:**
Cloud Run startup (app.py:181-186) warns if `SHOPQ_ADMIN_API_KEY` not set:
```python
if not os.getenv("SHOPQ_ADMIN_API_KEY"):
    logger.warning(
        "Security misconfiguration: SHOPQ_ADMIN_API_KEY not set in "
        "production environment. Admin endpoints are unprotected."
    )
```

This warning-only approach means production could deploy without authentication if environment variable omitted.

---

## Recommendations

### Immediate Actions (Within 1 Week)

1. **Add Authentication to Debug Endpoints**
   - Apply fix from [M1] to all debug routes
   - Verify with integration test: `curl -H "Authorization: Bearer invalid" /api/debug/ab-testing/summary` → 403

2. **Reduce PII in Logs**
   - Replace subject logging with thread_id (fix from [M2])
   - Run: `grep -r 'logger.*subject' shopq/` to find remaining instances
   - Update 10 most egregious log statements first

3. **Enforce Admin API Key in Production**
   - Change `auth.py:34-35` from allowing access to raising exception:
     ```diff
     - if not self.api_key:
     -     return True
     + if not self.api_key:
     +     raise HTTPException(
     +         status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
     +         detail="Server misconfiguration: authentication not configured",
     +     )
     ```
   - Deploy validation ensures `SHOPQ_ADMIN_API_KEY` set before Cloud Run starts

### Short-Term (Within 1 Month)

4. **Add Pre-Commit Hook for PII Logging**
   - Create `.pre-commit-config.yaml` rule:
     ```yaml
     - id: no-pii-logging
       name: Block PII in logs
       entry: bash -c 'grep -r "logger.*subject\|logger.*from_field\|logger.*email" --include="*.py" shopq/ && exit 1 || exit 0'
       language: system
     ```

5. **Log Scrubbing for Production**
   - Implement structured logging wrapper that redacts PII fields
   - Example: `logger.info("Processing email", thread_id=..., subject=REDACTED)`

6. **Security Headers Audit**
   - Verify `SecurityHeadersMiddleware` applied to all routes
   - Add CSP nonce for inline scripts if needed
   - Test with: https://securityheaders.com/

### Long-Term (Within 3 Months)

7. **Rate Limiting for Debug Endpoints**
   - Current rate limiter (`api/middleware/rate_limit.py`) applies to all routes
   - Consider stricter limits for debug endpoints (10 req/min vs 100 req/min)

8. **OAuth 2.0 for Admin Access**
   - Current API key auth is simple but inflexible
   - Consider Google IAP (Identity-Aware Proxy) for Cloud Run
   - Enables per-user audit logs and granular permissions

9. **Secrets Management Audit**
   - Verify no secrets in `shopq/data/shopq.db` (user_credentials table uses encrypted_token_json)
   - Rotate `SHOPQ_ADMIN_API_KEY` quarterly
   - Consider Google Secret Manager for centralized secrets

---

## Testing Recommendations

### Manual Security Tests

1. **SQL Injection Test:**
   ```bash
   curl "http://localhost:8080/api/debug/ab-testing/'; DROP TABLE ab_test_runs; --"
   # Expected: 404 (test_id not found) or 422 (type error), NOT 500
   ```

2. **Authentication Bypass Test:**
   ```bash
   curl http://localhost:8080/api/debug/ab-testing/summary
   # Expected: 401/403 (after fix), Currently: 200 (vulnerable)
   ```

3. **Path Traversal Test:**
   ```bash
   curl "http://localhost:8080/api/debug/ab-testing/../../../etc/passwd"
   # Expected: 404, NOT file contents
   ```

### Automated Security Tests

4. **Add to `tests/security/test_auth.py`:**
   ```python
   def test_debug_endpoints_require_auth():
       response = client.get("/api/debug/ab-testing/summary")
       assert response.status_code == 401

       response = client.get(
           "/api/debug/ab-testing/summary",
           headers={"Authorization": "Bearer invalid"},
       )
       assert response.status_code == 403
   ```

5. **PII Redaction Test:**
   ```python
   def test_no_pii_in_logs(caplog):
       # Trigger entity extraction failure
       process_email({"subject": "SENSITIVE DATA", "from": "user@example.com"})

       # Verify logs don't contain sensitive data
       log_output = "\n".join(record.message for record in caplog.records)
       assert "SENSITIVE DATA" not in log_output
       assert "user@example.com" not in log_output
   ```

---

## Appendix: Files Reviewed

### Refactored Files (Primary Review Scope)
1. `shopq/api/routes/debug_ab_testing.py` (194 lines)
2. `shopq/infrastructure/database_schema.py` (200 lines)
3. `shopq/classification/extractor_patterns.py` (320 lines)
4. `shopq/observability/tracking_reports.py` (221 lines)

### Supporting Files (Context Review)
5. `shopq/infrastructure/database.py` (585 lines)
6. `shopq/api/middleware/auth.py` (83 lines)
7. `shopq/api/routes/debug.py` (100 lines, partial)
8. `shopq/observability/validation.py` (150 lines, partial)
9. `shopq/storage/cloud.py` (100 lines, partial)

---

## Sign-Off

**Reviewed By:** Claude Security Agent
**Date:** 2025-12-07
**Methodology:** Evidence-based static analysis + data flow tracing
**Confidence:** High (concrete findings with code references)

**Recommendation:** Approve deployment after applying [M1] authentication fix. [M2] PII logging can be addressed in next sprint without blocking.

**Next Review:** After implementing recommendations (target: 2025-12-14)
