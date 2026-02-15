# Phase 1: Backend Consolidation Plan

> **Status**: DRAFT — awaiting approval
> **Precondition**: Phase 0 (Safety & Config) complete — 20 commits on main
> **Constraint**: App must remain demoable after every commit. No big-bang rewrites.
> **Doctrine**: Seams before Splits — encapsulate behind a facade in the same file before moving code to new modules.

---

## 1. Behavioral Invariants (Non-Negotiable)

These MUST be preserved through every commit in Phase 1. Any change that violates an invariant is a bug.

### API Response Shapes

| Endpoint | Response Model | Load-Bearing Fields (extension reads these) |
|----------|---------------|---------------------------------------------|
| `GET /api/returns` | `ReturnCardListResponse` | `cards[]`, `total`, `expiring_soon_count` |
| `GET /api/returns/expiring` | `list[ReturnCardResponse]` | Array of card objects |
| `GET /api/returns/counts` | `StatusCountsResponse` | `active`, `expiring_soon`, `expired`, `returned`, `dismissed`, `total` |
| `GET /api/returns/{id}` | `ReturnCardResponse` | All 21 card fields |
| `POST /api/returns` | `ReturnCardResponse` (201) | Full card object |
| `PUT /api/returns/{id}/status` | `ReturnCardResponse` | Full card object |
| `PATCH /api/returns/{id}` | `ReturnCardResponse` | At minimum `return_by_date` |
| `DELETE /api/returns/{id}` | 204 No Content | Empty body |
| `POST /api/returns/process` | `ProcessEmailResponse` | `success`, `stage_reached`, `rejection_reason`, `card` |
| `POST /api/returns/process-batch` | `ProcessBatchResponse` | `success`, `cards[]`, `stats` |
| `POST /api/returns/refresh-statuses` | `dict` | `updated_count`, `message` |

### Status Codes

- `200` for successful reads and updates
- `201` for card creation via `POST /api/returns`
- `204` for successful `DELETE`
- `400` for invalid status values
- `404` when card not found OR ownership check fails (no information leakage)
- `422` for Pydantic validation errors (sanitized)
- `500` for unhandled exceptions

### Dedup Invariants

1. **Strategy order**: order_number match → item_summary fuzzy match → email_id match. Never reorder.
2. **Order number conflict prevents merge**: If new and existing order_numbers differ, skip merge entirely (create new card).
3. **Dismissed cards invisible to dedup**: `find_by_order_key` excludes `status='dismissed'`; `find_by_item_summary` excludes `dismissed` AND `returned`.
4. **source_email_ids is append-only**: Email IDs are added, never removed.
5. **Batch vs single email_id check**: Batch loops ALL `source_email_ids`; single checks only the current `email_id`.

### Merge Precedence Rules

| Field | Rule | Condition |
|-------|------|-----------|
| `source_email_ids` | APPEND new | Always (if not already present) |
| `delivery_date` | NEW wins | Only if existing is NULL |
| `return_by_date` | NEW wins | Only if existing is NULL OR delivery_date was just updated |
| `item_summary` | LONGER wins | `len(new) > len(existing)` |
| `evidence_snippet` | NEW wins (if has keywords) | Contains "return", "refund", "days", or "policy" |
| `return_portal_link` | NEW wins | Only if existing is NULL |
| `shipping_tracking_link` | NEW wins | Only if existing is NULL |
| `updated_at` | Set to NOW | Always |

### Pipeline Stage Contract

- Stage 1 (Filter): No LLM call. Returns `FilterResult`.
- Stage 2 (Classifier): LLM call with retry. Returns `ReturnabilityResult`. On LLM failure: **REJECT** (strict).
- Stage 3 (Extractor): LLM call with retry. Returns `ExtractedFields`. On LLM failure: **fall back to rules-only** (permissive).
- Budget check between Stage 1 and Stage 2.

### Extension-Facing Contract Assumptions

- Extension maps `card.id` → `order_key`, `card.merchant` → `merchant_display_name`, `card.status` → `order_status`
- Extension reads `response.stage_reached` from `POST /api/returns/process` (logged only, not branched on)
- Extension reads `stats.rejected_filter`, `stats.rejected_classifier`, `stats.cards_created`, `stats.cards_merged` from batch response

---

## 2. Risk Analysis (Steps 1.5–1.8)

### Step 1.5: Create Returns Service Shell (Pass-Through)

| Risk | Likelihood | Impact | Prevention |
|------|-----------|--------|------------|
| Import cycle between routes ↔ service ↔ repository | Low | Server won't start | Service imports repository only; routes import service only. Verify with `python -c "from reclaim.api.routes.returns import router"`. |
| Method signature mismatch (service wraps repo incorrectly) | Medium | Wrong data returned | Service methods return EXACTLY what repository methods return. No transformation in this step. |
| Missing a route handler (some routes still call repo directly) | Medium | Inconsistent code paths | Checklist: every `ReturnCardRepository.xxx()` call in returns.py must be replaced. Grep for residual direct calls after commit. |

