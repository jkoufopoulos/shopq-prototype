# Structured Logging Retrofit Guide

**Status**: 3/7 Complete (✅ Logging kit + LLM classifier done)

This guide shows exact patch locations for retrofitting structured logging at the 4 remaining critical handoff points.

---

## ✅ COMPLETED

### 1. Python Logging Kit (`shopq/structured_logging.py`)
- ✅ Created with EventType enum, sampling, rate limiting, privacy redaction
- ✅ ~100 event target with 10% INFO sampling, 100% ERROR sampling

### 2. JavaScript Logging Utility (`extension/modules/structured-logger.js`)
- ✅ Mirrors Python kit with same EventType enum
- ✅ Per-event rate limiting, one-line JSON output

### 3. LLM Classification (`shopq/vertex_gemini_classifier.py`)
- ✅ Added structured logging for: `LLM_CALL_OK`, `LLM_CALL_ERROR`, `LLM_FALLBACK_INVOKED`
- ✅ Logs email_id, error type, attempt count, subject (redacted)
- ✅ Tracks circuit breaker trips, JSON errors, schema validation errors

---

## 🚧 REMAINING RETROFITS (Copy-Paste Ready)

### 4. Bridge Mapper (`shopq/bridge/mapper.py`)

**Location**: Find `class BridgeMapper` or `def map_email`

**Add import at top**:
```python
from shopq.structured_logging import EventType, get_logger as get_structured_logger

s_logger = get_structured_logger()
```

**Patch 1: Missing LLM record** (find `if not self._has_llm_record`):
```python
def map_email(self, email: dict) -> BridgeDecision:
    email_id = email.get("id", "unknown")

    if not self._has_llm_record(email):
        # STRUCTURED LOG: Missing field
        s_logger.log_event(
            EventType.MAP_MISSING_FIELD,
            email_id=email_id,
            field="llm_classification",
            decider=email.get("decider", "none"),
        )
        return BridgeDecision(
            importance=None,
            reason="missing_llm_record",
            source="missing",
            missing_llm=True,
        )
```

**Patch 2: Guardrail applied** (find `guardrail = self.guardrails.evaluate`):
```python
guardrail = self.guardrails.evaluate(email)
if guardrail:
    # STRUCTURED LOG: Guardrail override
    s_logger.map_guardrail_applied(
        email_id=email_id,
        rule_name=guardrail.rule_name,
        importance=guardrail.importance,
    )
    return self._decision_from_guardrail(guardrail)
```

**Patch 3: Final decision** (find `return BridgeDecision` or end of function):
```python
# After computing final decision
decision = BridgeDecision(
    importance=mapped_importance,
    reason=reason,
    source=source,  # "guardrail" | "mapper" | "default"
    rule_name=rule_name,
)

# STRUCTURED LOG: Mapping decision
s_logger.map_decision(
    email_id=email_id,
    importance=decision.importance,
    source=decision.source,
    rule_name=decision.rule_name,
)

return decision
```

---

### 5. Temporal Enrichment (`shopq/temporal_enrichment.py` or `shopq/context_digest.py`)

**Location**: Find `class TemporalEnricher` or `def enrich_temporal`

**Add import**:
```python
from shopq.structured_logging import EventType, get_logger as get_structured_logger

s_logger = get_structured_logger()
```

**Patch 1: Temporal parse errors** (find `try: parse_datetime` or similar):
```python
try:
    entity_time = parse_entity_timestamp(entity)
except (ValueError, TypeError) as e:
    # STRUCTURED LOG: Parse error
    s_logger.log_event(
        EventType.TEMPORAL_PARSE_ERROR,
        email_id=entity.source_email_id,
        timestamp=str(entity.timestamp),
        error=type(e).__name__,
    )
    continue
```

**Patch 2: Escalation/downgrade decisions** (find where importance changes):
```python
if hours_until_event < 1:
    # Escalate to urgent
    original_importance = entity.importance
    entity.importance = "urgent"

    # STRUCTURED LOG: Temporal decision
    s_logger.temporal_resolve(
        email_id=entity.source_email_id,
        decision="escalated",
        reason=f"event_in_{hours_until_event:.1f}h",
        hours_until=hours_until_event,
    )
elif hours_until_event > 168:  # 7 days
    # Downgrade or filter
    s_logger.temporal_resolve(
        email_id=entity.source_email_id,
        decision="downgraded",
        reason=f"event_in_{hours_until_event/24:.1f}d",
        hours_until=hours_until_event,
    )
```

**Patch 3: Summary stats** (find end of enrichment loop):
```python
# After enriching all entities
logger.info(
    "Temporal enrichment | processed=%d | escalated=%d | downgraded=%d | filtered=%d",
    stats['total_processed'],
    stats['escalated'],
    stats['downgraded'],
    stats['filtered'],
)
```

---

### 6. Entity Extraction (`shopq/entity_extractor.py`)

**Add import**:
```python
from shopq.structured_logging import EventType, get_logger as get_structured_logger

s_logger = get_structured_logger()
```

**Patch 1: Extraction success** (find end of extraction loop):
```python
# After extracting entities from all emails
count_by_type = {}
confidences = []

for entity in entities:
    entity_type = entity.type if hasattr(entity, 'type') else 'unknown'
    count_by_type[entity_type] = count_by_type.get(entity_type, 0) + 1

    if hasattr(entity, 'confidence'):
        confidences.append(entity.confidence)

avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

# STRUCTURED LOG: Extraction stats
s_logger.extract_entities_ok(
    count_by_type=count_by_type,
    avg_conf=avg_conf,
)
```

