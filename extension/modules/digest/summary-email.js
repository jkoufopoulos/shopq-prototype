/**
 * Summary Email Module
 *
 * Generates a summary email of inbox classifications once per browser session
 *
 * Features:
 * - Session-based triggering (once per browser session)
 * - Incremental updates (shows what changed since last summary)
 * - AI-powered high-level insights using Gemini
 * - Fun emojis and visual formatting
 * - Witty Office quote easter egg
 */

const SUMMARY_EMAIL_KEY = 'mailq_summary_email_sent';
const LAST_SUMMARY_DATA_KEY = 'mailq_last_summary_data';
const SESSION_START_KEY = 'mailq_session_start';
const SUMMARY_METRICS_KEY = 'mailq_summary_metrics';
const SUMMARY_ERRORS_KEY = 'mailq_summary_errors';
const LAST_DIGEST_SENT_KEY = 'mailq_last_digest_sent_at';
const DIGEST_PENDING_KEY = 'mailq_digest_pending';
const LAST_DIGEST_HASH_KEY = 'mailq_last_digest_hash';
const DIGEST_DEDUP_WINDOW_MS = 5 * 60 * 1000; // 5 minutes
const DIGEST_GENERATION_LOCK_KEY = 'mailq_digest_generation_lock';
const DIGEST_LOCK_TIMEOUT_MS = 30 * 1000; // 30 seconds max lock time
const DIGEST_COOLDOWN_MS = 10 * 1000; // 10 seconds cooldown between digests
const MAX_EMAIL_AGE_DAYS = 30;
const MS_IN_DAY = 24 * 60 * 60 * 1000;

// In-memory flag to prevent concurrent digest generation within same extension instance
let isGeneratingDigest = false;
let lastDigestTimestamp = 0; // Track last digest generation time

function buildDigestSubject(date) {
  try {
    const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'long' }).format(date);
    const month = new Intl.DateTimeFormat(undefined, { month: 'long' }).format(date);
    const day = String(date.getDate()).padStart(2, '0');
    const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date);
    return `Your Inbox --${weekday}, ${month} ${day} at ${time}`;
  } catch (error) {
    console.warn('⚠️ [SUMMARY] Failed to build subject from date:', error);
    return null;
  }
}

function formatDigestSubject(originalSubject, metadata) {
  try {
    const localIso = metadata?.generated_at_local;
    if (localIso) {
      const localDate = new Date(localIso);
      if (!Number.isNaN(localDate.getTime())) {
        const formatted = buildDigestSubject(localDate);
        if (formatted) {
          return formatted;
        }
      }
    }
  } catch (error) {
    console.warn('⚠️ [SUMMARY] Failed to format subject from metadata:', error);
  }

  const fallbackDate = new Date();
  const fallbackSubject = buildDigestSubject(fallbackDate);
  return fallbackSubject || originalSubject;
}

/**
 * Check if summary email should be sent this session
 */
async function shouldSendSummaryEmail() {
  try {
    // Check if we've already sent this session
    const result = await chrome.storage.session.get(SUMMARY_EMAIL_KEY);
    return !result[SUMMARY_EMAIL_KEY];
  } catch (error) {
    console.warn('⚠️ Failed to check summary email status:', error);
    return false;
  }
}

/**
 * Mark summary email as sent for this session
 */
async function markSummaryEmailSent() {
  try {
    await chrome.storage.session.set({ [SUMMARY_EMAIL_KEY]: true });
    console.log('✅ Summary email marked as sent for this session');
  } catch (error) {
    console.warn('⚠️ Failed to mark summary email as sent:', error);
  }
}

/**
 * Retrieve timestamp of the last digest that was successfully sent.
 */
async function getLastDigestSentAt() {
  try {
    const result = await chrome.storage.sync.get(LAST_DIGEST_SENT_KEY);
    return result[LAST_DIGEST_SENT_KEY] || null;
  } catch (error) {
    console.warn('⚠️ Failed to read last digest timestamp:', error);
    return null;
  }
}

/**
 * Persist timestamp of the last successfully sent digest across devices.
 */