**Rollback**: `git revert` — service is pure pass-through, reverting restores direct repo calls.

### Step 1.6: Move Ownership Verification to Service

| Risk | Likelihood | Impact | Prevention |
|------|-----------|--------|------------|
| Ownership check raises different exception type | Medium | Status code changes (e.g., 500 instead of 404) | Service raises `HTTPException(404)` — same as current route code. Verify with curl for wrong-user case. |
| Missing a route handler (some still have inline check) | Low | Inconsistent security | Grep for `card.user_id` in returns.py after commit — should find zero matches. |

**Rollback**: `git revert` — ownership logic is small and self-contained.

### Step 1.7: Move Dedup/Merge to Service

| Risk | Likelihood | Impact | Prevention |
|------|-----------|--------|------------|
| **Dedup strategy order changes** | HIGH | Silent wrong merges | Extract existing code block verbatim into service method. Do NOT refactor logic in the same commit. Diff route before/after to confirm only delegation changed. |
| **Batch vs single email_id check diverges** | HIGH | Batch dedup breaks | Service method takes a parameter `source_email_ids: list[str]` — single endpoint passes `[email_id]`, batch passes the full list. The loop-over-email-ids logic goes into the service, not the route. |
| **Merge field dict changes** | Medium | Data loss on merge | `new_data` dict construction moves verbatim. Verify with golden email set. |
| **Response shape changes** | Medium | Extension breaks | Routes still construct their own response models after calling service. Service returns `(card, is_new)` tuple; route wraps it in `ProcessEmailResponse` or `ProcessBatchResponse`. |

**Prevention tactic**: Introduce a `USE_SERVICE_DEDUP = True` flag in config.py. Both old (inline) and new (service) code paths exist for one commit. Flag defaults to True. If anything breaks, set to False to revert without code changes.

**Rollback**: Set `USE_SERVICE_DEDUP = False` in config.py, or `git revert`.

### Step 1.8: Move Merge Logic Out of Repository

| Risk | Likelihood | Impact | Prevention |
|------|-----------|--------|------------|
| **Merge precedence rules change** | HIGH | Delivery dates, return dates silently wrong | Move `merge_email_into_card()` body into service method verbatim. Repository gets a thin `update_card_fields(card_id, updates: dict)` method. Service calls repo.update_card_fields() with the computed updates dict. |
| **Transaction boundary shifts** | Medium | Partial updates on crash | Ensure service method wraps the read-compute-write in a single `db_transaction()` block, same as current repo method. |
| **`find_by_item_summary()` fuzzy matching changes** | Low | Dedup misses or false matches | See Section 9: keep `find_by_item_summary()` in repository as a query primitive. Only move the "policy" (order number conflict check) to service. |

**Rollback**: `git revert` — repo still has the old method until cleanup commit.

---

## 3. Smoke Test Matrix

Run after every step. Items marked with a step number are newly relevant at that step but should continue to pass in all subsequent steps.

| # | Test Action | Expected Result | Steps |
|---|-------------|-----------------|-------|
| S1 | `uv run python -c "from reclaim.api.app import app; print('OK')"` | Prints `OK`, no import errors | ALL |
| S2 | `curl -s localhost:8000/health \| jq .status` | `"healthy"` | ALL |
| S3 | `curl -s localhost:8000/debug/stats \| jq .returns.total` | Integer (matches DB) | ALL |
| S4 | `curl -s localhost:8000/api/returns -H "Authorization: Bearer TOKEN" \| jq '.cards \| length'` | Integer, returns list of cards | 1.5+ |
| S5 | `curl -s -X PUT localhost:8000/api/returns/{id}/status -H "Content-Type: application/json" -d '{"status":"returned"}' \| jq .status` | `"returned"` | 1.6+ |
| S6 | `curl -s -X PUT localhost:8000/api/returns/{id}/status -H "Authorization: Bearer WRONG_USER"` → check status code | `404` (ownership rejection) | 1.6+ |
| S7 | Process golden email via `POST /api/returns/process` → check `stage_reached` and card fields | Matches golden baseline | 1.7+ |
| S8 | Process same golden email set via `POST /api/returns/process-batch` → compare `stats` | `cards_created` + `cards_merged` match single-process run | 1.7+ |
| S9 | Process same email twice via `/process` → second response should show merge (not new card) | `card.source_email_ids` contains both email IDs | 1.7+ |
| S10 | **Gmail Demo Lock**: Load extension in Gmail → sidebar shows orders → mark one "Returned" → refresh page → "Returned" persists, no duplicates | Visual check | ALL |

