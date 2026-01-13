# MailQ Project Structure

> Last updated: 2025-11-06

## Overview

Clean, organized structure with all code, documentation, and scripts in logical locations.

## Directory Structure

```
mailq-prototype/
├── 📄 Core Documentation
│   ├── README.md                    # Project overview
│   ├── MAILQ_REFERENCE.md                    # AI assistant guide (TL;DR architecture)
│   ├── INDEX.md                     # Master navigation
│   ├── QUICKSTART.md                # Setup & common tasks
│   └── ROADMAP.md                   # Future plans
│
├── ⚙️  Configuration
│   ├── requirements.txt             # Python dependencies
│   ├── setup.py                     # Python package setup
│   ├── pytest.ini                   # Test configuration
│   ├── package.json                 # Node dependencies (for tests)
│   ├── playwright.config.js         # E2E test configuration
│   ├── .env                         # Environment variables (git-ignored)
│   ├── .gitignore                   # Git ignore rules
│   ├── Dockerfile                   # Docker container definition
│   ├── cloud-scheduler.yaml         # GCP Cloud Scheduler config
│   └── credentials.json             # Gmail API credentials
│
├── 🐍 mailq/                        # Python backend (FastAPI)
│   ├── api.py                       # Main FastAPI app
│   ├── api_*.py                     # API route modules
│   ├── *_classifier.py              # Classification logic
│   ├── *_extractor.py               # Entity extraction
│   ├── *_generator.py               # Content generation
│   ├── *_manager.py                 # Business logic managers
│   ├── entities.py                  # Entity data models
│   ├── mapper.py                    # Label mapping
│   │
│   ├── config/                      # Configuration modules
│   │   ├── confidence.py            # Confidence thresholds
│   │   ├── database.py              # Database paths
│   │   ├── settings.py              # General settings
│   │   └── default_categories.py   # Category definitions
│   │
│   ├── db/                          # Database layer
│   │   └── *.py                     # Repository classes
│   │
│   ├── prompts/                     # LLM prompts (external files)
│   │   ├── classifier_prompt.txt   # Main classifier
│   │   ├── verifier_prompt.txt     # Verification pass
│   │   └── README.md               # Prompt management guide
│   │
│   ├── data/                        # SQLite databases
│   │   ├── mailq.db                 # Main database
│   │   └── backups/                 # Database backups
│   │
│   ├── logs/                        # Application logs
│   └── tests/                       # Python unit tests
│
├── 🧩 extension/                    # Chrome extension
│   ├── background.js                # Service worker (main logic)
│   ├── content.js                   # Gmail DOM integration
│   ├── config.js                    # Extension configuration
│   ├── manifest.json                # Chrome extension manifest
│   │
│   ├── modules/                     # JavaScript modules
│   │   ├── gmail.js                 # Gmail API operations
│   │   ├── classifier.js            # API client
│   │   ├── verifier.js              # Verifier client
│   │   ├── mapper.js                # Label mapping
│   │   ├── cache.js                 # Caching (24hr expiry)
│   │   ├── budget.js                # Cost tracking
│   │   ├── detectors.js             # Pattern detection
│   │   ├── auto-organize.js         # Auto-organization
│   │   ├── summary-email.js         # Digest email generation
│   │   └── *.js                     # Other utilities
│   │
│   ├── icons/                       # Extension icons
│   └── tests/                       # Extension tests
│
├── 📚 docs/                         # Active Documentation (25 files)
│   ├── Architecture & Operations
│   │   ├── ARCHITECTURE.md          # Comprehensive system design
│   │   ├── ARCHITECTURE_OVERVIEW.md # High-level overview
│   │   ├── DATABASE_ARCHITECTURE.md # Database schema
│   │   ├── CONFIGURATION.md         # Environment setup
│   │   ├── DEBUGGING.md             # Troubleshooting guide
│   │   ├── TESTING.md               # Test procedures
│   │   ├── DEPLOYMENT_PLAYBOOK.md   # Deployment guide
│   │   ├── WORKFLOWS.md             # Development workflows
│   │   ├── PROJECT_STRUCTURE.md     # This file
│   │   ├── DEPENDENCY_GRAPH.md      # Component dependencies
│   │   └── SQL_GUIDE.md             # SQL operations
│   │
│   ├── Active Systems & Features
│   │   ├── VERIFY_FIRST_STRATEGY.md # Two-pass verification
│   │   ├── IMPORTANCE_LEARNING.md   # Learning system
│   │   ├── LABEL_CACHE.md           # In-memory caching
│   │   ├── DYNAMIC_EXAMPLES.md      # Few-shot learning
│   │   ├── LLM_USAGE_IN_DIGEST.md   # LLM pipeline reference
│   │   └── GMAIL_CATEGORIES.md      # Gmail labels
│   │
│   ├── Quality Monitoring
│   │   ├── QUALITY_MONITOR.md       # Automated monitoring
│   │   ├── QUALITY_CONTROL_PIPELINE.md # Pipeline overview
│   │   └── DIGEST_QUALITY_WORKFLOW.md # Manual testing
│   │
│   ├── Production Monitoring
│   │   ├── MONITORING_ALERTS.md     # SLOs and alerts
│   │   ├── OBSERVABILITY_MAP.md     # Logging/metrics
│   │   ├── RISK_REGISTER.md         # Risk mitigation
│   │   └── PRODUCTION_READINESS.md  # Pre-launch checklist
│   │
│   └── Implementation Guides
│       └── BACKEND_WEBHOOK_INTEGRATION.md # Webhook setup
│
├── 🔧 scripts/                      # Utility scripts
│   ├── mailq-db                     # Database CLI tool
│   ├── mailq-debug                  # Debugging CLI
│   ├── auto-fix-tests.sh            # Automated test fixing
│   ├── run-full-e2e-tests.sh        # E2E test runner
│   ├── test-with-my-gmail.sh        # Manual Gmail testing
│   ├── test-digest-quality.sh       # Digest quality tests
│   ├── validate-digest.sh           # Digest validation
│   ├── watch-and-debug.sh           # Watch mode debugging
│   └── claude-iterate-digest.sh     # Iterative digest improvement
│
├── 🧪 tests/                        # Integration tests
│   ├── test_*.py                    # Python integration tests
│   ├── e2e/                         # End-to-end tests
│   └── manual/                      # Manual test procedures
│
├── 📦 data/                         # Data storage
│   └── test-fixtures/               # Test data files
│       ├── new_digest_request.json
│       ├── old_digest_response.json
│       └── test_verifier.json
│
├── 📊 code-graph/                   # Diagram generation (auto-updated)
│   ├── scripts/                     # Diagram generation scripts
│   ├── visuals/                     # Generated diagrams
│   └── README.md                    # Documentation
│
├── 🗄️ archive/                      # Historical Documentation & Code
│   ├── docs/                        # Recent doc archives (Nov 2025)
│   │   ├── digest/                  # Digest development (8 docs)
│   │   ├── fixes/                   # Completed bug fixes (7 docs)
│   │   ├── phases/                  # Phase documentation (10 docs)
│   │   ├── planning/                # Superseded plans (6 docs)
│   │   ├── prds/                    # Implemented PRDs (4 docs)
│   │   └── quality/                 # Quality setup history (3 docs)
│   │
│   ├── implementation/              # Feature implementations (14 docs)
│   ├── confidence/                  # Confidence system history
│   ├── refactoring/                 # Refactoring plans
│   ├── deprecated_20251031/         # Oct 31 cleanup
│   ├── old_digest_systems/          # Previous implementations
│   └── README.md                    # Archive index
│
└── 🚀 Deployment
    └── deploy.sh                    # Deploy to Cloud Run

```

