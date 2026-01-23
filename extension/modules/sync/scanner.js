/**
 * Gmail Purchase Email Scanner
 *
 * Scans Gmail for purchase emails and processes them through the pipeline.
 * Uses Gmail's category:purchases for high-recall initial fetch.
 *
 * Scan Strategy:
 * - Fetches metadata first (cheap), body only when needed
 * - Skips already-processed emails
 * - Uses internalDate for incremental scanning
 * - Respects rate limits with delays between requests
 */

const SCANNER_LOG_PREFIX = '[ReturnWatch:Scanner]';

// ============================================================
// CONSTANTS
// ============================================================

/**
 * Gmail API base URL.
 */
const GMAIL_API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me';

/**
 * Delay between Gmail API requests (ms).
 */
const API_REQUEST_DELAY = 100;

/**
 * Maximum messages per search query.
 */
const MAX_MESSAGES_PER_QUERY = 100;

/**
 * Search queries for finding purchase emails.
 * Uses Gmail's built-in Purchases category plus targeted searches.
 */
const PURCHASE_SEARCH_QUERIES = [
  // Primary: Gmail's ML-classified Purchases category
  'category:purchases',

  // Backup: Shipping/delivery signals
  'subject:(shipped OR delivered OR "your order" OR "order confirmation")',
];

// ============================================================
// GMAIL API HELPERS
// ============================================================

/**
 * Make an authenticated Gmail API request.
 *
 * @param {string} endpoint - API endpoint (relative to base)
 * @param {string} token - OAuth token
 * @param {Object} [options] - Fetch options
 * @returns {Promise<Object>} Response JSON
 */
