/**
 * Gmail API Operations Module
 */

/**
 * In-memory cache for label IDs to prevent duplicate creation and 409 errors
 * Persists for the session (cleared on extension reload)
 */
const labelCache = new Map(); // labelName -> labelId

/**
 * Sanitize label name to comply with Gmail rules
 */
function sanitizeLabelName(name) {
  // Allow slashes for nested labels
  return name
    .trim()
    .substring(0, 50);
}

/**
 * Fetch with automatic retry for transient errors (500/503)
 * @param {string} url - URL to fetch
 * @param {object} options - Fetch options
 * @param {number} maxRetries - Maximum number of retry attempts (default: 3)
 * @returns {Promise<Response>} Fetch response
 */
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(url, options);

      // Success or non-retryable error
      if (response.ok || (response.status !== 429 && response.status !== 500 && response.status !== 503)) {
        return response;
      }

      // 429 (rate limit), 500, 503 errors - retry with exponential backoff
      if (attempt < maxRetries - 1) {
        // For 429, use longer delays since it's a quota issue
        const baseDelay = response.status === 429 ? 2000 : 1000;
        const delay = Math.min(baseDelay * Math.pow(2, attempt), 10000); // 429: 2s, 4s, 8s; others: 1s, 2s, 4s
        console.log(`⏳ Retry ${attempt + 1}/${maxRetries - 1} after ${delay}ms (HTTP ${response.status})`);
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }

      // Max retries reached
      return response;

    } catch (err) {
      // Network error
      if (attempt < maxRetries - 1) {
        const delay = Math.min(1000 * Math.pow(2, attempt), 5000);
        console.log(`⏳ Retry ${attempt + 1}/${maxRetries - 1} after ${delay}ms (network error)`);
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        throw err;
      }
    }
  }
}

/**
 * Get emails from inbox that need classification
 *
 * Uses messages endpoint (not threads) to ensure new replies are caught.
 * Gmail's threads.list sorts by FIRST message date, which means threads with
 * new replies to old messages get buried. Using messages.list sorts by
 * individual message date, so new replies bubble up.
 *
 * See: https://stackoverflow.com/questions/26727961
 */
