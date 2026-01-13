# Multi-Tenancy Preparation Plan

**Status**: 📋 Planned (Not yet implemented)
**Target Date**: Before multi-user launch
**Current State**: Single-user MVP with `user_id='default'`

## Current Architecture

### User ID Usage

**Database schema** ✅ Ready:
```sql
CREATE TABLE rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT DEFAULT 'default',  -- ✅ Multi-tenant ready
    pattern_type TEXT NOT NULL,
    ...
);
```

**Code patterns** ⚠️ Needs work:
```python
# Current: Hardcoded 'default' in function signatures
def get_rules(user_id: str = "default") -> list[dict]:
    ...

# Current: No authentication in API
@app.post("/api/classify")
async def classify(payload: ClassifyRequest):
    # user_id not extracted from auth token
    rules = get_rules(user_id="default")
    ...
```

## Phase 1: Add Authentication Middleware (P0.3)

### Step 1.1: Create Auth Dependency

Create `mailq/auth.py`:

```python
"""Authentication utilities for FastAPI"""

from fastapi import HTTPException, Header
from typing import Optional
import os

def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """
    Extract user_id from Authorization header.

    For MVP: Returns 'default' if no auth header (backward compatible)
    For production: Validates OAuth token and extracts user_id
    """
    # MVP mode: No auth required
    if os.getenv("AUTH_REQUIRED") != "true":
        return "default"

    # Production mode: Validate token
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.replace("Bearer ", "")

    # TODO: Validate OAuth token with Google
    # For now, extract email from token (placeholder)
    user_id = validate_and_extract_user_id(token)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user_id


def validate_and_extract_user_id(token: str) -> Optional[str]:
    """
    Validate OAuth token and extract user_id (email).

    TODO: Implement actual Google OAuth validation
    - Verify token with Google tokeninfo endpoint
    - Extract email from token
    - Cache validated tokens (short TTL)
    """
    # Placeholder implementation
    return None  # Replace with actual OAuth validation
```

### Step 1.2: Update API Endpoints

**Pattern**: Add auth dependency to all endpoints

```python
# mailq/api.py
from mailq.auth import get_current_user_id
from fastapi import Depends

@app.post("/api/classify")
async def classify(
    payload: ClassifyRequest,
    user_id: str = Depends(get_current_user_id)  # ✅ Extracted from token
):
    """Classify email with user-specific rules"""
    rules = get_rules(user_id=user_id)  # ✅ User-specific rules
    ...
```

**Endpoints to update** (18 endpoints):
- `/api/classify` ✅
- `/api/organize` ✅
- `/api/feedback` ✅
- `/api/rules` (GET, POST, PUT, DELETE) ✅
- `/api/pending-rules` ✅
- `/api/categories` ✅
- `/api/tracking/*` ✅
- `/api/verify/*` ✅
- `/api/linker/*` ✅

**Exempt endpoints** (no auth needed):
- `/health` ✅ Public
- `/` ✅ Public
- `/api/debug/*` ⚠️ Add IP whitelist or admin auth

### Step 1.3: Backward Compatibility

**Environment variable**: `AUTH_REQUIRED=false` (default for development)

```python
# Development: No auth required
AUTH_REQUIRED=false  # Returns 'default' for all requests

# Production: Auth required
AUTH_REQUIRED=true   # Validates OAuth tokens, extracts user_id
```

**Migration path**:
1. Deploy with `AUTH_REQUIRED=false` (no behavior change)
2. Test with `AUTH_REQUIRED=true` in development
3. Enable `AUTH_REQUIRED=true` in production after testing

## Phase 2: User ID Enforcement (Current Task)

### Step 2.1: Audit Current Usage

**Found 20+ locations with `user_id="default"`**:

```bash
# Search results
mailq/rules_engine.py:        user_id: str = "default"  # 5 occurrences
mailq/rules_manager.py:       user_id: str = "default"  # 4 occurrences
mailq/category_manager.py:    user_id: str = "default"  # 4 occurrences
mailq/memory_classifier.py:   user_id: str = "default"  # 3 occurrences
mailq/api.py:                 user_id: str = "default"  # 1 occurrence
mailq/api_feedback.py:        user_id: str = "default"  # 3 occurrences
```

### Step 2.2: Refactoring Strategy

**Option A**: Keep `user_id="default"` in signatures (RECOMMENDED)

✅ **Pros**:
- Backward compatible (no breaking changes)
- Works for single-user MVP
- Easy migration path

