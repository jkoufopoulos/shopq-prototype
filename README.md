# MailQ - AI-Powered Gmail Assistant

**Privacy-first email classification and digest generation for Gmail**

[![Status](https://img.shields.io/badge/status-MVP%20Development-blue)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue)]()
[![License](https://img.shields.io/badge/license-Proprietary-red)]()

---

## What is MailQ?

MailQ is an AI-powered Gmail assistant that automatically organizes your inbox and generates glanceable daily email digests. It uses a hybrid classification system combining deterministic rules with Gemini LLM fallback to achieve high precision while keeping costs low.

**Key Features:**
- 🎯 **Smart Classification** - Rules engine + Gemini LLM with two-pass verification
- 📧 **Auto-Organization** - Automatic Gmail label application and archiving
- 📊 **Daily Digests** - Glanceable HTML summaries of what matters
- 🔒 **Privacy-First** - Read-only by default, 14-day retention, no third-party data sharing
- 💰 **Cost-Efficient** - ~$0.0001 per email, rules cache saves 50-70% of LLM costs

**Architecture:**
- **Backend**: Python FastAPI + SQLite + Vertex AI (Gemini 2.0 Flash)
- **Frontend**: Chrome Extension (TypeScript)
- **Classification**: Rules engine → Gemini classifier → Verifier → Gmail labels
- **Digest**: Multi-stage pipeline with temporal decay and importance scoring

---

## Quick Start

### For Developers

```bash
# Clone and setup
git clone <repo-url>
cd mailq-prototype

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add your GOOGLE_API_KEY

# Run backend
uvicorn mailq.api:app --reload

# Load Chrome extension
# 1. Open chrome://extensions/
# 2. Enable Developer Mode
# 3. Load unpacked from extension/ directory
```

👉 **Complete setup guide**: [QUICKSTART.md](QUICKSTART.md)

### For AI Assistants (Claude, Cursor, etc.)

Start with these files for full context:
1. **[MAILQ_REFERENCE.md](MAILQ_REFERENCE.md)** - Complete system reference and architecture
2. **[claude.md](claude.md)** - Development guardrails and workflows
3. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Detailed technical design

---

## Documentation

### Essential Reading
- **[INDEX.md](INDEX.md)** - 📚 Complete documentation map
- **[QUICKSTART.md](QUICKSTART.md)** - 🚀 Setup, running, and common tasks
- **[MAILQ_REFERENCE.md](MAILQ_REFERENCE.md)** - 📖 AI assistant guide and project overview
- **[ROADMAP.md](ROADMAP.md)** - 🗺️ Feature roadmap and development status

### Technical Documentation
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design and data flow
- **[docs/DATABASE_ARCHITECTURE.md](docs/DATABASE_ARCHITECTURE.md)** - Database schema and policies
- **[docs/TESTING.md](docs/TESTING.md)** - Test procedures and workflows
- **[docs/DEPLOYMENT_PLAYBOOK.md](docs/DEPLOYMENT_PLAYBOOK.md)** - Production deployment guide

### Development
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development conventions and changelog
- **[claude.md](claude.md)** - AI pair-programming guardrails
- **[config/mailq_policy.yaml](config/mailq_policy.yaml)** - Runtime configuration

### Visual Documentation
- **[code-graph/](code-graph/)** - Auto-generated system diagrams
- **[code-graph/visuals/html/index.html](code-graph/visuals/html/index.html)** - Interactive diagram viewer

---

## Project Structure

```
mailq-prototype/
├── mailq/                    # Backend (Python/FastAPI)
│   ├── api.py                # Main API entry point
│   ├── digest/               # Digest generation pipeline
│   ├── bridge/               # Classification bridge components
│   ├── config/               # Configuration and database
│   ├── prompts/              # LLM prompts (editable!)
│   └── tests/                # Backend tests
│
├── extension/                # Chrome extension (TypeScript)
│   ├── background.js         # Service worker
│   ├── content.js            # Gmail page integration
│   └── modules/              # Core extension modules
│
├── docs/                     # Detailed documentation
├── tests/                    # Test suites
├── scripts/                  # Utility scripts
├── config/                   # Configuration files
└── code-graph/               # Visual documentation
```

---

## Key Concepts

### Classification Pipeline

```
Email → Rules Engine → [Match?] → Cache result (Free)
              ↓ No match
       Gemini Classifier → Classification (~$0.0001)
              ↓
       Confidence Filter → [High?] → Apply labels
              ↓ Suspicious
          Verifier LLM → Verify/Correct → Final labels
```

### Digest Pipeline

```
Emails → Stage 1: Importance Classification (CRITICAL/TIME_SENSITIVE/ROUTINE/NOISE)
       → Stage 2: Temporal Enrichment (event times, deadlines, OTPs)
       → Stage 3: Temporal Modulation (adjust importance based on timing)
       → Stage 4: Categorization (CRITICAL/TODAY/COMING_UP/WORTH_KNOWING/etc.)
       → Stage 5: Rendering (deterministic HTML output)
```

### Database Policy

MailQ uses **ONE central SQLite database**: `mailq/data/mailq.db`

- All tables use `user_id` for multi-tenancy
- Connection pooling for performance
- 14-day retention policy with automated cleanup
- WAL mode with regular checkpointing

---

## Configuration

All configuration is in `.env` file:

```bash
# Required
GOOGLE_API_KEY=AIzaSy...              # Vertex AI API key
GOOGLE_CLOUD_PROJECT=your-project     # GCP project ID
GEMINI_MODEL=gemini-2.0-flash         # Model to use

# Optional
API_PORT=8000                         # API server port
USE_RULES_ENGINE=true                 # Enable rules (recommended)
USE_AI_CLASSIFIER=true                # Enable LLM fallback

# Quality Monitoring
ANTHROPIC_API_KEY=sk-ant-...          # For automated quality analysis
GITHUB_TOKEN=ghp_...                  # For creating quality issues
```

See [MAILQ_REFERENCE.md](MAILQ_REFERENCE.md) for complete configuration reference.

---

## Development Status

**Current Phase**: MVP Development (20-40 users)

**Completed** ✅:
- Type Mapper (100% calendar event accuracy)
- Database Consolidation + Multi-tenancy
- Temporal Decay for Events
- Privacy & Retention (14-day policy)
- Model/Prompt Versioning
- Quality Monitoring System

**In Progress** 🟡:
- Deterministic Digest Rendering
- Importance Mapper Rules

**Upcoming** 🔴:
- Multi-user Authentication (OAuth)
- Public Beta Launch

See [ROADMAP.md](ROADMAP.md) for detailed development plan.

---

## Testing

```bash
# Backend tests
pytest                       # All tests
pytest -v                    # Verbose output
pytest -m unit               # Unit tests only

# Extension tests
cd extension && npm test

# Quality monitoring
./scripts/start-quality-system.sh
```

See [docs/TESTING.md](docs/TESTING.md) for comprehensive testing guide.

---

## Deployment

```bash
# Deploy to Google Cloud Run
./deploy.sh

# Verify deployment
curl https://your-service-url/health
```

See [docs/DEPLOYMENT_PLAYBOOK.md](docs/DEPLOYMENT_PLAYBOOK.md) for detailed deployment procedures.

---

## Support & Contributing

- **Documentation**: See [INDEX.md](INDEX.md) for complete navigation
- **Issues**: GitHub Issues (quality issues auto-created by monitoring system)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)
- **AI Development**: Follow [claude.md](claude.md) guardrails

---

## License

Proprietary - All rights reserved

---

## Architecture Highlights

### Rules Engine (T0 - Free)
- Exact sender matching in SQLite
- Learns from user corrections
- 50-70% cache hit rate = $0 cost

### Gemini Classifier (T3 - ~$0.0001)
- Gemini 2.0 Flash (fast, cheap)
- Temperature 0.2 (consistent)
- Multi-dimensional classification

### Verifier (Selective, ~10-20%)
- Second LLM pass for suspicious cases
- Temperature 0.1 (conservative)
- Challenges first classification

### Hybrid Digest Renderer
- Deterministic Pydantic-based rendering
- No LLM prose in output
- Byte-identical snapshots for testing

---

**For complete documentation, start with [INDEX.md](INDEX.md) or [QUICKSTART.md](QUICKSTART.md)**

**For AI assistants, read [MAILQ_REFERENCE.md](MAILQ_REFERENCE.md) first**
