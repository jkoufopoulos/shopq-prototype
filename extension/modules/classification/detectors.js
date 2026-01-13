/**
 * Email Pattern Detectors Module (Phase 2)
 *
 * High-precision, T0/T1 rules-based detection layer that runs BEFORE LLM calls.
 * Captures common patterns with high confidence to reduce costs and errors.
 *
 * Design principles:
 * - Favor precision over recall (conservative patterns)
 * - Pure functions (testable, no side effects)
 * - Clear reason strings for transparency
 * - Return null if no match (allow other detectors to try)
 */

/**
 * Compute client_label from type and importance.
 * Must match backend logic in mailq/storage/classification.py compute_client_label()
 *
 * Mapping Rules (in priority order):
 * 1. type=receipt → "receipts"
 * 2. type=message → "messages"
 * 3. type=otp → "everything-else" (OTPs are ephemeral)
 * 4. importance=critical → "action-required"
 * 5. Everything else → "everything-else"
 */
function computeClientLabel(type, importance) {
  if (type === 'receipt') return 'receipts';
  if (type === 'message') return 'messages';
  if (type === 'otp') return 'everything-else';
  if (importance === 'critical') return 'action-required';
  return 'everything-else';
}


/**
 * Detect OTP/security codes (2FA, login codes, verification)
 *
 * Per TAXONOMY.md otp_rules:
 * - type: otp
 * - importance: critical (urgent in the moment)
 * - client_label: everything-else (NOT action-required, OTPs are ephemeral)
 *
 * OTPs are filtered from digest by backend temporal decay (T1 stage).
 *
 * Patterns:
 * - "Your code is 123456"
 * - "Login code: 2530"
 * - "123456 is your verification code"
 *
 * @param {Object} email - { subject, snippet, from }
 * @returns {Object|null} Classification or null
 */
function detectOTP(email) {
  const text = `${email.subject} ${email.snippet}`.toLowerCase();

  // OTP patterns: 4-8 digit code + security keywords
  const otpPatterns = [
    /\b(\d{4,8})\b.{0,30}(code|otp|passcode|verification|2fa|two.?factor|security)/i,
    /(login|verification|security|authenticate|confirm).{0,30}\b(\d{4,8})\b/i,
    /your (code|otp|passcode) is.{0,10}\b(\d{4,8})\b/i
  ];

  const hasOTPPattern = otpPatterns.some(pattern => pattern.test(text));

  if (hasOTPPattern) {
    return {
      type: 'otp',  // Correct type per TAXONOMY.md
      type_conf: 0.98,
      attention: 'none',  // OTPs don't require user action in digest context
      attention_conf: 0.95,
      importance: 'critical',  // OTPs are critical in the moment
      importance_conf: 0.95,
      client_label: computeClientLabel('otp', 'critical'),  // → everything-else
      relationship: 'from_unknown',
      relationship_conf: 0.70,
      decider: 'rule',
      reason: 'OTP/security code detected (Phase 2 detector)',
      propose_rule: true,
      ttl_minutes: 15  // OTPs expire quickly
    };
  }

  return null;
}


/**
 * Detect receipts, orders, and shipping notifications
 *
 * Patterns:
 * - "Order #123456 confirmed"
 * - "Your receipt from Amazon"
 * - "Shipped: tracking #..."
 * - "Delivered: your package"
 *
 * @param {Object} email - { subject, snippet, from }
 * @returns {Object|null} Classification or null
 */