```python
# Function signatures stay the same
def get_rules(user_id: str = "default") -> list[dict]:
    ...

# API layer passes real user_id
@app.get("/api/rules")
async def get_rules_endpoint(user_id: str = Depends(get_current_user_id)):
    rules = get_rules(user_id=user_id)  # ✅ Passes real user_id
    ...
```

**Option B**: Remove defaults, require explicit user_id

❌ **Cons**:
- Breaking change for all function calls
- Requires updating 100+ call sites
- High risk of missing locations

### Step 2.3: Implementation Plan

**Recommended: Minimal changes, use dependency injection**

1. ✅ Add `mailq/auth.py` (auth dependency)
2. ✅ Update API endpoints to use `Depends(get_current_user_id)`
3. ✅ Keep `user_id="default"` in function signatures (backward compatible)
4. ✅ Set `AUTH_REQUIRED=false` for MVP (no behavior change)
5. ⏭️ Later: Enable `AUTH_REQUIRED=true` for multi-user

**Files to change**:
- `mailq/auth.py` (NEW) - Auth dependency
- `mailq/api.py` - Add auth to endpoints
- `mailq/api_feedback.py` - Add auth to endpoints
- `mailq/api_tracking.py` - Add auth to endpoints
- `mailq/api_verify.py` - Add auth to endpoints
- `mailq/api_linker.py` - Add auth to endpoints

## Phase 3: Database Indexes (Performance)

### Add user_id indexes

```sql
-- Add indexes for user_id queries
CREATE INDEX IF NOT EXISTS idx_rules_user_id ON rules(user_id, active);
CREATE INDEX IF NOT EXISTS idx_email_threads_user_id ON email_threads(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_digest_sessions_user_id ON digest_sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quality_issues_user_id ON quality_issues(user_id, created_at DESC);
```

**Migration script**: `mailq/scripts/add_user_indexes.py`

```python
import sqlite3

def add_indexes():
    conn = sqlite3.connect("mailq/data/mailq.db")
    cursor = conn.cursor()

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_rules_user_id ON rules(user_id, active)",
        "CREATE INDEX IF NOT EXISTS idx_email_threads_user_id ON email_threads(user_id, timestamp DESC)",
        # ... more indexes
    ]

    for sql in indexes:
        print(f"Creating index: {sql}")
        cursor.execute(sql)

    conn.commit()
    print("✅ All indexes created")

if __name__ == "__main__":
    add_indexes()
```

## Phase 4: Tenant Isolation Tests

### Add test suite for multi-tenancy

Create `tests/unit/test_multi_tenancy.py`:

```python
"""Test tenant isolation"""

import pytest
from mailq.rules_manager import get_rules, add_rule

def test_rules_isolated_by_user():
    """Rules for user A should not be visible to user B"""
    # Add rule for user A
    add_rule(
        pattern_type="subject",
        pattern="confidential",
        category="critical",
        user_id="user_a@example.com"
    )

    # User A should see their rule
    rules_a = get_rules(user_id="user_a@example.com")
    assert len(rules_a) > 0
    assert any(r["pattern"] == "confidential" for r in rules_a)

    # User B should NOT see user A's rule
    rules_b = get_rules(user_id="user_b@example.com")
    assert not any(r["pattern"] == "confidential" for r in rules_b)

def test_feedback_isolated_by_user():
    """Feedback for user A should not affect user B's model"""
    # TODO: Implement feedback isolation test
    pass

def test_digest_sessions_isolated_by_user():
    """Digest sessions should be user-specific"""
    # TODO: Implement digest isolation test
    pass
```

Run tests:
```bash
pytest tests/unit/test_multi_tenancy.py -v
```

## Phase 5: OAuth Token Validation

### Implement Google OAuth validation

```python
# mailq/auth.py
import requests
from functools import lru_cache
from datetime import datetime, timedelta

# Token cache (TTL: 5 minutes)
_token_cache = {}

def validate_and_extract_user_id(token: str) -> Optional[str]:
    """
    Validate OAuth token with Google and extract user email.

    Uses tokeninfo endpoint:
    https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=<token>
    """
    # Check cache first
    if token in _token_cache:
        cached_email, expires_at = _token_cache[token]
        if datetime.now() < expires_at:
            return cached_email
        else:
            del _token_cache[token]

    # Validate token with Google
    try:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v3/tokeninfo",
            params={"access_token": token},
            timeout=5
        )

        if response.status_code != 200:
            return None

        token_info = response.json()

        # Verify token is for Gmail scope
        required_scope = "https://www.googleapis.com/auth/gmail.modify"
        if required_scope not in token_info.get("scope", ""):
            return None

        email = token_info.get("email")
        if not email:
            return None

        # Cache token (5 minutes TTL)
        expires_at = datetime.now() + timedelta(minutes=5)
        _token_cache[token] = (email, expires_at)

        return email

    except Exception as e:
        print(f"❌ Token validation error: {e}")
        return None
```

