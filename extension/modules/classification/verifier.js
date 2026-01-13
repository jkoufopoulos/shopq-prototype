/**
 * Selective Verifier Module (Phase 6)
 *
 * Second-pass LLM call that challenges first classification on suspicious cases.
 * Goal: Catch obvious misses (e.g., "action_required" for review requests) without
 * re-running everything.
 *
 * Verifier triggers on ~10-30% of emails based on:
 * - Low confidence (below threshold, typically <0.7) on type/label/attention
 * - Multi-purpose senders (Amazon, Google, PayPal)
 * - Contradictions (promotion with order tokens, notification without OTP)
 * - Weak reasoning ("probably", "might be", "unsure")
 */


/**
 * Multi-purpose sender domains that need extra scrutiny
 */
const MULTI_PURPOSE_SENDERS = [
  'amazon.com',
  'google.com',
  'paypal.com',
  'chase.com',
  'bankofamerica.com',
  'wellsfargo.com',
  'citi.com',
  'capitalone.com',
  'apple.com',
  'microsoft.com',
  'uber.com',
  'lyft.com',
  'delta.com',
  'united.com',
  'aa.com'  // American Airlines
];


/**
 * Extract compact email features for verifier
 *
 * @param {Object} email - { subject, snippet, from }
 * @returns {Object} Compact feature set
 */
function extractEmailFeatures(email) {
  const text = `${email.subject} ${email.snippet}`.toLowerCase();

  return {
    has_order_id: /\b(order|receipt|invoice|confirmation)\s?#?\w{5,}/i.test(text),
    has_amount: /\$\d+\.\d{2}/i.test(text),
    has_calendar_link: /(zoom\.us|meet\.google\.com|teams\.microsoft\.com)/i.test(text),
    has_unsubscribe: /unsubscribe/i.test(text),
    has_otp: /\b\d{4,8}\b.{0,30}(code|otp|verification|2fa)/i.test(text),
    has_action_words: /\b(confirm|verify|reset|activate|click|sign in|log in|action required)\b/i.test(text),
    has_promo_words: /\b(sale|discount|offer|deal|limited time|expires|save|free shipping)\b/i.test(text),
    has_review_request: /(how was your|rate your|review your|tell us what you think)/i.test(text)
  };
}


/**
 * Check if sender is multi-purpose (needs extra scrutiny)
 *
 * @param {string} fromAddress - Email sender
 * @returns {boolean} True if multi-purpose sender
 */
function isMultiPurposeSender(fromAddress) {
  const domain = fromAddress.toLowerCase().split('@')[1] || '';
  return MULTI_PURPOSE_SENDERS.some(mpDomain => domain.includes(mpDomain));
}


/**
 * Detect contradictions in classification
 *
 * @param {Object} classification - First-pass classification result
 * @param {Object} features - Extracted email features
 * @returns {Array<string>} List of contradictions found
 */
function detectContradictions(classification, features) {
  const contradictions = [];

  // Promotion with order tokens (likely receipt, not promo)
  if (classification.type === 'promotion' && (features.has_order_id || features.has_amount)) {
    contradictions.push('promotion_with_order_tokens');
  }

  // Notification without OTP but has OTP pattern (detector should have caught this)
  if (classification.type === 'notification' && features.has_otp && classification.decider !== 'rule') {
    contradictions.push('notification_with_otp_pattern');
  }

  // Action required but no action words (might be review request)
  if (classification.attention === 'action_required' && !features.has_action_words) {
    contradictions.push('action_required_without_action_words');
  }

  // Receipt with unsubscribe footer (likely promo, not receipt)
  if (classification.type === 'receipt' && features.has_unsubscribe && !features.has_order_id) {
    contradictions.push('receipt_with_unsubscribe_no_order');
  }

  // Action required + promo words (likely promo pressure, not real action)
  if (classification.attention === 'action_required' && features.has_promo_words) {
    contradictions.push('action_required_with_promo_language');
  }

  // Review request pattern but not marked as notification/none
  if (features.has_review_request && classification.attention === 'action_required') {
    contradictions.push('review_request_marked_action_required');
  }

  return contradictions;
}


/**
 * Check if reasoning contains weak/uncertain language
 *
 * @param {string} reason - Classification reason string
 * @returns {boolean} True if reason contains weak language
 */
function hasWeakReasoning(reason) {
  if (!reason) return false;

  const weakTerms = [
    'probably',
    'might be',
    'could be',
    'seems like',
    'appears to',
    'looks like',
    'unsure',
    'possibly',
    'maybe',
    'unclear'
  ];

  const lowerReason = reason.toLowerCase();
  return weakTerms.some(term => lowerReason.includes(term));
}


/**
 * Determine if email needs verification (Phase 6 triggers)
 *
 * @param {Object} email - { subject, snippet, from }
 * @param {Object} classification - First-pass classification result
 * @returns {Object|null} { reason: string, features: Object, contradictions: Array } or null
 */
