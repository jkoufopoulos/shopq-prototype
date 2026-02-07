# Reclaim

**Track return windows on your online purchases. Never miss a return deadline again.**

Reclaim is a Chrome extension that lives in your Gmail sidebar. It automatically detects purchases from your emails, calculates return deadlines, and alerts you before windows close.

---

## Features

- **Automatic Detection** — Scans Gmail for order confirmations, shipping updates, and delivery notifications
- **Smart Deadline Calculation** — Uses delivery dates when available, falls back to purchase date + merchant policy
- **Expiring Alerts** — Red notification badge when returns are expiring soon
- **Inline Date Editing** — Manually adjust return dates with a date picker
- **Uber Direct Integration** — Schedule a pickup to return items without leaving home
- **Privacy-First** — All email processing happens locally in your browser

---

## How It Works

```
Gmail Emails
     │
     ▼
┌─────────────────────────────────────────────────┐
│  Chrome Extension (runs locally)                │
│                                                 │
│  1. Filter    - Skip newsletters, promos, etc.  │
│  2. Classify  - Is this a returnable purchase?  │
│  3. Extract   - Merchant, items, dates, order # │
│  4. Calculate - Return deadline from policy     │
└─────────────────────────────────────────────────┘
     │
     ▼
Gmail Sidebar showing your returns with deadlines
```

### Deadline Calculation Priority

1. **Actual delivery date** (from delivery confirmation email)
2. **Estimated delivery date** (from order/shipping email)
3. **Ship date** (from shipping notification)
4. **Purchase date** (from order confirmation)

Plus merchant-specific return window (default: 30 days).

---

## Installation

### For Users

1. Clone this repo:
   ```bash
   git clone https://github.com/jkoufopoulos/shopq-prototype.git
   cd shopq-prototype/extension
   npm install
   npm run build
   ```

2. Load in Chrome:
   - Go to `chrome://extensions`
   - Enable "Developer mode" (top right)
   - Click "Load unpacked"
   - Select the `extension` folder

3. Open Gmail — you'll see the Reclaim icon in the sidebar

### OAuth Setup

The extension needs Gmail read access. Currently in testing mode, so:
- Contact the developer to add your Gmail to the test users list
- Or set up your own OAuth credentials in Google Cloud Console

---

## Project Structure

```
shopq-prototype/
├── extension/                 # Chrome Extension (Manifest V3)
│   ├── background.js          # Service worker
│   ├── src/content.js         # Gmail page integration
│   ├── returns-sidebar-inner.js  # Sidebar UI
│   ├── modules/
│   │   ├── pipeline/          # Email processing stages
│   │   │   ├── filter.js      # Domain filtering
│   │   │   ├── classifier.js  # Purchase detection
│   │   │   ├── extractor.js   # Field extraction
│   │   │   └── lifecycle.js   # Deadline calculation
│   │   ├── storage/           # Local storage schema
│   │   └── gmail/             # Gmail API + OAuth
│   └── dist/                  # Built bundles
│
├── shopq/                     # Python backend (optional)
│   ├── api/                   # FastAPI routes
│   └── returns/               # LLM-based extraction
│
└── config/
    └── merchant_rules.yaml    # Return policies by domain
```

---

## Configuration

### Merchant Rules

Return window policies in `config/merchant_rules.yaml`:

```yaml
amazon.com:
  return_window_days: 30
  anchor: delivery

target.com:
  return_window_days: 90
  anchor: purchase

_default:
  return_window_days: 30
  anchor: delivery
```

---

## Development

```bash
# Extension
cd extension
npm install
npm run watch    # Build with hot reload

# Backend (optional, for LLM enrichment)
uv sync
uv run uvicorn shopq.api.app:app --reload
```

### Testing

```bash
# Extension tests
cd extension && npm test

# Backend tests
PYTHONPATH=. SHOPQ_USE_LLM=false uv run pytest tests/ -v
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Extension | Chrome Manifest V3, InboxSDK |
| Frontend | Vanilla JS, CSS |
| Backend | Python, FastAPI |
| AI | Google Gemini (via Vertex AI) |
| Database | SQLite (local + Cloud Run) |
| Delivery | Uber Direct API |

---

## License

MIT License — see [LICENSE](LICENSE)