## Phase 6: Extension Updates

### Update extension to send Authorization header

**Current**: Extension already sends Authorization header ✅

```javascript
// extension/background.js
const token = await getAuthToken();
const response = await fetch(`${CONFIG.MAILQ_API_URL}/api/classify`, {
  headers: {
    'Authorization': `Bearer ${token}`  // ✅ Already implemented!
  }
});
```

**No changes needed in extension** - already compatible!

## Rollout Plan

### Step-by-step deployment

**Week 1**: Infrastructure prep
1. ✅ Create `mailq/auth.py` with MVP mode (`AUTH_REQUIRED=false`)
2. ✅ Update API endpoints to accept auth dependency
3. ✅ Deploy with `AUTH_REQUIRED=false` (no behavior change)
4. ✅ Test in development

**Week 2**: Database optimization
5. ✅ Add `user_id` indexes to database
6. ✅ Run performance tests (query times < 100ms)

**Week 3**: Testing
7. ✅ Add multi-tenancy unit tests
8. ✅ Manual testing with 2 test accounts
9. ✅ Verify tenant isolation (no data leakage)

**Week 4**: Production rollout
10. ✅ Enable `AUTH_REQUIRED=true` in staging
11. ✅ Test with real OAuth tokens
12. ✅ Enable `AUTH_REQUIRED=true` in production
13. ✅ Monitor for auth errors

## Monitoring & Validation

### Metrics to track

**Authentication**:
- Auth success rate: > 99%
- Auth latency: < 200ms
- Token validation errors: < 1%

**Tenant isolation**:
- Cross-tenant queries: 0 (log any violations)
- User-specific rule count: > 0 for active users
- Feedback isolation: 100% (no cross-user learning)

**Performance**:
- Query latency with `user_id` filters: < 100ms
- Index hit rate: > 95%
- Database size growth: Linear with users

### Logging

**Auth events**:
```python
# Log successful auth
logger.info(f"User authenticated: {user_id}")

# Log auth failures
logger.warning(f"Auth failed: {error_type} - {token[:10]}...")

# Log cross-tenant access attempts (CRITICAL)
logger.error(f"SECURITY: User {user_id} attempted to access data for {other_user_id}")
```

## Rollback Plan

### If issues arise

**Symptom**: Auth errors, users can't access API

**Rollback**:
```bash
# Disable auth immediately
export AUTH_REQUIRED=false
# Restart service
systemctl restart mailq-api
```

**Symptom**: Performance degradation after index addition

**Rollback**:
```sql
-- Drop indexes if causing issues
DROP INDEX IF EXISTS idx_rules_user_id;
DROP INDEX IF EXISTS idx_email_threads_user_id;
```

**Symptom**: Data leakage between users

**Emergency action**:
1. Disable multi-user access immediately (`AUTH_REQUIRED=false`)
2. Investigate which query leaked data
3. Fix query, add tenant isolation test
4. Re-enable after verification

## Checklist

**Before enabling AUTH_REQUIRED=true**:

- [ ] `mailq/auth.py` implemented with OAuth validation
- [ ] All API endpoints use `Depends(get_current_user_id)`
- [ ] Database indexes added for `user_id`
- [ ] Multi-tenancy unit tests passing
- [ ] Manual testing with 2+ users (no data leakage)
- [ ] Monitoring dashboard created
- [ ] Rollback plan documented and tested
- [ ] Team trained on auth troubleshooting

## Related Documentation

- **Database Policy**: `/docs/DATABASE_POLICY.md`
- **Extension Security**: `/docs/EXTENSION_SECURITY.md`
- **API Documentation**: `/mailq/api.py`
- **Auth Module**: `/mailq/auth.py` (to be created)

---

**Status**: 📋 Planning phase
**Next Action**: Create `mailq/auth.py` with MVP mode
**Owner**: See `/CONTRIBUTING.md`