async function setLastDigestSentAt(timestampIso) {
  try {
    await chrome.storage.sync.set({ [LAST_DIGEST_SENT_KEY]: timestampIso });
  } catch (error) {
    console.warn('⚠️ Failed to store last digest timestamp:', error);
  }
}

/**
 * Clear the pending digest flag once a digest has been handled.
 */
async function clearDigestPending() {
  try {
    await chrome.storage.local.set({ [DIGEST_PENDING_KEY]: false });
  } catch (error) {
    console.warn('⚠️ Failed to clear digest pending flag:', error);
  }
}

/**
 * Generate a simple hash of email IDs to detect duplicate digests
 */
async function generateDigestHash(emails) {
  if (!emails || emails.length === 0) {
    return null;
  }

  // Sort email IDs for consistent hashing
  const emailIds = emails.map(e => e.id || e.messageId || '').filter(Boolean).sort();
  const hashInput = emailIds.join('|');

  // Simple hash function (for deduplication, not security)
  let hash = 0;
  for (let i = 0; i < hashInput.length; i++) {
    const char = hashInput.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }

  return hash.toString(36);
}

/**
 * Check if a digest with the same content was recently sent
 */
async function isDuplicateDigest(emails) {
  try {
    const currentHash = await generateDigestHash(emails);
    if (!currentHash) {
      return false;
    }

    const result = await chrome.storage.local.get(LAST_DIGEST_HASH_KEY);
    const lastDigest = result[LAST_DIGEST_HASH_KEY];

    if (!lastDigest) {
      return false;
    }

    // Check if hash matches and was sent recently (within dedup window)
    const timeSinceLastDigest = Date.now() - new Date(lastDigest.timestamp).getTime();
    const isDuplicate = lastDigest.hash === currentHash && timeSinceLastDigest < DIGEST_DEDUP_WINDOW_MS;

    if (isDuplicate) {
      console.log(`🚫 [SUMMARY] Duplicate digest detected (hash: ${currentHash}, ${Math.round(timeSinceLastDigest / 1000)}s ago)`);
    }

    return isDuplicate;
  } catch (error) {
    console.warn('⚠️ Failed to check duplicate digest:', error);
    return false;
  }
}

/**
 * Store digest hash to prevent duplicates
 */
async function storeDigestHash(emails) {
  try {
    const hash = await generateDigestHash(emails);
    if (hash) {
      await chrome.storage.local.set({
        [LAST_DIGEST_HASH_KEY]: {
          hash: hash,
          timestamp: new Date().toISOString()
        }
      });
    }
  } catch (error) {
    console.warn('⚠️ Failed to store digest hash:', error);
  }
}

/**
 * Acquire lock for digest generation with atomic compare-and-swap
 * Returns true if lock acquired, false if another process is generating
 */
async function acquireDigestLock() {
  try {
    // Check in-memory flag first (fastest)
    if (isGeneratingDigest) {
      console.log('🔒 [SUMMARY] Digest generation already in progress (in-memory check)');
      return false;
    }

    // Check cooldown period to prevent rapid-fire digest generation
    const timeSinceLastDigest = Date.now() - lastDigestTimestamp;
    if (lastDigestTimestamp > 0 && timeSinceLastDigest < DIGEST_COOLDOWN_MS) {
      console.log(`⏱️ [SUMMARY] Digest cooldown active (${Math.round((DIGEST_COOLDOWN_MS - timeSinceLastDigest) / 1000)}s remaining)`);
      return false;
    }

    // Generate unique lock ID for this attempt
    const lockId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    // Atomic compare-and-swap using storage
    const result = await chrome.storage.local.get([DIGEST_GENERATION_LOCK_KEY, 'mailq_organize_session_start']);
    const existingLock = result[DIGEST_GENERATION_LOCK_KEY];
    const sessionStart = result.mailq_organize_session_start;

    if (existingLock) {
      const lockAge = Date.now() - new Date(existingLock.timestamp).getTime();

      // Check if this is the same session trying to generate twice
      if (existingLock.sessionStart === sessionStart && lockAge < DIGEST_LOCK_TIMEOUT_MS) {
        console.log(`🔒 [SUMMARY] Digest already generated/generating for this session (${sessionStart})`);
        return false;
      }

      // If lock is recent (not stale), reject
      if (lockAge < DIGEST_LOCK_TIMEOUT_MS) {
        console.log(`🔒 [SUMMARY] Digest generation locked by another process (${Math.round(lockAge / 1000)}s ago, ID: ${existingLock.lockId})`);
        return false;
      } else {
        console.log(`⚠️ [SUMMARY] Stale lock detected (${Math.round(lockAge / 1000)}s old), clearing it`);
      }
    }

    // Acquire lock with session tracking
    isGeneratingDigest = true;
    await chrome.storage.local.set({
      [DIGEST_GENERATION_LOCK_KEY]: {
        timestamp: new Date().toISOString(),
        lockId: lockId,
        sessionStart: sessionStart
      }
    });

    console.log(`✅ [SUMMARY] Digest generation lock acquired (ID: ${lockId}, session: ${sessionStart})`);
    return true;
  } catch (error) {
    console.warn('⚠️ Failed to acquire digest lock:', error);
    return false;
  }
}

