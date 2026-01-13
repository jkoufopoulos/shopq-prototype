# ShopQ Copilot Instructions

## Project Overview

**ShopQ** is a hybrid AI email classification system combining rule-based matching with Google Cloud Vertex AI (Gemini) to intelligently categorize Gmail emails. The system uses a **multi-dimensional classification schema** (type, domains, attention, relationship) and learns from user feedback to improve accuracy over time.

**Architecture**: Python FastAPI backend + Chrome Manifest V3 extension
**AI Model**: Google Cloud Vertex AI (Gemini 1.5 Flash)
**Database**: SQLite (rules, feedback, categories)
**Deployment**: Google Cloud Run

## Development Workflow

### Starting the Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (auto-reload enabled)
uvicorn shopq.api:app --host 0.0.0.0 --port 8000 --reload

# Deploy to Cloud Run
./deploy.sh
```

### Running Tests

```bash
# Python tests (pytest)
pytest                        # All tests
pytest -v                     # Verbose
pytest -m unit                # Unit tests only
pytest -m integration         # Integration tests only
pytest shopq/tests/test_*.py  # Specific file

# Extension tests (vitest)
npm test
```

**Test Configuration**: Tests use `pytest.ini` for markers and paths. Backend tests live in `shopq/tests/`, extension tests in `extension/tests/`.

### Loading the Extension

1. Open Chrome → `chrome://extensions`
2. Enable "Developer mode"
3. Click "Load unpacked" → Select `/extension` directory
4. Update `extension/config.js` with your API URL

## Core Architecture

### Classification Pipeline (3-Tier System)

The system prioritizes **speed and cost efficiency** using a tiered approach:

```
Email Input → Rules Engine (T0: free) → Vertex Gemini (T3: ~$0.0001) → Confidence Filter → Gmail Labels
```

**Flow orchestrated by `shopq/memory_classifier.py`**:

1. **Rules First** (`rules_engine.py`): Check SQLite for exact sender matches
   - Hit → Return cached result (T0 cost: free)
   - Miss → Continue to step 2

2. **Gemini Classification** (`vertex_gemini_classifier.py`): LLM with few-shot learning
   - Uses 12 static examples (hardcoded in `_get_static_examples()`) + up to 5 learned patterns from user feedback
   - Returns multi-dimensional classification (T3 cost: ~$0.0001)

3. **Confidence Filtering** (`api_organize.py`): Apply thresholds
   - `type_conf ≥ 0.85` (type classification)
   - `domain_conf ≥ 0.75` (per domain)
   - Low confidence → "Uncategorized" (never misclassify)

4. **Label Mapping** (`mapper.py`): Semantic → Gmail labels
   - Maps dimensions to `ShopQ-*` prefixed labels

5. **Learning** (`rules_engine.py`): Build rule database
   - **Passive learning**: 2 consistent high-confidence classifications
   - **Active learning**: User corrections create immediate rules (conf=0.95)

### Multi-Dimensional Classification Schema

Defined in `extension/Schema.json`, every classification includes:

- **Type**: `newsletter|notification|receipt|event|promotion|message|uncategorized`
- **Domains**: Array of `finance|professional|personal|travel|shopping`
- **Attention**: `action_required|none`
- **Relationship**: `from_contact|from_unknown`
- **Decider**: `rule|gemini|fallback` (which system decided)

**Confidence scores** (0.0-1.0) for each dimension enable dynamic thresholding.

### Key Backend Modules

| Module | Purpose |
|--------|---------|
| `api.py` | FastAPI application, `/api/organize` endpoint |
| `api_organize.py` | Batch classification with confidence filtering |
| `api_feedback.py` | `/api/feedback` for user corrections |
| `api_debug.py` | `/api/debug/*` debugging endpoints |
| `memory_classifier.py` | Classification orchestrator (rules → LLM → mapping) |
| `rules_engine.py` | SQLite rule matching + learning logic |
| `vertex_gemini_classifier.py` | Vertex AI integration with few-shot prompting |
| `mapper.py` | Converts semantic results to Gmail label format |
| `feedback_manager.py` | Stores corrections, extracts learned patterns |
| `category_manager.py` | User category CRUD operations |
| `config/database.py` | Centralized SQLite connection management |

### Extension Architecture (Manifest V3)

**Service Worker Pattern** (`background.js`): Main orchestrator handling classification batches

**Key Modules** (`extension/modules/`):
- `auth.js`: Gmail OAuth token management
- `gmail.js`: Gmail API operations (fetch unlabeled, apply labels)
- `classifier.js`: Calls `/api/organize`, handles caching & deduplication
- `mapper.js`: Maps API results to Gmail label format
- `cache.js`: Local storage cache (24hr expiry, 10k entry limit)
- `budget.js`: Cost tracking ($0.50 daily cap, logged only - not enforced)
- `utils.js`: Settings storage, email deduplication

**Content Script** (`content.js`): Monitors Gmail DOM for user label corrections

## Critical Patterns & Conventions

### Confidence-Driven Decisions

**Never guess** - every classification includes confidence scores:
- Main gate: `type_conf ≥ 0.85` in `api_organize.py` (MIN_TYPE_CONF)
- Domain gate: `domain_conf ≥ 0.75` per domain in `mapper.py`
- Low confidence → Always use "Uncategorized" rather than risk misclassification

### Deduplication Strategy

The extension deduplicates emails **by sender domain** before API calls to minimize costs:
1. Group emails by sender (e.g., `noreply@github.com`)
2. Classify once per unique sender
3. Expand results to all emails from that sender

