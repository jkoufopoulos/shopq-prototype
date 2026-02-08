/**
 * On-Demand Policy Enrichment
 *
 * Triggered when user opens Order Detail AND:
 * - deadline_confidence === 'unknown', OR
 * - return_by_date === null
 *
 * Flow:
 * 1. Select candidate emails (confirmation first, then anchors)
 * 2. Fetch body if needed
 * 3. Detect return anchors (from extractor.js)
 * 4. If no anchors → show "Set merchant return window" CTA (no LLM call)
 * 5. If anchors → call LLM with context window (≤1000 chars)
 * 6. Validate evidence: quote must contain extracted values literally
 * 7. Persist and recompute return_by_date
 */

const POLICY_LOG_PREFIX = '[ReturnWatch:Policy]';

// ============================================================
// CONSTANTS
// ============================================================

/**
 * Maximum context to send to LLM (characters).
 */
const MAX_LLM_CONTEXT = CONFIG.MAX_LLM_CONTEXT_CHARS;

/**
 * Enrichment states for UI.
 */
const ENRICHMENT_STATE = {
  IDLE: 'idle',
  CHECKING: 'checking',
  ENRICHING: 'enriching',
  FOUND: 'found',
  NOT_FOUND: 'not_found',
  ERROR: 'error',
};

// ============================================================
// EMAIL SELECTION
// ============================================================

/**
 * Select candidate emails for enrichment.
 * Priority: confirmation emails first, then emails with return anchors.
 *
 * @param {Order} order
 * @returns {Promise<string[]>} Ordered list of email IDs to try
 */
async function selectCandidateEmails(order) {
  const candidates = [];
  const emailRecords = [];

  // Fetch all associated email records
  for (const emailId of order.source_email_ids) {
    const record = await getOrderEmail(emailId);
    if (record) {
      emailRecords.push(record);
    }
  }

  // Priority 1: Confirmation emails (most likely to have return policy)
  for (const record of emailRecords) {
    if (record.email_type === EMAIL_TYPE.CONFIRMATION) {
      candidates.push(record.email_id);
    }
  }

  // Priority 2: Emails with detected return anchors
  for (const record of emailRecords) {
    if (record.extracted?.hasReturnAnchors && !candidates.includes(record.email_id)) {
      candidates.push(record.email_id);
    }
  }

  // Priority 3: All other non-blocked emails
  for (const record of emailRecords) {
    if (!record.blocked && !candidates.includes(record.email_id)) {
      candidates.push(record.email_id);
    }
  }

  console.log(POLICY_LOG_PREFIX, 'CANDIDATES', order.order_key, candidates.length, 'emails');

  return candidates;
}

// ============================================================
// ANCHOR DETECTION
// ============================================================

/**
 * Check if order has any emails with return policy anchors.
 *
 * @param {Order} order
 * @returns {Promise<{hasAnchors: boolean, isFinalSale: boolean, anchorEmailId: string|null}>}
 */
async function checkForReturnAnchors(order) {
  for (const emailId of order.source_email_ids) {
    const record = await getOrderEmail(emailId);
    if (record?.extracted?.hasReturnAnchors) {
      return {
        hasAnchors: true,
        isFinalSale: record.extracted.isFinalSale || false,
        anchorEmailId: emailId,
      };
    }
  }

  return {
    hasAnchors: false,
    isFinalSale: false,
    anchorEmailId: null,
  };
}

// ============================================================
// CONTEXT PREPARATION
// ============================================================

/**
 * Prepare context for LLM extraction.
 * Extracts relevant portions around return policy mentions.
 *
 * @param {string} body - Full email body
 * @param {string[]} anchors - Detected anchor strings
 * @returns {string} Trimmed context (≤1000 chars)
 */
function prepareContext(body, anchors) {
  if (!body) return '';

  // If body is short enough, use it all
  if (body.length <= MAX_LLM_CONTEXT) {
    return body;
  }

  // Find anchor positions and extract context around them
  const contexts = [];

  for (const anchor of anchors) {
    const index = body.toLowerCase().indexOf(anchor.toLowerCase());
    if (index !== -1) {
      const start = Math.max(0, index - 200);
      const end = Math.min(body.length, index + anchor.length + 200);
      contexts.push(body.substring(start, end));
    }
  }

  // Combine contexts, removing duplicates
  if (contexts.length > 0) {
    const combined = [...new Set(contexts)].join('\n...\n');
    if (combined.length <= MAX_LLM_CONTEXT) {
      return combined;
    }
    return combined.substring(0, MAX_LLM_CONTEXT);
  }

  // Fallback: just use beginning of body
  return body.substring(0, MAX_LLM_CONTEXT);
}

// ============================================================
// LLM EXTRACTION
// ============================================================

/**
 * Call backend LLM API to extract return policy.
 *
 * @param {string} context - Email context to analyze
 * @param {string} merchant - Merchant name for context
 * @returns {Promise<LLMExtractionResult>}
 */
async function callLLMExtraction(context, merchant) {
  console.log(POLICY_LOG_PREFIX, 'LLM_CALL', 'context length:', context.length);

  try {
    const token = await getAuthToken();
    const apiUrl = CONFIG.API_BASE_URL;

    const response = await fetch(`${apiUrl}/api/returns/extract-policy`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        context,
        merchant,
      }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const result = await response.json();

    console.log(POLICY_LOG_PREFIX, 'LLM_RESULT', JSON.stringify(result));

    return {
      success: true,
      return_by_date: result.return_by_date || null,
      return_window_days: result.return_window_days || null,
      evidence_quote: result.evidence_quote || null,
      confidence: result.confidence || 'low',
    };

  } catch (error) {
    console.error(POLICY_LOG_PREFIX, 'LLM_ERROR', error.message);
    return {
      success: false,
      error: error.message,
    };
  }
}

