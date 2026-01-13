# Contributing to MailQ

This document outlines conventions and best practices for contributing to the MailQ project.

## Documentation Conventions

### When to Update Documentation

Every significant change should update the appropriate documentation files:

| Change Type | Update These Files |
|-------------|-------------------|
| New feature or major change | `claude.md`, relevant `docs/*.md`, add entry to changelog section below |
| Bug fix | Add to changelog section below, update relevant `docs/*.md` if behavior changed |
| Configuration change | `docs/CONFIGURATION.md`, `.env.example` |
| API endpoint change | `docs/ARCHITECTURE.md`, `claude.md` |
| Database schema change | `docs/DATABASE_ARCHITECTURE.md` |
| Deployment process | `docs/DEPLOYMENT_PLAYBOOK.md`, `QUICKSTART.md` |
| Testing procedures | `docs/TESTING.md` |
| Prompt changes | `mailq/prompts/README.md`, increment `PROMPT_VERSION` in `mailq/versioning.py` |
| Model/prompt version change | `mailq/versioning.py`, `VERSIONS.md`, follow workflow in this file |
| Rollback thresholds | `docs/ROLLBACK_CONDITIONS.md`, `config/mailq_policy.yaml` |

### Documentation Structure

```
/
├── claude.md              # AI assistant quick reference
├── CONTRIBUTING.md        # This file - conventions and practices
├── INDEX.md               # Master navigation
├── QUICKSTART.md          # Getting started guide
├── docs/
│   ├── ARCHITECTURE.md    # System design deep-dive
│   ├── CONFIGURATION.md   # Environment and config
│   ├── DEBUGGING.md       # Troubleshooting guide
│   ├── DEPLOYMENT_PLAYBOOK.md
│   ├── TESTING.md
│   └── WORKFLOWS.md
└── mailq/prompts/README.md  # Prompt engineering guide
```

### Changelog Entries

When making significant changes, add a changelog entry below:

## Changelog

### 2025-11-09 - Version Tracking & Rollback Infrastructure
- Added version stamping infrastructure (`mailq/versioning.py`)
- Created `VERSIONS.md` to track model/prompt version history
- Added `docs/ROLLBACK_CONDITIONS.md` with exact rollback thresholds
- Updated confidence logger to persist version metadata in all classifications
- Added comprehensive version tracking tests (`tests/test_versioning.py`)
- Updated `CONTRIBUTING.md` with version change workflow

### 2025-11-06 - Documentation Organization
- Organized quality monitoring documentation
- Updated CONTRIBUTING.md with quality monitoring workflows
- Clarified manual vs automated quality processes

### 2025-11-05 - Quality Monitoring System
- Added automated quality monitor daemon with AI-powered analysis
- Implemented 24/7 classification quality monitoring
- Added GitHub issue auto-creation for quality problems
- Created digest quality comparison workflow for manual testing

### 2025-11-01 - Verify-First Strategy
- Implemented two-pass verification for higher accuracy
- Reduced false positives in importance classification
- Added confidence scoring improvements

### 2025-10-31 - Database-Backed Categorization
- Migrated digest rules from hardcoded logic to SQLite database
- Added DigestCategorizer class with pattern matching
- Improved transparency and maintainability of digest logic

---

## Logging Conventions

### What to Log

**Always log:**
- Classification decisions (type, confidence, reasoning)
- Verifier invocations and results
- API errors and exceptions
- Performance metrics (latency, token usage)
- User feedback events (label corrections)

**Never log:**
- Email body content (privacy)
- Credentials or API keys
- Personal information (names, addresses)

### Logging Format

Use structured logging with clear prefixes:

```python
# Good
logger.info(f"Classification: type={classification.type} confidence={confidence:.2f} sender={sender}")
logger.error(f"API error: endpoint=/api/organize status={response.status_code}")

# Bad
logger.info("classified email")
logger.error("error")
```

### Log Levels

