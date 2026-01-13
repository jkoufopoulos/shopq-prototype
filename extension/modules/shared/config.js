/**
 * ShopQ Extension Configuration
 * Centralized constants and settings
 */

const VERSION = '1.0.13';

const CONFIG = {
  // 🚀 PRODUCTION: Cloud Run backend
  // TODO: Update URL after deploying shopq-api to Cloud Run
  SHOPQ_API_URL: 'http://localhost:8000',  // Local dev until shopq-api deployed
  API_BASE_URL: 'http://localhost:8000',   // Local dev until shopq-api deployed
  // PRODUCTION (after deployment): 'https://shopq-api-XXXXX.us-central1.run.app'

  VERSION: '1.0.13',

  // Gmail API settings
  GMAIL_API_BASE: 'https://www.googleapis.com/gmail/v1/users/me',

  // Classification settings
  MIN_EMAILS_PER_BATCH: 25,  // Minimum emails to scan per click
  MAX_EMAILS_PER_BATCH: 50,  // Maximum emails to scan per click
  BATCH_SIZE: 5,             // Emails per LLM API call (small to avoid Cloud Run timeouts)

  // Cost tracking
  DAILY_SPEND_CAP_USD: 1.00,  // Daily budget cap - stops classification if exceeded
  TIER_COSTS: {
    T0: 0.0,
    T1: 0.0,
    T2_LITE: 0.0001,
    T3: 0.001
  },

  // Cache settings
  CACHE_EXPIRY_MS: 24 * 60 * 60 * 1000,
  CACHE_MAX_ENTRIES: 10000,

  // Tuning mode - synced from backend feature_gates.py 'test_mode'
  // This is a fallback value - actual value fetched from /api/test/mode on startup
  // To change: edit shopq/feature_gates.py and redeploy backend
  TUNING_MODE: true,  // SYNCED FROM BACKEND - fallback only

  // Storage keys
  KEYS: {
    SETTINGS: 'shopq_settings',
    CLASSIFICATIONS: 'shopq_classifications',
    CACHE: 'shopq_cache',
    STATS: 'shopq_stats',
    USER_PREFS: 'shopq_prefs',
    SPEND_TRACKER: 'shopq_spend_tracker'
  },

  // Logging controls
  VERBOSE_LOGGING: false,

  // Background behaviors
  ENABLE_PASSIVE_DIGEST_TRIGGERS: false,
  ENABLE_AUTO_ORGANIZE: true,  // Continuous organization every 5 minutes

  // Default settings
  DEFAULT_SETTINGS: {
    autoClassify: false,
    showNotifications: true,
    maxEmailsPerBatch: 50  // Limit to 50 emails per batch for testing
  },

  // API endpoints
  ENDPOINTS: {
    CLASSIFY: '/api/organize',  // ✅ Changed from '/classify' to '/api/organize'
    ORGANIZE: '/api/organize',
    HEALTH: '/health',
    FEEDBACK: '/api/feedback',
    RULES: '/api/rules',
    DIGEST: '/api/context-digest',
  },
};