function shouldVerify(email, classification) {
  // Skip if detector already handled it (high confidence T0)
  if (classification.decider === 'rule') {
    return null;
  }

  const typeConf = classification.type_conf || 0;
  const attentionConf = classification.attention_conf || 0;
  const importanceConf = classification.importance_conf || 0;

  // Pass clean: high-confidence classifications (all fields >= 0.80) skip verification
  // Unless attention=action_required (always verify those) or weak reasoning
  if (
    classification.attention !== 'action_required' &&
    typeConf >= 0.80 &&
    attentionConf >= 0.80 &&
    importanceConf >= 0.80 &&
    !hasWeakReasoning(classification.reason)
  ) {
    return null;
  }

  const features = extractEmailFeatures(email);
  const contradictions = detectContradictions(classification, features);
  const weakReasoning = hasWeakReasoning(classification.reason);

  const triggers = [];

  // Trigger 1: Low confidence on ANY field below 0.80 threshold
  // Simplified: no more confusing typeConf < 0.90 guards
  const confidenceThreshold = 0.80;

  const lowConfidenceChecks = [];
  if (typeConf < confidenceThreshold) {
    lowConfidenceChecks.push(`type:${typeConf.toFixed(2)}`);
  }
  if (attentionConf < confidenceThreshold) {
    lowConfidenceChecks.push(`attention:${attentionConf.toFixed(2)}`);
  }
  if (importanceConf < confidenceThreshold) {
    lowConfidenceChecks.push(`importance:${importanceConf.toFixed(2)}`);
  }
  if (lowConfidenceChecks.length > 0) {
    triggers.push(`low_confidence:${lowConfidenceChecks.join(',')}`);
  }

  // Trigger 2: Multi-purpose sender
  if (isMultiPurposeSender(email.from)) {
    triggers.push('multi_purpose_sender');
  }

  // Trigger 3: Contradictions detected
  if (contradictions.length > 0) {
    triggers.push(`contradictions:${contradictions.join(',')}`);
  }

  // Trigger 4: Weak reasoning language
  if (weakReasoning) {
    triggers.push('weak_reasoning');
  }

  // Verify if ANY trigger fired
  if (triggers.length > 0) {
    return {
      reason: triggers.join(' | '),
      features: features,
      contradictions: contradictions
    };
  }

  return null;
}


/**
 * Call verifier API to challenge first classification
 *
 * @param {Object} email - { subject, snippet, from }
 * @param {Object} classification - First-pass classification
 * @param {Object} verifyContext - { reason, features, contradictions }
 * @returns {Promise<Object>} Verifier result or null if error
 */
async function callVerifier(email, classification, verifyContext) {
  try {
    const url = `${CONFIG.MAILQ_API_URL}/api/verify`;

    const redactedFrom = redactForLog(email.from);

    console.log('🌐 verifier.request', {
      url: redactForLog(url),
      from: redactedFrom,
      triggers: redactForLog(verifyContext.reason || '')
    });

    const payload = {
      email: {
        subject: email.subject,
        snippet: email.snippet,
        from: email.from
      },
      first_result: {
        type: classification.type,
        type_conf: classification.type_conf,
        attention: classification.attention,
        attention_conf: classification.attention_conf,
        importance: classification.importance,
        importance_conf: classification.importance_conf,
        client_label: classification.client_label,
        relationship: classification.relationship,
        relationship_conf: classification.relationship_conf,
        reason: classification.reason
      },
      features: verifyContext.features,
      contradictions: verifyContext.contradictions
    };

    const response = await resilientFetch(
      url,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      },
      { timeoutMs: 10000, retries: 1 }
    );

    if (!response.ok) {
      console.warn('⚠️ verifier.error', {
        status: response.status,
        from: redactedFrom
      });
      return null;
    }

    const data = await response.json();
    console.log('✅ verifier.success', {
      verdict: data.verdict,
      from: redactedFrom
    });

    return data;

  } catch (error) {
    console.error('❌ verifier.call_failed', {
      error: error?.message || String(error)
    });
    return null;
  }
}


/**
 * Decide whether to accept verifier correction
 *
 * @param {Object} verifierResult - Verifier API response
 * @returns {boolean} True if should accept correction
 */
function shouldAcceptCorrection(verifierResult) {
  // Accept both "reject" (new) and "correct" (old) for backwards compatibility
  const isRejecting = verifierResult && (verifierResult.verdict === 'reject' || verifierResult.verdict === 'correct');

  if (!isRejecting) {
    return false;
  }

  const confidenceDelta = Math.abs(verifierResult.confidence_delta || 0);
  const hasViolations = (verifierResult.rubric_violations || []).length > 0;

  // Accept if significant confidence change OR rubric violations found
  return confidenceDelta >= 0.15 || hasViolations;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { shouldVerify, shouldAcceptCorrection };
}