- `DEBUG`: Detailed diagnostic info (disabled in production)
- `INFO`: Normal operations (classifications, API calls)
- `WARNING`: Unexpected but handled situations (low confidence, retries)
- `ERROR`: Errors that need attention (API failures, exceptions)
- `CRITICAL`: System-breaking issues (service down, quota exceeded)

### Where Logs Live

| Component | Log Location |
|-----------|-------------|
| Local backend | `stdout` (captured by uvicorn) |
| Cloud Run | Google Cloud Logging (view with `gcloud logging read`) |
| Extension | Browser DevTools Console (F12 in Gmail) |
| Quality Monitor | `quality_monitor.log` |

## Code Organization

### Directory Structure

```
mailq/                  # Backend Python package
  ├── api*.py          # API endpoints
  ├── *_classifier.py  # Classification logic
  ├── prompts/         # LLM prompts (editable!)
  └── learning/        # Feedback and learning
extension/             # Chrome extension
  ├── modules/         # Feature modules
  └── Schema.json      # Classification schema
scripts/               # Utility scripts
  ├── quality-monitor/ # Quality monitoring system
  └── ...
docs/                  # Documentation
tests/                 # Test suites
```

### File Naming

- Python modules: `snake_case.py`
- JavaScript modules: `camelCase.js` or `kebab-case.js`
- Documentation: `SCREAMING_SNAKE_CASE.md`
- Scripts: `kebab-case.sh`

### When to Create New Files

- **New docs in `docs/`**: When documenting a new major feature or system
- **New scripts in `scripts/`**: When creating reusable automation
- **Archive old docs**: Move to `docs/archive/` when superseded, don't delete

## Git Commit Conventions

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring without behavior change
- `docs`: Documentation only
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**

```
feat: Add two-pass verification for importance scoring

Implement verifier that challenges initial classifications
to reduce false positives in digest categorization.

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

```
fix: Correct event time parsing for multi-day events

Previous logic only checked single date, now handles
date ranges correctly.

Fixes #123
```

### What to Commit

**Always commit:**
- Code changes
- Documentation updates
- Configuration files (`.env.example`, not `.env`)
- Test files

**Never commit:**
- `.env` files with secrets
- `credentials.json`
- Database files (`*.db`, `*.sqlite`)
- Log files (`*.log`)
- `node_modules/` or `venv/`

## Model and Prompt Version Management

### Why Version Tracking Matters

Every classification in MailQ is logged with three version identifiers:
- **model_name**: The LLM being used (e.g., `gemini-2.0-flash`)
- **model_version**: Model version string (e.g., `2.0`)
- **prompt_version**: Prompt template version (e.g., `v1`)

This enables:
- **Reproducible baselines**: Golden dataset results are tied to exact versions
- **A/B testing**: Shadow deployments can compare version combinations
- **Debugging**: When precision drops, trace it to a specific version change
- **Audit trail**: Know which model/prompt produced which classification

### Version Change Workflow

**IMPORTANT**: Changing model or prompt versions requires following this workflow:

1. **Before making changes:**
   - Document the reason for the change
   - Identify what you're changing (model, prompt, or both)

2. **Update version constants** in `mailq/versioning.py`:
   ```python
   MODEL_NAME = "gemini-2.0-flash"  # Change if switching models
   MODEL_VERSION = "2.0"             # Change if model provider updates
   PROMPT_VERSION = "v2"             # Increment for prompt changes
   ```

3. **Add entry to `VERSIONS.md`**:
   ```markdown
   | 2025-11-10 | gemini-2.0-flash  | 2.0  | v2  | Updated few-shot examples for better receipt detection |
   ```

4. **Run shadow period** (minimum 3 days):
   - Deploy new version alongside current version
   - Log both results with version pins
   - Compare classifications: `{current vs new}`
   - Inspect weekday/weekend drift

5. **Replay golden set**:
   - Run new version against golden dataset
   - Compare precision/recall/cost/latency to baseline
   - Update `baseline.md` with new version results

6. **Deploy** only after validating:
   - No regression in critical precision (≥ baseline - 5pp)
   - No significant cost increase (< baseline + 20%)
   - No latency degradation (p95 < baseline + 50ms)

7. **Monitor** post-deployment:
   - Watch automated quality monitor for new issues
   - Track confidence score distributions
   - Verify version fields in logs match expected values

### What Requires a Version Bump

**Prompt version bump required for:**
- Changes to few-shot examples
- Changes to classification instructions
- Changes to output schema or field definitions
- Changes to domain definitions or categories

**Prompt version bump NOT required for:**
- Formatting changes (whitespace, line breaks)
- Comment updates in prompts
- Variable name changes that don't affect output

**Model version bump required for:**
- Switching to a different model (e.g., GPT-4 → Gemini)
- Model provider updates the underlying model

### Version Verification

Run tests to verify versions are being logged:
```bash
pytest tests/test_versioning.py -v
```

Check recent classifications include versions:
```bash
sqlite3 mailq.db "SELECT model_name, model_version, prompt_version, type, type_conf FROM confidence_logs ORDER BY timestamp DESC LIMIT 10"
```

## Testing Requirements

### Before Committing

1. Run tests: `pytest -v`
2. Check classification accuracy: Test with sample emails
3. Verify extension loads: Test in Chrome
4. Review logs: Check for errors or warnings
5. **If changed model/prompt**: Verify version bump and VERSIONS.md entry

### Adding Tests

- Add unit tests in `tests/` for new backend functions
- Add integration tests for new API endpoints
- Document test cases in `docs/TESTING.md`

## Quality Monitoring

MailQ has two quality monitoring systems:

### 1. Automated Quality Monitor (Production)

**Purpose**: Continuous AI-powered monitoring of classification quality in production

**When to use**:
- Ongoing quality monitoring (runs 24/7)
- Detecting systematic classification issues
- Auto-creating GitHub issues for problems

**How to use**:
```bash
# Start the daemon
./run-quality-monitor.sh &

