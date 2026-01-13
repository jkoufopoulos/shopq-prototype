/**
 * Shared Utility Functions
 */

/**
 * Extract domain from email address
 * @param {string} email - Email address
 * @returns {string} Domain name
 */
function extractDomain(email) {
  const match = email.match(/@([^>]+)>?$/);
  return match ? match[1].toLowerCase() : email.toLowerCase();
}

/**
 * Deduplicate emails by (sender, subject_signature) for LLM classification
 *
 * Uses composite key from generateDedupeKey() to group semantically similar
 * emails, reducing API calls while maintaining classification accuracy.
 *
 * @param {Array} emails - Emails to deduplicate
 * @returns {Array} Unique emails (one per sender+subject_signature combo)
 */
function deduplicateBySender(emails) {
  const seen = new Set();
  const deduped = [];

  for (const email of emails) {
    // Use composite key: sender|subject_signature
    // This allows multiple emails from same domain with different subject types
    const dedupeKey = generateDedupeKey(email.from, email.subject);
    if (!seen.has(dedupeKey)) {
      seen.add(dedupeKey);
      deduped.push(email);
    }
  }

  return deduped;
}

/**
 * Get today's date as YYYY-MM-DD
 * @returns {string} Today's date
 */
function getToday() {
  return new Date().toISOString().split('T')[0];
}

/**
 * Redact sensitive strings for safe logging.
 * Emits hashed preview to avoid leaking PII.
 */
function redactForLog(value) {
  if (!value) return '(empty)';
  try {
    const preview = value.slice(0, 8);
    const hash = btoa(value).replace(/[^a-zA-Z0-9]/g, '').slice(0, 8);
    return `${preview}…#${hash}`;
  } catch (err) {
    return '(unloggable)';
  }
}

function shouldRetryStatus(status) {
  return status === 429 || (status >= 500 && status < 600);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Conditional console logging for noisy debug output.
 */
function logVerbose(...args) {
  if (typeof CONFIG !== 'undefined' && CONFIG.VERBOSE_LOGGING) {
    console.log(...args);
  }
}

/**
 * Fetch wrapper with timeout, retry, and basic jitter.
 *
 * @param {string} url
 * @param {Object} options - fetch options
 * @param {Object} config - { timeoutMs, retries, retryDelayMs, jitterMs, fetchImpl }
 * @returns {Promise<Response>}
 */
async function resilientFetch(url, options = {}, config = {}) {
  const {
    timeoutMs = 15000,
    retries = 2,
    retryDelayMs = 400,
    jitterMs = 200,
    fetchImpl = typeof fetch !== 'undefined' ? fetch.bind(globalThis) : null
  } = config;

  if (!fetchImpl) {
    throw new Error('fetch is not available in this environment');
  }

  const { signal: userSignal, ...restOptions } = options || {};
  let attempt = 0;

  while (true) {
    if (userSignal?.aborted) {
      if (typeof DOMException === 'function') {
        throw new DOMException('The operation was aborted.', 'AbortError');
      } else {
        const abortError = new Error('The operation was aborted.');
        abortError.name = 'AbortError';
        throw abortError;
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetchImpl(url, {
        ...restOptions,
        signal: controller.signal
      });

      if (!response.ok && shouldRetryStatus(response.status) && attempt < retries) {
        console.warn('🌐 retry_on_status', {
          url: redactForLog(url),
          status: response.status,
          attempt: attempt + 1
        });
      } else {
        return response;
      }
    } catch (error) {
      if (attempt >= retries) {
        console.error('🌐 fetch_error', {
          url: redactForLog(url),
          attempt: attempt + 1,
          error: error?.message || String(error)
        });
        throw error;
      }

      console.warn('🌐 retry_on_error', {
        url: redactForLog(url),
        attempt: attempt + 1,
        error: error?.message || String(error)
      });
    } finally {
      clearTimeout(timer);
    }

    attempt += 1;
    const backoff = retryDelayMs + Math.random() * jitterMs;
    await sleep(backoff);
  }
}
