# ShopQ - AI Assistant Guide

> **TL;DR**: AI-powered Gmail classifier. Hybrid Python/FastAPI backend + Chrome extension. Uses Vertex AI Gemini 2.0 with two-pass verification. Rules-first, then LLM.

## Quick Context

**What**: Email classification system for Gmail
**How**: Rules → LLM Classifier → Verifier → Gmail Labels
**Stack**: Python (FastAPI) + Chrome Extension + Vertex AI (Gemini)
**Databases**: SQLite (rules.db, feedback.db, shopq.sqlite)

## Core Architecture

```
Email → Rules Engine → [Match?] → Cache result (T0 cost: free)
              ↓ No match
       Gemini Classifier → Classification result (T3 cost: ~$0.0001)
              ↓
       Confidence Filter → [High?] → Apply labels
              ↓ Suspicious
          Verifier LLM → Verify/Correct → Final labels
```

### Classification Dimensions

```json
{
  "type": "newsletter|notification|receipt|event|promotion|message",
  "domains": ["finance", "shopping", "professional", "personal"],
  "attention": "action_required|none",
  "relationship": "from_contact|from_unknown"
}
```

### Gmail Label Mapping

```
Type → ShopQ-{Type}              (e.g., ShopQ-Newsletters)
Domain → ShopQ-{Domain}          (e.g., ShopQ-Finance)
Attention → ShopQ-Action-Required
```

## Key Files

### Backend (shopq/)

| File | Purpose |
|------|---------|
| `api.py` | FastAPI app, endpoints |
| `memory_classifier.py` | Classification orchestrator |
| `vertex_gemini_classifier.py` | Gemini LLM integration |
| `api_verify.py` | Verifier (2nd LLM pass) |
| `rules_engine.py` | SQLite rules matching |
| `mapper.py` | Semantic → Gmail labels |
| `prompts/classifier_prompt.txt` | LLM #1 prompt (editable!) |
| `prompts/verifier_prompt.txt` | LLM #2 prompt (editable!) |

### Extension (extension/)

| File | Purpose |
|------|---------|
| `background.js` | Service worker (main) |
| `content.js` | Gmail DOM monitoring |
| `modules/gmail.js` | Gmail API ops |
| `modules/classifier.js` | API client |
| `modules/verifier.js` | Verifier client |
| `modules/mapper.js` | Label mapping |
| `modules/cache.js` | Caching (24hr expiry) |

## Commands

```bash
# Backend
uvicorn shopq.api:app --reload         # Dev server
pytest -v                               # Run tests

# Extension
# Load unpacked from extension/ in chrome://extensions

# Deployment
./deploy.sh                             # Deploy to Cloud Run

# Edit prompts (no code changes!)
nano shopq/prompts/classifier_prompt.txt
nano shopq/prompts/verifier_prompt.txt

# Quality Monitoring (NEW!)
./scripts/start-quality-system.sh      # Start automated monitoring
./scripts/quality-system-status.sh     # Check status
./scripts/stop-quality-system.sh       # Stop monitoring
```

## Environment

**All configuration is in `.env` file** - no need to manually export!

```bash
# Required
GOOGLE_API_KEY=AIzaSy...
GOOGLE_CLOUD_PROJECT=mailq-467118
GEMINI_MODEL=gemini-2.0-flash

# Quality Monitoring (NEW!)
ANTHROPIC_API_KEY=sk-ant-...           # For Claude analysis
GITHUB_TOKEN=ghp_...                   # For creating issues
MIN_EMAILS_FOR_ANALYSIS=25             # Triggers analysis

# Optional
API_PORT=8000
USE_RULES_ENGINE=true
USE_AI_CLASSIFIER=true
```

## Classification Flow

### 1. Rules Engine (T0 - Free)
- Check SQLite for exact sender match
- If found → Return cached classification
- If not found → Continue to LLM

### 2. Gemini Classifier (T3 - ~$0.0001)
- Load prompts from `shopq/prompts/classifier_prompt.txt`
- Include 12 static + 5 learned few-shot examples
- Temperature: 0.2 (consistent)
- Returns multi-dimensional classification

### 3. Confidence Filter (Very Conservative)
```python
MIN_TYPE_CONF = 0.92    # Type must be 92%+ confident (increased from 0.85)
MIN_LABEL_CONF = 0.85   # Labels must be 85%+ confident (increased from 0.75)
```
- Below threshold → "Uncategorized"
- Above threshold → Continue

### 4. Verifier (Selective, ~10-20% of emails)