async function getUnlabeledEmails(token, maxResults = CONFIG.MAX_EMAILS_PER_BATCH) {
  // Search for emails in inbox only
  // Explicitly exclude each ShopQ label to avoid Gmail API caching issues
  // Note: We use explicit label names instead of wildcards because wildcards don't work reliably
  // This ensures we get ONLY emails that don't have ShopQ labels (Gmail search is source of truth)
  const shopqLabels = [
    'ShopQ/Receipts',
    'ShopQ/Shopping',
    'ShopQ/Messages',
    'ShopQ/Work',
    'ShopQ/Newsletters',
    'ShopQ/Notifications',
    'ShopQ/Events',
    'ShopQ/Finance',
    'ShopQ/Action-Required',
    'ShopQ/Digest',
    'ShopQ/Professional',
    'ShopQ/Personal'
  ];

  const excludeLabels = shopqLabels.map(l => `-label:${l}`).join(' ');
  const query = `in:inbox ${excludeLabels}`;
  const encodedQuery = encodeURIComponent(query);

  const scopeDescription = maxResults === 0 ? 'all unlabeled messages' : `up to ${maxResults} unlabeled threads`;
  console.log(`🔍 ShopQ scanning ${scopeDescription} in inbox...`);

  if (CONFIG.VERBOSE_LOGGING) {
    console.log('\n' + '='.repeat(80));
    console.log('🔍 GMAIL SEARCH QUERY:');
    console.log('='.repeat(80));
    console.log(`Query: "${query}"`);
    console.log(`Purpose: Find ALL emails in inbox WITHOUT any ShopQ labels`);
    console.log(`Strategy: Use messages endpoint to catch new replies to old threads`);
    console.log('='.repeat(80) + '\n');
  }

  // DIAGNOSTIC: Check what's actually in the inbox
  logVerbose('📊 DIAGNOSTIC: Checking inbox baseline...');
  try {
    const inboxCheckResponse = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=in:inbox&maxResults=10`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );
    const inboxData = await inboxCheckResponse.json();
    const inboxCount = inboxData.resultSizeEstimate || 0;
    logVerbose(`📥 Total in:inbox (no filters): ~${inboxCount} messages`);
    logVerbose(`📧 Our query will search within these messages\n`);
  } catch (error) {
    logVerbose('⚠️  Could not check inbox baseline\n');
  }

  const targetThreads = maxResults; // Target number of unique threads (conversations) - 0 means unlimited
  const seenThreads = new Map(); // threadId -> {message, timestamp} - keep newest message per thread

  if (maxResults === 0) {
    logVerbose(`📬 Fetching ALL unlabeled emails from inbox until inbox zero...`);
  } else {
    logVerbose(`📬 Fetching messages until we have ${targetThreads} unique threads...`);
  }

  // Gmail API maxResults is per-page (max 100).
  // Fetch more messages than target threads since we dedupe by thread.
  // Multiplier of 2 accounts for multi-message threads.
  const apiPageSize = maxResults === 0 ? 100 : Math.min(maxResults * 2, 100);
  let pageToken = null;
  let totalMessagesFetched = 0;
  const maxIterations = 10; // Safety limit to prevent infinite loops
  let iterations = 0;

  do {
    iterations++;

    // Use MESSAGES endpoint (not threads) - sorted by message date, newest first
    // This ensures new replies to old threads are returned first
    const url = pageToken
      ? `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${encodedQuery}&maxResults=${apiPageSize}&pageToken=${pageToken}`
      : `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${encodedQuery}&maxResults=${apiPageSize}`;

    logVerbose(`🔍 [DEBUG] Fetching from: ${url}`);

    const response = await fetch(url, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    logVerbose(`🔍 [DEBUG] Response status: ${response.status}`);

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`❌ [DEBUG] Gmail API error: ${response.status}`, errorText);

      // If 401 (authentication error), token might have expired - throw specific error
      if (response.status === 401) {
        throw new Error(`Gmail API authentication failed (401). Token may have expired.`);
      }

      throw new Error(`Gmail API error: ${response.status}`);
    }

    const data = await response.json();
    logVerbose(`🔍 [DEBUG] resultSizeEstimate: ${data.resultSizeEstimate || 0}`);
    logVerbose(`🔍 [DEBUG] nextPageToken: ${data.nextPageToken || 'none'}`);

    const messageStubs = data.messages || [];

    if (messageStubs.length === 0) {
      logVerbose('📭 No more unlabeled emails');
      break;
    }

    logVerbose(`📄 Page fetched: ${messageStubs.length} message stubs`);
    totalMessagesFetched += messageStubs.length;

    // Fetch full message details
    const batchEmails = await fetchEmailBatch(token, messageStubs);

    for (const message of batchEmails) {
      if (!message || !message.payload) {
        continue;
      }

      const parsed = parseEmailMessage(message);
      if (!parsed) continue;

      const threadId = parsed.threadId;
      const messageTimestamp = parseInt(parsed.timestamp) || 0;

      // Keep only the newest message per thread
      if (!seenThreads.has(threadId)) {
        seenThreads.set(threadId, { message: parsed, timestamp: messageTimestamp });
        logVerbose(`📧 New thread: ${parsed.subject.substring(0, 50)}...`);
      } else {
        const existing = seenThreads.get(threadId);
        if (messageTimestamp > existing.timestamp) {
          // This message is newer, replace
          seenThreads.set(threadId, { message: parsed, timestamp: messageTimestamp });
          logVerbose(`📧 Updated thread with newer message: ${parsed.subject.substring(0, 50)}...`);
        }
      }
    }

    logVerbose(`   → Unique threads so far: ${seenThreads.size}`);

    // Stop when we have enough unique threads (unless unlimited with targetThreads=0)
    if (targetThreads > 0 && seenThreads.size >= targetThreads) {
      logVerbose(`✅ Reached target of ${targetThreads} threads`);
      break;
    }

    // Safety: don't fetch forever
    if (iterations >= maxIterations) {
      logVerbose(`⚠️ Reached max iterations (${maxIterations}), stopping`);
      break;
    }

    pageToken = data.nextPageToken;

  } while (pageToken);

  // Extract the newest message from each thread
  let allEmails = Array.from(seenThreads.values()).map(entry => entry.message);

  // Enforce maxResults limit (batch processing may overshoot)
  if (targetThreads > 0 && allEmails.length > targetThreads) {
    console.log(`📋 ShopQ fetched ${totalMessagesFetched} messages, deduplicated to ${allEmails.length} threads, trimming to ${targetThreads}`);
    allEmails = allEmails.slice(0, targetThreads);
  } else {
    console.log(`📋 ShopQ fetched ${totalMessagesFetched} messages, deduplicated to ${allEmails.length} threads`);
  }

  // DETAILED LOGGING: Show what emails were fetched and what labels they have
  if (CONFIG.VERBOSE_LOGGING) {
    console.log('\n📧 DETAILED EMAIL LIST:');
    console.log('='.repeat(80));
    allEmails.forEach((email, i) => {
      const hasShopQLabel = (email.labels || []).some(l => l.startsWith('Label_2'));
      const labelStr = (email.labels || []).join(', ');
      console.log(`[${i+1}/${allEmails.length}] ${hasShopQLabel ? '⚠️  HAS ShopQ?' : '✅'} ${email.from}`);
      console.log(`        Subject: ${email.subject.substring(0, 60)}...`);
      console.log(`        Labels: ${labelStr || 'NONE'}`);
      console.log(`        ThreadID: ${email.threadId}`);
    });
    console.log('='.repeat(80) + '\n');
  }

  const filteredEmails = allEmails;

  console.log(`✅ After filtering: ${filteredEmails.length} messages from ${new Set(filteredEmails.map(e => e.threadId)).size} unlabeled threads`);

  // Filter out digest emails (catches race condition where digest just sent but not labeled yet)
  // Primary detection: X-ShopQ-Digest header (new digests)
  // Fallback detection: from yourself + "Your Inbox --" subject (old digests)
  const finalFiltered = filteredEmails.filter(email => {
    // Check custom header first (most reliable for new digests)
    if (email.isShopQDigest) {
      logVerbose(`🚫 Skipping ShopQ digest (X-ShopQ-Digest header): ${email.subject}`);
      return false;
    }

    // Fallback: Check sender + subject for old digest emails
    const fromYourself = email.from && email.from.toLowerCase().includes('jkoufopoulos@gmail.com');
    const hasDigestSubject = email.subject && email.subject.startsWith('Your Inbox --');
    const isOldDigest = fromYourself && hasDigestSubject;

    if (isOldDigest) {
      logVerbose(`🚫 Skipping old digest email (from ${email.from}): ${email.subject}`);
      return false;
    }

    return true;
  });

  if (finalFiltered.length !== filteredEmails.length) {
    logVerbose(`📧 Filtered out ${filteredEmails.length - finalFiltered.length} digest emails`);
  }

  return finalFiltered;
}

async function fetchThreadBatch(token, threads) {
  const promises = threads.map(async thread => {
    try {
      const response = await fetchWithRetry(
        `https://gmail.googleapis.com/gmail/v1/users/me/threads/${thread.id}?format=minimal`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        },
        3  // Retry up to 3 times for 429/500/503 errors
      );

      if (!response.ok) {
        console.error(`❌ Failed to fetch thread ${thread.id}: HTTP ${response.status}`);
        return null;
      }

      return await response.json();
    } catch (err) {
      console.error(`❌ Failed to fetch thread ${thread.id}:`, err);
      return null;
    }
  });

  const results = await Promise.all(promises);
  const failed = results.filter(r => r === null).length;
  if (failed > 0) {
    console.warn(`⚠️  Failed to fetch ${failed}/${threads.length} threads`);
  }
  return results;
}

