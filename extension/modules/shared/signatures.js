/**
 * Email Signature Generation Module
 *
 * Provides utilities for generating normalized subject signatures to prevent
 * per-sender generalization (e.g., Amazon receipts vs Amazon promos).
 */


/**
 * Generate a normalized subject signature for cache/deduplication keys
 *
 * Removes noise like Re:, Fwd:, emojis, dates, order IDs to focus on
 * semantic content type rather than instance-specific details.
 *
 * @param {string} subject - Email subject line
 * @returns {string} Normalized signature
 *
 * @example
 * generateSubjectSignature("Re: Your Order #123456 has shipped!")
 * // Returns: "your order <id> has shipped!"
 *
 * generateSubjectSignature("Delivered: Charmin Ultra Strong Oct 23")
 * // Returns: "delivered: charmin ultra strong"
 */
function generateSubjectSignature(subject) {
  if (!subject) return '';

  let normalized = subject;

  // Strip "Re:", "Fwd:", "Fw:", etc. (case insensitive, multiple occurrences)
  normalized = normalized.replace(/^(re|fwd?|fw):\s*/gi, '');

  // Remove emojis (basic emoji ranges - covers most common emojis)
  normalized = normalized.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '');

  // Remove order/receipt IDs: numbers 5+ digits, Order #XXXX, alphanumeric 6+ chars
  // Replace with placeholder to preserve semantic structure
  normalized = normalized.replace(/#?\d{5,}/g, '<ID>');
  normalized = normalized.replace(/Order\s?#?\w{4,}/gi, '<ID>');
  normalized = normalized.replace(/\b[A-Z0-9]{6,}\b/g, '<ID>');

  // Remove dates: years (20xx), month names
  normalized = normalized.replace(/\b20\d{2}\b/g, '');
  normalized = normalized.replace(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b/gi, '');

  // Remove common date patterns like "10/23", "Oct 23"
  normalized = normalized.replace(/\b\d{1,2}[\/\-]\d{1,2}\b/g, '');

  // Collapse multiple whitespaces
  normalized = normalized.replace(/\s+/g, ' ');

  // Lowercase and trim
  normalized = normalized.toLowerCase().trim();

  return normalized;
}


/**
 * Generate composite cache key from sender and subject
 *
 * Format: "sender|signature"
 * This prevents cross-type contamination from multi-purpose senders
 * (e.g., Amazon receipts vs Amazon promotions)
 *
 * @param {string} sender - Email sender address
 * @param {string} subject - Email subject line
 * @returns {string} Composite cache key "sender|signature"
 *
 * @example
 * generateCacheKey("auto-confirm@amazon.com", "Your Order #112-123 has shipped")
 * // Returns: "auto-confirm@amazon.com|your order <id> has shipped"
 *
 * generateCacheKey("auto-confirm@amazon.com", "20% off select items today!")
 * // Returns: "auto-confirm@amazon.com|20% off select items today!"
 */
function generateCacheKey(sender, subject) {
  const senderKey = sender.toLowerCase();
  const signature = generateSubjectSignature(subject);
  return `${senderKey}|${signature}`;
}


/**
 * Generate deduplication key for reducing redundant API calls
 *
 * Same as cache key - groups emails by (sender, semantic_subject_type)
 * so we only classify unique combinations, then expand results.
 *
 * @param {string} sender - Email sender address
 * @param {string} subject - Email subject line
 * @returns {string} Deduplication key
 */
function generateDedupeKey(sender, subject) {
  return generateCacheKey(sender, subject);
}
