# MailQ Architecture

Detailed system design and implementation guide.

> **📁 Repository Structure Update (Nov 2025)**: The `mailq/` backend has been restructured from 15 directories to 7 for clarity:
> `api/`, `classification/`, `digest/`, `gmail/`, `llm/`, `storage/`, `shared/`. See [mailq/README.md](../../mailq/README.md) and [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for details.

## System Overview

MailQ is a hybrid email classification system with four tiers:

1. **T0 (Free)**: Type Mapper - Global deterministic type rules (NEW - 2025-11-10)
2. **T0 (Free)**: Rules Engine - User-specific pattern matching
3. **T3 (~$0.0001)**: LLM Classifier - Gemini 2.0 Flash
4. **T3 (~$0.0001)**: Verifier - Selective second-pass LLM

**Goal**: Maximize precision, minimize cost through deterministic rules.

## Architecture Diagram

> 📊 **Visual Diagrams**: See auto-generated interactive Mermaid diagrams:
> - **[Interactive HTML Viewer](../code-graph/visuals/html/index.html)** - Beautiful, zoomable, exportable diagrams 🎨
> - [System Architecture](../code-graph/visuals/SYSTEM_DIAGRAM.md) - High-level component overview
> - [Classification Flow](../code-graph/visuals/CLASSIFICATION_FLOW.md) - Email → label processing
> - [Learning Loop](../code-graph/visuals/LEARNING_LOOP.md) - How system learns from user corrections
> - [Cost & Performance](../code-graph/visuals/COST_PERFORMANCE.md) - Cost breakdown & optimization opportunities
>
> These diagrams auto-update when code changes. Run `./code-graph/scripts/quick_regen.sh` to regenerate.

**Text-based overview**:

```
┌─────────────────────────────────────────────────────────────────┐
│                         Chrome Extension                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  background.js (Service Worker)                                  │
│      ↓                                                           │
│  modules/gmail.js → Fetch unlabeled emails                      │
│      ↓                                                           │
│  modules/cache.js → Check 24hr cache                            │
│      ↓                                                           │
│  modules/classifier.js → POST /api/organize                     │
│      ↓                                                           │
│  ┌────────────── Python Backend ───────────────┐               │
│  │                                               │               │
│  │  type_mapper.py → Global type rules (NEW)   │               │
│  │      ↓ (calendar → event, etc.)              │               │
│  │  rules_engine.py → User rules (SQLite)       │               │
│  │      ↓ (no match)                            │               │
│  │  vertex_gemini_classifier.py                 │               │
│  │      ↓ (classification)                      │               │
│  │  api_organize.py → Confidence filter         │               │
│  │      ↓ (suspicious?)                         │               │
│  │  api_verify.py → Verifier LLM                │               │
│  │      ↓ (final result)                        │               │
│  │  mapper.py → Convert to Gmail labels         │               │
│  │                                               │               │
│  └───────────────────────────────────────────────┘               │
│      ↓                                                           │
│  modules/mapper.js → Map API response                           │
│      ↓                                                           │
│  modules/gmail.js → Apply labels + Archive                      │
│      ↓                                                           │
│  content.js → Monitor user corrections → /api/feedback          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### Chrome Extension

#### background.js (Service Worker)
- **Purpose**: Main orchestrator
- **Responsibilities**:
  - Listen for extension icon clicks
  - Coordinate email fetching, classification, labeling
  - Handle errors and user notifications
- **Key Functions**:
  - `organizeEmails()` - Main entry point
  - Error handling with user-friendly messages

#### modules/gmail.js
- **Purpose**: Gmail API operations
- **Key Functions**:
  - `getUnlabeledEmails()` - Fetch emails without MailQ-* labels
  - `getOrCreateLabel()` - Create/find labels with caching
  - `applyLabels()` - Apply labels and archive emails
- **Label Cache**: In-memory Map to prevent 409 errors

#### modules/classifier.js
- **Purpose**: API client for classification
- **Key Functions**:
  - `classifyEmails()` - POST to /api/organize
  - Deduplication by sender domain (reduces API calls)
  - Caching integration

#### modules/verifier.js
- **Purpose**: Verifier client
- **Key Functions**:
  - `shouldVerify()` - Determine if email needs verification
  - `callVerifier()` - POST to /api/verify
  - Trigger detection (confidence, contradictions, weak reasoning)

#### modules/cache.js
- **Purpose**: Local storage caching
- **Strategy**: Cache by sender (24hr expiry)
- **Max size**: 10,000 entries

#### content.js
- **Purpose**: Gmail DOM monitoring
- **Monitors**: Label additions/removals by user
- **Action**: Send corrections to /api/feedback

### Python Backend

#### api.py
- **Purpose**: FastAPI application
- **Endpoints**:
  - `POST /api/organize` - Batch email classification
  - `POST /api/feedback` - User corrections
  - `POST /api/verify` - Verifier endpoint
  - `GET /health` - Health check

#### memory_classifier.py
- **Purpose**: Classification orchestrator
- **Flow** (Updated 2025-11-10):
  1. Try type_mapper (global deterministic rules for calendar invites, etc.)
  2. If no match → Try rules_engine (user-specific learned patterns)
  3. If no match → vertex_gemini_classifier (LLM fallback)
  4. Map to Gmail labels
  5. Return result
- **Reference**: `docs/TYPE_MAPPER_IMPLEMENTATION_SUMMARY.md`

#### type_mapper.py (NEW - 2025-11-10)
- **Purpose**: Global deterministic type classification
- **Scope**: Calendar events (MVP), receipts/newsletters (future)
- **Config**: `config/type_mapper_rules.yaml` (version 1.0)
- **Matching**:
  - Sender domains (e.g., `calendar-notification@google.com`)
  - Subject patterns (e.g., `Notification: X @ Wed`)
  - Body phrases (e.g., "Join with Google Meet")
  - ICS attachments
- **Performance**: <1ms per email (in-memory pattern matching)
- **Precision**: ≥98% confidence threshold
- **Benefits**:
  - Works day 1 for all users (not user-specific)
  - Ensures calendar invites → `type=event` (not notification)
  - Complements rules_engine (global vs user-specific)

#### vertex_gemini_classifier.py
- **Purpose**: Gemini LLM integration
- **Model**: gemini-2.0-flash
- **Prompt Loading**: `mailq/prompts/classifier_prompt.txt`
- **Temperature**: 0.2 (consistent)
- **Few-shot Examples**: 12 static + 5 learned
- **Validation**: Ensures schema compliance

#### api_verify.py
- **Purpose**: Verifier logic
- **Prompt Loading**: `mailq/prompts/verifier_prompt.txt`
- **Temperature**: 0.1 (conservative)
- **Strategy**: Challenge first classification with strict rubrics
- **Returns**: `verdict: "confirm"` or `"reject"` with correction

#### rules_engine.py
- **Purpose**: SQLite pattern matching
- **Database**: `mailq/data/mailq.db` (rules table)
- **Tables**:
  - `rules` - Confirmed patterns
  - `pending_rules` - Awaiting promotion (2+ consistent matches)
- **Matching**: Exact sender or wildcard (*@domain.com)

#### mapper.py
- **Purpose**: Semantic → Gmail label mapping
- **Confidence Gates** (from `mailq/config/confidence.py`):
  - Type: 0.92 (TYPE_GATE)
  - Domain: 0.75 (DOMAIN_GATE)
  - Attention: 0.85 (ATTENTION_GATE)
- **Fallback**: "MailQ-Uncategorized" if no labels qualify

#### feedback_manager.py
- **Purpose**: User correction storage
- **Database**: `mailq/data/mailq.db` (feedback tables)
- **Actions**:
  - Store corrections
  - Extract patterns for few-shot learning
  - Create rules from corrections (confidence=0.95)

## Classification Schema

### Type Dimension
```
newsletter    - Recurring content (blog, digest)
notification  - Status updates (shipped, statement ready, OTP)
receipt       - Transaction confirmations (order, payment)
event         - Calendar events, reservations
promotion     - Marketing, sales, offers
message       - Direct communication
uncategorized - Low confidence or unknown
```

### Domain Dimension
```
finance       - Banks, credit cards, investments, bills
shopping      - E-commerce, food delivery, ride shares
professional  - Work, recruiting, career development
personal      - Social, entertainment, hobbies
```

### Attention Dimension
```
action_required - OTP codes, security alerts, time-critical (<24h)
none            - DEFAULT (newsletters, receipts, reviews)
```

### Relationship Dimension
```
from_contact  - Known sender (in contacts)
from_unknown  - Unknown sender
```

## Confidence System

> ✨ **NEW**: All confidence thresholds are now centralized in `mailq/config/confidence.py`
>
> See **[Confidence Flow Diagram](../code-graph/visuals/CONFIDENCE_FLOW.md)** for complete visualization of all gates and thresholds.

### Centralized Configuration

All thresholds are imported from `mailq/config/confidence.py`:

```python
# Classification Gates
TYPE_CONFIDENCE_MIN = 0.92      # Type must be 92%+ confident
LABEL_CONFIDENCE_MIN = 0.85     # Labels must be 85%+ confident

# Mapper Gates
TYPE_GATE = 0.92               # Matches TYPE_CONFIDENCE_MIN
DOMAIN_GATE = 0.75             # Domain labels (lower for multi-label)
ATTENTION_GATE = 0.85          # Action-required is important

# Learning Gate
LEARNING_MIN_CONFIDENCE = 0.85  # Only learn from high-confidence LLM

# LLM Internal
DOMAIN_MIN_THRESHOLD = 0.60    # Boost domains below this
DOMAIN_BOOST_VALUE = 0.70      # Boost weak domains to this value

# Verifier
VERIFIER_LOW_CONFIDENCE = 0.50   # Verifier trigger range: 50-90%
VERIFIER_HIGH_CONFIDENCE = 0.90
VERIFIER_CORRECTION_DELTA = 0.15 # Min delta to accept correction
```

### Usage in Code

**api_organize.py** (Gate 1 & 2):
```python
from mailq.config.confidence import TYPE_CONFIDENCE_MIN, LABEL_CONFIDENCE_MIN

if result['type_conf'] < TYPE_CONFIDENCE_MIN:  # Gate 1
    filtered_labels = ['Uncategorized']

filtered = [label for label in labels
           if conf >= LABEL_CONFIDENCE_MIN]  # Gate 2
```

**mapper.py** (Gate 3):
```python
from mailq.config.confidence import TYPE_GATE, DOMAIN_GATE, ATTENTION_GATE

# Apply gates when mapping to Gmail labels
```

**memory_classifier.py** (Gate 4):
```python
from mailq.config.confidence import LEARNING_MIN_CONFIDENCE

if type_conf >= LEARNING_MIN_CONFIDENCE:
    rules.learn_from_classification(...)  # Create pending rule
```

**vertex_gemini_classifier.py** (Gate 5):
```python
from mailq.config.confidence import DOMAIN_MIN_THRESHOLD, DOMAIN_BOOST_VALUE

# Boost weak domain confidences
```

### Confidence Logging

All classifications are logged to `confidence_logs` table via `ConfidenceLogger`:

```python
from mailq.confidence_logger import ConfidenceLogger

logger = ConfidenceLogger()
logger.log_classification(result, email_id, subject, filtered_labels)
```

**API Endpoints**:
- `GET /api/config/confidence` - Get all thresholds
- `GET /api/confidence/stats?days=7` - Aggregated statistics
- `GET /api/confidence/low?limit=100` - Low-confidence emails
- `GET /api/confidence/trend?days=30` - Trend over time

See `CONFIDENCE_MIGRATION.md` for complete migration details.

## Data Flow Examples

### Example 1: High-Confidence Email (Rules Match)

```
Email: "auto-confirm@amazon.com" / "Order Confirmation"
  ↓
rules_engine.py → Match found in rules.db
  ↓
Return: { type: "receipt", domains: ["shopping"], ... }
  ↓
Cost: $0 (T0)
```

### Example 2: New Email (LLM Classification)

```
Email: "noreply@newsite.com" / "Weekly Newsletter"
  ↓
rules_engine.py → No match
  ↓
vertex_gemini_classifier.py → Gemini 2.0 Flash
  ↓
Return: { type: "newsletter", type_conf: 0.92, ... }
  ↓
Confidence filter: 0.92 >= 0.85 → PASS
  ↓
mapper.py → ["MailQ-Newsletters"]
  ↓
Cost: ~$0.0001 (T3)
```

### Example 3: Suspicious Email (Verifier Triggered)

```
Email: "promo@amazon.com" / "Reserve your grocery slot!"
  ↓
vertex_gemini_classifier.py
  ↓
Return: { attention: "action_required", attention_conf: 0.55 }
  ↓
verifier.js → shouldVerify() = true (low confidence 0.55)
  ↓
api_verify.py → Verifier LLM
  ↓
Verifier: verdict: "reject", correction: { attention: "none" }
  ↓
Final: { attention: "none" }
  ↓
Cost: ~$0.0002 (T3 × 2)
```

## Caching Strategy

### Extension Cache
```javascript
// modules/cache.js
{
  key: "sender@domain.com",
  value: { type: "...", domains: [...], ... },
  expiry: Date.now() + 86400000  // 24 hours
}
```

### Label ID Cache
```javascript
// modules/gmail.js
const labelCache = new Map();  // labelName → labelId
// Prevents duplicate label creation (409 errors)
```

### Rules Cache
```python
# rules_engine.py
# SQLite provides implicit caching via indexes
```

## Cost Optimization

### Strategies
1. **Rules-first**: 50-70% of emails hit T0 (free)
2. **Deduplication**: Group emails by sender before API call
3. **Caching**: 24hr expiry prevents re-classification
4. **Selective Verifier**: Only 5-10% of emails need second pass
5. **Daily budget cap**: $0.50 enforced by extension

### Cost Breakdown
```
1000 emails/day:
- 700 emails → Rules match ($0)
- 270 emails → LLM classify ($0.027)
- 30 emails → Verifier ($0.003)
Total: ~$0.03/day
```

## Security & Privacy

### Authentication
- Gmail OAuth 2.0 (scopes: gmail.modify, gmail.labels)
- Vertex AI: Application Default Credentials

### Data Storage
- **Extension**: Local storage only (cache, settings)
- **Backend**: SQLite databases (rules, feedback, categories)
- **No PII**: Email content not stored, only sender/metadata

### API Keys
- Stored in `.env` (not committed)
- Google Cloud: IAM roles for production

### Additional Trust Practices (MVP → NEXT)

- **No send permission (MVP):** We do not request `gmail.send`, and we do not create drafts.
- **Optional writes:** `gmail.modify` is requested only if a user turns on Smart labels; otherwise we remain read-only.
- **Scoped storage:** Per-user isolation on every table; we store derived metadata (IDs, headers, entities), not bodies.
- **No destructive ops:** The Gmail client never calls `trash` or `delete`. Labeling is reversible.
- **Planned:** Enable encryption at rest in NEXT (keys managed via secrets manager).

## Error Handling

### Extension
```javascript
// background.js
try {
  await organizeEmails();
} catch (error) {
  if (error.message.includes('409')) {
    showError('Label conflict detected...');
  } else if (error.message.includes('401')) {
    showError('Authentication failed...');
  }
  // ... other error types
}
```

### Backend
```python
# api.py
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )
```

### Graceful Degradation
- LLM error → Fallback to "uncategorized"
- Verifier error → Keep first classification
- Cache miss → Fresh classification

## Performance

### Latency Targets
- Rules match: <10ms
- LLM classification: <500ms (p50)
- Verifier: <500ms (p50)
- Total (with verifier): <2s (p95)

### Throughput
- Backend: ~10 req/s (single instance)
- Extension: Batch size 20 emails
- Parallel processing: Deduplication reduces API calls

## Monitoring & Telemetry

### Extension (modules/telemetry.js)
```javascript
{
  classificationsCount: 150,
  cacheHits: 75,
  apiCalls: 75,
  totalCost: 0.0075,
  byDecider: { rule: 50, gemini: 70, verifier: 5 }
}
```

### Backend Logging
```python
# api_organize.py
print(f"✅ Classified: {total} emails in {elapsed_ms}ms")
print(f"🎯 High confidence: {high_confidence}")
print(f"⚠️  Low confidence: {low_confidence}")
```

## Future Enhancements

### Planned
- Persistent label cache (survive reloads)
- Active learning from corrections
- User-specific domain customization
- Rule auto-promotion with confidence decay

### Possible
- Multi-account support
- Scheduled classification (background)
- Advanced telemetry dashboard
- A/B testing framework for prompts

---

**See Also**:
- [MAILQ_REFERENCE.md](../MAILQ_REFERENCE.md) - Quick reference
- [QUICKSTART.md](../QUICKSTART.md) - Setup guide
- [TESTING.md](TESTING.md) - Test procedures

**Visual Diagrams**:
- [Interactive HTML Viewer](../code-graph/visuals/html/index.html) - All diagrams in one place
- [System Architecture](../code-graph/visuals/SYSTEM_DIAGRAM.md) - Component overview
- [Classification Flow](../code-graph/visuals/CLASSIFICATION_FLOW.md) - Email processing flow
- [Learning Loop](../code-graph/visuals/LEARNING_LOOP.md) - User feedback & learning
- [Cost & Performance](../code-graph/visuals/COST_PERFORMANCE.md) - Cost breakdown & optimization
