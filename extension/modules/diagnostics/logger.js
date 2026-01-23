/**
 * Diagnostics Logger
 *
 * Structured logging for Return Watch pipeline.
 * All log events are prefixed and can be filtered in DevTools.
 *
 * Log Events:
 * - FILTER_BLOCKED: Email blocked by P1 filter
 * - SKIP_ALREADY_PROCESSED: Email already in processed set
 * - PRIMARY_MERGE_BY_ORDER_ID: P2 linked by order_id
 * - PRIMARY_MERGE_BY_TRACKING: P2 linked by tracking number
 * - HINT_ATTACH: P3 thread hint attached (no field updates)
 * - CREATE_ORDER_FULL: P4/P6 created full order from confirmation
 * - CREATE_ORDER_PARTIAL: P4/P6 created partial order from shipping/delivery
 * - TEMP_ORDER_KEY_CREATED: P6 created temporary key (no primary key)
 * - SAFE_MERGE_ESCALATION: P7 merged two orders
 * - DEADLINE_COMPUTED: P8 computed return_by_date
 * - LLM_ENRICH_START: On-demand enrichment started
 * - LLM_ENRICH_SUCCESS: On-demand enrichment succeeded
 * - LLM_ENRICH_FAIL: On-demand enrichment failed
 * - SCAN_START: Scan started
 * - SCAN_COMPLETE: Scan completed
 */

const LOGGER_PREFIX = '[ReturnWatch]';

// ============================================================
// LOG LEVELS
// ============================================================

const LOG_LEVEL = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
};

// Current log level (can be changed at runtime)
let currentLogLevel = LOG_LEVEL.INFO;

/**
 * Set the current log level.
 *
 * @param {number} level - LOG_LEVEL value
 */
function setLogLevel(level) {
  currentLogLevel = level;
  console.log(LOGGER_PREFIX, 'Log level set to:', Object.keys(LOG_LEVEL).find(k => LOG_LEVEL[k] === level));
}

// ============================================================
// CORE LOGGING FUNCTIONS
// ============================================================

/**
 * Log a debug message.
 *
 * @param {string} event - Event name
 * @param {...any} args - Additional arguments
 */
function logDebug(event, ...args) {
  if (currentLogLevel <= LOG_LEVEL.DEBUG) {
    console.debug(LOGGER_PREFIX, `[${event}]`, ...args);
  }
}

/**
 * Log an info message.
 *
 * @param {string} event - Event name
 * @param {...any} args - Additional arguments
 */
function logInfo(event, ...args) {
  if (currentLogLevel <= LOG_LEVEL.INFO) {
    console.log(LOGGER_PREFIX, `[${event}]`, ...args);
  }
}

/**
 * Log a warning message.
 *
 * @param {string} event - Event name
 * @param {...any} args - Additional arguments
 */
function logWarn(event, ...args) {
  if (currentLogLevel <= LOG_LEVEL.WARN) {
    console.warn(LOGGER_PREFIX, `[${event}]`, ...args);
  }
}

/**
 * Log an error message.
 *
 * @param {string} event - Event name
 * @param {...any} args - Additional arguments
 */
function logError(event, ...args) {
  if (currentLogLevel <= LOG_LEVEL.ERROR) {
    console.error(LOGGER_PREFIX, `[${event}]`, ...args);
  }
}

// ============================================================
// PIPELINE EVENT LOGGERS
// ============================================================

/**
 * Log P1 filter blocked event.
 *
 * @param {string} emailId
 * @param {string} reason
 */
function logFilterBlocked(emailId, reason) {
  logInfo('FILTER_BLOCKED', emailId, reason);
}

/**
 * Log skip already processed event.
 *
 * @param {string} emailId
 */
function logSkipProcessed(emailId) {
  logDebug('SKIP_ALREADY_PROCESSED', emailId);
}

/**
 * Log P2 primary merge by order_id.
 *
 * @param {string} orderId
 * @param {string} orderKey
 */
function logPrimaryMergeByOrderId(orderId, orderKey) {
  logInfo('PRIMARY_MERGE_BY_ORDER_ID', orderId, '->', orderKey);
}

/**
 * Log P2 primary merge by tracking number.
 *
 * @param {string} tracking
 * @param {string} orderKey
 */
function logPrimaryMergeByTracking(tracking, orderKey) {
  logInfo('PRIMARY_MERGE_BY_TRACKING', tracking, '->', orderKey);
}

/**
 * Log P3 thread hint attach.
 *
 * @param {string} emailId
 * @param {string} orderKey
 */
function logHintAttach(emailId, orderKey) {
  logInfo('HINT_ATTACH', emailId, '->', orderKey, '(no field updates)');
}

/**
 * Log P4/P6 full order creation.
 *
 * @param {string} orderKey
 * @param {string} emailId
 */