### Single-vs-Batch Parity Check (S7/S8)

1. Clear test data: delete all cards for test user
2. Process golden emails one-by-one via `POST /api/returns/process`
3. Record: cards created, card IDs, field values
4. Clear test data again
5. Process same emails via `POST /api/returns/process-batch`
6. Compare: same number of cards, same field values, same dedup behavior

---

## 4. Golden Email Set

### File Path

```
tests/fixtures/golden_emails.json
```

### Structure

```json
{
  "description": "Fixed email set for Phase 1 regression testing",
  "created": "2026-02-08",
  "emails": [
    {
      "id": "golden_order_confirmation",
      "email_id": "test_email_001",
      "from_address": "auto-confirm@amazon.com",
      "subject": "Your Amazon.com order #112-1234567-8901234",
      "body": "Your order has been placed. Item: Wireless Headphones. Order total: $49.99. Estimated delivery: Feb 15.",
      "expected": {
        "stage_reached": "complete",
        "merchant_domain": "amazon.com",
        "order_number": "112-1234567-8901234",
        "item_summary_contains": "Wireless Headphones"
      }
    },
    {
      "id": "golden_shipping_notification",
      "email_id": "test_email_002",
      "from_address": "ship-confirm@amazon.com",
      "subject": "Your Amazon.com order has shipped",
      "body": "Your order #112-1234567-8901234 has shipped. Wireless Headphones. Delivery expected Feb 15. Track: https://track.amazon.com/123",
      "expected": {
        "stage_reached": "complete",
        "should_merge_with": "golden_order_confirmation",
        "merge_reason": "same order_number"
      }
    },
    {
      "id": "golden_newsletter_reject",
      "email_id": "test_email_003",
      "from_address": "deals@marketing.amazon.com",
      "subject": "Top deals this week",
      "body": "Check out our weekly deals and promotions!",
      "expected": {
        "stage_reached": "filter",
        "success": false
      }
    },
    {
      "id": "golden_different_merchant",
      "email_id": "test_email_004",
      "from_address": "noreply@target.com",
      "subject": "Order confirmed #T-98765",
      "body": "Thanks for your Target order! Item: Running Shoes, $79.99. Return within 90 days.",
      "expected": {
        "stage_reached": "complete",
        "merchant_domain": "target.com",
        "order_number": "T-98765"
      }
    }
  ]
}
```

### Usage Procedure

1. Before each step (1.5–1.8): Run golden set through `POST /api/returns/process` one-by-one, capture responses
2. After code change: Run same set, diff responses against baseline
3. Key checks: `stage_reached` values match, card counts match, merge behavior matches
4. The fixture file is committed to the repo and never modified during Phase 1

---

## 5. Dead Code Deletion Proof (Step 1.1)

### Item 1: `reclaim/shared/pipeline.py`

**Evidence it's safe to remove:**
- `grep -r "from reclaim.shared.pipeline" reclaim/` → **zero matches**
- `grep -r "from reclaim.shared import pipeline" reclaim/` → **zero matches**
- `grep -r "import pipeline" reclaim/` → **zero matches**
- No dynamic imports (`importlib`) reference this module
- Module imports `reclaim.storage.checkpoint`, `reclaim.gmail.client`, `reclaim.storage.models` — these are NOT exclusively used by pipeline.py, so removing it has no side effects on other modules
- The file was a previous pipeline design superseded by `reclaim/returns/extractor.py`

**Verdict**: SAFE TO DELETE. No references anywhere.

### Item 2: `/api/organize` in `rate_limit.py`

**Evidence it's safe to remove:**
- `grep -r "api/organize" reclaim/` → Only in `rate_limit.py` (lines 7, 186, 263, 266, 344, 367, 368)
- `grep -r "organize" extension/` → **zero matches**
- No route definition for `/api/organize` anywhere in codebase
- The email-count rate limiting code (lines 263-310, 344-370) is entirely gated behind `if request.url.path == "/api/organize"` — it never executes
- This code block also accesses `request._receive` (private Starlette attribute) — removing it eliminates a fragility

**Verdict**: SAFE TO REMOVE the dead code block. Keep the rest of rate_limit.py intact. Remove docstring references to `/api/organize`.

### Item 3: `extraction_method` field in `ExtractedFields`

**Evidence — NOT dead:**
- `field_extractor.py:77` — defined
- `field_extractor.py:365` — set to `"hybrid"` or `"rules"`
- `field_extractor.py:373` — **LOGGED via `log_event("returns.extractor.complete", method=result.extraction_method)`**

**Verdict**: DEFER. Field is used in telemetry logging. Removing it loses observability signal. Not worth the risk.

---

