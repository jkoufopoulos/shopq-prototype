/**
 * P5: Rules Extraction (FREE)
 *
 * Regex-based extraction of structured data from emails:
 * - order_id, tracking_number (reuses linker patterns)
 * - amount, currency
 * - dates (purchase, ship, delivery, return_by)
 * - return_portal_link
 * - item_summary from subject
 * - Return anchor detection for on-demand LLM enrichment
 *
 * Note: This is FREE extraction using rules only.
 * LLM extraction happens on-demand in Phase 5.
 */

const EXTRACTOR_LOG_PREFIX = '[ReturnWatch:Extractor]';

// ============================================================
// DATE EXTRACTION PATTERNS
// ============================================================

/**
 * Patterns for extracting dates from email content.
 * These capture various date formats commonly used in commerce emails.
 */
const DATE_PATTERNS = {
  // ISO format: 2024-01-15
  iso: /(\d{4}-\d{2}-\d{2})/,

  // US format: January 15, 2024 or Jan 15, 2024
  us_long: /(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}/gi,

  // US short: 01/15/2024 or 1/15/24
  us_short: /(\d{1,2}\/\d{1,2}\/\d{2,4})/g,

  // Relative: "by December 15" or "before January 20"
  relative: /(?:by|before|until)\s+((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,?\s+\d{4})?)/gi,
};

/**
 * Month name to number mapping.
 */
const MONTH_MAP = {
  'january': 0, 'jan': 0,
  'february': 1, 'feb': 1,
  'march': 2, 'mar': 2,
  'april': 3, 'apr': 3,
  'may': 4,
  'june': 5, 'jun': 5,
  'july': 6, 'jul': 6,
  'august': 7, 'aug': 7,
  'september': 8, 'sep': 8,
  'october': 9, 'oct': 9,
  'november': 10, 'nov': 10,
  'december': 11, 'dec': 11,
};

// ============================================================
// AMOUNT EXTRACTION PATTERNS
// ============================================================

/**
 * Patterns for extracting purchase amounts.
 */
const EXTRACTOR_AMOUNT_PATTERNS = [
  // Total: $123.45 or Grand Total: $1,234.56
  /(?:total|grand total|order total)[:\s]+\$?([\d,]+\.\d{2})/i,

  // Charged: $123.45
  /(?:charged|charge|payment)[:\s]+\$?([\d,]+\.\d{2})/i,

  // $123.45 (standalone with context)
  /(?:amount|price|subtotal)[:\s]+\$?([\d,]+\.\d{2})/i,
];

// ============================================================
// RETURN POLICY PATTERNS (for anchor detection)
// ============================================================

/**
 * Patterns that indicate return policy information is present.
 * These are "anchors" that signal LLM enrichment may be valuable.
 */
const RETURN_ANCHOR_PATTERNS = [
  // Explicit return window
  /(\d+)\s*(?:day|days)\s*(?:return|refund)/i,
  /return\s*(?:within|by)\s*(\d+)\s*(?:day|days)/i,
  /(?:return|refund)\s*policy/i,
  /(?:return|refund)\s*window/i,

  // Return deadline
  /return\s*(?:by|before|until)/i,
  /(?:return|refund)\s*deadline/i,

  // Return portal links
  /(?:start|initiate)\s*(?:a\s*)?return/i,
  /(?:return|returns)\s*(?:center|portal)/i,

  // Final sale indicators (negative anchor - no return possible)
  /final\s*sale/i,
  /no\s*returns?/i,
  /non-?returnable/i,
  /all\s*sales\s*final/i,
];

/**
 * Patterns for extracting return portal URLs.
 */
