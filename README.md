# ShopQ - Return Watch

**Track return windows on your online purchases. Never miss a return deadline again.**

---

## What is Return Watch?

Return Watch is a Gmail companion that automatically detects your online purchases and tracks return deadlines. It uses a 3-stage AI pipeline to identify returnable purchases and calculate when your return window closes.

**Key Features:**
- **Automatic Detection** - Scans Gmail for purchase receipts and shipping confirmations
- **Smart Filtering** - Filters out non-returnable transactions (subscriptions, services, digital goods)
- **Return Window Tracking** - Calculates return-by dates using merchant-specific policies
- **Gmail Sidebar** - View all returnable purchases in Gmail's native sidebar

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Return Watch                               │
├─────────────────────────────────────────────────────────────────┤
│  Chrome Extension          │  FastAPI Backend                   │
│                            │                                    │
│  ┌──────────────┐          │  ┌──────────────────────────────┐ │
│  │ Popup        │──────────┼─▶│ GET /api/returns             │ │
│  │ Sidebar UI   │          │  │ POST /api/returns/process    │ │
│  │ Gmail Scan   │          │  │ PUT /api/returns/{id}/status │ │
│  └──────────────┘          │  └──────────────────────────────┘ │
│                            │                                    │
│                            │  ┌──────────────────────────────┐ │
│                            │  │ 3-Stage Extraction Pipeline  │ │
│                            │  │ 1. Domain Filter (FREE)      │ │
│                            │  │ 2. Returnability Classifier  │ │
│                            │  │ 3. Field Extractor           │ │
│                            │  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Extraction Pipeline

```
Email → Stage 1: Domain Filter (FREE)
              │
              ├─ Blocklist (Uber, Netflix, etc.) → Reject
              ├─ Allowlist (Amazon, Target, etc.) → Pass
              └─ Unknown → Keyword heuristics
              │
        Stage 2: Returnability Classifier (~$0.0001)
              │
              └─ LLM determines: product_order | service | subscription | digital
              │
        Stage 3: Field Extractor (~$0.0002)
              │
              └─ Extract: merchant, items, dates, order number
              └─ Compute: return_by_date using merchant rules
              │
        Result: ReturnCard with confidence (exact | estimated | unknown)
```

---

## Project Structure

```
shopq-prototype/
├── extension/               # Chrome extension
│   ├── background.js        # Service worker, Gmail scanning
│   ├── popup.*              # Extension popup UI
│   ├── returns-sidebar.*    # Gmail sidebar for returns
│   ├── src/content.js       # Gmail page integration
│   └── modules/             # Shared modules
│
├── shopq/                   # Python backend
│   ├── api/                 # FastAPI routes
│   │   └── routes/returns.py
│   ├── returns/             # Return Watch core
│   │   ├── filters.py       # Domain blocklist/allowlist
│   │   ├── returnability_classifier.py
│   │   ├── field_extractor.py
│   │   ├── extractor.py     # Pipeline orchestrator
│   │   ├── models.py        # ReturnCard model
│   │   └── repository.py    # Database operations
│   ├── gmail/               # Gmail API client
│   ├── infrastructure/      # Database, auth
│   └── observability/       # Logging, telemetry
│
├── config/
│   └── merchant_rules.yaml  # Return window policies
│
├── docs/
│   └── RETURN_WATCH_PRD.yaml
│
└── tests/
    └── integration/
        └── test_extraction_pipeline.py
```

---

## Quick Start

### Backend

```bash
cd shopq-prototype

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your GOOGLE_CLOUD_PROJECT

# Run backend
uv run uvicorn shopq.api.app:app --reload
```

### Extension

```bash
cd extension

# Install dependencies
npm install

# Build
npm run build

# Load in Chrome
# 1. Open chrome://extensions/
# 2. Enable Developer Mode
# 3. Load unpacked from extension/ directory
```

---

## Configuration

### Merchant Rules

Return window policies are defined in `config/merchant_rules.yaml`:

```yaml
merchants:
  amazon.com:
    days: 30
    anchor: delivery
    return_url: https://www.amazon.com/gp/css/returns

  target.com:
    days: 90
    anchor: purchase

  _default:
    days: 30
    anchor: delivery
```

### Environment Variables

```bash
# Required
GOOGLE_CLOUD_PROJECT=your-project-id

# Optional
SHOPQ_USE_LLM=true  # Enable LLM classification
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/returns` | GET | List return cards for user |
| `/api/returns/process` | POST | Process email through extraction pipeline |
| `/api/returns/{id}/status` | PUT | Update card status (returned/dismissed) |
| `/api/returns/counts` | GET | Get status counts by status |
| `/api/returns/expiring` | GET | Get cards expiring soon |
| `/api/health` | GET | Health check |

---

## Testing

```bash
# Run extraction pipeline tests
PYTHONPATH=. SHOPQ_USE_LLM=false uv run pytest tests/integration/test_extraction_pipeline.py -v
```

---

## Data Model

### ReturnCard

```python
class ReturnCard:
    id: str
    user_id: str
    merchant: str
    merchant_domain: str
    item_summary: str
    status: active | expiring_soon | expired | returned | dismissed
    confidence: exact | estimated | unknown
    return_by_date: datetime | None
    order_number: str | None
    amount: float | None
    # ... more fields
```

### Confidence Levels

| Level | Description |
|-------|-------------|
| `exact` | Return-by date explicitly stated in email |
| `estimated` | Calculated from merchant rules + anchor date |
| `unknown` | No date information available |

---

## License

Proprietary
