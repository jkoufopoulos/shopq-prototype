/**
 * Label Cache Module
 *
 * Write-Through Cache for thread classification data.
 * Stores classification results when emails are classified, enabling the content script
 * to render badges without calling Gmail API or parsing DOM.
 *
 * Storage Format:
 * chrome.storage.local['mailq_label_cache'] = {
 *   [threadId]: {
 *     type: 'Event' | 'Notification' | 'Newsletter' | 'Promotion' | 'Receipt' | 'Message' | 'OTP',
 *     importance: 'critical' | 'time_sensitive' | 'routine',
 *     clientLabel: 'receipts' | 'messages' | 'action-required' | 'everything-else',
 *     updatedAt: ISO timestamp
 *   }
 * }
 */

const LABEL_CACHE_KEY = 'mailq_label_cache';
const CACHE_TTL_DAYS = 30;
const MAX_CACHE_ENTRIES = 20000;
const EVICTION_RATIO = 0.2; // Evict oldest 20% when limit reached

/**
 * Store classification result for a thread (write-through)
 * Called after classification, before labels are applied to Gmail
 *
 * Side Effects:
 * - Writes to chrome.storage.local
 * - If cache exceeds 20,000 entries, evicts oldest 20% by updatedAt timestamp
 * - Logs eviction events to console
 *
 * @param {string} threadId - Gmail thread ID
 * @param {Object} classification - Classification result from API
 * @param {string} classification.type - Email type (event, notification, etc.)
 * @param {string} classification.importance - Importance level (critical, time_sensitive, routine)
 * @param {string} classification.client_label - Client label category
 * @param {Object} emailMeta - Optional email metadata for digest
 * @returns {Promise<void>}
 */
async function storeLabelCache(threadId, classification, emailMeta = {}) {
  try {
    const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
    let cache = data[LABEL_CACHE_KEY] || {};

    // Check cache size and evict oldest entries if needed
    const cacheSize = Object.keys(cache).length;
    if (cacheSize >= MAX_CACHE_ENTRIES) {
      const evictCount = Math.floor(MAX_CACHE_ENTRIES * EVICTION_RATIO);

      // Sort entries by updatedAt timestamp (oldest first)
      const sortedEntries = Object.entries(cache).sort((a, b) => {
        const timeA = new Date(a[1].updatedAt || 0).getTime();
        const timeB = new Date(b[1].updatedAt || 0).getTime();
        return timeA - timeB;
      });

      // Remove oldest entries
      const toEvict = sortedEntries.slice(0, evictCount);
      for (const [threadId] of toEvict) {
        delete cache[threadId];
      }

      console.log(`🧹 Label cache eviction: removed ${evictCount} oldest entries (cache was ${cacheSize}/${MAX_CACHE_ENTRIES})`);
    }

    // Capitalize type for display (event → Event)
    const type = classification.type
      ? classification.type.charAt(0).toUpperCase() + classification.type.slice(1)
      : null;

    cache[threadId] = {
      type: type,
      importance: classification.importance || 'routine',
      clientLabel: classification.client_label || 'everything-else',
      // Email metadata for digest generation
      subject: emailMeta.subject || '',
      from: emailMeta.from || '',
      snippet: emailMeta.snippet || '',
      messageId: emailMeta.messageId || emailMeta.id || '',
      date: emailMeta.date || new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    await chrome.storage.local.set({ [LABEL_CACHE_KEY]: cache });
    console.log(`💾 Label cache stored for thread ${threadId}:`, cache[threadId]);
  } catch (error) {
    console.error('❌ Failed to store label cache:', error);
  }
}

/**
 * Get cached classification data for a thread
 * @param {string} threadId - Gmail thread ID
 * @returns {Promise<{type: string|null, importance: string, clientLabel: string}|null>}
 */
async function getLabelCache(threadId) {
  try {
    const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
    const cache = data[LABEL_CACHE_KEY] || {};
    return cache[threadId] || null;
  } catch (error) {
    console.error('❌ Failed to get label cache:', error);
    return null;
  }
}

/**
 * Get all cached classification data
 * @returns {Promise<Object>}
 */
async function getAllLabelCache() {
  try {
    const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
    return data[LABEL_CACHE_KEY] || {};
  } catch (error) {
    console.error('❌ Failed to get label cache:', error);
    return {};
  }
}

/**
 * Bootstrap sync: Fetch threads with MailQ labels from Gmail and populate cache
 *
 * Extracts clientLabel from Gmail labels (type comes from API classification, not labels).
 *
 * @param {string} token - Gmail OAuth token
 * @returns {Promise<{synced: number, errors: number}>}
 */
async function syncFromGmail(token) {
  console.log('🔄 Syncing label cache from Gmail...');

  // Query for threads with any of the 4 MailQ folder labels
  const query = 'label:MailQ-Receipts OR label:MailQ-Messages OR label:MailQ-Action-Required OR label:MailQ-Everything-Else';
  const encodedQuery = encodeURIComponent(query);

  let synced = 0;
  let errors = 0;
  let pageToken = null;
  const maxPages = 5;
  let pages = 0;

  try {
    const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
    const cache = data[LABEL_CACHE_KEY] || {};

    do {
      pages++;
      const url = pageToken
        ? `https://gmail.googleapis.com/gmail/v1/users/me/threads?q=${encodedQuery}&maxResults=50&pageToken=${pageToken}`
        : `https://gmail.googleapis.com/gmail/v1/users/me/threads?q=${encodedQuery}&maxResults=50`;

      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        console.error(`❌ Gmail API error during sync: ${response.status}`);
        errors++;
        break;
      }

      const result = await response.json();
      const threads = result.threads || [];

      for (const thread of threads) {
        try {
          // Skip if already in cache with type data (write-through from API has full classification)
          if (cache[thread.id]?.type) {
            continue;
          }

          const threadResponse = await fetch(
            `https://gmail.googleapis.com/gmail/v1/users/me/threads/${thread.id}?format=metadata`,
            { headers: { 'Authorization': `Bearer ${token}` } }
          );

          if (!threadResponse.ok) {
            errors++;
            continue;
          }

          const threadData = await threadResponse.json();
          const labelIds = threadData.messages?.[0]?.labelIds || [];

          // Get label names (only clientLabel available from Gmail labels)
          const labels = await getLabelNamesFromIds(token, labelIds);
          const clientLabel = extractClientLabel(labels);

          if (clientLabel) {
            // Preserve existing type/importance from classification if present
            // syncFromGmail only knows clientLabel (from Gmail labels), not type/importance
            const existing = cache[thread.id] || {};
            cache[thread.id] = {
              type: existing.type || null,  // Preserve classification type
              importance: existing.importance || 'routine',  // Preserve classification importance
              clientLabel: clientLabel,
              // Preserve email metadata if it exists
              subject: existing.subject,
              from: existing.from,
              snippet: existing.snippet,
              messageId: existing.messageId,
              date: existing.date,
              updatedAt: new Date().toISOString()
            };
            synced++;
          }
        } catch (err) {
          console.warn(`⚠️ Failed to sync thread ${thread.id}:`, err);
          errors++;
        }
      }

      pageToken = result.nextPageToken;
    } while (pageToken && pages < maxPages);

    // Evict old entries
    const cutoff = Date.now() - (CACHE_TTL_DAYS * 24 * 60 * 60 * 1000);
    for (const threadId of Object.keys(cache)) {
      const entry = cache[threadId];
      if (entry.updatedAt && new Date(entry.updatedAt).getTime() < cutoff) {
        delete cache[threadId];
      }
    }

    await chrome.storage.local.set({ [LABEL_CACHE_KEY]: cache });
    console.log(`✅ Label cache sync complete: ${synced} threads synced, ${errors} errors, ${Object.keys(cache).length} total cached`);

  } catch (error) {
    console.error('❌ Label cache sync failed:', error);
    errors++;
  }

  return { synced, errors };
}