/**
 * Release digest generation lock
 */
async function releaseDigestLock() {
  try {
    isGeneratingDigest = false;
    await chrome.storage.local.remove(DIGEST_GENERATION_LOCK_KEY);
    console.log('🔓 [SUMMARY] Digest generation lock released');
  } catch (error) {
    console.warn('⚠️ Failed to release digest lock:', error);
  }
}

/**
 * Get session start time
 */
async function getSessionStart() {
  try {
    const result = await chrome.storage.session.get(SESSION_START_KEY);

    if (!result[SESSION_START_KEY]) {
      // First time - set session start
      const now = new Date().toISOString();
      await chrome.storage.session.set({ [SESSION_START_KEY]: now });
      return now;
    }

    return result[SESSION_START_KEY];
  } catch (error) {
    console.warn('⚠️ Failed to get session start:', error);
    return new Date().toISOString();
  }
}

/**
 * Get last summary data from local storage (persists across sessions)
 */
async function getLastSummaryData() {
  try {
    const result = await chrome.storage.local.get(LAST_SUMMARY_DATA_KEY);
    return result[LAST_SUMMARY_DATA_KEY] || null;
  } catch (error) {
    console.warn('⚠️ Failed to get last summary data:', error);
    return null;
  }
}

/**
 * Save current summary data to local storage
 */
async function saveLastSummaryData(data) {
  try {
    await chrome.storage.local.set({
      [LAST_SUMMARY_DATA_KEY]: {
        timestamp: new Date().toISOString(),
        classifications: data
      }
    });
  } catch (error) {
    console.warn('⚠️ Failed to save summary data:', error);
  }
}

/**
 * Get current classification data from logger (filtered by last summary time)
 */