## 6. Enum Change Safety (`stage_reached`)

### Serialization Analysis

| Surface | Serialized? | Details |
|---------|-------------|---------|
| API response (`ProcessEmailResponse`) | YES | `stage_reached: str` field in Pydantic model (returns.py:510) |
| Database | NO | Not stored in any column |
| Telemetry | NO | `log_event()` uses hardcoded strings, not the field |
| Extension | YES (logged) | `scanner.js:525` logs `response.stage_reached` to console |
| Tests | YES (asserted) | `test_extraction_pipeline.py` asserts exact string values |

### Approach: `str` Enum (Backward-Compatible)

```python
class ExtractionStage(str, Enum):
    NONE = "none"
    FILTER = "filter"
    CLASSIFIER = "classifier"
    CANCELLATION_CHECK = "cancellation_check"
    EXTRACTOR = "extractor"
    COMPLETE = "complete"
    ERROR = "error"
```

Using `str` mixin means:
- JSON serialization produces the same string values (`"filter"`, `"complete"`, etc.)
- Pydantic auto-serializes `.value` — no API response change
- Extension sees identical strings
- Python comparisons `stage == "filter"` still work (str Enum inherits `__eq__` from str)

**Risk**: Zero. `str` Enum is fully backward-compatible at all boundaries.

---

## 7. Database Housekeeping Safety (Step 1.9)

### Migration Risk

- SQLite database is at `reclaim/data/reclaim.db`
- No migration framework exists; schema uses `CREATE TABLE IF NOT EXISTS`
- Phase 1 changes are **additive only**: adding an index, moving table creation

### Changes

**1. Add compound index:**
```sql
CREATE INDEX IF NOT EXISTS idx_return_cards_user_status_date
ON return_cards(user_id, status, return_by_date);
```

- `IF NOT EXISTS` makes this idempotent — safe to run on existing DB
- Index creation on existing data: instant for small tables (<10K rows), seconds for larger
- Does NOT lock table for writes (SQLite creates index in a single transaction)

**2. Move `llm_usage` table creation from `llm_budget.py` module-level to `database_schema.py`:**

- Currently: table created at import time via `_ensure_budget_table()` (llm_budget.py:76-79)
- Move to: `init_database()` in `database_schema.py` alongside other tables
- Keep `CREATE TABLE IF NOT EXISTS` — still idempotent
- Remove the try/except at module level in llm_budget.py (silent failure path eliminated)
- All indexes for `llm_usage` move to `database_schema.py` too

### Validation

```bash
# Before: capture current table list and index list
sqlite3 reclaim/data/reclaim.db ".tables"
sqlite3 reclaim/data/reclaim.db ".indexes return_cards"

# After change: verify new index exists
sqlite3 reclaim/data/reclaim.db ".indexes return_cards"
# Should include: idx_return_cards_user_status_date

# Verify llm_usage table still exists
sqlite3 reclaim/data/reclaim.db ".schema llm_usage"

# Verify server starts
uv run python -c "from reclaim.api.app import app; print('OK')"
```

---

## 8. Seams-Before-Splits: Commit-by-Commit Plan (Steps 1.5–1.8)

### Commit 1.5a: Introduce `ReturnsService` class in `reclaim/returns/service.py`

**Goal**: Create the seam. Service exists but nothing uses it yet.

**New file: `reclaim/returns/service.py`**

```python
class ReturnsService:
    """Facade over ReturnCardRepository. Introduced as a seam for Phase 1."""

    @staticmethod
    def list_returns(user_id: str, status_filter: list[str] | None, limit: int, offset: int) -> tuple[list[ReturnCard], int]:
        ...  # delegates to ReturnCardRepository.list_by_user()

    @staticmethod
    def get_return(user_id: str, card_id: str) -> ReturnCard:
        ...  # delegates to repo.get_by_id() + ownership check

    @staticmethod
    def create_return(user_id: str, card_data: dict) -> ReturnCard:
        ...  # delegates to repo.create()

    @staticmethod
    def update_status(user_id: str, card_id: str, new_status: str) -> ReturnCard:
        ...  # delegates to repo.update() + ownership check

    @staticmethod
    def update_card(user_id: str, card_id: str, updates: dict) -> ReturnCard:
        ...  # delegates to repo.update() + ownership check

    @staticmethod
    def delete_return(user_id: str, card_id: str) -> None:
        ...  # delegates to repo.delete() + ownership check

    @staticmethod
    def refresh_statuses(user_id: str, threshold_days: int = 7) -> int:
        ...  # delegates to repo.refresh_statuses()

    @staticmethod
    def get_counts(user_id: str) -> dict[str, int]:
        ...  # delegates to repo.count_by_status()

    @staticmethod
    def list_expiring(user_id: str, threshold_days: int) -> list[ReturnCard]:
        ...  # delegates to repo.list_expiring_soon()
```