function detectReceipt(email) {
  const text = `${email.subject} ${email.snippet}`.toLowerCase();

  // Receipt/order lifecycle keywords
  const receiptPatterns = [
    /\border\s?(number|#|id|confirmation)?\s?#?\w{5,}/i,
    /\b(receipt|invoice|purchase|payment|transaction)\b/i,
    /(shipped|delivered|tracking|out for delivery|order placed)/i,
    /\$\d+\.\d{2}.*\b(total|subtotal|amount|charged|paid)\b/i,
    /you (sent|paid|received).{0,20}\$\d+/i,  // PayPal, Venmo
    /\b(order|item|package).{0,20}(confirmed|received|processed|shipped)/i
  ];

  const hasReceiptPattern = receiptPatterns.some(pattern => pattern.test(text));

  if (hasReceiptPattern) {
    return {
      type: 'receipt',
      type_conf: 0.92,
      attention: 'none',
      attention_conf: 0.90,
      importance: 'routine',  // Per TAXONOMY.md: receipts are routine by default
      importance_conf: 0.90,
      client_label: computeClientLabel('receipt', 'routine'),  // → receipts
      relationship: 'from_unknown',
      relationship_conf: 0.70,
      decider: 'rule',
      reason: 'Receipt/order lifecycle detected (Phase 2 detector)',
      propose_rule: true
    };
  }

  return null;
}


/**
 * Detect calendar events and meeting notifications
 *
 * Patterns:
 * - "Notification: Meeting @ Wed..."
 * - "Don't forget: Event starts in 1 hour"
 * - Google Calendar event format
 * - Zoom/Meet links with date/time
 *
 * @param {Object} email - { subject, snippet, from }
 * @returns {Object|null} Classification or null
 */
function detectCalendarEvent(email) {
  const text = `${email.subject} ${email.snippet}`.toLowerCase();
  const subject = email.subject.toLowerCase();

  // Calendar/event patterns
  const eventPatterns = [
    /notification:.{0,50}@.{0,50}(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)/i,
    /(zoom\.us|meet\.google\.com|teams\.microsoft\.com|webex\.com)/i,
    /(starts in|don't forget|reminder|upcoming|tomorrow|today).{0,30}(meeting|event|call|appointment)/i,
    /\b(invitation|invited to|rsvp|calendar|appointment|meeting)\b/i
  ];

  const hasEventPattern = eventPatterns.some(pattern => pattern.test(text));

  // Check for Google Calendar sender
  const isFromGoogleCalendar = email.from.toLowerCase().includes('calendar-notification@google.com');

  if (hasEventPattern || isFromGoogleCalendar) {
    // Check if imminent (contains time-sensitive keywords)
    const isImminent = /(starts in|in \d+ (hour|minute)|don't forget|reminder|today|tomorrow)/i.test(text);

    // Check if post-event (recording, replay, follow-up)
    const isPostEvent = /(recording|replay|watch the|session video|thank you for (attending|joining))/i.test(text);

    // Per TAXONOMY.md: AttentionType = Literal["action_required", "none"]
    // 'follow_up' is NOT a valid value
    let attention = 'none';
    let attention_conf = 0.85;
    let importance = 'routine';

    if (isImminent) {
      attention = 'action_required';
      attention_conf = 0.95;
      importance = 'time_sensitive';
    } else if (isPostEvent) {
      // Post-event emails are routine, not action-required
      attention = 'none';
      attention_conf = 0.88;
      importance = 'routine';
    } else {
      // Upcoming events are time_sensitive
      importance = 'time_sensitive';
    }

    return {
      type: 'event',
      type_conf: 0.94,
      attention: attention,
      attention_conf: attention_conf,
      importance: importance,
      importance_conf: 0.90,
      client_label: computeClientLabel('event', importance),  // → everything-else or action-required
      relationship: 'from_unknown',
      relationship_conf: 0.70,
      decider: 'rule',
      reason: isImminent
        ? 'Imminent calendar event detected (Phase 2 detector)'
        : isPostEvent
        ? 'Post-event follow-up detected (Phase 2 detector)'
        : 'Calendar event detected (Phase 2 detector)',
      propose_rule: true,
      phase: isImminent ? 'pre_event' : isPostEvent ? 'post_event' : 'live'
    };
  }

  return null;
}


/**
 * Detect proxy votes and shareholder notices (finance)
 *
 * Patterns:
 * - "Cast your proxy vote"
 * - "Shareholder meeting notice"
 * - "Vote now on..."
 *
 * @param {Object} email - { subject, snippet, from }
 * @returns {Object|null} Classification or null
 */
function detectProxyVote(email) {
  const text = `${email.subject} ${email.snippet}`.toLowerCase();

  const proxyPatterns = [
    /\b(proxy vote|vote now|cast your vote|shareholder|proxy statement|annual meeting|voting rights)\b/i
  ];

  const hasProxyPattern = proxyPatterns.some(pattern => pattern.test(text));

  if (hasProxyPattern) {
    return {
      type: 'notification',
      type_conf: 0.96,
      attention: 'action_required',
      attention_conf: 0.94,
      importance: 'time_sensitive',  // Proxy votes have deadlines but aren't critical
      importance_conf: 0.92,
      client_label: computeClientLabel('notification', 'time_sensitive'),  // → everything-else
      relationship: 'from_unknown',
      relationship_conf: 0.70,
      decider: 'rule',
      reason: 'Proxy vote/shareholder notice detected (Phase 2 detector)',
      propose_rule: true
    };
  }

  return null;
}


/**
 * Detect account security changes and alerts
 *
 * Patterns:
 * - "Your password was updated"
 * - "Security alert"
 * - "Address changed"
 *
 * @param {Object} email - { subject, snippet, from }
 * @returns {Object|null} Classification or null
 */
function detectAccountSecurity(email) {
  const text = `${email.subject} ${email.snippet}`.toLowerCase();

  const securityPatterns = [
    /your (password|email|address|phone|travel).{0,20}(updated|changed|modified)/i,
    /\b(security alert|account (change|update)|suspicious activity|unusual sign-in)\b/i,
    /we (noticed|detected).{0,30}(activity|sign-in|login)/i
  ];

  const hasSecurityPattern = securityPatterns.some(pattern => pattern.test(text));

  if (hasSecurityPattern) {
    return {
      type: 'notification',
      type_conf: 0.93,
      attention: 'none',  // Per TAXONOMY.md: AttentionType = Literal["action_required", "none"]
      attention_conf: 0.88,
      importance: 'critical',  // Security changes are critical per guardrails
      importance_conf: 0.90,
      client_label: computeClientLabel('notification', 'critical'),  // → action-required
      relationship: 'from_unknown',
      relationship_conf: 0.70,
      decider: 'rule',
      reason: 'Account security change detected (Phase 2 detector)',
      propose_rule: true
    };
  }

  return null;
}


/**
 * Detect PDF receipt attachments from known senders
 *
 * Patterns:
 * - Email has PDF attachment
 * - Filename contains receipt/invoice/statement keywords
 *
 * @param {Object} email - { subject, snippet, from, attachments }
 * @returns {Object|null} Classification or null
 */
function detectPdfReceipt(email) {
  // Check if email has PDF attachments
  if (!email.attachments || !email.attachments.hasPdf) {
    return null;
  }

  // Check for receipt-related keywords in PDF filenames
  const pdfNames = (email.attachments.pdfFilenames || []).join(' ').toLowerCase();
  const hasReceiptKeyword = /\b(receipt|invoice|statement|bill|payment|order)\b/i.test(pdfNames);

  // Only classify as receipt when attachment metadata signals a receipt.
  // Previously we whitelisted specific senders which caused personal mail to be mis-filed.
  if (hasReceiptKeyword) {
    return {
      type: 'receipt',
      type_conf: 0.94,
      attention: 'none',
      attention_conf: 0.92,
      importance: 'routine',  // Per TAXONOMY.md: receipts are routine by default
      importance_conf: 0.92,
      client_label: computeClientLabel('receipt', 'routine'),  // → receipts
      relationship: 'from_unknown',
      relationship_conf: 0.70,
      decider: 'rule',
      reason: 'PDF receipt attachment detected (Phase 2 detector)',
      propose_rule: true
    };
  }

  return null;
}


/**
 * Run all detectors in sequence (Phase 2)
 *
 * Detectors are ordered by precision (highest first):
 * 1. OTP (very specific pattern, high confidence)
 * 2. PDF receipts (high precision for attachment-based receipts)
 * 3. Proxy vote (rare but high-value)
 * 4. Receipt/order (common, high precision)
 * 5. Calendar events (common, moderate precision)
 * 6. Account security (moderate precision)
 *
 * @param {Object} email - { subject, snippet, from, attachments }
 * @returns {Object|null} First matching classification or null
 */
function runDetectors(email) {
  // Order matters: run highest-precision detectors first
  const detectors = [
    detectOTP,
    detectPdfReceipt,  // Check PDF receipts early, before generic receipt detector
    detectProxyVote,
    detectReceipt,
    detectCalendarEvent,
    detectAccountSecurity
  ];

  for (const detector of detectors) {
    const result = detector(email);
    if (result) {
      // Detector hit! Return early to skip LLM
      console.log(`🎯 Phase 2 detector hit: ${detector.name} → ${result.type} (${result.reason})`);
      return result;
    }
  }

  // No detector matched - will fall through to LLM
  return null;
}