async function gmailRequest(endpoint, token, options = {}) {
  const url = `${GMAIL_API_BASE}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = new Error(`Gmail API error: ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

/**
 * Search for messages matching a query.
 *
 * @param {string} token - OAuth token
 * @param {string} query - Gmail search query
 * @param {number} [maxResults=100] - Maximum results
 * @returns {Promise<Array<{id: string, threadId: string}>>}
 */
async function searchMessages(token, query, maxResults = MAX_MESSAGES_PER_QUERY) {
  try {
    const data = await gmailRequest(
      `/messages?q=${encodeURIComponent(query)}&maxResults=${maxResults}`,
      token
    );
    return data.messages || [];
  } catch (error) {
    console.warn(SCANNER_LOG_PREFIX, 'Search failed:', query, error.message);
    return [];
  }
}

/**
 * Get message metadata (headers only, no body).
 *
 * @param {string} token - OAuth token
 * @param {string} messageId - Message ID
 * @returns {Promise<Object>} Message metadata
 */
async function getMessageMetadata(token, messageId) {
  return gmailRequest(
    `/messages/${messageId}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date`,
    token
  );
}

/**
 * Get full message (including body).
 *
 * @param {string} token - OAuth token
 * @param {string} messageId - Message ID
 * @returns {Promise<Object>} Full message
 */
async function getFullMessage(token, messageId) {
  return gmailRequest(
    `/messages/${messageId}?format=full`,
    token
  );
}

/**
 * Extract header value from message.
 *
 * @param {Object} message - Gmail message object
 * @param {string} headerName - Header name (case-insensitive)
 * @returns {string} Header value or empty string
 */
function getHeader(message, headerName) {
  const headers = message.payload?.headers || [];
  const header = headers.find(h => h.name.toLowerCase() === headerName.toLowerCase());
  return header?.value || '';
}

/**
 * Decode base64url encoded string.
 *
 * @param {string} data - Base64url encoded data
 * @returns {string} Decoded string
 */
function decodeBase64Url(data) {
  try {
    const base64 = data.replace(/-/g, '+').replace(/_/g, '/');
    return decodeURIComponent(escape(atob(base64)));
  } catch {
    return '';
  }
}

/**
 * Extract plain text body from message payload.
 *
 * @param {Object} payload - Message payload
 * @returns {string} Plain text body
 */
function extractBodyFromPayload(payload) {
  if (!payload) return '';

  // Plain text part
  if (payload.mimeType === 'text/plain' && payload.body?.data) {
    return decodeBase64Url(payload.body.data);
  }

  // HTML part (strip tags)
  if (payload.mimeType === 'text/html' && payload.body?.data) {
    const html = decodeBase64Url(payload.body.data);
    return html
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Multipart: recurse into parts
  if (payload.parts) {
    // Prefer plain text
    for (const part of payload.parts) {
      if (part.mimeType === 'text/plain') {
        const text = extractBodyFromPayload(part);
        if (text) return text;
      }
    }
    // Fall back to HTML
    for (const part of payload.parts) {
      const text = extractBodyFromPayload(part);
      if (text) return text;
    }
  }

  return '';
}

// ============================================================
// PIPELINE INTEGRATION
// ============================================================

/**
 * Process a single email through the full pipeline.
 *
 * Pipeline stages:
 * P1: Filter (blocklist)
 * P2: Primary key linking
 * P3: Thread hinting
 * P4: Classification
 * P5: Extraction
 * P6-P7: Resolution & merge
 * P8: Lifecycle & deadline
 *
 * @param {Object} params
 * @param {string} params.user_id
 * @param {Object} params.message - Gmail message object
 * @param {string} params.token - OAuth token for fetching body if needed
 * @returns {Promise<{processed: boolean, order: Order|null, action: string}>}
 */
async function processEmailThroughPipeline({ user_id, message, token }) {
  const email_id = message.id;
  const thread_id = message.threadId;

  // Check if already processed
  if (await isEmailProcessed(email_id)) {
    console.log(SCANNER_LOG_PREFIX, 'SKIP_ALREADY_PROCESSED', email_id);
    return { processed: false, order: null, action: 'skip_processed' };
  }

  // Extract metadata
  const from_address = getHeader(message, 'From');
  const subject = getHeader(message, 'Subject');
  const snippet = message.snippet || '';
  const internalDate = message.internalDate;
  const received_at = internalDate
    ? new Date(parseInt(internalDate)).toISOString()
    : new Date().toISOString();

  console.log(SCANNER_LOG_PREFIX, 'PROCESSING', email_id, subject.substring(0, 50));

  // P1: Early Filter
  const filterResult = filterEmail(from_address, subject, snippet);
  if (filterResult.blocked) {
    console.log(SCANNER_LOG_PREFIX, 'FILTER_BLOCKED', email_id, filterResult.reason);

    // Record as blocked email
    const emailRecord = createEmailRecord({
      email_id,
      thread_id,
      received_at,
      merchant_domain: filterResult.merchant_domain,
      email_type: EMAIL_TYPE.OTHER,
      blocked: true,
      extracted: null,
    });
    await storeOrderEmail(emailRecord);
    await markEmailProcessed(email_id);

    return { processed: true, order: null, action: 'blocked' };
  }

  const merchant_domain = filterResult.merchant_domain;
  const merchant_display_name = extractMerchantDisplayName(from_address);

  // P2: Primary Key Linking (from subject/snippet first)
  const linkResult = await attemptPrimaryKeyLink(subject, snippet);

  // P4: Classification
  const { email_type, purchase_confirmed } = classifyEmail(
    subject,
    snippet,
    linkResult.keys.order_id !== null
  );

  // Determine if we need the full body
  // We need body if:
  // - No primary key found yet
  // - It's a confirmation/shipping/delivery email (may have return policy info)
  const needsBody = !linkResult.linked ||
    email_type === EMAIL_TYPE.CONFIRMATION ||
    email_type === EMAIL_TYPE.SHIPPING ||
    email_type === EMAIL_TYPE.DELIVERY;

  let body = '';
  if (needsBody) {
    try {
      const fullMessage = await getFullMessage(token, email_id);
      body = extractBodyFromPayload(fullMessage.payload);
    } catch (error) {
      console.warn(SCANNER_LOG_PREFIX, 'Failed to fetch body:', email_id, error.message);
    }
  }

  // P5: Extraction (with body if available)
  const extracted = extractFields(subject, snippet, body);

  // If we didn't find primary key in subject/snippet, check body
  let linked_order = linkResult.order;
  let linked_by = linkResult.linked_by;

  if (!linkResult.linked && (extracted.order_id || extracted.tracking_number)) {
    const bodyLinkResult = await linkByPrimaryKey(extracted.order_id, extracted.tracking_number);
    linked_order = bodyLinkResult.order;
    linked_by = bodyLinkResult.linked_by;
  }

  // P3: Thread Hinting (only if no primary key match)
  if (!linked_order && thread_id) {
    const hintResult = await attemptThreadHint(email_id, thread_id, merchant_domain);
    if (hintResult.hinted) {
      console.log(SCANNER_LOG_PREFIX, 'HINT_ATTACH', email_id, '->', hintResult.order.order_key);
      // Hint-attached emails don't create or update orders further
      // Just record the email and return
      const emailRecord = createEmailRecord({
        email_id,
        thread_id,
        received_at,
        merchant_domain,
        email_type,
        blocked: false,
        extracted,
      });
      await storeOrderEmail(emailRecord);
      await markEmailProcessed(email_id);

      return { processed: true, order: hintResult.order, action: 'hint_attach' };
    }
  }

  // P6-P7: Resolution
  const resolveResult = await resolveEmail({
    user_id,
    email_id,
    thread_id,
    received_at,
    merchant_domain,
    merchant_display_name,
    extracted,
    email_type,
    purchase_confirmed,
    linked_order,
    linked_by,
  });

  // P8: Lifecycle (if order was created/updated)
  if (resolveResult.order) {
    const finalOrder = await applyEventAndComputeDeadline(resolveResult.order);
    await upsertOrder(finalOrder);

    console.log(SCANNER_LOG_PREFIX, 'PIPELINE_COMPLETE', email_id,
      'action:', resolveResult.action,
      'order:', finalOrder.order_key,
      'deadline:', finalOrder.return_by_date || 'unknown');

    return { processed: true, order: finalOrder, action: resolveResult.action };
  }

  console.log(SCANNER_LOG_PREFIX, 'PIPELINE_COMPLETE', email_id,
    'action:', resolveResult.action, '(no order)');

  return { processed: true, order: null, action: resolveResult.action };
}

// ============================================================
// MAIN SCANNER
// ============================================================

/**
 * Scan Gmail for purchase emails and process them.
 *
 * @param {Object} options
 * @param {number} [options.window_days=14] - How many days back to scan
 * @param {boolean} [options.incremental=true] - Use incremental scanning
 * @returns {Promise<ScanResult>}
 */
async function scanPurchases(options = {}) {
  const {
    window_days = 14,
    incremental = true,
  } = options;

  console.log(SCANNER_LOG_PREFIX, '='.repeat(60));
  console.log(SCANNER_LOG_PREFIX, 'SCAN_START', `window=${window_days}d, incremental=${incremental}`);
  console.log(SCANNER_LOG_PREFIX, '='.repeat(60));

  const startTime = Date.now();

  // Get auth token
  const token = await getAuthToken();
  if (!token) {
    throw new Error('No auth token available');
  }

  // SEC-002: Get authenticated user ID (never use default_user)
  const user_id = await getAuthenticatedUserId();

  // Get last scan state for incremental
  const lastScan = await getLastScanState();

  // Build date constraint for query
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - window_days);
  const dateQuery = `newer_than:${window_days}d`;

  // Collect all message IDs to process
  const allMessageIds = new Set();

  for (const baseQuery of PURCHASE_SEARCH_QUERIES) {
    const query = `${baseQuery} ${dateQuery}`;
    console.log(SCANNER_LOG_PREFIX, 'SEARCH', query);

    const messages = await searchMessages(token, query);
    console.log(SCANNER_LOG_PREFIX, 'FOUND', messages.length, 'messages');

    for (const msg of messages) {
      allMessageIds.add(msg.id);
    }

    // Rate limiting
    await new Promise(resolve => setTimeout(resolve, API_REQUEST_DELAY));
  }

  console.log(SCANNER_LOG_PREFIX, 'TOTAL_UNIQUE', allMessageIds.size, 'messages');

  // Process each message
  const stats = {
    total: allMessageIds.size,
    processed: 0,
    skipped: 0,
    blocked: 0,
    orders_created: 0,
    orders_updated: 0,
    hints_attached: 0,
    errors: 0,
  };

  for (const messageId of allMessageIds) {
    try {
      // Get message metadata
      const message = await getMessageMetadata(token, messageId);

      // Check incremental: skip if older than last scan
      if (incremental && lastScan.internal_date_ms) {
        const msgDate = parseInt(message.internalDate || '0');
        if (msgDate < lastScan.internal_date_ms) {
          stats.skipped++;
          continue;
        }
      }

      // Process through pipeline
      const result = await processEmailThroughPipeline({
        user_id,
        message,
        token,
      });

      if (result.processed) {
        stats.processed++;

        switch (result.action) {
          case 'blocked':
            stats.blocked++;
            break;
          case 'create_full':
          case 'create_partial':
            stats.orders_created++;
            break;
          case 'primary_merge':
          case 'merge_escalation':
            stats.orders_updated++;
            break;
          case 'hint_attach':
            stats.hints_attached++;
            break;
        }
      } else {
        stats.skipped++;
      }

      // Rate limiting
      await new Promise(resolve => setTimeout(resolve, API_REQUEST_DELAY));

    } catch (error) {
      console.error(SCANNER_LOG_PREFIX, 'ERROR', messageId, error.message);
      stats.errors++;
    }
  }

  // Update scan state
  const now = Date.now();
  await updateLastScanState(now, now, window_days);

  const duration = ((Date.now() - startTime) / 1000).toFixed(1);

  console.log(SCANNER_LOG_PREFIX, '='.repeat(60));
  console.log(SCANNER_LOG_PREFIX, 'SCAN_COMPLETE', `${duration}s`);
  console.log(SCANNER_LOG_PREFIX, 'STATS', JSON.stringify(stats));
  console.log(SCANNER_LOG_PREFIX, '='.repeat(60));

  return {
    success: true,
    duration_seconds: parseFloat(duration),
    stats,
  };
}

/**
 * @typedef {Object} ScanResult
 * @property {boolean} success
 * @property {number} duration_seconds
 * @property {Object} stats
 * @property {number} stats.total
 * @property {number} stats.processed
 * @property {number} stats.skipped
 * @property {number} stats.blocked
 * @property {number} stats.orders_created
 * @property {number} stats.orders_updated
 * @property {number} stats.hints_attached
 * @property {number} stats.errors
 */
