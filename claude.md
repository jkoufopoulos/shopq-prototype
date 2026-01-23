# ShopQ Return Watch - Claude Code Guidelines

## Project Overview

**ShopQ Return Watch** is a Gmail companion that automatically detects online purchases from order/delivery emails and tracks return deadlines. It helps users never miss return windows through a three-stage AI extraction pipeline.

**Architecture**: Python FastAPI backend + Chrome Manifest V3 extension
**AI Model**: Google Gemini (via Vertex AI)
**Database**: SQLite (single centralized database)
**Deployment**: Google Cloud Run

## North Star

Help users track and act on return windows before they expire. Every feature should make it easier to:
1. Detect purchases from Gmail
2. Calculate accurate return deadlines
3. Surface expiring returns at the right time

## Critical Rules

### Single Database Principle
All features use ONE centralized SQLite database at `shopq/data/shopq.db`. Creating new databases is forbidden without architectural review. Use `shopq/infrastructure/database.py` for all database access.

### Three-Stage Extraction Pipeline
Email processing follows a fixed cost-optimization pattern:
1. **Filter (Stage 1)**: Domain blocklist/allowlist - FREE, rejects ~70% of emails
2. **Classifier (Stage 2)**: LLM returnability check - ~$0.0001 per email
3. **Extractor (Stage 3)**: Field extraction + date calculation - ~$0.0002 per email

Never bypass stages. See `shopq/returns/extractor.py` for orchestration.

### Module Import Convention
Always use explicit `shopq.*` imports for Docker compatibility:
```python
# Correct
from shopq.returns.models import ReturnCard
from shopq.returns.extractor import ExtractionPipeline

# Wrong
from returns.models import ReturnCard
```

## Key Directories

```
shopq/                      # Python backend
├── api/                    # FastAPI routes and middleware
├── returns/                # Core return tracking domain
│   ├── models.py           # ReturnCard, ReturnStatus, ReturnConfidence
│   ├── extractor.py        # 3-stage pipeline orchestrator
│   ├── filters.py          # Stage 1: Domain filtering
│   ├── returnability_classifier.py  # Stage 2: LLM check
│   ├── field_extractor.py  # Stage 3: Field extraction
│   └── repository.py       # Database persistence
├── infrastructure/         # Database, cross-cutting concerns
├── gmail/                  # Gmail API client
├── llm/                    # LLM client abstraction
└── utils/                  # Email parsing, PII redaction

extension/                  # Chrome Extension
├── background.js           # Service worker for email scanning
├── popup.js                # Extension popup UI
├── returns-sidebar-inner.js # Gmail sidebar
├── modules/                # Shared JS modules
│   ├── returns/api.js      # Backend API client
│   └── gmail/              # Gmail API + OAuth
└── dist/                   # Built artifacts (webpack)

config/
└── merchant_rules.yaml     # Return policies by merchant domain
```

## Data Models

### ReturnCard
Core domain model with these key fields:
- `status`: ACTIVE | EXPIRING_SOON | EXPIRED | RETURNED | DISMISSED
- `confidence`: EXACT (explicit date) | ESTIMATED (calculated) | UNKNOWN
- `return_by_date`: Calculated deadline
- `merchant_name`, `item_description`, `purchase_date`, `order_id`

Use `to_db_dict()` and `from_db_row()` for persistence.

### Merchant Rules (YAML)
Return policies live in `config/merchant_rules.yaml`:
```yaml
amazon.com:
  return_window_days: 30
  anchor: delivery  # or "order"
```
Default: 30 days from delivery for unknown merchants.

## Development Commands

### Backend
```bash
# Install dependencies
uv sync

# Run API server (development)
uv run uvicorn shopq.api.app:app --reload

# Run tests
PYTHONPATH=. SHOPQ_USE_LLM=false uv run pytest tests/ -v

# Code quality
make fmt        # Auto-format with ruff
make lint       # Check formatting + linting
make typecheck  # Run mypy
make ci         # Full CI pipeline
```

### Extension
```bash
cd extension
npm install
npm run build   # Production build
npm run watch   # Development with hot reload
npm test        # Run tests
```

Load in Chrome: `chrome://extensions` → Developer mode → Load unpacked → select `extension/`

## Environment Variables

Required in `.env`:
```bash
GOOGLE_API_KEY              # Gemini API key
GOOGLE_CLOUD_PROJECT        # GCP project ID
SHOPQ_ENV                   # development | production
SHOPQ_USE_LLM               # true | false (disable for tests)
```

## Code Style

- **Python**: Ruff formatter, line length 100, Google-style docstrings
- **JavaScript**: ESLint, Webpack bundling
- **Commits**: Semantic prefixes (`feat:`, `fix:`, `test:`)

## API Design Patterns

- FastAPI + Pydantic for strong typing
- Rate limiting: 60 req/min, 1000 req/hour per user
- CORS restricted to known origins (localhost allowed in dev)
- Use `@retry_on_db_lock()` decorator for SQLite operations

## Testing

```bash
# Integration tests (mock LLM)
SHOPQ_USE_LLM=false pytest tests/integration/ -v

# Specific test file
pytest tests/integration/test_extraction_pipeline.py -v
```

## Common Tasks

### Adding a New Merchant
Edit `config/merchant_rules.yaml`:
```yaml
newstore.com:
  return_window_days: 14
  anchor: order
```

### Debugging Extraction
Enable verbose logging or check the extraction pipeline:
```python
from shopq.returns.extractor import ExtractionPipeline
pipeline = ExtractionPipeline()
result = pipeline.process_email(email_content)
```

### Database Queries
Always use the infrastructure module:
```python
from shopq.infrastructure.database import get_db_connection
with get_db_connection() as conn:
    # queries here
```

## Known Issues & Tech Debt

See `BACKLOG.md` for the full prioritized list. Key items:

### Critical (P0) - Must fix before production
- **No user authentication** on API endpoints - anyone can access any user's data
- **All users share `default_user`** - no privacy isolation
- **XSS vulnerability** in extension content script

### High Priority (P1) - Fix before scaling
- In-memory rate limiting doesn't work with multiple Cloud Run instances
- No LLM cost budget/rate limiting
- SQLite on ephemeral storage (data loss on instance restart)
- `datetime.utcnow()` deprecated - use `datetime.now(timezone.utc)`

## Architecture Review Notes

**Scores**: Architecture 7/10, Code Quality 5/10

**Strengths**:
- Well-designed 3-stage pipeline (cost-optimized)
- Good observability (telemetry, structured logging)
- Proper SQLite concurrency (`@retry_on_db_lock`)
- Clean module boundaries and repository pattern

**Weaknesses**:
- Security gaps (auth, user isolation, XSS)
- Scalability limitations (in-memory state, ephemeral DB)
- Test coverage gaps

## Agents

Custom agents are available in `.claude/agents/`:
- **architecture-advisor**: Design decisions, technology comparisons, refactoring strategy
- **code-reviewer**: Security vulnerabilities, error handling, code quality

Use via Task tool with appropriate prompts.
