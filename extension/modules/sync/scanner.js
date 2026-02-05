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
 * Uses Gmail's built-in Purchases category plus a targeted
 * cancellation/refund query for cross-email suppression.
 */
const PURCHASE_SEARCH_QUERIES = [
  // Gmail's ML-classified Purchases category (privacy-preserving)
  'category:purchases',
  // Cancellation/refund emails (often in Updates, not Purchases)
  'subject:(cancelled OR cancellation OR "refund issued")',
];

// ============================================================
// CANCELLATION DETECTION
// ============================================================

/**
 * Amazon order number pattern: 3-7-7 digits.
 */
const AMAZON_ORDER_RE = /\b\d{3}-\d{7}-\d{7}\b/g;

/**
 * Detect cancelled order numbers from collected email metadata.
 *
 * Scans subjects and snippets for cancellation/refund signals,
 * then extracts Amazon order numbers from matching emails.
 * This is free (no API calls) and deterministic.
 *
 * @param {Array<{id: string, subject: string, snippet: string}>} emailMetas
 * @returns {Set<string>} Set of cancelled order number strings
 */
function detectCancelledOrders(emailMetas) {
  const cancelled = new Set();

  for (const meta of emailMetas) {
    const subject = (meta.subject || '').toLowerCase();
    const snippet = (meta.snippet || '').toLowerCase();
    const combined = `${subject} ${snippet}`;

    // Check subject for cancellation signals
    let isCancellation = CANCELLATION_SUBJECT_KEYWORDS.some(kw => subject.includes(kw));

    // Check snippet for body-level cancellation signals
    if (!isCancellation) {
      isCancellation = CANCELLATION_BODY_KEYWORDS.some(kw => combined.includes(kw));
    }

    if (!isCancellation) continue;

    // Extract order numbers from original (non-lowered) text
    const rawText = `${meta.subject || ''} ${meta.snippet || ''}`;
    const matches = rawText.match(AMAZON_ORDER_RE);

    if (matches) {
      for (const orderNum of matches) {
        cancelled.add(orderNum);
      }
      console.log(SCANNER_LOG_PREFIX, 'CANCELLATION_DETECTED', meta.id, 'orders:', matches);
    }
  }

  return cancelled;
}

/**
 * Suppress orders in IndexedDB that match cancelled order numbers.
 *
 * @param {Set<string>} cancelledOrderNumbers - Order numbers to cancel
 * @returns {Promise<number>} Number of orders suppressed
 */
async function suppressCancelledOrders(cancelledOrderNumbers) {
  let suppressed = 0;

  for (const orderNum of cancelledOrderNumbers) {
    const result = await cancelOrderByOrderId(orderNum);
    if (result) {
      suppressed++;
      console.log(SCANNER_LOG_PREFIX, 'SUPPRESSED_ORDER', orderNum,
        'merchant:', result.merchant_display_name);
    }
  }

  return suppressed;
}

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
 * Paginates through all results up to maxResults.
 *
 * @param {string} token - OAuth token
 * @param {string} query - Gmail search query
 * @param {number} [maxResults=500] - Maximum total results across all pages
 * @returns {Promise<Array<{id: string, threadId: string}>>}
 */
