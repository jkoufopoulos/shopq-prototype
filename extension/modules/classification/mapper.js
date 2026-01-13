/**
 * Map API classification to Gmail label names
 *
 * Uses client_label from API (single source of truth computed by backend)
 * See: docs/TAXONOMY.md for client_label definitions
 * See: shopq/storage/classification.py compute_client_label() for mapping logic
 */

// =============================================================================
// CLIENT LABEL → GMAIL LABEL MAPPING
// =============================================================================
// These are the 4 UI-facing categories defined in TAXONOMY.md
// The backend computes client_label from type + attention (action_required/none)
// NOTE: Use hyphens to match backend gmail_labels format and avoid conflicts

const CLIENT_LABEL_TO_GMAIL = {
  'receipts': 'ShopQ-Receipts',
  'action-required': 'ShopQ-Action-Required',
  'messages': 'ShopQ-Messages',
  'everything-else': 'ShopQ-Everything-Else'
};

// =============================================================================
// MAIN MAPPER FUNCTION
// =============================================================================

/**
 * Map API classification result to Gmail labels.
 *
 * Combines:
 * 1. Backend's gmail_labels (type + domain + attention labels from API)
 * 2. Client label (one of the 4 UI categories)
 *
 * @param {Object} classification - Classification result from API
 * @param {Object} emailMeta - Optional email metadata (unused, kept for API compat)
 * @returns {string[]} Array of Gmail label names
 */
function mapToLabels(classification, emailMeta = null) {
  // Defensive check: handle undefined/null classification
  if (!classification) {
    console.warn('⚠️ mapToLabels called with undefined classification');
    return ['ShopQ-Everything-Else'];
  }

  const labels = [];

  // Use client_label ONLY (one of the 4 UI categories)
  // We intentionally ignore backend's gmail_labels (type/domain labels) to keep Gmail UI clean
  if (classification.client_label && CLIENT_LABEL_TO_GMAIL[classification.client_label]) {
    labels.push(CLIENT_LABEL_TO_GMAIL[classification.client_label]);
  } else {
    // Fallback: compute client_label from type + attention
    console.warn('⚠️ [MAPPER] client_label not found, computing from type/attention', {
      type: classification.type,
      attention: classification.attention
    });
    const clientLabel = computeClientLabel(classification.type, classification.attention);
    labels.push(CLIENT_LABEL_TO_GMAIL[clientLabel] || 'ShopQ-Everything-Else');
  }

  return labels;
}

/**
 * Compute client_label from type and attention.
 * Must match backend logic in shopq/storage/classification.py compute_client_label()
 *
 * Note: Uses attention (action_required/none), NOT importance (critical/time_sensitive/routine)
 */
function computeClientLabel(type, attention) {
  if (type === 'receipt') return 'receipts';
  if (type === 'message') return 'messages';
  if (type === 'otp') return 'everything-else';
  if (attention === 'action_required') return 'action-required';
  return 'everything-else';
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { mapToLabels, computeClientLabel };
}
