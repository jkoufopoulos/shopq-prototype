# Extension Checkpointing Pattern (Manifest V3)

**Status**: 📋 Planned (Implementation guide)
**Problem**: Service workers can be killed mid-operation, losing progress
**Solution**: Checkpoint pattern with resumable operations

## The Problem

Manifest V3 service workers are **event-driven and ephemeral**:
- Chrome kills them after 30 seconds of inactivity
- Can be killed mid-batch operation
- No persistent state (must use chrome.storage)

**Example failure scenario**:
```javascript
// ❌ BAD: Can be killed mid-loop
async function organizeInbox() {
  const emails = await fetchEmails();  // 100 emails

  for (const email of emails) {
    await classifyAndLabel(email);     // If killed at email 50, lose all progress
  }
}
```

## The Solution: Checkpoint Pattern

### Pattern 1: Batch with Checkpoints

```javascript
// ✅ GOOD: Checkpoint after each batch
async function organizeInbox() {
  const BATCH_SIZE = 10;

  // Load checkpoint
  const { lastProcessedId } = await chrome.storage.local.get('lastProcessedId');

  // Fetch emails after checkpoint
  const emails = await fetchEmails({ afterId: lastProcessedId });

  // Process in batches
  for (let i = 0; i < emails.length; i += BATCH_SIZE) {
    const batch = emails.slice(i, i + BATCH_SIZE);

    await processBatch(batch);

    // Save checkpoint
    const lastId = batch[batch.length - 1].id;
    await chrome.storage.local.set({ lastProcessedId: lastId });

    console.log(`✅ Checkpoint: Processed ${i + BATCH_SIZE}/${emails.length}`);
  }

  // Clear checkpoint when complete
  await chrome.storage.local.remove('lastProcessedId');
  console.log('✅ Inbox organization complete');
}
```

### Pattern 2: Resumable State Machine

```javascript
// ✅ GOOD: State machine with resume capability
const STATES = {
  IDLE: 'idle',
  FETCHING: 'fetching',
  CLASSIFYING: 'classifying',
  LABELING: 'labeling',
  COMPLETE: 'complete'
};

async function organizeInboxResumable() {
  // Load state
  const { state = STATES.IDLE, emails = [], currentIndex = 0 } =
    await chrome.storage.local.get(['state', 'emails', 'currentIndex']);

  console.log(`Resuming from state: ${state}, index: ${currentIndex}`);

  try {
    switch (state) {
      case STATES.IDLE:
      case STATES.FETCHING:
        await setState(STATES.FETCHING);
        const fetchedEmails = await fetchEmails();
        await chrome.storage.local.set({ emails: fetchedEmails });
        // Fall through to next state

      case STATES.CLASSIFYING:
        await setState(STATES.CLASSIFYING);
        const emailsToProcess = emails || await getStoredEmails();

        for (let i = currentIndex; i < emailsToProcess.length; i++) {
          await classifyEmail(emailsToProcess[i]);

          // Save progress
          await chrome.storage.local.set({ currentIndex: i + 1 });
        }
        // Fall through to next state

      case STATES.LABELING:
        await setState(STATES.LABELING);
        // Apply all labels
        await applyLabels();
        // Fall through to complete

      case STATES.COMPLETE:
        await setState(STATES.COMPLETE);
        await clearState();
        console.log('✅ Organization complete');
        break;
    }
  } catch (error) {
    console.error('❌ Error, state preserved for retry:', error);
    // State is preserved, can retry
  }
}

async function setState(newState) {
  await chrome.storage.local.set({ state: newState });
}

async function clearState() {
  await chrome.storage.local.remove(['state', 'emails', 'currentIndex']);
}
```

### Pattern 3: Heartbeat Alarm (Missed Digest Protection)