# Check status
./quality-monitor-status.sh

# View detected issues
./view-quality-issues.sh
```

**What it monitors**:
- `/api/tracking/sessions` endpoint (production digest sessions)
- Classification patterns and systematic issues
- Misclassification rates by category
- Confidence score distributions

**Documentation**: See `docs/QUALITY_MONITOR.md` (includes complete pipeline architecture)

### 2. Manual Digest Quality Comparison (Development)

**Purpose**: Manual testing and comparison of digest outputs during development

**When to use**:
- Testing changes to digest logic
- Validating importance classification improvements
- Before deploying digest algorithm changes

**How to use**:
```bash
# 1. Generate a test digest (via extension or API)
# Logs saved to: quality_logs/actual_digest_TIMESTAMP.html
#                quality_logs/input_emails_TIMESTAMP.json

# 2. Generate comparison with AI-suggested ideal
python scripts/generate_ideal_digest.py

# 3. Review comparison file
open quality_logs/comparison_TIMESTAMP.md

# 4. Edit the suggested ideal to match your judgment
# 5. Identify gaps and fix classification logic
```

**Documentation**: See `docs/DIGEST_QUALITY_WORKFLOW.md`

### When Changes Affect Classification

**If changing digest logic** (importance patterns, categorization):
1. Run manual digest comparison (Method 2)
2. Verify improvements before deploying
3. Monitor automated quality monitor after deploy

**If changing email classification** (types, domains):
1. Run tests: `pytest -v`
2. Check automated quality monitor for new issues
3. Monitor verifier rejection rate in Cloud Run logs

## AI Assistant Guidelines

This project uses Claude Code. When working with AI:

1. Reference `claude.md` for quick context
2. Update `claude.md` when adding major features
3. Keep prompts in `mailq/prompts/` directory (not hardcoded)
4. Document prompt changes in `mailq/prompts/README.md`

## Questions?

- Check `INDEX.md` for documentation navigation
- See `QUICKSTART.md` for common tasks
- Review `docs/ARCHITECTURE.md` for system design
- Ask in project issues or discussions
