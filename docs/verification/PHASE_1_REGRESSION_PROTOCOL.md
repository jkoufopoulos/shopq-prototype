# Phase 1 Regression Protocol

**Time budget:** 10 minutes
**When to run:** After any Phase 2+ commit, or whenever backend behavior is in question.

---

## Prerequisites

```bash
# Terminal 1: Start backend (if not already running)
cd shopq-prototype
uv run uvicorn shopq.api.app:app --port 8000

# Verify it's up
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected: `"status": "healthy"`, `"version": "1.0.0"`

**CSRF note:** State-changing requests (POST/PUT/PATCH/DELETE) require an `Origin` header.
In development mode, `http://localhost:8000` is in the CSRF allowlist. All curl commands
below include `-H "Origin: http://localhost:8000"` where needed.

**Auth note:** In development mode (`SHOPQ_ENV=development`, the default), the API returns
a default user when no `Authorization` header is provided. In production, all endpoints
require a valid Google OAuth Bearer token.

---

## Step 1: Health Checks (30 seconds)

```bash
# Service health
curl -s http://localhost:8000/health | python3 -m json.tool

# Database health
curl -s http://localhost:8000/health/db | python3 -m json.tool

# Debug stats (aggregate counts, no PII)
curl -s http://localhost:8000/debug/stats | python3 -m json.tool
```

**Invariants:**
- `/health` returns `200` with `status: "healthy"`
- `/health/db` returns `200` with pool stats and `usage_percent` < 80
- `/debug/stats` returns `200` with `returns.total` and `returns.by_status` object

---

## Step 2: CRUD Round-Trip (3 minutes)

### 2a. Create a card

```bash
curl -s -X POST http://localhost:8000/api/returns \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8000" \
  -d '{
    "merchant": "Test Store",
    "merchant_domain": "teststore.com",
    "item_summary": "Regression test widget",
    "confidence": "exact",
    "order_number": "REGTEST-001",
    "return_by_date": "2099-12-31T00:00:00",
    "source_email_ids": ["regression_test_email_1"]
  }' | python3 -m json.tool
```

**Invariants:**
- Status `201`
- Response has `id` (UUID), `status: "active"`, `confidence: "exact"`
- `merchant_domain` is `"teststore.com"` (validated, lowercased)
- `source_email_ids` contains `"regression_test_email_1"`
- `days_remaining` is a positive integer (card expires in 2099)

Save the returned `id` for subsequent steps:
```bash
CARD_ID="<paste id from response>"
```

### 2b. Get by ID

```bash
curl -s http://localhost:8000/api/returns/$CARD_ID | python3 -m json.tool
```

**Invariants:**
- Status `200`, same fields as creation response
- `user_id` is `"default"` (MVP mode, no auth)

### 2c. List returns

```bash
curl -s "http://localhost:8000/api/returns?status=active&limit=5" | python3 -m json.tool
```

**Invariants:**
- Status `200`
- Response has `cards` array, `total` count, `expiring_soon_count`
- The card from 2a appears in the list

### 2d. Update status (mark returned)

```bash
curl -s -X PUT http://localhost:8000/api/returns/$CARD_ID/status \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8000" \
  -d '{"status": "returned"}' | python3 -m json.tool
```

**Invariants:**
- Status `200`
- `status` is now `"returned"`
- Card no longer appears in `?status=active` list

### 2e. Update status back (returned -> active via PATCH)

```bash
curl -s -X PATCH http://localhost:8000/api/returns/$CARD_ID \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8000" \
  -d '{"status": "active", "notes": "Regression test note"}' | python3 -m json.tool
```

**Invariants:**
- Status `200`
- `status` is `"active"`, `notes` is `"Regression test note"`

### 2f. Counts

```bash
curl -s http://localhost:8000/api/returns/counts | python3 -m json.tool
```

**Invariants:**
- All count fields present: `active`, `expiring_soon`, `expired`, `returned`, `dismissed`, `total`
- `total` equals sum of individual counts

### 2g. Delete

```bash
curl -s -X DELETE http://localhost:8000/api/returns/$CARD_ID \
  -H "Origin: http://localhost:8000" -w "\nHTTP %{http_code}\n"
```

**Invariants:**
- Status `204` (no body)
- GET on same ID now returns `404`

---

## Step 3: Dedup/Merge (3 minutes)

### 3a. Create base card

```bash
curl -s -X POST http://localhost:8000/api/returns \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8000" \
  -d '{
    "merchant": "Amazon",
    "merchant_domain": "amazon.com",
    "item_summary": "Wireless Bluetooth Headphones with Noise Cancelling",
    "confidence": "estimated",
    "order_number": "112-3456789-0000000",
    "source_email_ids": ["msg_base_001"]
  }' | python3 -m json.tool
```

Save the `id`:
```bash
BASE_ID="<paste id>"
```

### 3b. Process duplicate (same order number)