**Patch 2: Metadata inconsistency** (find thread_id recovery logic):
```python
if not entity.source_thread_id:
    s_logger.log_event(
        EventType.EXTRACT_INCONSISTENT,
        email_id=entity.source_email_id,
        issue="missing_thread_id",
        recovery="subject_search" if recovered else "failed",
    )
```

---

### 7. Extension Label Application (`extension/modules/auto-organize.js`)

**Add import at top**:
```javascript
// Import structured logger
importScripts('modules/structured-logger.js');

// Create session logger (in background.js or at start of organize)
const s_logger = new StructuredLogger();
```

**Patch 1: Batch start** (find start of `organizeInboxSilently`):
```javascript
async function organizeInboxSilently() {
  // STRUCTURED LOG: Batch start
  const sessionId = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
  const s_logger = new StructuredLogger(sessionId);

  s_logger.logEvent(EventType.EXT_BATCH_START, null, {
    batch_size: BATCH_SIZE,
    checkpoint: checkpoint ? 'resume' : 'new',
  });
```

**Patch 2: Label application errors** (find `applyLabels` result handling):
```javascript
const labelResults = await applyLabels(freshToken, emailsWithLabels, true);

if (!labelResults.success || labelResults.success === 0) {
  // STRUCTURED LOG: Label error
  s_logger.logEvent(EventType.EXT_LABEL_APPLY_ERROR, batch[0]?.id, {
    error: labelResults.error || 'unknown',
    batch_size: batch.length,
  });
  throw new Error('Label application failed for entire batch');
}
```

**Patch 3: Label mismatch detection** (add after label application):
```javascript
// Check for mismatch between classified and applied labels
for (let j = 0; j < batch.length; j++) {
  const classified = emailsWithLabels[j].labels || [];
  const applied = labelResults.details?.[j]?.labels || [];

  if (JSON.stringify(classified.sort()) !== JSON.stringify(applied.sort())) {
    // STRUCTURED LOG: Mismatch
    s_logger.extMismatch(batch[j].id, classified, applied);
  }
}
```

**Patch 4: Batch complete** (find end of `organizeInboxSilently`):
```javascript
// STRUCTURED LOG: Batch done
s_logger.extBatchDone(
  processed,           // successfully processed
  emailsToProcess.length - processed,  // skipped
  0                    // failed (or track separately)
);

return {
  success: true,
  processedCount: totalProcessed + processed,
  remainingCount: remaining.length,
  classifications: allClassifications
};
```

---

## Testing the Retrofit

### Example Output (After All Retrofits)

```json
{"ts":"2025-11-11T23:45:12.123Z","level":"INFO","session":"20251111_234512","event":"llm_call_ok","email":"18c2a4f8d","type":"receipt","type_conf":0.95,"domains":["finance"],"attention":"none"}
{"ts":"2025-11-11T23:45:12.234Z","level":"INFO","session":"20251111_234512","event":"map_decision","email":"18c2a4f8d","importance":"routine","source":"mapper","rule":"finance_routine"}
{"ts":"2025-11-11T23:45:12.345Z","level":"ERROR","session":"20251111_234512","event":"temporal_parse_error","email":"18c2a4f8d","timestamp":"invalid","error":"ValueError"}
{"ts":"2025-11-11T23:45:12.456Z","level":"INFO","session":"20251111_234512","event":"extract_entities_ok","counts":{"event":5,"deadline":3,"notification":12},"avg_conf":0.87}
{"ts":"2025-11-11T23:45:12.567Z","level":"INFO","session":"20251111_234512","event":"ext_batch_done","processed":10,"skipped":0,"failed":0}
```

### Grep-ability

```bash
# Find all LLM errors
grep '"event":"llm_call_error"' logs.json

# Find all guardrail applications
grep '"event":"map_guardrail_applied"' logs.json | jq .

# Count temporal escalations
grep '"decision":"escalated"' logs.json | wc -l

# Find label mismatches
grep '"event":"ext_mismatch"' logs.json | jq -r '.email'
```

---

## Estimated Impact

### Before Retrofit (Current State)
- ~392 log calls total
- ~50 errors (13% of logging)
- No correlation IDs
- No structured format
- Debug logs only in verbose mode

### After Retrofit (Target State)
- ~100 high-signal events per session
- All errors logged (100% sampling)
- Session + email correlation IDs
- One-line JSON (grep/jq ready)
- Privacy-safe (subjects redacted)

---

## Priority Order

1. ✅ **LLM Classifier** (DONE) - Catches most expensive failures
2. **Bridge Mapper** (NEXT) - Critical for understanding label decisions
3. **Extension Labeler** (NEXT) - User-facing failures
4. **Temporal Enrichment** - Time-sensitive bugs are hard to debug
5. **Entity Extraction** - Lower priority (metadata issues less common)

---

## Rollout Strategy

1. **Week 1**: LLM + Bridge Mapper (catch classification pipeline issues)
2. **Week 2**: Extension Labeler (catch user-facing issues)
3. **Week 3**: Temporal + Entity (polish edge cases)
4. **Week 4**: Tune sampling rates based on log volume

Target: ~100 logs/session without flooding Chrome console.
