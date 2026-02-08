/**
 * Reclaim Return Watch Extension Configuration
 *
 * SINGLE SOURCE OF TRUTH for all extension constants.
 * Import CONFIG instead of defining local constants.
 */

const VERSION = '1.0.0';

const CONFIG = {
  // --- API Endpoints (SINGLE SOURCE OF TRUTH) ---
  API_BASE_URL: 'https://reclaim-api-488078904670.us-central1.run.app',
  GMAIL_API_BASE: 'https://www.googleapis.com/gmail/v1/users/me',

  VERSION: VERSION,

  // --- Scan Settings ---
  MAX_EMAILS_PER_SCAN: 50,

  // --- Timing ---
  DIGEST_REFRESH_DEBOUNCE_MS: 5000,
  SIDEBAR_REFRESH_INTERVAL_MS: 60000,
  DATE_REFRESH_INTERVAL_MS: 60000,
  TOAST_DURATION_MS: 3000,
  TOAST_FADEOUT_MS: 300,

  // --- Thresholds ---
  EXPIRING_SOON_DAYS: 7,
  CRITICAL_DAYS: 3,
  THREAD_MATCH_WINDOW_DAYS: 30,

  // --- Scan Windows (days) ---
  SCAN_WINDOW_FULL: 60,
  SCAN_WINDOW_FOCUS: 7,
  SCAN_WINDOW_PERIODIC: 3,
  SCAN_WINDOW_MANUAL: 30,

  // --- Refresh ---
  FOCUS_THRESHOLD_MS: 10 * 60 * 1000,
  STALE_THRESHOLD_MS: 6 * 60 * 60 * 1000,
  PERIODIC_INTERVAL_MS: 45 * 60 * 1000,

  // --- Rate Limiting ---
  MESSAGE_RATE_LIMIT_MAX: 100,
  MESSAGE_RATE_LIMIT_WINDOW_MS: 1000,

  // --- Gmail API ---
  API_REQUEST_DELAY_MS: 100,
  MAX_MESSAGES_PER_QUERY: 100,

  // --- Token ---
  TOKEN_VALIDATION_INTERVAL_MS: 5 * 60 * 1000,
  TOKEN_MIN_LIFETIME_SECONDS: 300,

  // --- Enrichment ---
  MAX_LLM_CONTEXT_CHARS: 1000,

  // --- Batch Processing ---
  BATCH_CHUNK_SIZE: 10,

  // --- Storage Keys ---
  KEYS: {
    USER_ID: 'reclaim_user_id',
    RETURNS: 'reclaim_returns',
    SETTINGS: 'reclaim_settings',
    LABEL_CACHE: 'shopq_label_cache',
    ENCRYPTION_KEY: 'encryption_key_material',
  },

  VERBOSE_LOGGING: false,
};