/**
 * Extract client label from Gmail labels
 * @param {string[]} labels - Gmail label names
 * @returns {string|null} - Client label (receipts, messages, action-required, everything-else)
 */
function extractClientLabel(labels) {
  for (const label of labels) {
    if (label === 'MailQ-Receipts') return 'receipts';
    if (label === 'MailQ-Messages') return 'messages';
    if (label === 'MailQ-Action-Required') return 'action-required';
    if (label === 'MailQ-Everything-Else') return 'everything-else';
  }
  return null;
}

// Cache for label ID to name mapping
const labelIdNameCache = new Map();

/**
 * Convert label IDs to label names
 */
async function getLabelNamesFromIds(token, labelIds) {
  const names = [];

  for (const labelId of labelIds) {
    if (!labelId.startsWith('Label_')) {
      names.push(labelId);
      continue;
    }

    if (labelIdNameCache.has(labelId)) {
      names.push(labelIdNameCache.get(labelId));
      continue;
    }

    try {
      const response = await fetch(
        `https://gmail.googleapis.com/gmail/v1/users/me/labels/${labelId}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );

      if (response.ok) {
        const label = await response.json();
        labelIdNameCache.set(labelId, label.name);
        names.push(label.name);
      }
    } catch (err) {
      console.warn(`⚠️ Failed to fetch label name for ${labelId}`);
    }
  }

  return names;
}

/**
 * Clear the entire label cache
 */
async function clearLabelCache() {
  await chrome.storage.local.remove(LABEL_CACHE_KEY);
  console.log('🗑️ Label cache cleared');
}

// Make functions available globally
globalThis.storeLabelCache = storeLabelCache;
globalThis.getLabelCache = getLabelCache;
globalThis.getAllLabelCache = getAllLabelCache;
globalThis.syncFromGmail = syncFromGmail;
globalThis.clearLabelCache = clearLabelCache;
globalThis.LABEL_CACHE_KEY = LABEL_CACHE_KEY;