async function getCurrentClassifications(options = {}) {
  try {
    console.log('📧 [SUMMARY] Checking logger availability...');

    if (typeof logger === 'undefined') {
      console.warn('⚠️ [SUMMARY] Logger not available, cannot get classifications');
      console.warn('⚠️ [SUMMARY] typeof logger:', typeof logger);
      return [];
    }

    console.log('📧 [SUMMARY] Logger is available, calling getClassifications()');
    console.log('📧 [SUMMARY] logger.getClassifications type:', typeof logger.getClassifications);

    let startDate = options.startDate || null;

    if (startDate) {
      console.log('📧 [SUMMARY] Using provided start time (likely last digest):', startDate);
    } else {
      const lastDigestSentAt = await getLastDigestSentAt();
      if (lastDigestSentAt) {
        startDate = lastDigestSentAt;
        console.log('📧 [SUMMARY] Using last digest timestamp as cutoff:', startDate);
      } else {
        const sessionStart = await chrome.storage.local.get('mailq_organize_session_start');
        if (sessionStart.mailq_organize_session_start) {
          startDate = sessionStart.mailq_organize_session_start;
          console.log('📧 [SUMMARY] Using session start time:', startDate);
        } else {
          console.log('📧 [SUMMARY] No digest or session start timestamp found; using full history');
        }
      }
    }

    // Get classifications from this organize session only
    const filters = {};
    if (startDate) {
      filters.startDate = startDate;
    }

    const classifications = await logger.getClassifications(filters);

    console.log('📧 [SUMMARY] getClassifications() returned:', classifications);
    console.log('📧 [SUMMARY] Classifications count since cutoff:', classifications ? classifications.length : 0);

    if (classifications && classifications.length > 0) {
      console.log('📧 [SUMMARY] First classification keys:', Object.keys(classifications[0]));
    }

    // Filter out MailQ's own summary emails to prevent self-reference
    const filtered = (classifications || []).filter(email => {
      // Skip if subject starts with "Your Inbox --" (our digest emails)
      if (email.subject && (email.subject.startsWith('Your Inbox --') || email.subject.includes('MailQ Digest'))) {
        console.log('📧 [SUMMARY] Filtering out MailQ Digest email:', email.subject);
        return false;
      }
      return true;
    });

    console.log('📧 [SUMMARY] After filtering MailQ emails:', filtered.length);

    // Drop emails that are too old to matter to the current session.
    const cutoffMs = Date.now() - (MAX_EMAIL_AGE_DAYS * MS_IN_DAY);
    const recencyFiltered = filtered.filter(entry => {
      const rawTs = entry.emailTimestamp;
      if (!rawTs) {
        return true;
      }

      let tsMs = null;
      if (typeof rawTs === 'number') {
        tsMs = rawTs;
      } else if (typeof rawTs === 'string') {
        const numeric = Number(rawTs);
        if (!Number.isNaN(numeric) && numeric > 1e9) {
          tsMs = numeric;
        } else {
          const parsed = Date.parse(rawTs);
          if (!Number.isNaN(parsed)) {
            tsMs = parsed;
          }
        }
      }

      if (tsMs === null) {
        return true;
      }

      return tsMs >= cutoffMs;
    });

    if (recencyFiltered.length !== filtered.length) {
      console.log(`📧 [SUMMARY] Removed ${filtered.length - recencyFiltered.length} stale emails older than ${MAX_EMAIL_AGE_DAYS} days`);
    }

    // Deduplicate by messageId - keep only the most recent entry per email
    // This handles cases where the same email was logged multiple times
    // (e.g., cached emails re-logged with fresh timestamps)
    const dedupeMap = new Map();
    for (const entry of recencyFiltered) {
      const messageId = entry.messageId;
      if (!messageId) {
        // No messageId, keep it (shouldn't happen but defensive)
        continue;
      }

      const existing = dedupeMap.get(messageId);
      if (!existing) {
        dedupeMap.set(messageId, entry);
      } else {
        // Keep the more recent one (by logger timestamp, not email timestamp)
        if (entry.timestamp > existing.timestamp) {
          dedupeMap.set(messageId, entry);
        }
      }
    }

    const deduplicated = Array.from(dedupeMap.values());
    if (deduplicated.length !== recencyFiltered.length) {
      console.log(`📧 [SUMMARY] Deduplicated: ${recencyFiltered.length} → ${deduplicated.length} unique emails`);
    }

    return deduplicated;
  } catch (error) {
    console.error('❌ [SUMMARY] Failed to get current classifications:', error);
    console.error('❌ [SUMMARY] Error stack:', error.stack);
    return [];
  }
}

/**
 * Generate summary email HTML using backend API
 */
async function generateSummaryHTML(currentData, previousData, sessionStart) {
  try {
    const apiUrl = CONFIG.MAILQ_API_URL;

    const response = await fetch(`${apiUrl}/api/summary`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        current_data: currentData,
        previous_data: previousData,
        session_start: sessionStart
      })
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();
    return result;  // { html, subject }

  } catch (error) {
    console.error('❌ Failed to generate summary HTML:', error);
    throw error;
  }
}

/**
 * Unicode-safe base64 encoding for Gmail API
 * Handles emojis and other Unicode characters
 */
function utf8ToBase64(str) {
  // Convert string to UTF-8 bytes
  const encoder = new TextEncoder();
  const bytes = encoder.encode(str);

  // Convert bytes to base64 string
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }

  // Base64 encode and make URL-safe for Gmail API
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/**
 * Encode subject line using RFC 2047 for non-ASCII characters
 * Format: =?UTF-8?B?base64?=
 */