async function fetchEmailBatch(token, batch) {
  const promises = batch.map(async msg => {
    try {
      const response = await fetchWithRetry(
        `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msg.id}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        },
        3  // Retry up to 3 times for 429/500/503 errors
      );

      if (!response.ok) {
        console.error(`❌ Failed to fetch message ${msg.id}: HTTP ${response.status}`);
        return null;
      }

      return await response.json();
    } catch (err) {
      console.error(`❌ Failed to fetch message ${msg.id}:`, err);
      return null;
    }
  });

  const results = await Promise.all(promises);
  const failed = results.filter(r => r === null).length;
  if (failed > 0) {
    console.warn(`⚠️  Failed to fetch ${failed}/${batch.length} messages`);
  }
  return results;
}

function parseEmailMessage(message) {
  if (!message || !message.payload || !message.payload.headers) {
    console.warn('⚠️ Invalid message structure:', message?.id);
    return null;
  }

  const headers = message.payload.headers;
  const subject = headers.find(h => h.name === 'Subject')?.value || '(no subject)';
  const from = headers.find(h => h.name === 'From')?.value || 'unknown';
  const isShopQDigest = headers.find(h => h.name === 'X-ShopQ-Digest')?.value === 'true';

  // Extract attachment information
  const attachments = extractAttachments(message.payload);

  return {
    id: message.id,
    threadId: message.threadId,
    subject,
    from,
    snippet: message.snippet || '',
    labelIds: message.labelIds || [],
    isShopQDigest,  // Flag to identify digest emails
    timestamp: message.internalDate,  // Gmail's timestamp in milliseconds since epoch
    attachments  // { hasPdf: boolean, pdfFilenames: string[], hasImages: boolean, count: number }
  };
}

/**
 * Extract attachment information from Gmail message payload
 */
function extractAttachments(payload) {
  const result = {
    hasPdf: false,
    pdfFilenames: [],
    hasImages: false,
    count: 0
  };

  if (!payload || !payload.parts) {
    return result;
  }

  // Recursively check all parts for attachments
  function checkParts(parts) {
    for (const part of parts) {
      // Check if this part is an attachment
      if (part.filename && part.body && part.body.attachmentId) {
        result.count++;

        const filename = part.filename.toLowerCase();
        if (filename.endsWith('.pdf')) {
          result.hasPdf = true;
          result.pdfFilenames.push(part.filename);
        } else if (filename.match(/\.(jpg|jpeg|png|gif|bmp|webp)$/)) {
          result.hasImages = true;
        }
      }

      // Recursively check nested parts (multipart messages)
      if (part.parts) {
        checkParts(part.parts);
      }
    }
  }

  checkParts(payload.parts);
  return result;
}

/**
 * Get or create a Gmail label with in-memory caching
 */
async function getOrCreateLabel(token, labelName) {
  try {
    // ✅ Sanitize the label name first
    const safeLabelName = sanitizeLabelName(labelName);

    // Check in-memory cache first (prevents duplicate API calls)
    if (labelCache.has(safeLabelName)) {
      const cachedId = labelCache.get(safeLabelName);
      logVerbose(`💾 Label cache hit: ${safeLabelName} (${cachedId})`);
      return cachedId;
    }

    logVerbose(`🔍 Looking for label: ${safeLabelName}`);

    // Fetch all labels from Gmail API
    const response = await fetch(
      `https://www.googleapis.com/gmail/v1/users/me/labels`,
      {
        headers: { 'Authorization': `Bearer ${token}` }
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch labels: ${response.status}`);
    }

    const data = await response.json();
    const existingLabel = data.labels.find(l => l.name === safeLabelName);

    if (existingLabel) {
      logVerbose(`✅ Found existing label: ${safeLabelName} (${existingLabel.id})`);
      // Cache the result before returning
      labelCache.set(safeLabelName, existingLabel.id);
      return existingLabel.id;
    }

    // Create new label
    logVerbose(`➕ Creating label: ${safeLabelName}`);
    const createResponse = await fetch(
      `https://www.googleapis.com/gmail/v1/users/me/labels`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: safeLabelName,
          labelListVisibility: 'labelShow',
          messageListVisibility: 'show'
        })
      }
    );

    if (!createResponse.ok) {
      const errorData = await createResponse.json();

      // Handle 409 Conflict - label already exists (race condition)
      if (createResponse.status === 409) {
        logVerbose(`⚠️ Label "${safeLabelName}" already exists (409), fetching existing label...`);

        // Re-fetch labels to get the existing one
        const refetchResponse = await fetch(
          `https://www.googleapis.com/gmail/v1/users/me/labels`,
          {
            headers: { 'Authorization': `Bearer ${token}` }
          }
        );

        if (refetchResponse.ok) {
          const refetchData = await refetchResponse.json();
          const existingLabel = refetchData.labels.find(l => l.name === safeLabelName);

          if (existingLabel) {
            logVerbose(`✅ Found existing label after 409: ${safeLabelName} (${existingLabel.id})`);
            // Cache the recovered label before returning
            labelCache.set(safeLabelName, existingLabel.id);
            return existingLabel.id;
          }
        }
      }

      console.error('❌ Label creation failed:', JSON.stringify(errorData, null, 2));
      throw new Error(`Failed to create label: ${createResponse.status} - ${JSON.stringify(errorData)}`);
    }

    const newLabel = await createResponse.json();
    logVerbose(`✅ Created label: ${safeLabelName} (${newLabel.id})`);
    // Cache the newly created label before returning
    labelCache.set(safeLabelName, newLabel.id);
    return newLabel.id;

  } catch (error) {
    console.error(`❌ Error with label "${labelName}":`, error);
    throw error;
  }
}

