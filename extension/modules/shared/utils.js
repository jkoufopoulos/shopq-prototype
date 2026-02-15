/**
 * Shared Utility Functions for Reclaim Return Watch
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
 * Get today's date as YYYY-MM-DD
 * @returns {string} Today's date
 */
function getToday() {
  return new Date().toISOString().split('T')[0];
}

/**
 * Redact sensitive strings for safe logging.
 */
function redactForLog(value) {
  if (!value) return '(empty)';
  try {
    const preview = value.slice(0, 8);
    return `${preview}…`;
  } catch {
    return '(unloggable)';
  }
}

/**
 * Sleep for specified milliseconds
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Conditional console logging for verbose debug output
 */
function logVerbose(...args) {
  if (typeof CONFIG !== 'undefined' && CONFIG.VERBOSE_LOGGING) {
    console.log(...args);
  }
}