async function searchMessages(token, query, maxResults = 500) {
  const allMessages = [];
  let pageToken = null;

  try {
    do {
      const pageSize = Math.min(MAX_MESSAGES_PER_QUERY, maxResults - allMessages.length);
      let endpoint = `/messages?q=${encodeURIComponent(query)}&maxResults=${pageSize}`;
      if (pageToken) {
        endpoint += `&pageToken=${pageToken}`;
      }

      const data = await gmailRequest(endpoint, token);
      const messages = data.messages || [];
      allMessages.push(...messages);
      pageToken = data.nextPageToken || null;

      if (pageToken) {
        await new Promise(resolve => setTimeout(resolve, API_REQUEST_DELAY));
      }
    } while (pageToken && allMessages.length < maxResults);

    return allMessages;
  } catch (error) {
    console.warn(SCANNER_LOG_PREFIX, 'Search failed:', query, error.message);
    return allMessages; // Return whatever we collected before the error
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

/**
 * Extract raw HTML body from message payload.
 * Returns the HTML string without stripping tags, for backend processing.
 *
 * @param {Object} payload - Message payload
 * @returns {string|null} HTML body or null if not found
 */
function extractHtmlBodyFromPayload(payload) {
  if (!payload) return null;

  if (payload.mimeType === 'text/html' && payload.body?.data) {
    return decodeBase64Url(payload.body.data);
  }

  if (payload.parts) {
    for (const part of payload.parts) {
      if (part.mimeType === 'text/html' && part.body?.data) {
        return decodeBase64Url(part.body.data);
      }
      // Recurse into nested multipart
      const html = extractHtmlBodyFromPayload(part);
      if (html) return html;
    }
  }

  return null;
}

// ============================================================
// PIPELINE INTEGRATION (via backend API)
// ============================================================

/**
 * Extract order number from text using common patterns.
 * Handles cases where backend didn't extract order_number but it's in item_summary.
 *
 * @param {string} text - Text to search
 * @returns {string|null} Extracted order number or null
 */
function extractOrderNumber(text) {
  if (!text) return null;

  const patterns = [
    // Amazon format: 123-1234567-1234567
    /\b(\d{3}-\d{7}-\d{7})\b/,
    // Generic: Order #ABC123 or Order #: ABC123
    /order\s*#\s*:?\s*([A-Z0-9][-A-Z0-9]{3,20})/i,
    // Confirmation #ABC123
    /confirmation\s*[#:]\s*([A-Z0-9][-A-Z0-9]{3,20})/i,
    // For/regarding ABC123 at end of string
    /(?:for|regarding)\s+#?\s*([A-Z0-9][-A-Z0-9]{4,20})\s*$/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      return match[1].toUpperCase();
    }
  }
  return null;
}

/**
 * Normalize merchant domain to canonical form.
 * Handles cases where same merchant uses multiple domains/subdomains.
 *
 * @param {string} domain - Raw domain
 * @returns {string} Normalized domain
 */
function normalizeMerchantDomain(domain) {
  if (!domain) return 'unknown';

  let normalized = domain.toLowerCase().trim();

  // Remove common prefixes
  normalized = normalized.replace(/^(www\.|shop\.|store\.|mail\.|email\.|orders?\.)/, '');

  // Domain aliases - map variants to canonical domain
  const aliases = {
    'iliabeauty.com': 'ilia.com',
    'shopifyemail.com': null,  // Will use merchant name instead
    'postmarkapp.com': null,
    'sendgrid.net': null,
    'mailchimp.com': null,
    'klaviyo.com': null,
  };

  if (aliases[normalized] !== undefined) {
    return aliases[normalized];
  }

  return normalized;
}

/**
 * Generate a deterministic order key for client-side deduplication.
 * Uses merchant_domain + order_number when available, falls back to
 * merchant_domain + item_summary hash.
 *
 * @param {Object} card - ReturnCardResponse from backend
 * @returns {string} Deterministic order key
 */
function generateOrderKey(card) {
  // Normalize domain, fall back to merchant name for email service domains
  let domain = normalizeMerchantDomain(card.merchant_domain);
  if (!domain) {
    domain = (card.merchant || 'unknown').toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  // Primary: merchant + order_number (most reliable)
  let orderNum = card.order_number;

  // Fallback: try to extract order number from item_summary
  // (handles cases where backend didn't extract it but it's in the text)
  if (!orderNum) {
    orderNum = extractOrderNumber(card.item_summary);
  }

  if (orderNum) {
    return `${domain}::${orderNum.toUpperCase()}`;
  }

  // Fallback: merchant + item_summary hash (for orders without order numbers)
  const summary = (card.item_summary || '').toLowerCase().trim();
  if (summary) {
    // Simple hash: first 40 chars alphanumeric + length
    const hash = summary.substring(0, 40).replace(/[^a-z0-9]/g, '') + summary.length;
    return `${domain}::item::${hash}`;
  }

  // Last resort: use backend ID (won't dedup, but rare)
  return card.id;
}

/**
 * Convert a backend ReturnCardResponse to the extension's Order model.
 *
 * @param {Object} card - ReturnCardResponse from POST /api/returns/process
 * @param {string} user_id - Authenticated user ID
 * @returns {Order}
 */
function convertReturnCardToOrder(card, user_id) {
  const now = new Date().toISOString();
  return {
    order_key: generateOrderKey(card),
    user_id,
    merchant_domain: card.merchant_domain || '',
    merchant_display_name: card.merchant || '',
    order_id: card.order_number || undefined,
    purchase_date: card.order_date || now,
    delivery_date: card.delivery_date || undefined,
    return_by_date: card.return_by_date || undefined,
    deadline_confidence: card.confidence || 'unknown',
    item_summary: card.item_summary || '',
    amount: card.amount || undefined,
    currency: card.currency || 'USD',
    evidence_quote: card.evidence_snippet || undefined,
    return_portal_link: card.return_portal_link || undefined,
    order_status: card.status === 'returned' ? 'returned'
      : card.status === 'dismissed' ? 'dismissed'
      : 'active',
    source_email_ids: card.source_email_ids || [],
    created_at: card.created_at || now,
    updated_at: card.updated_at || now,
  };
}

/**
 * Process a single email through the backend LLM pipeline.
 *
 * Sends the email to POST /api/returns/process which runs the
 * validated 3-stage pipeline (filter → classifier → extractor).
 * Converts the resulting ReturnCard to a local Order for storage.
 *
 * @param {Object} params
 * @param {string} params.user_id
 * @param {Object} params.message - Gmail message metadata object
 * @param {string} params.token - OAuth token for fetching body
 * @returns {Promise<{processed: boolean, order: Order|null, action: string}>}
 */
async function processEmailThroughPipeline({ user_id, message, token }) {
  const email_id = message.id;

  // Check if already processed
  if (await isEmailProcessed(email_id)) {
    console.log(SCANNER_LOG_PREFIX, 'SKIP_ALREADY_PROCESSED', email_id);
    return { processed: false, order: null, action: 'skip_processed' };
  }

  // Extract metadata
  const from_address = getHeader(message, 'From');
  const subject = getHeader(message, 'Subject');
  const snippet = message.snippet || '';

  console.log(SCANNER_LOG_PREFIX, 'PROCESSING', email_id, subject.substring(0, 50));

  // P1: Local domain filter (free, avoids unnecessary API calls)
  const filterResult = filterEmail(from_address, subject, snippet);
  if (filterResult.blocked) {
    console.log(SCANNER_LOG_PREFIX, 'FILTER_BLOCKED', email_id, filterResult.reason);
    await markEmailProcessed(email_id);
    return { processed: true, order: null, action: 'blocked' };
  }

  // Fetch full email body (backend pipeline needs it)
  let body = '';
  try {
    const fullMessage = await getFullMessage(token, email_id);
    body = extractBodyFromPayload(fullMessage.payload);
  } catch (error) {
    console.warn(SCANNER_LOG_PREFIX, 'Failed to fetch body:', email_id, error.message);
    await markEmailProcessed(email_id);
    return { processed: true, order: null, action: 'body_fetch_failed' };
  }

  if (!body) {
    console.log(SCANNER_LOG_PREFIX, 'SKIP_EMPTY_BODY', email_id);
    await markEmailProcessed(email_id);
    return { processed: true, order: null, action: 'empty_body' };
  }

  // Send to backend LLM pipeline
  console.log(SCANNER_LOG_PREFIX, 'BACKEND_PROCESS', email_id);
  let response;
  try {
    response = await processEmail({
      id: email_id,
      from: from_address,
      subject,
      body,
    });
  } catch (error) {
    console.error(SCANNER_LOG_PREFIX, 'BACKEND_API_ERROR', email_id, error.message);
    // Don't mark as processed so it can be retried on next scan
    return { processed: false, order: null, action: 'backend_api_error' };
  }

  await markEmailProcessed(email_id);

  // Backend rejected the email (not a returnable purchase)
  if (!response.success || !response.card) {
    console.log(SCANNER_LOG_PREFIX, 'BACKEND_REJECTED', email_id,
      'stage:', response.stage_reached,
      'reason:', response.rejection_reason);
    return { processed: true, order: null, action: 'backend_rejected' };
  }

  // Convert backend ReturnCard to local Order and store
  const order = convertReturnCardToOrder(response.card, user_id);
  await upsertOrder(order);

  console.log(SCANNER_LOG_PREFIX, 'PIPELINE_COMPLETE', email_id,
    'order:', order.order_key,
    'merchant:', order.merchant_display_name,
    'deadline:', order.return_by_date || 'unknown');

  return { processed: true, order, action: 'backend_created' };
}

// ============================================================
// MAIN SCANNER
// ============================================================

/**
 * Scan Gmail for purchase emails and process them as a batch.
 *
 * Flow:
 * 1. Collect — Loop through messages, apply local filter, fetch body for those that pass
 * 2. Batch send — Send all collected emails to POST /api/returns/process-batch
 * 3. Store — Clear stale orders, upsert each returned card into local storage
 * 4. Post-scan — Local cancellation detection as safety net
 *
 * @param {Object} options
 * @param {number} [options.window_days=14] - How many days back to scan
 * @param {boolean} [options.incremental=true] - Use incremental scanning
 * @param {boolean} [options.skipPersistence=false] - Skip backend DB save/dedup
 * @returns {Promise<ScanResult>}
 */
async function scanPurchases(options = {}) {
  const {
    window_days = 14,
    incremental = true,
    skipPersistence = false,
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

  const stats = {
    total: allMessageIds.size,
    processed: 0,
    skipped: 0,
    blocked: 0,
    orders_created: 0,
    orders_cancelled: 0,
    errors: 0,
  };

  // ---- Phase 1: Collect emails that pass local filter ----
  const emailsForBackend = [];
  const emailMetas = [];

  for (const messageId of allMessageIds) {
    try {
      // Get message metadata
      const message = await getMessageMetadata(token, messageId);

      const subject = getHeader(message, 'Subject');
      const from_address = getHeader(message, 'From');
      const snippet = message.snippet || '';
      const receivedAt = message.internalDate
        ? new Date(parseInt(message.internalDate)).toISOString()
        : null;

      // Collect for local cancellation detection (safety net)
      emailMetas.push({ id: messageId, subject, snippet });

      // Check incremental: skip if older than last scan
      if (incremental && lastScan.internal_date_ms) {
        const msgDate = parseInt(message.internalDate || '0');
        if (msgDate < lastScan.internal_date_ms) {
          stats.skipped++;
          continue;
        }
      }

      // Check if already processed
      if (await isEmailProcessed(messageId)) {
        stats.skipped++;
        continue;
      }

      // Local domain filter (free, avoids unnecessary body fetches)
      const filterResult = filterEmail(from_address, subject, snippet);
      if (filterResult.blocked) {
        console.log(SCANNER_LOG_PREFIX, 'FILTER_BLOCKED', messageId, filterResult.reason);
        await markEmailProcessed(messageId);
        stats.blocked++;
        stats.processed++;
        continue;
      }

      // Fetch full email body
      let body = '';
      let body_html = null;
      try {
        const fullMessage = await getFullMessage(token, messageId);
        body = extractBodyFromPayload(fullMessage.payload);
        // Also extract HTML body for better extraction
        body_html = extractHtmlBodyFromPayload(fullMessage.payload);
      } catch (error) {
        console.warn(SCANNER_LOG_PREFIX, 'Failed to fetch body:', messageId, error.message);
        await markEmailProcessed(messageId);
        stats.processed++;
        continue;
      }

      if (!body) {
        console.log(SCANNER_LOG_PREFIX, 'SKIP_EMPTY_BODY', messageId);
        await markEmailProcessed(messageId);
        stats.processed++;
        continue;
      }

      emailsForBackend.push({
        email_id: messageId,
        from_address,
        subject,
        body,
        body_html,
        received_at: receivedAt,
      });

      // Rate limiting between Gmail API calls
      await new Promise(resolve => setTimeout(resolve, API_REQUEST_DELAY));

    } catch (error) {
      console.error(SCANNER_LOG_PREFIX, 'ERROR', messageId, error.message);
      stats.errors++;
    }
  }

  console.log(SCANNER_LOG_PREFIX, 'COLLECT_COMPLETE',
    emailsForBackend.length, 'emails ready for batch processing');

  // ---- Phase 2+3: Send to backend in chunks, store results after each ----
  const BATCH_CHUNK_SIZE = 10;
  let batchCards = [];

  if (emailsForBackend.length > 0) {
    // Split into chunks to avoid service worker timeout (~5 min limit)
    const chunks = [];
    for (let i = 0; i < emailsForBackend.length; i += BATCH_CHUNK_SIZE) {
      chunks.push(emailsForBackend.slice(i, i + BATCH_CHUNK_SIZE));
    }

    console.log(SCANNER_LOG_PREFIX, 'BATCH_SEND', emailsForBackend.length,
      'emails in', chunks.length, 'chunks of', BATCH_CHUNK_SIZE);

    for (let ci = 0; ci < chunks.length; ci++) {
      const chunk = chunks[ci];
      try {
        console.log(SCANNER_LOG_PREFIX, 'BATCH_CHUNK',
          `${ci + 1}/${chunks.length}`, chunk.length, 'emails');

        const batchResponse = await processEmailBatch(chunk, { skipPersistence });

        if (batchResponse.success) {
          const chunkCards = batchResponse.cards || [];
          batchCards.push(...chunkCards);
          stats.orders_created += batchResponse.stats?.cards_created || 0;

          // Store results immediately so cards appear progressively
          // upsertOrder() preserves user-initiated statuses (returned/dismissed)
          for (const card of chunkCards) {
            const order = convertReturnCardToOrder(card, user_id);
            await upsertOrder(order);
          }

          console.log(SCANNER_LOG_PREFIX, 'BATCH_CHUNK_RESULT',
            `${ci + 1}/${chunks.length}`,
            'cards:', chunkCards.length,
            'total:', batchCards.length);
        } else {
          console.error(SCANNER_LOG_PREFIX, 'BATCH_CHUNK_FAILED',
            `${ci + 1}/${chunks.length}`, 'success=false');
          stats.errors += chunk.length;
        }

        // Mark chunk emails as processed
        for (const email of chunk) {
          await markEmailProcessed(email.email_id);
        }
        stats.processed += chunk.length;

      } catch (error) {
        console.error(SCANNER_LOG_PREFIX, 'BATCH_CHUNK_ERROR',
          `${ci + 1}/${chunks.length}`, error.message);
        // Don't mark as processed so they can be retried on next scan
        stats.errors += chunk.length;
      }
    }

    if (batchCards.length > 0) {
      console.log(SCANNER_LOG_PREFIX, 'STORED', batchCards.length, 'orders from',
        chunks.length, 'chunks');
    }
  }

  // ---- Phase 4: Post-scan local cancellation detection (safety net) ----
  const cancelledOrders = detectCancelledOrders(emailMetas);
  if (cancelledOrders.size > 0) {
    console.log(SCANNER_LOG_PREFIX, 'CANCELLATION_SWEEP',
      cancelledOrders.size, 'cancelled order numbers found');
    stats.orders_cancelled = await suppressCancelledOrders(cancelledOrders);
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
 * @property {number} stats.orders_cancelled
 * @property {number} stats.errors
 */