**Triggers** (widened range for more conservative approach):
- Low/medium confidence (0.50-0.90) - wider than before (was 0.45-0.75)
- Multi-purpose senders (Amazon, Google, banks)
- Contradictions detected (e.g., promotion with order #)
- Weak reasoning ("probably", "might be")

**Verifier Prompt**: `shopq/prompts/verifier_prompt.txt`
- Challenges first classification
- Applies strict rubrics
- Temperature: 0.1 (conservative)
- Returns: `verdict: "confirm"` or `"reject"` with correction

### 5. Gmail Label Application
- Map dimensions to ShopQ-* labels
- Apply via Gmail API
- Cache label IDs (in-memory)
- Archive from inbox

## Learning & Feedback

### User Corrections (Label Learning - ACTIVE)
```
User removes/adds label → content.js detects → /api/feedback
→ Creates rule (confidence=0.95) → Future emails auto-classified
```

### Pending Rules
- LLM suggests high-confidence patterns
- Requires 2 consistent classifications
- Promoted to confirmed rules

### Digest Learning (DISABLED - Future Feature)
**Status:** Code written but commented out as of 2025-11-01
**Reason:** Need to perfect core importance scoring first
**Location:**
- Extension: `modules/digest-feedback.js` (not loaded)
- Backend: `/api/feedback/digest` (commented out)
- Docs: `docs/IMPORTANCE_LEARNING.md`

When ready to re-enable, this will track user interactions with digest emails (opens, stars, archives) to learn importance patterns.

## Debugging

### Check Classification
```bash
# Backend logs
tail -f /tmp/shopq.log

# Extension console (F12 in Gmail)
# Look for: 🔍 🏷️ ✅ ❌ 💾 emojis
```

### Low Confidence?
1. Edit `shopq/prompts/classifier_prompt.txt`
2. Add clearer rules or examples
3. Test: curl -X POST localhost:8000/api/organize -d @test.json

### Verifier Rejecting Too Much?
1. Edit `shopq/prompts/verifier_prompt.txt`
2. Adjust rubric strictness
3. Check confidence_delta threshold (currently 0.15)

## Data Flow

```
Gmail Inbox
  ↓ (Gmail API)
Extension: Fetch unlabeled emails (query: -label:ShopQ-*)
  ↓
Extension: Check cache → Deduplicate by sender
  ↓ (HTTP POST)
Backend: /api/organize
  ↓
Rules Engine → [Match?] → Return result
  ↓ No match
Gemini Classifier → Classification
  ↓
Confidence Filter → [High?] → Continue
  ↓ Suspicious
Verifier LLM → Verify/Correct
  ↓
Mapper: Semantic → Gmail labels
  ↓ (Response)
Extension: Apply labels + Archive
  ↓
Content Script: Monitor corrections → /api/feedback
```

## Costs

| Operation | Cost | When |
|-----------|------|------|
| Rules match | $0 | 50-70% of emails (T0) |
| Gemini 2.0 Flash classification | ~$0.0001 | 30-50% of emails (T3) |
| Gemini 2.0 Flash verifier | ~$0.0001 | 5-10% of suspicious emails (T3) |

**Pricing details** (Vertex AI, as of 2025):
- Input: $0.15 per 1M tokens
- Output: $0.60 per 1M tokens
- Typical email: ~250 input + 125 output tokens = $0.000113 per email

**Daily cap**: $0.50 (enforced by extension/modules/budget.js)

## Common Patterns

### Add a New Domain
1. Update schema: `extension/Schema.json`
2. Add to mapper: `shopq/mapper.py` + `extension/modules/mapper.js`
3. Update prompts: `shopq/prompts/classifier_prompt.txt`
4. Update verifier: `shopq/prompts/verifier_prompt.txt`

### Improve Classification
1. Edit prompts in `shopq/prompts/*.txt` (no code changes!)
2. Test classification
3. Check confidence scores
4. Iterate

### Add a Detector Pattern
1. Edit `extension/modules/detectors.js`
2. Add pattern (regex, keywords, etc.)
3. Test with sample emails
4. Monitor precision

## Documentation

### Core System
- **[INDEX.md](INDEX.md)** - Master navigation
- **[QUICKSTART.md](QUICKSTART.md)** - Setup & common tasks
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Detailed system design
- **[docs/TESTING.md](docs/TESTING.md)** - Test procedures
- **[docs/PROMPT_IMPROVEMENTS.md](docs/PROMPT_IMPROVEMENTS.md)** - Prompt optimization history
- **[shopq/prompts/README.md](shopq/prompts/README.md)** - Prompt management guide

### Quality Monitoring (NEW!)
- **[SETUP_COMPLETE.md](SETUP_COMPLETE.md)** - Environment setup & current status
- **[QUICKSTART_QUALITY.md](QUICKSTART_QUALITY.md)** - 30-second quality monitoring setup
- **[QUALITY_SYSTEM_SUMMARY.md](QUALITY_SYSTEM_SUMMARY.md)** - What was built and why
- **[docs/QUALITY_CONTROL_PIPELINE.md](docs/QUALITY_CONTROL_PIPELINE.md)** - Complete technical documentation
- **[docs/BACKEND_WEBHOOK_INTEGRATION.md](docs/BACKEND_WEBHOOK_INTEGRATION.md)** - Optional webhook integration

## Important Notes

- **Prompts are external**: Edit `shopq/prompts/*.txt`, changes load automatically
- **No "travel" domain**: Removed, use shopping for Uber/Lyft
- **Label cache**: In-memory, prevents 409 errors
- **Confidence thresholds**: Adjust in `shopq/api_organize.py`
- **Verifier is selective**: Only runs on ~5-10% of emails

---

**For detailed architecture**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
**For quick tasks**: See [QUICKSTART.md](QUICKSTART.md)
**For prompt editing**: See [shopq/prompts/README.md](shopq/prompts/README.md)