## Key Directories Explained

### `/mailq` - Python Backend
- FastAPI application
- Email classification, entity extraction, digest generation
- SQLite database storage
- LLM integration (Vertex AI Gemini)

### `/extension` - Chrome Extension
- Service worker architecture
- Gmail API integration
- Client-side classification orchestration
- Daily digest email generation

### `/docs` - Active Documentation
- 25 current reference documents
- Organized into 5 categories: Architecture, Systems, Quality, Production, Implementation
- Historical docs moved to `/archive/docs/`
- See INDEX.md for complete navigation

### `/scripts` - Utility Scripts
- CLI tools for database management and debugging
- Test automation scripts
- Setup utilities
- Consolidated from root directory

### `/tests` - Test Suite
- Python integration tests
- E2E tests using Playwright
- Test results stored in `test-results/`

### `/data` - Data Storage
- `mailq.db` - Main database (in `/mailq/data/`)
- Test fixtures in `test-fixtures/`
- CSV exports (git-ignored)

### `/archive` - Historical Documentation & Code
- **Single location** for all archived content
- `archive/docs/` - Recent documentation archives (38 docs from Nov 2025)
- Organized subdirectories for implementation docs, confidence system, refactoring plans
- Deprecated implementations preserved for reference
- Comprehensive README.md index