function encodeSubject(subject) {
  // Check if subject contains non-ASCII characters
  if (/[^\x00-\x7F]/.test(subject)) {
    // Encode as UTF-8 base64
    const encoder = new TextEncoder();
    const bytes = encoder.encode(subject);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const encoded = btoa(binary);
    return `=?UTF-8?B?${encoded}?=`;
  }
  return subject;
}

/**
 * Send email via Gmail API
 */
async function sendEmail(subject, htmlBody) {
  try {
    // Get Gmail access token with automatic refresh
    const token = await getAuthToken();

    // Get user's email address
    const profileResponse = await fetch('https://gmail.googleapis.com/gmail/v1/users/me/profile', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const profile = await profileResponse.json();
    const userEmail = profile.emailAddress;

    // Build RFC 2822 compliant email with proper MIME headers
    // Add custom header to identify MailQ digest emails
    const email =
      `From: ${userEmail}\r\n` +
      `To: ${userEmail}\r\n` +
      `Subject: ${encodeSubject(subject)}\r\n` +
      `X-MailQ-Digest: true\r\n` +
      `MIME-Version: 1.0\r\n` +
      `Content-Type: text/html; charset=utf-8\r\n\r\n` +
      htmlBody;

    // Send email using Gmail API with Unicode-safe encoding
    const response = await fetch('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        raw: utf8ToBase64(email)
      })
    });

    if (!response.ok) {
      // Get detailed error message from Gmail API
      const errorBody = await response.text();
      console.error('❌ Gmail API Error Response:', errorBody);
      throw new Error(`Gmail API error: ${response.status} ${response.statusText} - ${errorBody}`);
    }

    const message = await response.json();
    console.log('✅ Summary email sent:', message.id);
    return message;

  } catch (error) {
    console.error('❌ Failed to send email:', error);
    throw error;
  }
}

/**
 * Main function: Generate and send summary email
 */