**What stays in routes**: Everything. Routes still work. Service exists but is unused.
**What moves**: Nothing yet.
**Smoke test**: S1 (imports clean)

### Commit 1.5b: Wire CRUD routes through service

**Goal**: Routes call service instead of repository for CRUD operations (list, get, create, update, delete, counts, expiring, refresh).

**What moves to service**: Ownership verification (currently duplicated in 4 handlers).
**What stays in routes**: Request parsing, response model construction, exception → HTTP status mapping.
**What stays in repo**: All query methods unchanged.

**After this commit**:
- Route handlers are ~5-10 lines each: parse request → call service → wrap response
- Service methods are ~5-15 lines each: validate → call repo → return domain object
- Repository is unchanged

**Smoke test**: S1, S2, S3, S4, S5, S6

### Commit 1.7a: Add feature flag `USE_SERVICE_DEDUP`

**Goal**: Safety net for dedup migration.

**In `reclaim/config.py`:**
```python
USE_SERVICE_DEDUP: bool = os.getenv("RECLAIM_USE_SERVICE_DEDUP", "true").lower() == "true"
```

**In `reclaim/api/routes/returns.py`:**
```python
# In process_email():
if USE_SERVICE_DEDUP:
    card, is_new = ReturnsService.process_and_dedup(user_id, result, email_id)
else:
    # existing inline code (unchanged)
```

Both code paths exist. Flag defaults to `True` (new path). Set to `False` to revert.

**Smoke test**: S1, S7 (with flag=True), S7 (with flag=False, verify same result)

### Commit 1.7b: Implement `ReturnsService.process_and_dedup()`

**Goal**: Move dedup/merge logic to service. Code moves verbatim — no refactoring.

**New methods in service:**
```python
class ReturnsService:
    @staticmethod
    def process_and_dedup(
        user_id: str,
        result: ExtractionResult,
        source_email_ids: list[str],
    ) -> tuple[ReturnCard, bool]:
        """
        Deduplicate and persist an extraction result.
        Returns (card, is_new) where is_new=True means a new card was created.
        """
        # Verbatim copy of dedup logic from routes
        # 1. find_by_order_key
        # 2. find_by_item_summary (with order number conflict check)
        # 3. find_by_email_id (loop over all source_email_ids)
        # 4. If existing: merge_email_into_card
        # 5. If new: create card
```

**What moves**: The ~140-line dedup block from `process_email()`. Identical logic serves both single and batch endpoints.
**What stays in routes**: Response construction, stats counting (batch).
**What stays in repo**: All query and merge methods unchanged.

**Key detail**: Single endpoint passes `source_email_ids=[email_id]`. Batch passes the full list from `result.card.source_email_ids`. Service method loops over the list — this handles the batch vs single divergence noted in the invariants.

**Smoke test**: S1, S7, S8, S9

### Commit 1.7c: Remove old inline dedup code from routes

**Goal**: Delete the now-unused inline dedup code. Flag `USE_SERVICE_DEDUP` still exists but the old code path is gone.

**What's removed**: ~280 lines of inline dedup/merge code from both `process_email()` and `process_email_batch()`.
**What remains**: Route handlers call `ReturnsService.process_and_dedup()`.

**Smoke test**: S1, S7, S8, S9, S10

### Commit 1.8a: Extract merge logic from repository to service

**Goal**: `merge_email_into_card()` in repository becomes two parts:
1. **Service**: Computes the `updates` dict (merge precedence rules)
2. **Repository**: New `update_card_fields(card_id, updates)` method applies the dict

**New repository method:**
```python
@staticmethod
@retry_on_db_lock()
def update_card_fields(card_id: str, updates: dict) -> ReturnCard | None:
    """Apply a dict of field updates to a card. Pure persistence."""
```

**New service method:**
```python
@staticmethod
def merge_email_into_card(card_id: str, email_id: str, new_data: dict) -> ReturnCard | None:
    """Compute merge updates and persist. Business logic lives here."""
    # 1. Read current card from repo
    # 2. Apply merge precedence rules (verbatim from old repo method)
    # 3. Call repo.update_card_fields(card_id, updates)
```

**What moves**: Merge precedence logic (lines 540-600 of repository.py) → service.
**What stays in repo**: `update_card_fields()` (pure write) + old `merge_email_into_card()` (kept but unused, deleted in next commit).
**Transaction boundary**: Service method wraps read + compute + write in `db_transaction()`.

**Smoke test**: S1, S7, S8, S9

### Commit 1.8b: Remove old `merge_email_into_card()` from repository

**Goal**: Clean up. Delete the old method from repository now that service handles it.

