/**
 * Structured Logger for ShopQ Extension
 *
 * Mirrors Python structured_logging.py with:
 * - Event taxonomy (same EventType enum)
 * - Rate limiting per event key
 * - Privacy redaction
 * - One-line JSON output
 *
 * Usage:
 *   import { StructuredLogger, EventType } from './structured-logger.js';
 *
 *   const logger = new StructuredLogger('20251111_234512');
 *   logger.logEvent(EventType.LLM_CALL_ERROR, '18c2a4f8d', {
 *     error: 'QuotaExceeded',
 *     fallback: true,
 *     cost: 0.0001
 *   });
 */

/**
 * Event types matching Python EventType enum
 */
const EventType = {
  // LLM Classification
  LLM_CALL_START: 'llm_call_start',
  LLM_CALL_OK: 'llm_call_ok',
  LLM_CALL_ERROR: 'llm_call_error',
  LLM_RATE_LIMITED: 'llm_rate_limited',
  LLM_FALLBACK_INVOKED: 'llm_fallback_invoked',
  LLM_FALLBACK_OK: 'llm_fallback_ok',
  LLM_FALLBACK_ERROR: 'llm_fallback_error',

  // Bridge Mapper
  MAP_START: 'map_start',
  MAP_DECISION: 'map_decision',
  MAP_MISSING_FIELD: 'map_missing_field',
  MAP_GUARDRAIL_APPLIED: 'map_guardrail_applied',
  MAP_DEFAULT_USED: 'map_default_used',
  MAP_ERROR: 'map_error',

  // Temporal Enrichment
  TEMPORAL_PARSE_OK: 'temporal_parse_ok',
  TEMPORAL_PARSE_ERROR: 'temporal_parse_error',
  TEMPORAL_RESOLVE_DECISION: 'temporal_resolve_decision',
  TEMPORAL_FILTER_APPLIED: 'temporal_filter_applied',

  // Entity Extraction
  EXTRACT_ENTITIES_OK: 'extract_entities_ok',
  EXTRACT_ENTITIES_ERROR: 'extract_entities_error',
  EXTRACT_INCONSISTENT: 'extract_inconsistent',

  // Digest Assembly
  DIGEST_BUILD_OK: 'digest_build_ok',
  DIGEST_BUILD_ERROR: 'digest_build_error',
  DIGEST_MISSED_DETECTED: 'digest_missed_detected',
  DIGEST_FLAGGED_PENDING: 'digest_flagged_pending',

  // Extension/Label Application
  EXT_BATCH_START: 'ext_batch_start',
  EXT_BATCH_DONE: 'ext_batch_done',
  EXT_LABEL_APPLY_OK: 'ext_label_apply_ok',
  EXT_LABEL_APPLY_ERROR: 'ext_label_apply_error',
  EXT_ARCHIVE_ERROR: 'ext_archive_error',
  EXT_MISMATCH: 'ext_mismatch',

  // Heartbeat/Checkpointing
  HEARTBEAT_RESUME_DETECTED: 'heartbeat_resume_detected',
  HEARTBEAT_RESUME_OK: 'heartbeat_resume_ok',
  HEARTBEAT_RESUME_ERROR: 'heartbeat_resume_error',
  CHECKPOINT_SAVE: 'checkpoint_save',
  CHECKPOINT_CLEAR: 'checkpoint_clear',
  CHECKPOINT_LOAD: 'checkpoint_load',
};

/**
 * Event severity mapping
 */