```javascript
// ✅ GOOD: Heartbeat ensures no missed operations
const HEARTBEAT_INTERVAL = 30; // minutes

// Install heartbeat alarm
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('heartbeat', { periodInMinutes: HEARTBEAT_INTERVAL });
});

// Heartbeat handler
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'heartbeat') {
    console.log('💓 Heartbeat: Checking for missed operations');

    // Check if daily digest was missed
    const { lastDigestAttempt } = await chrome.storage.local.get('lastDigestAttempt');
    const now = Date.now();
    const hoursSinceLastAttempt = (now - lastDigestAttempt) / (1000 * 60 * 60);

    if (hoursSinceLastAttempt > 25) {  // Missed yesterday's digest
      console.log('⚠️ Digest was missed, triggering now');
      await generateDigest();
    }

    // Check for incomplete organization sessions
    const { organizationInProgress } = await chrome.storage.local.get('organizationInProgress');
    if (organizationInProgress) {
      console.log('🔄 Resuming incomplete organization');
      await organizeInboxResumable();
    }
  }
});
```

## Implementation Guide

### Step 1: Add Checkpoint Keys

Define checkpoint keys in `extension/config.js`:

```javascript
// Checkpoint keys for resumable operations
const CHECKPOINT_KEYS = {
  LAST_PROCESSED_EMAIL: 'checkpoint_last_email_id',
  ORGANIZATION_STATE: 'checkpoint_org_state',
  ORGANIZATION_PROGRESS: 'checkpoint_org_progress',
  DIGEST_PENDING: 'checkpoint_digest_pending',
  LAST_DIGEST_ATTEMPT: 'checkpoint_last_digest'
};
```

### Step 2: Update auto-organize.js

Add checkpointing to `extension/modules/auto-organize.js`:

```javascript
// At top of file
const BATCH_SIZE = 10;
const CHECKPOINT_KEY = 'auto_organize_checkpoint';

async function organizeInbox() {
  try {
    // Load checkpoint
    const { lastProcessedId, totalProcessed = 0 } =
      await chrome.storage.local.get([CHECKPOINT_KEY]);

    console.log(`Starting organization (checkpoint: ${lastProcessedId || 'none'})`);

    // Fetch emails (after checkpoint if exists)
    const emails = await fetchUnlabeledEmails({ afterId: lastProcessedId });

    if (emails.length === 0) {
      console.log('✅ No emails to process');
      await clearCheckpoint();
      return { success: true, processed: 0 };
    }

    // Process in batches
    let processed = 0;
    for (let i = 0; i < emails.length; i += BATCH_SIZE) {
      const batch = emails.slice(i, Math.min(i + BATCH_SIZE, emails.length));

      await processBatch(batch);
      processed += batch.length;

      // Save checkpoint
      const lastId = batch[batch.length - 1].id;
      await saveCheckpoint({
        lastProcessedId: lastId,
        totalProcessed: totalProcessed + processed,
        timestamp: Date.now()
      });

      console.log(`✅ Checkpoint: ${processed}/${emails.length} emails processed`);
    }

    // Clear checkpoint on success
    await clearCheckpoint();

    return { success: true, processed: totalProcessed + processed };

  } catch (error) {
    console.error('❌ Organization failed, checkpoint preserved:', error);
    throw error;  // Checkpoint preserved for retry
  }
}

async function saveCheckpoint(checkpoint) {
  await chrome.storage.local.set({ [CHECKPOINT_KEY]: checkpoint });
}

async function clearCheckpoint() {
  await chrome.storage.local.remove(CHECKPOINT_KEY);
}

// Resume incomplete organization on startup
chrome.runtime.onStartup.addListener(async () => {
  const { [CHECKPOINT_KEY]: checkpoint } = await chrome.storage.local.get(CHECKPOINT_KEY);

  if (checkpoint) {
    console.log('🔄 Resuming incomplete organization from checkpoint');
    await organizeInbox();
  }
});
```

### Step 3: Add Heartbeat to background.js

Add to `extension/background.js`:

```javascript
// Heartbeat alarm (check every 30 minutes)
const HEARTBEAT_INTERVAL = 30;

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('heartbeat', { periodInMinutes: HEARTBEAT_INTERVAL });
  console.log('💓 Heartbeat alarm installed');
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'heartbeat') {
    console.log('💓 Heartbeat check');

    // Check for missed digest
    await checkMissedDigest();

    // Check for incomplete organization
    await resumeIncompleteOrganization();
  }
});

async function checkMissedDigest() {
  const { lastDigestAttempt } = await chrome.storage.local.get('lastDigestAttempt');

  if (!lastDigestAttempt) return;

  const hoursSince = (Date.now() - lastDigestAttempt) / (1000 * 60 * 60);

  if (hoursSince > 25) {
    console.log('⚠️ Digest was missed, triggering now');
    await generateDailyDigest();
  }
}

async function resumeIncompleteOrganization() {
  const checkpoint = await chrome.storage.local.get('auto_organize_checkpoint');

  if (checkpoint.auto_organize_checkpoint) {
    const minutesSince = (Date.now() - checkpoint.auto_organize_checkpoint.timestamp) / (1000 * 60);

    if (minutesSince > 5) {  // Resume if checkpoint older than 5 minutes
      console.log('🔄 Resuming incomplete organization');
      await organizeInbox();
    }
  }
}
```

### Step 4: Add Retry Logic with Exponential Backoff

Add to `extension/modules/network.js`:

```javascript
async function fetchWithRetry(url, options = {}, maxRetries = 3) {
  const delays = [1000, 2000, 4000];  // Exponential backoff

  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(url, options);

      if (response.ok) {
        return response;
      }

      // Retry on 5xx errors
      if (response.status >= 500) {
        console.warn(`Server error ${response.status}, retry ${i + 1}/${maxRetries}`);
        await sleep(delays[i]);
        continue;
      }

      // Don't retry on 4xx errors
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);

    } catch (error) {
      if (i === maxRetries - 1) throw error;

      console.warn(`Network error, retry ${i + 1}/${maxRetries}:`, error.message);
      await sleep(delays[i]);
    }
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
```

## Testing Checkpointing

### Manual Test: Kill Service Worker

```javascript
// In DevTools console (chrome://extensions → Mailq → Inspect)
// 1. Start organization
await organizeInbox();

// 2. In another console tab, kill the service worker
chrome.runtime.reload();

// 3. Verify checkpoint was saved
chrome.storage.local.get('auto_organize_checkpoint', console.log);

// 4. Trigger resume (should continue from checkpoint)
await organizeInbox();
```

### Automated Test

```javascript
// tests/extension/test_checkpointing.js
describe('Checkpointing', () => {
  it('should resume from checkpoint after interruption', async () => {
    // Start organization
    const promise = organizeInbox();

    // Simulate interruption after 5 emails
    await sleep(2000);
    chrome.runtime.reload();

    // Verify checkpoint exists
    const { auto_organize_checkpoint } = await chrome.storage.local.get('auto_organize_checkpoint');
    expect(auto_organize_checkpoint).toBeDefined();
    expect(auto_organize_checkpoint.totalProcessed).toBeGreaterThan(0);

    // Resume
    await organizeInbox();

    // Verify completion
    const { auto_organize_checkpoint: finalCheckpoint } =
      await chrome.storage.local.get('auto_organize_checkpoint');
    expect(finalCheckpoint).toBeUndefined();  // Cleared on success
  });
});
```

## Benefits

1. **Resilience**: Operations survive service worker kills
2. **Progress tracking**: Users see incremental progress
3. **Debugging**: Checkpoints provide audit trail
4. **User experience**: No "lost work" frustration

## Related Documentation

- **Extension README**: `/extension/README.md`
- **Manifest V3 Guide**: [Chrome Developer Docs](https://developer.chrome.com/docs/extensions/mv3/)
- **Service Workers**: [Chrome Service Worker Lifecycle](https://developer.chrome.com/docs/extensions/mv3/service_workers/)

---

**Status**: Implementation guide complete
**Next Step**: Implement checkpointing in `extension/modules/auto-organize.js`
**Priority**: P1 (should-have within 1 month)
