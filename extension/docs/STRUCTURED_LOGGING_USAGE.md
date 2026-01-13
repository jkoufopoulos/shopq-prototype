# Structured Logging Usage in Extension

The structured logger is now imported in `background.js` and available globally.

## Quick Start

```javascript
// Create logger (in any module after importScripts)
const s_logger = new StructuredLogger();

// Log events
s_logger.logEvent(EventType.EXT_BATCH_START, null, {
  batch_size: 10,
  checkpoint: 'new'
});

s_logger.extLabelApplyError('18c2a4f8d', 'QuotaExceeded');
s_logger.extMismatch('18c2a4f8d', ['IMPORTANT'], ['CATEGORY_UPDATES']);
s_logger.extBatchDone(10, 0, 0); // processed, skipped, failed
```

## Integration Points

### 1. auto-organize.js - Batch Processing

**Add at start of `organizeInboxSilently()`:**
```javascript
async function organizeInboxSilently() {
  const sessionId = new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 15);
  const s_logger = new StructuredLogger(sessionId);

  const checkpoint = await loadCheckpoint();

  // LOG: Batch start
  s_logger.logEvent(EventType.EXT_BATCH_START, null, {
    batch_size: BATCH_SIZE,
    checkpoint: checkpoint ? 'resume' : 'new',
  });
```

**Add in batch loop (after applyLabels):**
```javascript
// After: const labelResults = await applyLabels(freshToken, emailsWithLabels, true);
if (!labelResults.success || labelResults.success === 0) {
  s_logger.extLabelApplyError(batch[0]?.id, labelResults.error || 'unknown');
  throw new Error('Label application failed');
}

// Check for mismatches
for (let j = 0; j < batch.length; j++) {
  const classified = emailsWithLabels[j].labels || [];
  const applied = labelResults.details?.[j]?.labels || [];

  if (JSON.stringify(classified.sort()) !== JSON.stringify(applied.sort())) {
    s_logger.extMismatch(batch[j].id, classified, applied);
  }
}
```

**Add at end of function:**
```javascript
// Before return
s_logger.extBatchDone(processed, emailsToProcess.length - processed, 0);

return {
  success: true,
  processedCount: totalProcessed + processed,
  remainingCount: remaining.length,
  classifications: allClassifications
};
```

### 2. Checkpoint Operations

Already integrated in checkpoint functions:

```javascript
async function saveCheckpoint(checkpoint) {
  // ... existing code ...
  if (typeof StructuredLogger !== 'undefined') {
    const s_logger = new StructuredLogger();
    s_logger.checkpointSave(checkpoint.totalProcessed, checkpoint.retryCount || 0);
  }
}
```

### 3. Heartbeat Handler

```javascript
async function handleHeartbeat() {
  const s_logger = new StructuredLogger();

  const checkpoint = await chrome.storage.local.get('auto_organize_checkpoint');

  if (checkpoint.auto_organize_checkpoint) {
    const minutesSince = (Date.now() - checkpoint.auto_organize_checkpoint.timestamp) / (1000 * 60);

    if (minutesSince > 5 && minutesSince < 120) {
      s_logger.heartbeatResumeDetected(minutesSince);
      await organizeInboxSilently();
    }
  }
}
```

## Output Examples

```json
{"ts":"2025-11-11T23:45:12.123Z","level":"INFO","session":"20251111234512","event":"ext_batch_start","batch_size":10,"checkpoint":"new"}
{"ts":"2025-11-11T23:45:12.234Z","level":"ERROR","session":"20251111234512","event":"ext_label_apply_error","email":"18c2a4f8d","error":"QuotaExceeded"}
{"ts":"2025-11-11T23:45:12.345Z","level":"WARN","session":"20251111234512","event":"ext_mismatch","email":"18c2a4f8d","classified":"IMPORTANT","applied":"CATEGORY_UPDATES"}
{"ts":"2025-11-11T23:45:12.456Z","level":"INFO","session":"20251111234512","event":"ext_batch_done","processed":10,"skipped":0,"failed":0}
```

## Testing

1. Open Chrome DevTools → Extensions → MailQ → Inspect
2. Trigger organization (icon click or auto-organize)
3. Check console for JSON logs
4. Copy logs and paste into Claude Code for debugging

## Benefits

- **One-line JSON**: Easy to grep/filter
- **Session correlation**: All events in same run have same session ID
- **Email correlation**: Track individual email through pipeline
- **Privacy-safe**: Email IDs hashed to 12 chars, subjects redacted
- **Rate-limited**: Won't flood console (10% sampling for INFO)
