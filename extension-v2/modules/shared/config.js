/**
 * Reclaim v2 Configuration
 * Local-first extension — no API URLs, no Gmail settings.
 *
 * Loaded via importScripts in the service worker.
 */

const CONFIG = {
  // Deadline urgency thresholds
  EXPIRING_SOON_DAYS: 7,
  CRITICAL_DAYS: 3,

  // Default return policy (for unknown merchants)
  DEFAULT_RETURN_DAYS: 30,
  DEFAULT_ANCHOR: 'delivery',

  // Notification settings
  NOTIFICATION_7DAY: true,
  NOTIFICATION_3DAY: true,

  // Deadline check alarm interval (minutes) — twice daily
  DEADLINE_CHECK_INTERVAL_MINUTES: 720,
};