See `extension/modules/utils.js` → `deduplicateEmails()`

### Gmail Label Convention

All labels use `ShopQ-*` prefix to prevent conflicts:
- Type → `ShopQ-Newsletters`, `ShopQ-Notifications`, etc.
- Domain → `ShopQ-Finance`, `ShopQ-Work`, etc.
- Attention → `ShopQ-Action-Required`

### Learning Velocity Control

Two learning paths with different promotion thresholds:

**Passive (Gemini-based)**:
- Requires 2 consistent classifications at high confidence
- Creates "pending rules" in `shopq/data/shopq.db` (rules table)
- Promoted to confirmed rules on second match

**Active (User corrections)**:
- User removes/changes label in Gmail
- Content script detects change → sends to `/api/feedback`
- Immediately creates rule with confidence=0.95
- No pending period - instant learning

See `rules_engine.py` → `learn_from_classification()` and `feedback_manager.py`

### Database Structure

**Single central SQLite database**: `shopq/data/shopq.db`
- Contains all tables: rules, feedback, classifications, digest data, quality monitoring, etc.
- All tables have `user_id` column for multi-tenancy
- Connection pooling enabled for performance
- 14-day retention policy with automated cleanup

**Connection Management**: Use `config/database.py` → `get_db_connection()` for proper connection handling (foreign keys enabled, Row factory, timeouts, connection pooling).

### Module Import Convention

Backend uses **explicit shopq.* imports**:
```python
# ✅ Correct
from shopq.memory_classifier import MemoryClassifier
from shopq.rules_engine import RulesEngine

# ❌ Avoid
from memory_classifier import MemoryClassifier
```

This ensures proper module resolution in Docker (PYTHONPATH=/app).

### Graceful Degradation

System never crashes on classification failure:
- LLM failure → Returns fallback result with `"decider": "fallback"`
- Schema validation failure → Returns uncategorized result
- See `memory_classifier.py` → `_fallback_semantic()`

## External Services

**Google Cloud Vertex AI**:
- Project: `mailq-467118`
- Model: `gemini-1.5-flash`
- Location: `us-central1`
- Configure via `.env` → `GOOGLE_CLOUD_PROJECT`, `GEMINI_MODEL`

**Gmail API**:
- OAuth scopes: `gmail.modify`, `gmail.labels`
- Query pattern: `in:inbox -label:ShopQ-*` (fetch unlabeled only)

**Cloud Run Deployment**:
- URL: `https://shopq-api-488078904670.us-central1.run.app`
- Environment: Production only (no staging)
- Container: Python 3.11 + FastAPI
- Deploy script: `./deploy.sh` (handles IAM permissions, env vars)
- Flow: Local development → Production (use feature flags for safe deploys)

## Environment Configuration

Required `.env` variables:
```bash
GOOGLE_API_KEY=AIzaSy...         # Vertex AI key
GOOGLE_CLOUD_PROJECT=mailq-467118
GEMINI_MODEL=gemini-1.5-flash
GEMINI_LOCATION=us-central1

API_HOST=0.0.0.0
API_PORT=8000

USE_RULES_ENGINE=true            # Enable rule matching
USE_AI_CLASSIFIER=true           # Enable Gemini fallback
```

## Common Tasks

### Adding a New Email Type

1. Update `extension/Schema.json` → Add to `type` enum
2. Update `shopq/mapper.py` → Add to `type_label_map`
3. Update `shopq/vertex_gemini_classifier.py` → Add few-shot examples

### Debugging Classification Issues

Use debug endpoints in `api_debug.py`:
- `GET /api/debug/last-batch` - View last batch results
- `GET /api/debug/rules` - List all rules
- `GET /api/debug/stats` - Classification statistics

Or enable verbose logging: `pytest -v` or check `shopq/logs/`

### Changing Confidence Thresholds

Edit constants in:
- `shopq/api_organize.py` → `MIN_TYPE_CONF`, `MIN_LABEL_CONF`
- `shopq/mapper.py` → `type_gate`, `domain_gate`, `attention_gate`

### Testing Schema Validation

Schema validation is critical - use `mapper.py` → `validate_classification_result()`:
```python
result = classifier.classify(...)
assert validate_classification_result(result), "Schema mismatch"
```

## Key Files Reference

**Backend Entry Points**:
- `shopq/api.py` - FastAPI app initialization
- `shopq/api_organize.py` - Classification endpoint logic

**Classification Core**:
- `shopq/memory_classifier.py` - Main orchestrator
- `shopq/rules_engine.py` - Rule database & learning
- `shopq/vertex_gemini_classifier.py` - Vertex AI integration

**Extension Core**:
- `extension/background.js` - Service worker
- `extension/content.js` - Gmail DOM monitoring
- `extension/config.js` - Configuration constants
- `extension/Schema.json` - Classification schema

**Configuration**:
- `pytest.ini` - Test configuration (markers, paths)
- `vitest.config.js` - Extension test configuration
- `Dockerfile` - Container definition
- `deploy.sh` - Cloud Run deployment
- `.env` - Backend secrets (not committed)

## Testing Philosophy

- **Unit tests** (`@pytest.mark.unit`): Fast, isolated, no external dependencies
- **Integration tests** (`@pytest.mark.integration`): Test API endpoints, database interactions
- **Gmail tests** (`@pytest.mark.gmail`): Marker exists but tests not yet implemented

Run focused tests during development: `pytest -m unit -v`

## Deprecated Scripts

- `shopq/scripts/consolidate_databases.py` - One-time migration script, safe to delete