function logCreateOrderFull(orderKey, emailId) {
  logInfo('CREATE_ORDER_FULL', orderKey, 'from email', emailId);
}

/**
 * Log P4/P6 partial order creation.
 *
 * @param {string} orderKey
 * @param {string} emailId
 */
function logCreateOrderPartial(orderKey, emailId) {
  logInfo('CREATE_ORDER_PARTIAL', orderKey, 'from email', emailId);
}

/**
 * Log P6 temporary order key creation.
 *
 * @param {string} orderKey
 */
function logTempOrderKey(orderKey) {
  logWarn('TEMP_ORDER_KEY_CREATED', orderKey);
}

/**
 * Log P7 safe merge escalation.
 *
 * @param {string} winnerKey
 * @param {string} loserKey
 */
function logMergeEscalation(winnerKey, loserKey) {
  logInfo('SAFE_MERGE_ESCALATION', 'winner:', winnerKey, 'loser:', loserKey);
}

/**
 * Log P8 deadline computed.
 *
 * @param {string} orderKey
 * @param {string} returnByDate
 * @param {string} confidence
 */
function logDeadlineComputed(orderKey, returnByDate, confidence) {
  logInfo('DEADLINE_COMPUTED', orderKey, `return_by=${returnByDate}`, `confidence=${confidence}`);
}

/**
 * Log LLM enrichment start.
 *
 * @param {string} orderKey
 */
function logEnrichStart(orderKey) {
  logInfo('LLM_ENRICH_START', orderKey);
}

/**
 * Log LLM enrichment success.
 *
 * @param {string} orderKey
 * @param {Object} result
 */
function logEnrichSuccess(orderKey, result) {
  logInfo('LLM_ENRICH_SUCCESS', orderKey, result);
}

/**
 * Log LLM enrichment failure.
 *
 * @param {string} orderKey
 * @param {string} error
 */
function logEnrichFail(orderKey, error) {
  logWarn('LLM_ENRICH_FAIL', orderKey, error);
}

/**
 * Log scan start.
 *
 * @param {number} windowDays
 * @param {boolean} incremental
 */
function logScanStart(windowDays, incremental) {
  logInfo('SCAN_START', `window=${windowDays}d`, `incremental=${incremental}`);
}

/**
 * Log scan complete.
 *
 * @param {number} durationSeconds
 * @param {Object} stats
 */
function logScanComplete(durationSeconds, stats) {
  logInfo('SCAN_COMPLETE', `${durationSeconds}s`, JSON.stringify(stats));
}

// ============================================================
// DIAGNOSTIC UTILITIES
// ============================================================

/**
 * Get diagnostic summary of current state.
 *
 * @returns {Promise<Object>}
 */
async function getDiagnosticSummary() {
  const storageStats = await getStorageStats();
  const refreshState = getRefreshState();

  return {
    timestamp: new Date().toISOString(),
    storage: storageStats,
    refresh: refreshState,
    logLevel: Object.keys(LOG_LEVEL).find(k => LOG_LEVEL[k] === currentLogLevel),
  };
}

/**
 * Log diagnostic summary to console.
 */
async function logDiagnosticSummary() {
  const summary = await getDiagnosticSummary();
  console.log(LOGGER_PREFIX, '='.repeat(60));
  console.log(LOGGER_PREFIX, 'DIAGNOSTIC_SUMMARY');
  console.log(LOGGER_PREFIX, JSON.stringify(summary, null, 2));
  console.log(LOGGER_PREFIX, '='.repeat(60));
}

/**
 * Run storage tests and log results.
 */
async function runDiagnostics() {
  console.log(LOGGER_PREFIX, '='.repeat(60));
  console.log(LOGGER_PREFIX, 'RUNNING DIAGNOSTICS');
  console.log(LOGGER_PREFIX, '='.repeat(60));

  try {
    // Check storage health
    const stats = await getStorageStats();
    console.log(LOGGER_PREFIX, 'Storage stats:', stats);

    // Check refresh state
    const refreshState = getRefreshState();
    console.log(LOGGER_PREFIX, 'Refresh state:', refreshState);

    // Check merchant rules
    const rules = await getAllMerchantRules();
    console.log(LOGGER_PREFIX, 'Merchant rules:', Object.keys(rules).length, 'rules configured');

    console.log(LOGGER_PREFIX, '='.repeat(60));
    console.log(LOGGER_PREFIX, 'DIAGNOSTICS COMPLETE');
    console.log(LOGGER_PREFIX, '='.repeat(60));

    return { success: true };
  } catch (error) {
    console.error(LOGGER_PREFIX, 'DIAGNOSTICS FAILED:', error);
    return { success: false, error: error.message };
  }
}
