# Digest Pipeline Architecture

> Last Updated: November 2025 (Phase 0.5)

## Overview

The ShopQ digest pipeline transforms classified emails into a prioritized HTML summary. The V2 pipeline uses a 7-stage architecture that assigns sections BEFORE entity extraction, solving the problem where only 4.3% of emails were featured in the previous approach.

## Pipeline Flow

```
Emails → TemporalExtraction → T0SectionAssignment → T1TemporalDecay
       → EntityStage → EnrichmentStage → SynthesisAndRendering → Validation
```

## 7 Pipeline Stages

### 1. TemporalExtractionStage

**Purpose**: Extract temporal context and filter expired emails.

**Input**: Raw classified emails with `type`, `importance`, `subject`, `snippet`
**Output**: Emails with temporal context, expired emails filtered

**Key Logic**:
- Extract event times, delivery dates, purchase dates from subject/snippet
- Filter emails more than 48 hours past their temporal deadline
- Add temporal context dict to each email

**File**: `shopq/digest/digest_stages_v2.py:TemporalExtractionStage`

### 2. T0SectionAssignmentStage

**Purpose**: Assign intrinsic section based on "What IS this email?"

**Input**: Emails with temporal context
**Output**: Section assignments (critical, today, coming_up, everything_else, skip)

**Key Logic**:
- Uses Gemini's `type` and `importance` classification
- critical → "critical" section
- time_sensitive → "today" section
- routine → "everything_else" section

**File**: `shopq/digest/section_assignment_t0.py`

### 3. T1TemporalDecayStage

**Purpose**: Apply time-based decay to T0 sections.

**Input**: T0 section assignments + temporal contexts
**Output**: T1 section assignments (may differ from T0)

**Key Logic**:
- Events past their time → skip
- Deliveries > 24h ago → noise
- Purchases in past → routine
- Future events within 24h → today

**File**: `shopq/digest/temporal.py:apply_temporal_decay`

### 4. EntityStage

**Purpose**: Extract structured entities and build featured items.

**Input**: Emails with T1 sections
**Output**: Featured items for digest

**Key Logic**:
- Extract flights, events, deadlines from email content
- Link entities to emails via message_id
- Build featured_items list for rendering

**File**: `shopq/digest/digest_stages_v2.py:EntityStage`

### 5. EnrichmentStage

**Purpose**: Add temporal enrichment, weather, and greeting.

**Input**: Featured items + context
**Output**: Enriched digest context

**Key Logic**:
- Add relative time labels ("in 2 hours", "tomorrow")
- Fetch weather for user's location
- Generate personalized greeting

**File**: `shopq/digest/digest_stages_v2.py:EnrichmentStage`

### 6. SynthesisAndRenderingStage

**Purpose**: Build timeline and render HTML.

**Input**: Enriched context
**Output**: HTML digest string

**Key Logic**:
- Build chronological timeline from featured items
- Generate Gmail thread links
- Render responsive HTML template

**File**: `shopq/digest/digest_stages_v2.py:SynthesisAndRenderingStage`

### 7. ValidationStage

**Purpose**: Fact verification and schema validation.

**Input**: Rendered digest
**Output**: Validated digest with error list

**Key Logic**:
- Verify all links are valid
- Check section counts match expectations
- Validate HTML structure

**File**: `shopq/digest/digest_stages_v2.py:ValidationStage`

## Key Data Structures

### DigestContext

Central state object passed through all stages:

```python
@dataclass
class DigestContext:
    emails: list[dict]              # Input emails
    current_time: datetime          # Evaluation timestamp
    user_timezone: str              # User's timezone
    temporal_contexts: dict         # email_id → temporal info
    section_assignments: dict       # email_id → section
    featured_items: list            # Items for digest
    html: str                       # Final rendered HTML
    errors: list                    # Validation errors
```

### Section Types

The digest uses these section buckets:

| Section | Description | UI Label |
|---------|-------------|----------|
| critical | Must act immediately | 🚨 CRITICAL |
| today | Happening today | 📅 TODAY |
| coming_up | Next 24-72 hours | 🔜 COMING UP |
| everything_else | Routine/informational | Everything else |
| skip | Filter from digest | (hidden) |

## Entry Points

### ContextDigest.generate_v2()

Main entry point for V2 pipeline:

```python
digest = ContextDigest()
result = digest.generate_v2(
    emails=classified_emails,
    timezone="America/New_York",
    city_hint="New York"
)
# Returns: {"html": "...", "featured_count": 5, ...}
```

### Fallback Behavior

If V2 pipeline fails, falls back to simple email-based summary:

```python
# Fallback produces deterministic HTML from importance buckets
result = digest._generate_fallback(
    emails=emails,
    timezone=timezone
)
```

## Configuration

### Feature Flags

```python
# shopq/runtime/flags.py
ENABLE_V2_PIPELINE = True  # Use 7-stage pipeline
ENABLE_TEMPORAL_DECAY = True  # Apply T1 time-based decay
ENABLE_WEATHER_ENRICHMENT = True  # Fetch weather data
```

### Temporal Thresholds

```python
# shopq/digest/temporal.py
EVENT_GRACE_PERIOD = timedelta(hours=1)  # Events visible 1h after
DELIVERY_DECAY_HOURS = 24  # Deliveries decay after 24h
COMING_UP_WINDOW = timedelta(hours=72)  # "Coming up" = next 72h
```

## Testing

### Unit Tests

```bash
pytest tests/unit/test_temporal_extraction.py -v
pytest tests/unit/test_section_assignment.py -v
```

### Integration Tests

```bash
pytest tests/integration/test_digest_generation_gds.py -v
pytest tests/integration/test_phase1_integration.py -v
```

### End-to-End

```bash
# Generate digest from GDS sample
python scripts/evals/classification_accuracy.py --generate-digest
```

## Architecture Decisions

### Why Section-First?

Previous approach: Entity extraction first, then section assignment.
Problem: Only 4.3% of emails got entities, leaving 95.7% unsectioned.

V2 approach: Section assignment first based on type/importance.
Result: 100% of emails get a section, entities enhance but don't gate.

### Why T0/T1 Split?

T0 (intrinsic): "What IS this email?" - Based on type and importance.
T1 (temporal): "When should we show it?" - Based on current time.

This allows consistent classification with dynamic presentation.

### Why 7 Stages?

Consolidated from original 9 stages for clarity:
- Merged filter + extraction into TemporalExtractionStage
- Kept T0/T1 separation for debugging
- Merged synthesis + rendering (always done together)

## File Reference

| File | Purpose |
|------|---------|
| `shopq/digest/context_digest.py` | Main ContextDigest class |
| `shopq/digest/digest_pipeline.py` | Pipeline orchestration |
| `shopq/digest/digest_stages_v2.py` | 7 pipeline stage implementations |
| `shopq/digest/section_assignment_t0.py` | T0 intrinsic section logic |
| `shopq/digest/temporal.py` | T1 temporal decay logic |
| `shopq/digest/templates/` | Jinja2 HTML templates |

## See Also

- [T0_T1_TEMPORAL_ARCHITECTURE.md](T0_T1_TEMPORAL_ARCHITECTURE.md) - T0/T1 design
- [T0_T1_IMPORTANCE_CLASSIFICATION.md](../features/T0_T1_IMPORTANCE_CLASSIFICATION.md) - Importance classification
- [TAXONOMY.md](../TAXONOMY.md) - Email type and importance taxonomy