/**
 * Apply labels to emails and optionally remove from inbox
 */
async function applyLabels(token, emailsWithLabels, removeFromInbox = false) {
  const action = removeFromInbox ? 'and archiving from inbox' : '(keeping in inbox)';
  console.log(`🏷️ Applying Gmail labels ${action}...`);

  // Refresh token before batch operations to avoid 401 errors during long classification runs
  console.log('🔄 Refreshing OAuth token before Gmail API calls...');
  token = await getAuthToken({ forceRefresh: false });

  const labelToEmails = {};

  emailsWithLabels.forEach(item => {
    if (!item.labels || !Array.isArray(item.labels)) {
      console.warn('⚠️ No labels for email:', item.id);
      return;
    }

    item.labels.forEach(label => {
      if (!labelToEmails[label]) {
        labelToEmails[label] = [];
      }
      labelToEmails[label].push(item);
    });
  });

  const labelIds = {};
  for (const labelName of Object.keys(labelToEmails)) {
    labelIds[labelName] = await getOrCreateLabel(token, labelName);
  }

  let successCount = 0;
  let errors = [];

  for (const item of emailsWithLabels) {
    try {
      const addLabelIds = item.labels
        .map(label => labelIds[label])
        .filter(id => id);

      if (addLabelIds.length === 0) {
        console.warn('⚠️ No valid labels for:', item.subject);
        continue;
      }

      // Always add INBOX label to keep emails visible in inbox during debugging
      // Include INBOX in addLabelIds if not archiving
      const labelsToAdd = removeFromInbox ? addLabelIds : [...addLabelIds, 'INBOX'];

      const requestBody = {
        addLabelIds: labelsToAdd,
        // Remove INBOX label to archive and IMPORTANT to allow archiving
        // IMPORTANT label can prevent emails from being archived in Gmail
        // NOTE: We keep UNREAD - emails should stay unread after organizing
        removeLabelIds: removeFromInbox ? ['INBOX', 'IMPORTANT'] : []
      };

      logVerbose(`🔧 [DEBUG] Modifying thread ${item.threadId}:`, JSON.stringify(requestBody));

      // Use threads.modify instead of messages.modify to ensure entire thread is labeled/archived
      // This prevents issues where threads with multiple messages don't archive properly
      const response = await fetchWithRetry(
        `https://gmail.googleapis.com/gmail/v1/users/me/threads/${item.threadId}/modify`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        },
        3  // Retry up to 3 times for 500/503 errors
      );

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`❌ [DEBUG] Gmail API error for ${item.id}:`, errorText);

        // If 401, add helpful context about token expiration
        if (response.status === 401) {
          console.error(`🔒 Token expired during batch operation. Consider refreshing token more frequently.`);
        }

        throw new Error(`API error ${response.status}: ${errorText}`);
      }

      const responseData = await response.json();
      logVerbose(`✅ [DEBUG] Gmail API response for ${item.id}:`, responseData);

      // VERIFY: Check if archiving actually worked
      if (removeFromInbox) {
        const stillInInbox = responseData.messages?.some(msg => msg.labelIds?.includes('INBOX'));
        if (stillInInbox) {
          console.warn(`⚠️  [ARCHIVE FAILED] Thread ${item.threadId} still has INBOX label after removal attempt!`);
          console.warn(`   Subject: ${item.subject}`);
          console.warn(`   From: ${item.from}`);
          console.warn(`   Messages in thread: ${responseData.messages?.length}`);
          console.warn(`   This email will need manual cleanup or re-processing`);
          errors.push({
            email: item,
            error: 'INBOX label still present after archive attempt',
            threadId: item.threadId,
            messageCount: responseData.messages?.length
          });
        } else {
          logVerbose(`   ✅ Verified: INBOX label removed successfully`);
        }
      }

      successCount++;
      const labelNames = item.labels.join(', ');
      logVerbose(`✅ [${successCount}/${emailsWithLabels.length}] Labeled: ${item.subject.substring(0, 50)}... → [${labelNames}]`);

      // Write-through to label cache for content script badge rendering
      // Pass full classification data (type, importance, client_label)
      if (typeof storeLabelCache === 'function') {
        await storeLabelCache(item.threadId, {
          type: item.type,
          importance: item.importance,
          client_label: item.client_label
        });
      }

    } catch (err) {
      console.error(`❌ Failed to label ${item.subject}:`, err);
      errors.push({ email: item, error: err.message });
    }
  }

  const uniqueLabels = Object.keys(labelIds);
  console.log(`\n📊 Results: ${successCount}/${emailsWithLabels.length} labeled successfully`);
  console.log(`🏷️  Labels used: ${uniqueLabels.join(', ')}`);
  console.log(`💾 Label cache size: ${labelCache.size} labels cached`);

  if (errors.length > 0) {
    console.warn(`⚠️ ${errors.length} errors:`, errors);
  }

  return {
    success: successCount,
    total: emailsWithLabels.length,
    errors,
    labelsUsed: uniqueLabels
  };
}

// Functions are available globally when loaded via importScripts() in background.js
// No export statement needed for Manifest V3 service workers