**Smoke test**: S1, S7, S8, S9, S10

### Commit 1.8c: Remove `USE_SERVICE_DEDUP` flag

**Goal**: Clean up the feature flag now that migration is validated.

**Smoke test**: S1 through S10

### Summary: What lives where after Step 1.8

| Layer | Responsibilities |
|-------|-----------------|
| **Routes** (`returns.py`) | Parse request, call service, construct response model, map exceptions to HTTP status |
| **Service** (`service.py`) | Ownership verification, dedup strategy orchestration, merge precedence rules, status refresh |
| **Repository** (`repository.py`) | Pure CRUD: create, read, update_card_fields, delete, list queries, find queries |

---

## 9. Repository Boundary: `find_by_item_summary()`

### Decision: Keep in Repository

`find_by_item_summary()` is a **query primitive** — it encapsulates a SQL `LIKE` query with a 50-char prefix match. This is persistence logic (how to search), not business logic (when to search or what to do with results).

The **policy** (when to use it, how to handle order number conflicts) moves to the service:

```python
# In service.py (Step 1.7b):
def _dedup_by_item_summary(self, user_id, merchant_domain, item_summary, new_order_number):
    candidate = ReturnCardRepository.find_by_item_summary(user_id, merchant_domain, item_summary)
    if candidate and new_order_number and candidate.order_number:
        if new_order_number != candidate.order_number:
            return None  # Order number conflict — don't merge
    return candidate
```

**Rationale**: Moving the SQL query to the service would mean raw SQL in the service layer, violating the repository pattern. The current method signature is clean (`user_id, merchant_domain, item_summary → ReturnCard | None`). The only "business logic" in the method is the 10-char minimum and 50-char prefix — these are query tuning parameters, not business rules.

**Churn estimate**: Zero. Method stays in repo with no changes. Policy wrapping added in service.

---

## 10. Shared Sanitize + Shared Retry Parity

### Sanitize Parity

The two `_sanitize()` implementations (classifier:307-350, extractor:618-660) are **identical** — copy-pasted code.

`sanitize_for_prompt()` in `utils/redaction.py` is **different** — lighter-weight with different coverage:

| Feature | Classifier/Extractor `_sanitize()` | `sanitize_for_prompt()` |
|---------|-------------------------------------|-------------------------|
| Truncation order | After pattern removal | **Before** pattern removal |
| Control char removal | YES | NO |
| Role impersonation patterns | 7 patterns (you are, act as, pretend, roleplay, angle/square brackets) | 3 patterns (system:, assistant:, user:) |
| LLM-specific markers | NO | YES (`[INST]`, `<\|im_start\|>`) |
| Code block detection | YES | NO |
| Script tag detection | YES | NO |
| Template `{}` handling | Escapes to `{{}}` | Removes entirely |
| Telemetry logging | YES (counter) | NO |

**Decision**: Do NOT replace `_sanitize()` with `sanitize_for_prompt()`. They serve different purposes and have different coverage.

**Instead**: Extract the shared `_sanitize()` into a new function `sanitize_llm_input()` in `reclaim/utils/redaction.py` alongside the existing `sanitize_for_prompt()`. Both classifier and extractor import it. The existing `sanitize_for_prompt()` is untouched.

The new function preserves:
- All 15 pattern checks from the current `_sanitize()`
- Truncation AFTER pattern removal (current behavior)
- Telemetry logging on injection attempts
- `max_length` parameter with stage-specific defaults

### Retry Parity

The two `_call_llm_with_retry()` implementations are **semantically different**:

| Feature | Classifier (Stage 2) | Extractor (Stage 3) |
|---------|----------------------|---------------------|
| Retry decorator | Identical (`stop_after_attempt(3)`, exponential 1-10s) | Identical |
| Retryable exceptions | `TimeoutError, ConnectionError, OSError` | `TimeoutError, ConnectionError, OSError` |
| `DeadlineExceeded` handling | Generic catch → reraise | Explicit catch → convert to `TimeoutError` |
| `ServiceUnavailable` handling | Generic catch → reraise | Explicit catch → convert to `ConnectionError` |
| Telemetry granularity | `returns.classifier.error` only | Per-exception counters |
| Final failure behavior | Returns `not_returnable()` (REJECT) | Returns `{}` (FALLBACK) |

**Decision**: The shared retry helper handles ONLY the retry decorator + LLM call + exception conversion. Each stage keeps its own final-failure handler.