## Important Files

| File | Purpose |
|------|---------|
| `mailq/api.py` | Main FastAPI application entry point |
| `mailq/prompts/classifier_prompt.txt` | LLM classification prompt (editable!) |
| `extension/background.js` | Chrome extension service worker |
| `extension/modules/gmail.js` | Gmail API operations |
| `scripts/mailq-debug` | Debugging CLI tool |
| `scripts/mailq-db` | Database management CLI |
| `.env` | Environment variables (API keys, etc.) |
| `requirements.txt` | Python dependencies |

## Configuration Files

- **Python**: `requirements.txt`, `setup.py`, `pytest.ini`
- **Node/Testing**: `package.json`, `playwright.config.js`
- **Docker**: `Dockerfile`
- **GCP**: `cloud-scheduler.yaml`
- **Git**: `.gitignore`
- **Environment**: `.env` (git-ignored, use `.env.example` as template)

## Generated/Ignored Directories

These exist locally but are git-ignored:

- `venv/` - Python virtual environment
- `node_modules/` - Node dependencies
- `__pycache__/` - Python bytecode
- `exports/` - CSV exports from organize sessions
- `credentials/` - Gmail API tokens
- `test-results/` - Test output files
- `playwright-report/` - Test reports
- `.pytest_cache/` - Pytest cache

## Cleanup History

**2025-11-06 Documentation Consolidation:**
- Archived 35 historical docs from `docs/` to `archive/docs/`
- Consolidated `docs/archive/` into unified `/archive` location
- Reduced active documentation from 60 to 25 files (58% reduction)
- Created comprehensive archive index with categorization
- Updated CONTRIBUTING.md with quality monitoring workflows
- Updated INDEX.md with organized documentation structure

**2025-10-31 Major Reorganization:**
- Root directory reduced from 60+ items to ~15 core files
- Documentation moved to `docs/` (10 files)
- Fix tracking moved to `docs/fixes/` (6 files)
- Scripts consolidated to `scripts/` (10 files)
- Test fixtures organized in `data/test-fixtures/`
- Unused modules archived to `archive/deprecated_20251031/`
- Temporary files and empty databases removed

## Navigation

- **Getting Started**: See `QUICKSTART.md`
- **Architecture**: See `MAILQ_REFERENCE.md` (TL;DR) or `docs/DATABASE_ARCHITECTURE.md` (detailed)
- **Testing**: See `docs/E2E_TESTING_GUIDE.md` or `docs/TESTING_GUIDE.md`
- **Feature Flags**: See `docs/FEATURE_GATES.md`
- **All Documentation**: See `INDEX.md`

---

For questions about structure or to suggest improvements, see `MAILQ_REFERENCE.md` for AI assistant guidance.