const RETURN_PORTAL_PATTERNS = [
  // Common return portal URL patterns
  /https?:\/\/[^\s"'<>]+(?:return|returns)[^\s"'<>]*/gi,
  /https?:\/\/[^\s"'<>]*narvar[^\s"'<>]*/gi,
  /https?:\/\/[^\s"'<>]*returnly[^\s"'<>]*/gi,
  /https?:\/\/[^\s"'<>]*loop[^\s"'<>]*return[^\s"'<>]*/gi,
];

// ============================================================
// EXTRACTION FUNCTIONS
// ============================================================

/**
 * Parse a date string into ISO format (YYYY-MM-DD).
 *
 * @param {string} dateStr - Date string to parse
 * @returns {string|null} ISO date string or null
 */
function parseDateToISO(dateStr) {
  if (!dateStr) return null;

  try {
    // Try ISO format first
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      return dateStr;
    }

    // Try US short format: MM/DD/YYYY or M/D/YY
    const usShortMatch = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
    if (usShortMatch) {
      let [, month, day, year] = usShortMatch;
      if (year.length === 2) {
        year = year > '50' ? '19' + year : '20' + year;
      }
      return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    }

    // Try long format: January 15, 2024
    const longMatch = dateStr.match(/([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})/);
    if (longMatch) {
      const [, monthName, day, year] = longMatch;
      const month = MONTH_MAP[monthName.toLowerCase()];
      if (month !== undefined) {
        return `${year}-${String(month + 1).padStart(2, '0')}-${day.padStart(2, '0')}`;
      }
    }

    // Fallback: try Date.parse
    const parsed = new Date(dateStr);
    if (!isNaN(parsed.getTime())) {
      return parsed.toISOString().split('T')[0];
    }
  } catch {
    // Parsing failed
  }

  return null;
}

/**
 * Extract all dates from text.
 *
 * @param {string} text
 * @returns {string[]} Array of ISO date strings
 */
function extractDates(text) {
  if (!text) return [];

  const dates = new Set();

  // ISO dates
  const isoMatches = text.match(DATE_PATTERNS.iso);
  if (isoMatches) {
    isoMatches.forEach(d => {
      const parsed = parseDateToISO(d);
      if (parsed) dates.add(parsed);
    });
  }

  // US long dates
  const usLongMatches = text.match(DATE_PATTERNS.us_long);
  if (usLongMatches) {
    usLongMatches.forEach(d => {
      const parsed = parseDateToISO(d);
      if (parsed) dates.add(parsed);
    });
  }

  // US short dates
  const usShortMatches = text.match(DATE_PATTERNS.us_short);
  if (usShortMatches) {
    usShortMatches.forEach(d => {
      const parsed = parseDateToISO(d);
      if (parsed) dates.add(parsed);
    });
  }

  return Array.from(dates).sort();
}

/**
 * Extract purchase date from email.
 * Looks for contextual clues like "ordered on", "purchased", etc.
 *
 * @param {string} text
 * @returns {string|null} ISO date or null
 */
function extractPurchaseDate(text) {
  if (!text) return null;

  const patterns = [
    /(?:ordered|purchased|placed)\s*(?:on)?\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:order|purchase)\s*date\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:ordered|purchased|placed)\s*(?:on)?\s*:?\s*(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const parsed = parseDateToISO(match[1]);
      if (parsed) return parsed;
    }
  }

  return null;
}

/**
 * Extract ship date from email.
 *
 * @param {string} text
 * @returns {string|null} ISO date or null
 */
function extractShipDate(text) {
  if (!text) return null;

  const patterns = [
    /(?:shipped|dispatched)\s*(?:on)?\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:ship|shipping)\s*date\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:shipped|dispatched)\s*(?:on)?\s*:?\s*(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const parsed = parseDateToISO(match[1]);
      if (parsed) return parsed;
    }
  }

  return null;
}

/**
 * Extract ACTUAL delivery date from email (past tense - item was delivered).
 * This is for delivery confirmation emails.
 *
 * @param {string} text
 * @returns {string|null} ISO date or null
 */
function extractActualDeliveryDate(text) {
  if (!text) return null;

  // Patterns for ACTUAL delivery (past tense)
  const patterns = [
    /(?:delivered|was delivered)\s*(?:on)?\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:delivery|delivered)\s*date\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:delivered|was delivered)\s*(?:on)?\s*:?\s*(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
    /your (?:package|order|item) (?:has been |was )?delivered/i,  // Just a trigger, date from context
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const parsed = parseDateToISO(match[1]);
      if (parsed) return parsed;
    }
  }

  return null;
}

/**
 * Extract ESTIMATED delivery date from email (future tense - expected arrival).
 * This is for order confirmation and shipping emails.
 *
 * @param {string} text
 * @returns {string|null} ISO date or null
 */