```python
# reclaim/llm/retry.py
@retry(stop=stop_after_attempt(LLM_MAX_RETRIES), ...)
def call_llm(prompt: str, counter_prefix: str = "llm") -> str:
    """Call LLM with retry. Raises on final failure (caller handles)."""
    model = get_gemini_model()
    try:
        response = model.generate_content(prompt)
        return response.text
    except DeadlineExceeded as e:
        counter(f"{counter_prefix}.timeout")
        raise TimeoutError(...) from e
    except ServiceUnavailable as e:
        counter(f"{counter_prefix}.service_unavailable")
        raise ConnectionError(...) from e
    except Exception as e:
        counter(f"{counter_prefix}.error")
        raise
```

Each stage wraps this in its own try/except for final-failure policy:
- Classifier: `except Exception: return not_returnable()`
- Extractor: `except Exception: return {}`

This preserves both stages' behavior exactly while eliminating duplicated retry/conversion code.

---

## 11. Scope Trim (If Limited to 5 Commits)

If we must cut Phase 1 to 5 commits, keep these:

| Priority | Step | Commit | Why Keep |
|----------|------|--------|----------|
| 1 | 1.1 | Delete dead code | Zero risk, reduces confusion, enables clean greps |
| 2 | 1.2 | Extract shared sanitization | Eliminates 50 lines of duplicated security-critical code |
| 3 | 1.5a+1.5b | Service shell + wire CRUD | Creates the architectural seam for all future work |
| 4 | 1.7a+1.7b+1.7c | Dedup to service | Highest-value consolidation (280 lines of duplication) |
| 5 | 1.9 | Database index + schema cleanup | Improves query performance, no risk |

**Defer**:
- Step 1.3 (shared retry) — duplication is 30 lines, lower impact than 280 lines of dedup
- Step 1.4 (stage_reached Enum) — cosmetic improvement, no functional benefit
- Step 1.8 (merge out of repo) — repo is "good enough" after dedup moves to service
- Step 1.10 (auth logging, extension ID) — small fixes, low urgency

---

## 12. Step-by-Step Execution Plan (Full)

### Step 1.1: Delete Dead Code

- **Goal**: Remove code that never executes, reducing confusion for future work
- **Changes**:
  - Delete `reclaim/shared/pipeline.py`
  - Remove `/api/organize` dead code block from `rate_limit.py` (lines 263-310, 344-370, docstring references)
- **Seams/facades**: None
- **Rollback**: `git revert`
- **Smoke**: S1, S2, S3
- **Commit**: `chore: remove dead code (pipeline.py, /api/organize rate limit block)`

### Step 1.2: Extract Shared Sanitization

- **Goal**: Single source of truth for LLM input sanitization
- **Changes**:
  - Add `sanitize_llm_input(text, max_length)` to `reclaim/utils/redaction.py`
  - Replace `_sanitize()` in `returnability_classifier.py` with call to shared function
  - Replace `_sanitize()` in `field_extractor.py` with call to shared function
- **Seams/facades**: Shared function introduced in existing module. Old `_sanitize()` methods become one-liner wrappers first (seam), then deleted (split).
- **Rollback**: `git revert`
- **Smoke**: S1, S2
- **Commit**: `refactor: extract shared LLM input sanitization to utils/redaction.py`

### Step 1.3: Extract Shared LLM Retry

- **Goal**: Single retry + exception conversion logic
- **Changes**:
  - Create `reclaim/llm/retry.py` with `call_llm(prompt, counter_prefix)`
  - Replace `_call_llm_with_retry()` in classifier and extractor with calls to shared function
  - Each stage keeps its own try/except for final-failure policy
- **Seams/facades**: Old methods become wrappers calling shared function first (seam), then deleted.
- **Rollback**: `git revert`
- **Smoke**: S1, S2
- **Commit**: `refactor: extract shared LLM retry logic to llm/retry.py`

### Step 1.4: `stage_reached` Enum

- **Goal**: Type safety for pipeline stages
- **Changes**:
  - Add `ExtractionStage(str, Enum)` to `reclaim/returns/extractor.py`
  - Update `ExtractionResult.stage_reached` type to `ExtractionStage`
  - Update factory methods to use enum values
  - Update comparisons in `returns.py` `process_email_batch()`
- **Seams/facades**: `str` Enum is backward-compatible at API boundary
- **Rollback**: `git revert`
- **Smoke**: S1, S2, S7
- **Commit**: `refactor: stage_reached uses ExtractionStage str Enum`

### Step 1.5: Returns Service Layer

- **Goal**: Introduce service layer between routes and repository
- **Changes (commit 1.5a)**: Create `reclaim/returns/service.py` with pass-through methods
- **Changes (commit 1.5b)**: Wire all CRUD routes through service; move ownership checks to service
- **Seams/facades**: Service is the seam. Routes delegate; repo unchanged.
- **Rollback**: `git revert` either commit independently
- **Smoke**: S1–S6
- **Commits**:
  - `refactor: introduce ReturnsService as seam (unused)`
  - `refactor: wire CRUD routes through ReturnsService`