// ============================================================
// MAIN ENRICHMENT FUNCTION
// ============================================================

/**
 * Enrich an order with return policy information.
 * Called when user opens Order Detail.
 *
 * @param {string} order_key
 * @returns {Promise<EnrichmentResult>}
 */
async function enrichOrder(order_key) {
  console.log(POLICY_LOG_PREFIX, 'ENRICH_START', order_key);

  const order = await getOrder(order_key);
  if (!order) {
    return {
      state: ENRICHMENT_STATE.ERROR,
      error: 'Order not found',
    };
  }

  // Check if enrichment is needed
  if (order.deadline_confidence !== DEADLINE_CONFIDENCE.UNKNOWN && order.return_by_date) {
    console.log(POLICY_LOG_PREFIX, 'ENRICH_SKIP', 'already has deadline');
    return {
      state: ENRICHMENT_STATE.FOUND,
      order,
      message: 'Return policy already known',
    };
  }

  // Check for return anchors
  const anchorCheck = await checkForReturnAnchors(order);

  if (anchorCheck.isFinalSale) {
    console.log(POLICY_LOG_PREFIX, 'ENRICH_FINAL_SALE', order_key);
    return {
      state: ENRICHMENT_STATE.NOT_FOUND,
      order,
      message: 'Item marked as final sale - no returns',
      showMerchantRuleCTA: false,
    };
  }

  if (!anchorCheck.hasAnchors) {
    console.log(POLICY_LOG_PREFIX, 'ENRICH_NO_ANCHORS', order_key);
    return {
      state: ENRICHMENT_STATE.NOT_FOUND,
      order,
      message: 'No return policy information found in emails',
      showMerchantRuleCTA: true,
    };
  }

  // Fetch email body for LLM context
  const candidates = await selectCandidateEmails(order);
  if (candidates.length === 0) {
    return {
      state: ENRICHMENT_STATE.NOT_FOUND,
      order,
      message: 'No emails available for enrichment',
      showMerchantRuleCTA: true,
    };
  }

  // Try each candidate email
  for (const emailId of candidates) {
    const record = await getOrderEmail(emailId);
    if (!record) continue;

    // Get anchors for this email
    const anchors = record.extracted?.returnAnchors || [];
    if (anchors.length === 0) continue;

    // Fetch full message body
    let body = '';
    try {
      const token = await getAuthToken();
      const response = await fetch(
        `https://gmail.googleapis.com/gmail/v1/users/me/messages/${emailId}?format=full`,
        {
          headers: { 'Authorization': `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const message = await response.json();
        body = extractBodyFromPayload(message.payload);
      }
    } catch (error) {
      console.warn(POLICY_LOG_PREFIX, 'BODY_FETCH_ERROR', emailId, error.message);
      continue;
    }

    if (!body) continue;

    // Prepare context and call LLM
    const context = prepareContext(body, anchors);
    const llmResult = await callLLMExtraction(context, order.merchant_display_name);

    if (!llmResult.success) continue;

    // Validate extraction
    const validation = validateExtraction(llmResult, body);

    if (validation.valid) {
      console.log(POLICY_LOG_PREFIX, 'ENRICH_VALIDATED', order_key);

      // Update order with validated data
      if (validation.validated.return_by_date) {
        order.explicit_return_by_date = validation.validated.return_by_date;
      }
      if (validation.validated.return_window_days) {
        order.return_window_days = validation.validated.return_window_days;
      }
      if (validation.validated.evidence_quote) {
        order.evidence_quote = validation.validated.evidence_quote;
        order.evidence_message_id = emailId;
      }

      // Store LLM extraction on email record
      record.llm_extraction = {
        extracted_at: new Date().toISOString(),
        result: llmResult,
        validation: validation,
      };
      await storeOrderEmail(record);

      // Recompute deadline
      const updatedOrder = await applyEventAndComputeDeadline(order);
      await upsertOrder(updatedOrder);

      console.log(POLICY_LOG_PREFIX, 'ENRICH_SUCCESS', order_key,
        'deadline:', updatedOrder.return_by_date,
        'confidence:', updatedOrder.deadline_confidence);

      return {
        state: ENRICHMENT_STATE.FOUND,
        order: updatedOrder,
        message: 'Return policy found',
      };
    } else {
      console.log(POLICY_LOG_PREFIX, 'ENRICH_VALIDATION_FAILED', validation.errors);
    }
  }

  // No valid extraction found
  console.log(POLICY_LOG_PREFIX, 'ENRICH_NOT_FOUND', order_key);

  return {
    state: ENRICHMENT_STATE.NOT_FOUND,
    order,
    message: 'Could not find a return deadline in emails',
    showMerchantRuleCTA: true,
  };
}

/**
 * Check if an order needs enrichment.
 *
 * @param {Order} order
 * @returns {boolean}
 */
function needsEnrichment(order) {
  return order.deadline_confidence === DEADLINE_CONFIDENCE.UNKNOWN || !order.return_by_date;
}

/**
 * @typedef {Object} EnrichmentResult
 * @property {string} state - ENRICHMENT_STATE value
 * @property {Order} [order] - Updated order
 * @property {string} [message] - User-facing message
 * @property {string} [error] - Error message
 * @property {boolean} [showMerchantRuleCTA] - Show "Set merchant return window" button
 */

/**
 * @typedef {Object} LLMExtractionResult
 * @property {boolean} success
 * @property {string} [return_by_date] - ISO date
 * @property {number} [return_window_days]
 * @property {string} [evidence_quote]
 * @property {string} [confidence] - 'high', 'medium', 'low'
 * @property {string} [error]
 */