const EventSeverity = {
  // LLM
  [EventType.LLM_CALL_START]: 'DEBUG',
  [EventType.LLM_CALL_OK]: 'INFO',
  [EventType.LLM_CALL_ERROR]: 'ERROR',
  [EventType.LLM_RATE_LIMITED]: 'ERROR',
  [EventType.LLM_FALLBACK_INVOKED]: 'WARN',
  [EventType.LLM_FALLBACK_OK]: 'INFO',
  [EventType.LLM_FALLBACK_ERROR]: 'ERROR',

  // Bridge
  [EventType.MAP_START]: 'DEBUG',
  [EventType.MAP_DECISION]: 'INFO',
  [EventType.MAP_MISSING_FIELD]: 'WARN',
  [EventType.MAP_GUARDRAIL_APPLIED]: 'INFO',
  [EventType.MAP_DEFAULT_USED]: 'WARN',
  [EventType.MAP_ERROR]: 'ERROR',

  // Temporal
  [EventType.TEMPORAL_PARSE_OK]: 'DEBUG',
  [EventType.TEMPORAL_PARSE_ERROR]: 'ERROR',
  [EventType.TEMPORAL_RESOLVE_DECISION]: 'INFO',
  [EventType.TEMPORAL_FILTER_APPLIED]: 'INFO',

  // Entity
  [EventType.EXTRACT_ENTITIES_OK]: 'INFO',
  [EventType.EXTRACT_ENTITIES_ERROR]: 'ERROR',
  [EventType.EXTRACT_INCONSISTENT]: 'WARN',

  // Digest
  [EventType.DIGEST_BUILD_OK]: 'INFO',
  [EventType.DIGEST_BUILD_ERROR]: 'ERROR',
  [EventType.DIGEST_MISSED_DETECTED]: 'WARN',
  [EventType.DIGEST_FLAGGED_PENDING]: 'INFO',

  // Extension
  [EventType.EXT_BATCH_START]: 'INFO',
  [EventType.EXT_BATCH_DONE]: 'INFO',
  [EventType.EXT_LABEL_APPLY_OK]: 'DEBUG',
  [EventType.EXT_LABEL_APPLY_ERROR]: 'ERROR',
  [EventType.EXT_ARCHIVE_ERROR]: 'ERROR',
  [EventType.EXT_MISMATCH]: 'WARN',

  // Heartbeat
  [EventType.HEARTBEAT_RESUME_DETECTED]: 'INFO',
  [EventType.HEARTBEAT_RESUME_OK]: 'INFO',
  [EventType.HEARTBEAT_RESUME_ERROR]: 'ERROR',
  [EventType.CHECKPOINT_SAVE]: 'DEBUG',
  [EventType.CHECKPOINT_CLEAR]: 'DEBUG',
  [EventType.CHECKPOINT_LOAD]: 'INFO',
};

/**
 * Structured Logger
 */
class StructuredLogger {
  /**
   * @param {string} sessionId - Session ID (e.g., '20251111_234512')
   * @param {number} sampleRateInfo - Sample rate for INFO logs (0.0-1.0)
   * @param {number} sampleRateError - Sample rate for ERROR logs (0.0-1.0)
   */
  constructor(sessionId = null, sampleRateInfo = 0.1, sampleRateError = 1.0) {
    this.sessionId = sessionId || this._generateSessionId();
    this.sampleRateInfo = sampleRateInfo;
    this.sampleRateError = sampleRateError;
    this.rateLimiter = new Map(); // event_key -> last_log_time
  }

  /**
   * Generate session ID: YYYYMMDD_HHMMSS
   */
  _generateSessionId() {
    const now = new Date();
    const year = now.getUTCFullYear();
    const month = String(now.getUTCMonth() + 1).padStart(2, '0');
    const day = String(now.getUTCDate()).padStart(2, '0');
    const hour = String(now.getUTCHours()).padStart(2, '0');
    const min = String(now.getUTCMinutes()).padStart(2, '0');
    const sec = String(now.getUTCSeconds()).padStart(2, '0');
    return `${year}${month}${day}_${hour}${min}${sec}`;
  }

  /**
   * Hash email ID to 12-char prefix
   */
  static hashEmailId(emailId) {
    if (!emailId) return 'unknown';
    return emailId.substring(0, 12);
  }

  /**
   * Redact subject line for privacy
   */
  static redactSubject(subject, maxLen = 50) {
    if (!subject) return '';

    let truncated = subject.substring(0, maxLen);

    // Replace email addresses
    truncated = truncated.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g, '[EMAIL]');

    // Replace phone numbers
    truncated = truncated.replace(/\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g, '[PHONE]');