function extractEstimatedDeliveryDate(text) {
  if (!text) return null;

  // Patterns for ESTIMATED delivery (future tense)
  const patterns = [
    /(?:arriving|arrives?|expected|estimated)\s*(?:on|by)?\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:arriving|arrives?|expected|estimated)\s*(?:on|by)?\s*:?\s*([A-Za-z]+\s+\d{1,2})/i,
    /(?:delivery|arrival)\s*(?:date|estimate)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:estimated|expected)\s*(?:delivery|arrival)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:get it|receive it|arrives?)\s*(?:by)?\s*([A-Za-z]+\.?\s+\d{1,2})/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const parsed = parseDateToISO(match[1]);
      if (parsed) return parsed;
    }
  }

  return null;
}

/**
 * Extract delivery date from email.
 * Returns actual delivery date if found, otherwise estimated.
 *
 * @deprecated Use extractActualDeliveryDate and extractEstimatedDeliveryDate separately
 * @param {string} text
 * @returns {string|null} ISO date or null
 */
function extractDeliveryDate(text) {
  // First try actual delivery date
  const actual = extractActualDeliveryDate(text);
  if (actual) return actual;

  // Fall back to estimated
  return extractEstimatedDeliveryDate(text);
}

/**
 * Extract explicit return-by date from email.
 *
 * @param {string} text
 * @returns {string|null} ISO date or null
 */
function extractReturnByDate(text) {
  if (!text) return null;

  const patterns = [
    /return\s*(?:by|before|until)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:return|refund)\s*deadline\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
    /(?:eligible\s*for\s*return\s*until|returns?\s*accepted\s*until)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const parsed = parseDateToISO(match[1]);
      if (parsed) return parsed;
    }
  }

  return null;
}

/**
 * Extract return window in days.
 *
 * @param {string} text
 * @returns {number|null}
 */
function extractReturnWindowDays(text) {
  if (!text) return null;

  const patterns = [
    /(\d+)\s*(?:day|days)\s*(?:return|refund)/i,
    /return\s*(?:within|in)\s*(\d+)\s*(?:day|days)/i,
    /(\d+)\s*(?:day|days)\s*(?:to\s*return|money\s*back)/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const days = parseInt(match[1], 10);
      if (days > 0 && days <= 365) {
        return days;
      }
    }
  }

  return null;
}

/**
 * Extract purchase amount.
 *
 * @param {string} text
 * @returns {{amount: number|null, currency: string}}
 */
function extractAmount(text) {
  if (!text) return { amount: null, currency: 'USD' };

  for (const pattern of EXTRACTOR_AMOUNT_PATTERNS) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const amount = parseFloat(match[1].replace(/,/g, ''));
      if (!isNaN(amount) && amount > 0) {
        return { amount, currency: 'USD' };
      }
    }
  }

  // Fallback: look for any dollar amount
  const dollarMatch = text.match(/\$([\d,]+\.\d{2})/);
  if (dollarMatch) {
    const amount = parseFloat(dollarMatch[1].replace(/,/g, ''));
    if (!isNaN(amount) && amount > 0) {
      return { amount, currency: 'USD' };
    }
  }

  return { amount: null, currency: 'USD' };
}

/**
 * Extract return portal link.
 *
 * @param {string} text
 * @returns {string|null}
 */
function extractReturnPortalLink(text) {
  if (!text) return null;

  for (const pattern of RETURN_PORTAL_PATTERNS) {
    const matches = text.match(pattern);
    if (matches && matches[0]) {
      // Clean up the URL
      let url = matches[0];
      // Remove trailing punctuation
      url = url.replace(/[.,;:!?)]+$/, '');
      return url;
    }
  }

  return null;
}

/**
 * Extract item summary from subject line.
 * Falls back to first line of body if subject doesn't have useful info.
 *
 * @param {string} subject
 * @param {string} [body]
 * @returns {string}
 */
