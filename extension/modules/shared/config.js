/**
 * Reclaim Return Watch Extension Configuration
 */

const VERSION = '1.0.0';

const CONFIG = {
  // API Settings
  // Development: localhost, Production: Cloud Run
  SHOPQ_API_URL: 'https://shopq-api-488078904670.us-central1.run.app',
  API_BASE_URL: 'https://shopq-api-488078904670.us-central1.run.app',

  VERSION: VERSION,

  // Gmail API
  GMAIL_API_BASE: 'https://www.googleapis.com/gmail/v1/users/me',

  // Scan settings
  MAX_EMAILS_PER_SCAN: 50,

  // Storage keys
  KEYS: {
    USER_ID: 'reclaim_user_id',
    RETURNS: 'reclaim_returns',
    SETTINGS: 'reclaim_settings',
  },

  // Logging
  VERBOSE_LOGGING: false,
};