### Step 1.7: Move Dedup/Merge to Service

- **Goal**: Single dedup implementation serving both single and batch endpoints
- **Changes (commit 1.7a)**: Add `USE_SERVICE_DEDUP` flag + service method signature
- **Changes (commit 1.7b)**: Implement `process_and_dedup()` with verbatim logic from routes
- **Changes (commit 1.7c)**: Remove old inline dedup code and flag
- **Seams/facades**: Feature flag is the safety lever. Old code preserved until 1.7c.
- **Rollback**: Set `USE_SERVICE_DEDUP=false` (1.7a-b), or `git revert` (1.7c)
- **Smoke**: S1, S7–S10
- **Commits**:
  - `refactor: add USE_SERVICE_DEDUP flag and service method signature`
  - `refactor: implement dedup/merge in ReturnsService`
  - `refactor: remove inline dedup from routes, clean up flag`

### Step 1.8: Move Merge Logic Out of Repository

- **Goal**: Repository becomes pure CRUD; merge precedence rules live in service
- **Changes (commit 1.8a)**: Add `update_card_fields()` to repo; add `merge_email_into_card()` to service
- **Changes (commit 1.8b)**: Remove old `merge_email_into_card()` from repo
- **Changes (commit 1.8c)**: Remove `USE_SERVICE_DEDUP` flag if still present
- **Seams/facades**: Old repo method kept until 1.8b. New method co-exists.
- **Rollback**: `git revert`
- **Smoke**: S1, S7–S10
- **Commits**:
  - `refactor: extract merge logic to service, add repo update_card_fields()`
  - `refactor: remove old merge_email_into_card from repository`

### Step 1.9: Database Housekeeping

- **Goal**: Performance + schema consolidation
- **Changes**:
  - Add compound index `(user_id, status, return_by_date)` in `database_schema.py`
  - Move `llm_usage` table creation from `llm_budget.py` to `database_schema.py`
  - Remove module-level `_ensure_budget_table()` call from `llm_budget.py`
- **Seams/facades**: None (additive, idempotent)
- **Rollback**: Index is harmless; `git revert` if needed
- **Smoke**: S1, S2, S3, validate with `sqlite3 .indexes`
- **Commit**: `fix: add missing compound index, consolidate schema init`

### Step 1.10: Small Fixes

- **Goal**: Clean up auth logging + extension ID duplication
- **Changes**:
  - `auth.py`: Replace `print()` with `logger.warning()`/`logger.info()`
  - Add `CHROME_EXTENSION_ID` to `config.py`, reference from `app.py` and `rate_limit.py`
- **Seams/facades**: None
- **Rollback**: `git revert`
- **Smoke**: S1, S2
- **Commit**: `fix: auth uses logger, consolidate extension ID to config`

---

## 13. Deferred Items

| Item | Rationale |
|------|-----------|
| `extraction_method` field removal | Used in telemetry — not dead code |
| Migration framework | No schema changes in Phase 1 require it; `IF NOT EXISTS` suffices |
| Gmail client batching / pagination | Extension-adjacent, not backend consolidation |
| In-memory idempotency → database | Operational concern, not structural refactoring |
| Cache memory leak fix | Operational concern |
| Cloud.py thread safety | Low-risk singleton issue |
| Request/response Pydantic models cleanup | API contract is stable; cosmetic improvement |
| Naming standardization (shopq vs reclaim) | Cross-cutting; completed in dedicated rename phase |
| Webhook handler refactor (delivery.py) | Delivery module already has service layer; lower priority |

---

## 14. Total Commit Count

| Step | Commits | Description |
|------|---------|-------------|
| 1.1 | 1 | Dead code deletion |
| 1.2 | 1 | Shared sanitization |
| 1.3 | 1 | Shared retry |
| 1.4 | 1 | stage_reached Enum |
| 1.5 | 2 | Service shell + wire CRUD |
| 1.7 | 3 | Dedup to service (flag → implement → cleanup) |
| 1.8 | 2 | Merge out of repo (extract → cleanup) |
| 1.9 | 1 | Database housekeeping |
| 1.10 | 1 | Small fixes |
| **Total** | **13** | |

---

## Progress Tracker

| Step | Status | Commit SHA | Notes |
|------|--------|-----------|-------|
| 1.1 | PENDING | | |
| 1.2 | PENDING | | |
| 1.3 | PENDING | | |
| 1.4 | PENDING | | |
| 1.5a | PENDING | | |
| 1.5b | PENDING | | |
| 1.7a | PENDING | | |
| 1.7b | PENDING | | |
| 1.7c | PENDING | | |
| 1.8a | PENDING | | |
| 1.8b | PENDING | | |
| 1.9 | PENDING | | |
| 1.10 | PENDING | | |