function extractItemSummary(subject, body = '') {
  if (!subject) return 'Unknown item';

  // Remove common prefixes
  let summary = subject
    .replace(/^(re:|fwd?:|order confirmation|your order|order #?\d+[-\s]?)/gi, '')
    .replace(/^(thanks for your order|thank you for your order)/gi, '')
    .replace(/^(shipped?|delivered|on the way|arriving)/gi, '')
    .trim();

  // Remove order numbers from the end
  summary = summary.replace(/\s*[-–]\s*order\s*#?\s*[\w-]+$/i, '').trim();

  // If we have something meaningful, use it
  if (summary.length > 3 && summary.length < 100) {
    return summary;
  }

  // Fallback: use cleaned subject
  return subject.substring(0, 50).trim() || 'Unknown item';
}

/**
 * Detect if email has return policy anchors.
 * If true, on-demand LLM enrichment may be valuable.
 *
 * @param {string} text
 * @returns {{hasAnchors: boolean, isFinalSale: boolean, anchors: string[]}}
 */
function detectReturnAnchors(text) {
  if (!text) return { hasAnchors: false, isFinalSale: false, anchors: [] };

  const anchors = [];
  let isFinalSale = false;

  for (const pattern of RETURN_ANCHOR_PATTERNS) {
    const match = text.match(pattern);
    if (match) {
      const anchor = match[0].toLowerCase();
      if (anchor.includes('final sale') || anchor.includes('no return') || anchor.includes('non-returnable') || anchor.includes('all sales final')) {
        isFinalSale = true;
      }
      anchors.push(match[0]);
    }
  }

  return {
    hasAnchors: anchors.length > 0,
    isFinalSale,
    anchors,
  };
}

/**
 * Full extraction: extract all fields from email content.
 *
 * @param {string} subject
 * @param {string} snippet
 * @param {string} [body]
 * @returns {ExtractedFields}
 */
function extractFields(subject, snippet, body = '') {
  const text = `${subject || ''}\n${snippet || ''}\n${body || ''}`;

  // Reuse linker functions for primary keys
  const order_id = extractOrderId(text);
  const tracking_number = extractTrackingNumber(text);

  // Extract dates
  const purchase_date = extractPurchaseDate(text);
  const ship_date = extractShipDate(text);
  // Extract both actual and estimated delivery dates separately
  const actual_delivery_date = extractActualDeliveryDate(text);
  const estimated_delivery_date = extractEstimatedDeliveryDate(text);
  // For backwards compatibility, delivery_date is actual if found, otherwise estimated
  const delivery_date = actual_delivery_date || estimated_delivery_date;
  const explicit_return_by_date = extractReturnByDate(text);
  const return_window_days = extractReturnWindowDays(text);

  // Extract amount
  const { amount, currency } = extractAmount(text);

  // Extract return portal
  const return_portal_link = extractReturnPortalLink(text);

  // Extract item summary
  const item_summary = extractItemSummary(subject, body);

  // Detect return anchors for on-demand enrichment
  const returnAnchors = detectReturnAnchors(text);

  const result = {
    order_id,
    tracking_number,
    purchase_date,
    ship_date,
    delivery_date,
    actual_delivery_date,
    estimated_delivery_date,
    explicit_return_by_date,
    return_window_days,
    amount,
    currency,
    return_portal_link,
    item_summary,
    hasReturnAnchors: returnAnchors.hasAnchors,
    isFinalSale: returnAnchors.isFinalSale,
    returnAnchors: returnAnchors.anchors,
  };

  console.log(EXTRACTOR_LOG_PREFIX, 'Extracted fields:', JSON.stringify(result, null, 2));

  return result;
}

/**
 * @typedef {Object} ExtractedFields
 * @property {string|null} order_id
 * @property {string|null} tracking_number
 * @property {string|null} purchase_date
 * @property {string|null} ship_date
 * @property {string|null} delivery_date - Actual or estimated (for backwards compatibility)
 * @property {string|null} actual_delivery_date - Actual confirmed delivery date
 * @property {string|null} estimated_delivery_date - Estimated/expected delivery date
 * @property {string|null} explicit_return_by_date
 * @property {number|null} return_window_days
 * @property {number|null} amount
 * @property {string} currency
 * @property {string|null} return_portal_link
 * @property {string} item_summary
 * @property {boolean} hasReturnAnchors
 * @property {boolean} isFinalSale
 * @property {string[]} returnAnchors
 */