async function generateAndSendSummaryEmail(options = {}) {
  const startTime = Date.now();
  const metrics = {
    success: false,
    step: null,
    classificationsCount: 0,
    apiCallDuration: 0,
    emailSendDuration: 0,
    totalDuration: 0,
    error: null,
    trigger: options.trigger || 'unspecified'
  };

  const startDateOverride = options.startDateOverride || null;
  const forceSend = Boolean(options.force);
  const lastDigestSentAt = await getLastDigestSentAt();
  const classificationStartDate = startDateOverride || lastDigestSentAt || null;
  metrics.lastDigestSentAt = lastDigestSentAt;
  metrics.startDate = classificationStartDate;

  // Acquire lock to prevent concurrent digest generation
  const lockAcquired = await acquireDigestLock();
  if (!lockAcquired && !forceSend) {
    console.log('⏭️ [SUMMARY] Skipping digest generation - already in progress');
    metrics.step = 'locked';
    await storeSummaryMetrics(metrics);
    return { success: false, error: 'Digest generation already in progress' };
  }

  try {
    console.log('📧 [SUMMARY] Starting summary email generation...');
    console.log('📧 [SUMMARY] Step 1: Fetching current classifications from logger');
    if (classificationStartDate) {
      console.log(`📧 [SUMMARY] Pulling classifications since ${classificationStartDate}`);
    } else {
      console.log('📧 [SUMMARY] No last digest timestamp found, using session fallback');
    }

    // Get current classifications
    const currentData = await getCurrentClassifications({ startDate: classificationStartDate });
    console.log(`📧 [SUMMARY] Classifications retrieved: ${currentData ? currentData.length : 0} items`);
    console.log(`📧 [SUMMARY] Sample classification:`, currentData && currentData.length > 0 ? currentData[0] : 'none');

    if (!currentData || currentData.length === 0) {
      console.log('ℹ️ [SUMMARY] No classifications to summarize');
      metrics.step = 'no_data';
      await storeSummaryMetrics(metrics);
      if (!forceSend) {
        await chrome.storage.local.remove('mailq_organize_session_start');
        await clearDigestPending();
        return { success: false, error: 'No classifications to summarize' };
      }
    }

    metrics.classificationsCount = currentData.length;
    console.log(`📊 [SUMMARY] Found ${currentData.length} classifications to summarize`);

    console.log('📧 [SUMMARY] Step 2: Checking for duplicate digest');
    // Check if we recently sent a digest with the same emails
    const isDuplicate = await isDuplicateDigest(currentData);
    if (isDuplicate && !forceSend) {
      console.log('ℹ️ [SUMMARY] Duplicate digest detected, skipping send');
      metrics.step = 'duplicate_skipped';
      await storeSummaryMetrics(metrics);
      await clearDigestPending();
      return { success: false, error: 'Duplicate digest within deduplication window' };
    }

    console.log('📧 [SUMMARY] Step 3: Getting last summary data for delta');
    // Get last summary data (for delta)
    const lastSummary = await getLastSummaryData();
    const previousData = lastSummary?.classifications || null;
    console.log(`📧 [SUMMARY] Previous data: ${previousData ? previousData.length : 0} items`);

    console.log('📧 [SUMMARY] Step 4: Getting session start time');
    // Get session start time
    const sessionStart = await getSessionStart();
    console.log(`📧 [SUMMARY] Session started at: ${sessionStart}`);

    console.log('📧 [SUMMARY] Step 5: Checking digest type');
    // Check if context digest is enabled
    const useContextDigest = await isContextDigestEnabled();
    console.log(`📧 [SUMMARY] Using ${useContextDigest ? 'Context Digest' : 'Classic Digest'}`);

    // Generate summary HTML
    const apiStartTime = Date.now();
    let html, subject, result;

    if (useContextDigest) {
      console.log(`📧 [SUMMARY] API URL: ${CONFIG.MAILQ_API_URL}/api/context-digest`);
      console.log(`📧 [SUMMARY] Request payload:`, {
        current_data_count: currentData.length
      });
      result = await generateContextDigestHTML(currentData);
      html = result.html;
      subject = result.subject;
    } else {
      console.log(`📧 [SUMMARY] API URL: ${CONFIG.MAILQ_API_URL}/api/summary`);
      console.log(`📧 [SUMMARY] Request payload:`, {
        current_data_count: currentData.length,
        previous_data_count: previousData ? previousData.length : 0,
        session_start: sessionStart
      });
      result = await generateSummaryHTML(
        currentData,
        previousData,
        sessionStart
      );
      html = result.html;
      subject = result.subject;
    }

    subject = formatDigestSubject(subject, result?.metadata);

    metrics.apiCallDuration = Date.now() - apiStartTime;

    console.log(`📧 [SUMMARY] API response received in ${metrics.apiCallDuration}ms`);
    console.log(`📧 [SUMMARY] Subject: ${subject}`);
    console.log(`📧 [SUMMARY] HTML length: ${html ? html.length : 0} characters`);
    console.log(`📧 [SUMMARY] HTML preview (first 500 chars):`, html ? html.substring(0, 500) : 'none');

    console.log('📧 [SUMMARY] Step 6: Sending email via Gmail API');
    // Send email
    const emailStartTime = Date.now();
    const emailResult = await sendEmail(subject, html);
    metrics.emailSendDuration = Date.now() - emailStartTime;

    console.log(`📧 [SUMMARY] Email sent in ${metrics.emailSendDuration}ms`);
    console.log(`📧 [SUMMARY] Email ID: ${emailResult.id}`);

    // Label the digest email immediately to exclude it from future classification
    console.log('🏷️ [SUMMARY] Labeling digest email to prevent classification...');
    try {
      const token = await getAuthToken();
      console.log('🔑 [SUMMARY] Got auth token');
      const digestLabelId = await getOrCreateLabel(token, 'MailQ/Digest');
      console.log(`🏷️ [SUMMARY] Got label ID: ${digestLabelId}`);

      // Apply MailQ/Digest label and archive (maintain inbox zero)
      // Keep UNREAD so user knows to read the digest
      const labelResponse = await fetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${emailResult.id}/modify`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          addLabelIds: [digestLabelId],
          removeLabelIds: ['INBOX']  // Only remove INBOX, keep UNREAD
        })
      });

      if (!labelResponse.ok) {
        const errorText = await labelResponse.text();
        throw new Error(`Gmail API error ${labelResponse.status}: ${errorText}`);
      }

      console.log('✅ [SUMMARY] Digest email labeled with MailQ/Digest and archived');
    } catch (labelError) {
      console.error('❌ [SUMMARY] Failed to label digest email:', labelError);
      console.error('   Email ID:', emailResult.id);
      console.error('   Error details:', labelError.message || labelError);
    }

    // NOTE: Don't reload here - let background.js handle the single reload at the end
    // This prevents interrupting any pending operations (labeling, etc.)
    console.log('✅ [SUMMARY] Digest sent and labeled (reload will happen after all operations complete)');

    console.log('📧 [SUMMARY] Step 7: Saving data and digest hash for deduplication');
    // Store digest hash to prevent duplicates
    await storeDigestHash(currentData);
    await saveLastSummaryData(currentData);

    const sentAt = new Date().toISOString();
    await setLastDigestSentAt(sentAt);
    await clearDigestPending();

    metrics.success = true;
    metrics.step = 'completed';
    metrics.totalDuration = Date.now() - startTime;
    metrics.sentAt = sentAt;

    // Update cooldown timestamp
    lastDigestTimestamp = Date.now();

    console.log(`✅ [SUMMARY] Summary email sent successfully! Total time: ${metrics.totalDuration}ms`);

    // Clear session start time (ready for next organize session)
    await chrome.storage.local.remove('mailq_organize_session_start');
    console.log('🧹 Organize session timestamp cleared');

    // Store metrics
    await storeSummaryMetrics(metrics);

    // Show notification to user (non-blocking)
    try {
      chrome.notifications.create({
        type: 'basic',
        iconUrl: chrome.runtime.getURL('icons/icon128.png'),
        title: 'MailQ Summary Sent',
        message: 'Your inbox summary has been sent to your email!',
        priority: 1
      }, (notificationId) => {
        if (chrome.runtime.lastError) {
          console.warn('⚠️ Notification failed (non-critical):', chrome.runtime.lastError);
        }
      });
    } catch (notifError) {
      console.warn('⚠️ Could not show notification (non-critical):', notifError);
    }

    // Return digest data for tracking (only if using context digest)
    if (useContextDigest) {
      console.log('📊 [SUMMARY] Preparing digest data for tracking...');

      // Extract session_id from context digest result
      const sessionId = result?.metadata?.session_id;

      if (sessionId) {
        console.log(`📊 [SUMMARY] Session ID: ${sessionId}`);

        try {
          // Fetch threads from tracking API
          console.log(`📊 [SUMMARY] Fetching threads from tracking API...`);
          const trackingResponse = await fetch(`${CONFIG.MAILQ_API_URL}/api/tracking/session/${sessionId}`);

          if (trackingResponse.ok) {
            const trackingData = await trackingResponse.json();
            const threads = trackingData.threads || [];

            console.log(`📊 [SUMMARY] Retrieved ${threads.length} threads for tracking`);

            return {
              success: true,
              session_id: sessionId,
              threads: threads,
              metadata: result.metadata
            };
          } else {
            console.warn(`⚠️ [SUMMARY] Failed to fetch tracking data: ${trackingResponse.status}`);
          }
        } catch (trackingError) {
          console.warn('⚠️ [SUMMARY] Error fetching tracking data (non-critical):', trackingError);
        }
      }

      // Fallback: return minimal data
      return {
        success: true,
        session_id: sessionId,
        threads: [],
        metadata: result?.metadata
      };
    }

    return { success: true };

  } catch (error) {
    metrics.step = 'error';
    metrics.error = error.message;
    metrics.totalDuration = Date.now() - startTime;

    console.error('❌ [SUMMARY] Failed to generate summary email:', error);
    console.error('❌ [SUMMARY] Error stack:', error.stack);
    console.error('❌ [SUMMARY] Metrics:', metrics);

    // Store error and metrics
    await storeSummaryError(error);
    await storeSummaryMetrics(metrics);

    return { success: false, error: error.message };
  } finally {
    // Always release lock
    if (lockAcquired) {
      await releaseDigestLock();
    }
  }
}

/**
 * Reset session flag (for testing)
 */
async function resetSummaryEmailFlag() {
  try {
    await chrome.storage.session.remove(SUMMARY_EMAIL_KEY);
    console.log('🔄 Summary email flag reset');
  } catch (error) {
    console.warn('⚠️ Failed to reset summary flag:', error);
  }
}

/**
 * Store summary generation metrics for analysis
 */
async function storeSummaryMetrics(metrics) {
  try {
    const existing = await chrome.storage.local.get(SUMMARY_METRICS_KEY);
    const allMetrics = existing[SUMMARY_METRICS_KEY] || [];

    // Add new metric with timestamp
    allMetrics.push({
      ...metrics,
      timestamp: new Date().toISOString()
    });

    // Keep only last 50 metrics
    const recentMetrics = allMetrics.slice(-50);

    await chrome.storage.local.set({ [SUMMARY_METRICS_KEY]: recentMetrics });
    console.log('📊 Summary metrics stored:', metrics);
  } catch (error) {
    console.warn('⚠️ Failed to store metrics:', error);
  }
}

/**
 * Store summary generation error for analysis
 */
async function storeSummaryError(error) {
  try {
    const existing = await chrome.storage.local.get(SUMMARY_ERRORS_KEY);
    const allErrors = existing[SUMMARY_ERRORS_KEY] || [];

    // Add new error with timestamp
    allErrors.push({
      message: error.message,
      stack: error.stack,
      timestamp: new Date().toISOString()
    });

    // Keep only last 20 errors
    const recentErrors = allErrors.slice(-20);

    await chrome.storage.local.set({ [SUMMARY_ERRORS_KEY]: recentErrors });
    console.log('❌ Summary error stored:', error.message);
  } catch (storageError) {
    console.warn('⚠️ Failed to store error:', storageError);
  }
}

/**
 * Get summary metrics (for debugging)
 */
async function getSummaryMetrics() {
  try {
    const result = await chrome.storage.local.get([SUMMARY_METRICS_KEY, SUMMARY_ERRORS_KEY]);
    return {
      metrics: result[SUMMARY_METRICS_KEY] || [],
      errors: result[SUMMARY_ERRORS_KEY] || []
    };
  } catch (error) {
    console.warn('⚠️ Failed to get metrics:', error);
    return { metrics: [], errors: [] };
  }
}

/**
 * Console helper to view summary metrics (call from browser console)
 * Usage: showSummaryMetrics()
 */
async function showSummaryMetrics() {
  const { metrics, errors } = await getSummaryMetrics();

  console.log('\n📊 ===== SUMMARY EMAIL METRICS =====');
  console.log(`Total attempts: ${metrics.length}`);
  console.log(`Total errors: ${errors.length}`);

  if (metrics.length > 0) {
    console.log('\n📈 Recent Attempts:');
    metrics.slice(-5).forEach((m, i) => {
      console.log(`\n${i + 1}. ${m.timestamp}`);
      console.log(`   Step: ${m.step}`);
      console.log(`   Success: ${m.success}`);
      console.log(`   Classifications: ${m.classificationsCount}`);
      if (m.success) {
        console.log(`   API call: ${m.apiCallDuration}ms`);
        console.log(`   Email send: ${m.emailSendDuration}ms`);
        console.log(`   Total: ${m.totalDuration}ms`);
      }
      if (m.error) {
        console.log(`   Error: ${m.error}`);
      }
    });
  }

  if (errors.length > 0) {
    console.log('\n❌ Recent Errors:');
    errors.slice(-3).forEach((e, i) => {
      console.log(`\n${i + 1}. ${e.timestamp}`);
      console.log(`   ${e.message}`);
      if (e.stack) {
        console.log(`   Stack: ${e.stack.substring(0, 200)}...`);
      }
    });
  }

  console.log('\n===================================\n');
  return { metrics, errors };
}

// Make helper globally available
if (typeof window !== 'undefined') {
  window.showSummaryMetrics = showSummaryMetrics;
}

// Export functions
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    shouldSendSummaryEmail,
    generateAndSendSummaryEmail,
    resetSummaryEmailFlag,
    storeSummaryMetrics,
    storeSummaryError,
    getSummaryMetrics,
    showSummaryMetrics,
    getLastDigestSentAt,
    setLastDigestSentAt,
    clearDigestPending
  };
}
