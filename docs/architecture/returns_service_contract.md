# Returns Service Contract

Defines the boundaries and responsibilities of the three layers that handle return card operations.

---

## Layer Diagram

```
HTTP Request
    |
    v
[Routes]           shopq/api/routes/returns.py
    |               - Request/response models (Pydantic)
    |               - HTTP status codes
    |               - Input parsing (date strings -> datetime)
    |               - Error sanitization
    |
    v
[Service]           shopq/returns/service.py
    |               - Ownership enforcement (card.user_id == caller)
    |               - Dedup strategy (order_number -> item_summary -> email_id)
    |               - Merge policy (_compute_merge_updates)
    |               - Status auto-refresh before reads
    |
    v
[Repository]        shopq/returns/repository.py
                    - SQL generation and execution
                    - Transaction boundaries (db_transaction)
                    - Retry on SQLite lock (@retry_on_db_lock)
                    - Model serialization (to_db_dict / from_db_row)
```

---

## Layer Responsibilities

### Routes (`shopq/api/routes/returns.py`)

**Owns:**
- Pydantic request/response models (`CreateReturnCardRequest`, `ReturnCardResponse`, etc.)
- HTTP semantics (status codes, headers, error responses)
- Input parsing: converting string dates to `datetime`, string statuses to `ReturnStatus` enum
- Error sanitization via `sanitize_error_message()` (SEC-011)
- Input validation via Pydantic `field_validator` decorators (SEC-012)
- Lazy import of `ReturnableReceiptExtractor` in process endpoints

**Does NOT own:**
- Ownership checks (delegated to Service)
- Dedup/merge logic (delegated to Service)
- Direct database access (no `ReturnCardRepository` import)
- Business rules about status transitions

**Contract with Service:**
- Always passes `user_id` from authenticated user
- Calls `ReturnsService.*` static methods, never `ReturnCardRepository.*` directly
- Trusts Service to return `None` for not-found/not-owned cards, translates to HTTP 404

### Service (`shopq/returns/service.py`)

**Owns:**
- **Ownership enforcement:** Every method that takes `card_id + user_id` checks `card.user_id == user_id` before acting. Returns `None` (or `False` for delete) when not owned.
- **Dedup strategy order** (invariant, do not reorder):
  1. Match by `merchant_domain` + `order_number`
  2. Match by `merchant_domain` + `item_summary` (50-char prefix, with order# conflict guard)
  3. Match by `email_id` (any in `source_email_ids`)
- **Merge policy** (`_compute_merge_updates`, invariant rules):
  - `delivery_date`: fill if empty
  - `return_by_date`: fill if empty, or replace if `delivery_date` was just filled
  - `item_summary`: longer wins
  - `evidence_snippet`: keyword-gated (must contain "return", "refund", "days", or "policy")
  - `return_portal_link`: fill if empty
  - `shipping_tracking_link`: fill if empty
- **Auto-refresh:** Calls `Repository.refresh_statuses()` before every read operation (`list_returns`, `list_expiring`, `get_counts`)
- **`DedupResult` dataclass:** Communicates merge outcome (card + was_merged flag) to routes

**Does NOT own:**
- HTTP concepts (no status codes, no request/response models)
- SQL or database access (delegates all persistence to Repository)
- Pipeline execution (extractor is called by routes, card is passed to `dedup_and_persist`)

**Contract with Repository:**
- Calls Repository static methods with validated arguments
- For merges: computes field updates dict, then calls `add_email_and_update(card_id, email_id, field_updates)` — Repository does not interpret merge policy
- For creates: constructs `ReturnCardCreate` and calls `Repository.create()`

### Repository (`shopq/returns/repository.py`)

**Owns:**
- All SQL generation and execution
- Transaction boundaries (`db_transaction()` context manager)
- SQLite lock retry (`@retry_on_db_lock()` decorator)
- Model serialization: `ReturnCard.to_db_dict()` for writes, `ReturnCard.from_db_row()` for reads
- Column whitelist validation (`ALLOWED_UPDATE_COLUMNS`) for dynamic UPDATE statements
- Initial status computation on create (ACTIVE / EXPIRING_SOON / EXPIRED based on `return_by_date`)
- ID generation (`uuid.uuid4()`)
- Timestamp management (`utc_now()`)

**Does NOT own:**
- Ownership checks (no `user_id` comparison logic)
- Dedup strategy or merge policy
- Business rules about when/how cards should be merged

**Contract with Service:**
- Pure CRUD: `create`, `get_by_id`, `update`, `update_status`, `delete`
- Finder methods for dedup: `find_by_order_key`, `find_by_item_summary`, `find_by_email_id`
- Atomic merge primitive: `add_email_and_update(card_id, email_id, field_updates)` — appends email_id to `source_email_ids` and applies pre-resolved field updates in a single transaction
- `refresh_statuses(user_id, threshold_days)` — bulk status transitions (ACTIVE -> EXPIRING_SOON -> EXPIRED)

---

## Invariants

These rules must hold across all layers. Violating them is a bug.

### Dedup Strategy Order
The three strategies in `dedup_and_persist()` MUST execute in this order:
1. `order_number` match first (strongest signal)
2. `item_summary` prefix match second (fuzzy, with order# conflict guard)
3. `email_id` match last (weakest, catch-all)

Reordering would cause different merge behavior for the same input.

### Merge Precedence
The rules in `_compute_merge_updates()` are additive and non-destructive:
- **Never overwrite** a non-empty field with an empty value
- **Never remove** entries from `source_email_ids` (append-only)
- **Longer wins** only applies to `item_summary`, not other text fields
- **Keyword gate** on `evidence_snippet` prevents promotional text from replacing return policy text

### Ownership Enforcement
Every Service method that accepts `card_id + user_id` MUST check ownership. The pattern is:
```python
card = ReturnCardRepository.get_by_id(card_id)
if not card or card.user_id != user_id:
    return None  # or False for delete
```
Routes MUST NOT bypass Service to call Repository directly.

### Auto-Refresh Before Reads
`list_returns`, `list_expiring`, and `get_counts` MUST call `refresh_statuses()` before querying. This ensures status fields reflect the current date without requiring a background job.

### No Business Logic in Repository
`add_email_and_update()` takes a pre-computed `field_updates` dict. It does not decide which fields to update — that decision belongs to `_compute_merge_updates()` in Service.

---

## Adding New Features

### New field on ReturnCard
1. Add column to `database_schema.py`
2. Add field to `ReturnCard` model in `models.py`
3. Update `to_db_dict()` and `from_db_row()` in models
4. Add to `ReturnCardCreate` if settable on creation
5. Add to `ReturnCardResponse` in routes if exposed via API
6. If mergeable: add merge rule to `_compute_merge_updates()` in Service
7. If updatable: add to `ALLOWED_UPDATE_COLUMNS` in Repository and `ReturnCardUpdate` in models

### New dedup strategy
1. Add finder method to Repository (e.g., `find_by_tracking_number`)
2. Add strategy step in `dedup_and_persist()` — insert at the correct priority position
3. Document the priority order change in this file

### New status transition
1. Add value to `ReturnStatus` enum in models
2. Update `refresh_statuses()` in Repository if it should auto-transition
3. Update `update_return_status()` in routes if user-initiated
4. Update `StatusCountsResponse` in routes