```bash
curl -s -X POST http://localhost:8000/api/returns/process \
  -H "Content-Type: application/json" \
  -d '{
    "email_id": "msg_delivery_002",
    "from_address": "shipment-tracking@amazon.com",
    "subject": "Your Amazon order has been delivered",
    "body": "Your order 112-3456789-0000000 for Wireless Bluetooth Headphones was delivered on February 7, 2026. Return by March 9, 2026. Track: https://track.amazon.com/12345"
  }' | python3 -m json.tool
```

**Invariants (if LLM is enabled and processes correctly):**
- If `stage_reached` is `"complete"`: the returned card `id` matches `BASE_ID` (merged, not duplicated)
- `source_email_ids` contains both `"msg_base_001"` and `"msg_delivery_002"`
- If `stage_reached` is `"filter"` or `"classifier"` (LLM disabled): rejection is expected, skip merge checks

### 3c. Verify merge (check the base card)

```bash
curl -s http://localhost:8000/api/returns/$BASE_ID | python3 -m json.tool
```

**Invariants (merge path):**
- `source_email_ids` array has 2 entries (append-only)
- `delivery_date` was filled (if pipeline extracted it)
- `item_summary` is the longer of the two (longer-wins rule)
- `order_number` unchanged (`"112-3456789-0000000"`)

### 3d. Cleanup

```bash
curl -s -X DELETE http://localhost:8000/api/returns/$BASE_ID -w "\nHTTP %{http_code}\n"
```

---

## Step 4: Batch Processing (2 minutes)

```bash
curl -s -X POST http://localhost:8000/api/returns/process-batch?skip_persistence=true \
  -H "Content-Type: application/json" \
  -d '{
    "emails": [
      {
        "email_id": "batch_test_1",
        "from_address": "noreply@amazon.com",
        "subject": "Your Amazon.com order of Wireless Mouse",
        "body": "Thank you for your order! Order #111-0000001. Wireless Mouse. Estimated delivery: Feb 10."
      },
      {
        "email_id": "batch_test_2",
        "from_address": "newsletter@marketing.com",
        "subject": "Big sale this weekend!",
        "body": "Check out our deals on electronics. 50% off everything."
      }
    ]
  }' | python3 -m json.tool
```

**Invariants:**
- Status `200`
- `stats.total` is `2`
- `stats.rejected_filter >= 1` (the newsletter should be filtered)
- `skip_persistence=true` means no DB side effects

---

## Step 5: Gmail UI Smoke Test (2 minutes)

> Only needed if extension code was changed. Skip for backend-only changes.

1. Open Gmail in Chrome with the extension loaded
2. **Sidebar loads:** Click the Reclaim icon in the sidebar. Existing cards appear.
3. **Card detail:** Click a card. Detail view opens with merchant, dates, links.
4. **Status change:** Click "Mark Returned" on a card. Card moves to Returned section.
5. **Undo:** Click "Undo" or change status back. Card returns to Active.

**Invariants:**
- No console errors (DevTools > Console, filter to extension ID)
- Sidebar reflects backend state (refresh shows same data as curl)
- Status changes persist after page reload

---

## Step 6: Expiring Returns (30 seconds)

```bash
curl -s "http://localhost:8000/api/returns/expiring?threshold_days=7" | python3 -m json.tool
```

**Invariants:**
- Status `200`
- Returns array (may be empty if no cards expire within 7 days)
- Each card has `return_by_date` within 7 days from today

---

## Quick Reference: API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Service health |
| GET | `/health/db` | Database pool health |
| GET | `/debug/stats` | Aggregate stats (no PII) |
| GET | `/api/returns` | List cards (filterable) |
| GET | `/api/returns/expiring` | Expiring cards |
| GET | `/api/returns/counts` | Status counts |
| GET | `/api/returns/{id}` | Get single card |
| POST | `/api/returns` | Create card |
| PUT | `/api/returns/{id}/status` | Update status |
| PATCH | `/api/returns/{id}` | Update fields |
| DELETE | `/api/returns/{id}` | Delete card |
| POST | `/api/returns/process` | Process single email |
| POST | `/api/returns/process-batch` | Process email batch |
| POST | `/api/returns/refresh-statuses` | Refresh status timestamps |

---

## Failure Triage

| Symptom | Likely Cause | Check |
|---------|-------------|-------|
| `500` on any endpoint | Import error or DB issue | Check server logs in terminal |
| `422` on POST | Request body validation | Check field names and types |
| `404` on GET by ID | Card deleted or wrong user | Verify card exists via list endpoint |
| Merge didn't happen | LLM disabled or filter rejected | Check `stage_reached` in process response |
| Counts don't add up | Status refresh needed | Call `/api/returns/refresh-statuses` first |
| Extension sidebar blank | API URL mismatch | Compare `extension/modules/shared/config.js` API_BASE_URL with running server |