    return truncated + (subject.length > maxLen ? '...' : '');
  }

  /**
   * Determine if event should be logged based on sampling
   */
  _shouldLog(eventType) {
    const severity = EventSeverity[eventType] || 'INFO';

    // Always log ERROR
    if (severity === 'ERROR') {
      return Math.random() < this.sampleRateError;
    }

    // Sample INFO/DEBUG
    return Math.random() < this.sampleRateInfo;
  }

  /**
   * Rate limit events by key
   * @param {string} eventKey - Rate limit key
   * @param {number} minIntervalMs - Minimum interval in milliseconds
   * @returns {boolean} True if should log, false if rate limited
   */
  _rateLimit(eventKey, minIntervalMs = 60000) {
    const now = Date.now();
    const lastLog = this.rateLimiter.get(eventKey) || 0;

    if (now - lastLog < minIntervalMs) {
      return false; // Rate limited
    }

    this.rateLimiter.set(eventKey, now);
    return true;
  }

  /**
   * Log a structured event
   * @param {string} eventType - Event type from EventType
   * @param {string} emailId - Email ID (will be hashed)
   * @param {Object} fields - Additional fields
   * @param {string} rateLimitKey - Optional rate limit key
   */
  logEvent(eventType, emailId = null, fields = {}, rateLimitKey = null) {
    // Check sampling
    if (!this._shouldLog(eventType)) {
      return;
    }

    // Check rate limiting
    const rlKey = rateLimitKey || `${eventType}:${StructuredLogger.hashEmailId(emailId || 'none')}`;
    const severity = EventSeverity[eventType] || 'INFO';

    // Only rate limit INFO/DEBUG (not errors)
    if (severity !== 'ERROR' && !this._rateLimit(rlKey)) {
      return;
    }

    // Build event payload
    const event = {
      ts: new Date().toISOString(),
      level: severity,
      session: this.sessionId,
      event: eventType,
    };

    // Add email ID if provided
    if (emailId) {
      event.email = StructuredLogger.hashEmailId(emailId);
    }

    // Add custom fields
    for (const [key, value] of Object.entries(fields)) {
      // Redact subject if present
      if (key === 'subject' && typeof value === 'string') {
        event[key] = StructuredLogger.redactSubject(value);
      }
      // Truncate long strings
      else if (typeof value === 'string' && value.length > 200) {
        event[key] = value.substring(0, 200) + '...';
      } else {
        event[key] = value;
      }
    }

    // Log as one-line JSON
    const jsonLine = JSON.stringify(event);

    // Use appropriate console method
    if (severity === 'ERROR') {
      console.error(jsonLine);
    } else if (severity === 'WARN') {
      console.warn(jsonLine);
    } else {
      console.log(jsonLine);
    }
  }

  // Convenience methods

  llmCallError(emailId, error, fallback = false, cost = 0.0) {
    this.logEvent(EventType.LLM_CALL_ERROR, emailId, { error, fallback, cost });
  }

  llmRateLimited(emailId, retryAfter = null) {
    this.logEvent(EventType.LLM_RATE_LIMITED, emailId, { retry_after: retryAfter });
  }

  mapDecision(emailId, importance, source, ruleName = null) {
    this.logEvent(EventType.MAP_DECISION, emailId, {
      importance,
      source,
      rule: ruleName,
    });
  }

  mapGuardrailApplied(emailId, ruleName, importance) {
    this.logEvent(EventType.MAP_GUARDRAIL_APPLIED, emailId, {
      rule: ruleName,
      importance,
    });
  }

  extBatchDone(processed, skipped, failed) {
    this.logEvent(EventType.EXT_BATCH_DONE, null, { processed, skipped, failed });
  }

  extLabelApplyError(emailId, error) {
    this.logEvent(EventType.EXT_LABEL_APPLY_ERROR, emailId, { error });
  }

  extMismatch(emailId, classified, applied) {
    this.logEvent(EventType.EXT_MISMATCH, emailId, {
      classified: classified.join(','),
      applied: applied.join(','),
    });
  }

  checkpointSave(totalProcessed, retryCount = 0) {
    this.logEvent(EventType.CHECKPOINT_SAVE, null, {
      total: totalProcessed,
      retry: retryCount,
    });
  }

  checkpointLoad(totalProcessed, ageMinutes) {
    this.logEvent(EventType.CHECKPOINT_LOAD, null, {
      total: totalProcessed,
      age_min: ageMinutes,
    });
  }

  heartbeatResumeDetected(checkpointAge) {
    this.logEvent(EventType.HEARTBEAT_RESUME_DETECTED, null, {
      age_min: checkpointAge,
    });
  }
}

// Global logger instance
let _globalLogger = null;

/**
 * Get or create global structured logger
 * @param {string} sessionId - Optional session ID
 * @returns {StructuredLogger}
 */
function getLogger(sessionId = null) {
  if (sessionId || !_globalLogger) {
    _globalLogger = new StructuredLogger(sessionId);
  }
  return _globalLogger;
}

// Export for ES modules and CommonJS
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { StructuredLogger, EventType, getLogger };
}
