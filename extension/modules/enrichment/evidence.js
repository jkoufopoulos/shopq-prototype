/**
 * Evidence Validation
 *
 * Validates that LLM-extracted values appear literally in source quotes.
 * This prevents hallucinations from polluting order data.
 *
 * Rule: Extracted date/number MUST appear verbatim in the evidence_quote.
 */

const EVIDENCE_LOG_PREFIX = '[ReturnWatch:Evidence]';

// ============================================================
// VALIDATION FUNCTIONS
// ============================================================

/**
 * Normalize text for comparison.
 * - Lowercase
 * - Remove extra whitespace
 * - Normalize dashes/hyphens
 *
 * @param {string} text
 * @returns {string}
 */
function normalizeText(text) {
  if (!text) return '';
  return text
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/[–—−]/g, '-')  // Normalize dashes
    .trim();
}

/**
 * Check if a date appears in the quote.
 * Handles multiple formats:
 * - ISO: 2024-01-15
 * - US: January 15, 2024 or Jan 15, 2024
 * - Numeric: 1/15/2024 or 01/15/2024
 *
 * @param {string} quote - The evidence quote
 * @param {string} date - ISO date string (YYYY-MM-DD)
 * @returns {boolean}
 */
function dateAppearsInQuote(quote, date) {
  if (!quote || !date) return false;

  const normalizedQuote = normalizeText(quote);
  const normalizedDate = normalizeText(date);

  // Direct ISO match
  if (normalizedQuote.includes(normalizedDate)) {
    return true;
  }

  // Parse the date
  const [year, month, day] = date.split('-').map(s => parseInt(s, 10));
  if (!year || !month || !day) return false;

  const monthNames = [
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december'
  ];
  const monthAbbrevs = [
    'jan', 'feb', 'mar', 'apr', 'may', 'jun',
    'jul', 'aug', 'sep', 'oct', 'nov', 'dec'
  ];

  const monthName = monthNames[month - 1];
  const monthAbbrev = monthAbbrevs[month - 1];

  // Check various formats
  const formats = [
    // January 15, 2024
    `${monthName} ${day}, ${year}`,
    `${monthName} ${day} ${year}`,
    // Jan 15, 2024
    `${monthAbbrev} ${day}, ${year}`,
    `${monthAbbrev} ${day} ${year}`,
    // 1/15/2024 and 01/15/2024
    `${month}/${day}/${year}`,
    `${String(month).padStart(2, '0')}/${String(day).padStart(2, '0')}/${year}`,
    // 1/15/24
    `${month}/${day}/${String(year).slice(-2)}`,
  ];

  for (const format of formats) {
    if (normalizedQuote.includes(format)) {
      return true;
    }
  }

  return false;
}

/**
 * Check if a number of days appears in the quote.
 *
 * @param {string} quote - The evidence quote
 * @param {number} days - Number of days
 * @returns {boolean}
 */
function daysAppearsInQuote(quote, days) {
  if (!quote || days === null || days === undefined) return false;

  const normalizedQuote = normalizeText(quote);
  const daysStr = String(days);

  // Patterns to check
  const patterns = [
    `${daysStr} day`,
    `${daysStr}-day`,
    `${daysStr}day`,
  ];

  for (const pattern of patterns) {
    if (normalizedQuote.includes(pattern)) {
      return true;
    }
  }

  return false;
}

/**
 * Check if an amount appears in the quote.
 *
 * @param {string} quote - The evidence quote
 * @param {number} amount - Dollar amount
 * @returns {boolean}
 */
function amountAppearsInQuote(quote, amount) {
  if (!quote || amount === null || amount === undefined) return false;

  const normalizedQuote = normalizeText(quote);

  // Format with 2 decimal places
  const formatted = amount.toFixed(2);
  const withCommas = amount >= 1000
    ? amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : formatted;

  // Check both formats
  if (normalizedQuote.includes(`$${formatted}`) ||
      normalizedQuote.includes(`$${withCommas}`) ||
      normalizedQuote.includes(formatted) ||
      normalizedQuote.includes(withCommas)) {
    return true;
  }

  return false;
}

// ============================================================
// EVIDENCE EXTRACTION
// ============================================================

/**
 * Find the best quote containing the extracted value.
 * Searches for a sentence or clause containing the value.
 *
 * @param {string} body - Full email body
 * @param {string} searchTerm - Value to find
 * @param {number} [contextChars=200] - Characters of context to include
 * @returns {string|null} Quote or null
 */
function findQuoteContaining(body, searchTerm, contextChars = 200) {
  if (!body || !searchTerm) return null;

  const normalizedBody = body;
  const normalizedTerm = searchTerm;

  const index = normalizedBody.toLowerCase().indexOf(normalizedTerm.toLowerCase());
  if (index === -1) return null;

  // Find sentence boundaries
  const start = Math.max(0, index - contextChars / 2);
  const end = Math.min(body.length, index + searchTerm.length + contextChars / 2);

  let quote = body.substring(start, end);

  // Clean up: trim to sentence boundaries if possible
  if (start > 0) {
    const periodIndex = quote.indexOf('. ');
    if (periodIndex !== -1 && periodIndex < quote.length / 3) {
      quote = quote.substring(periodIndex + 2);
    }
  }

  if (end < body.length) {
    const lastPeriod = quote.lastIndexOf('. ');
    if (lastPeriod !== -1 && lastPeriod > quote.length * 2 / 3) {
      quote = quote.substring(0, lastPeriod + 1);
    }
  }

  return quote.trim();
}

/**
 * Find a quote containing a date.
 *
 * @param {string} body - Email body
 * @param {string} date - ISO date to find
 * @returns {string|null}
 */
function findDateQuote(body, date) {
  if (!body || !date) return null;

  const [year, month, day] = date.split('-').map(s => parseInt(s, 10));
  if (!year || !month || !day) return null;

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  // Try different date formats
  const searchTerms = [
    date,
    `${monthNames[month - 1]} ${day}, ${year}`,
    `${monthNames[month - 1]} ${day}`,
    `${month}/${day}/${year}`,
  ];

  for (const term of searchTerms) {
    const quote = findQuoteContaining(body, term);
    if (quote) return quote;
  }

  return null;
}

/**
 * Find a quote containing a return window.
 *
 * @param {string} body - Email body
 * @param {number} days - Days in window
 * @returns {string|null}
 */
function findDaysQuote(body, days) {
  if (!body || days === null) return null;

  const searchTerms = [
    `${days} day`,
    `${days}-day`,
  ];

  for (const term of searchTerms) {
    const quote = findQuoteContaining(body, term);
    if (quote) return quote;
  }

  return null;
}

// ============================================================
// VALIDATION RESULT
// ============================================================

/**
 * Validate LLM extraction against source text.
 *
 * Quote Resolution:
 * - If LLM's quote contains the value, use it
 * - Otherwise, search sourceBody for a quote containing the value
 * - Priority: return_by_date quote > return_window_days quote
 * - Final quote may only contain evidence for one field (acceptable for MVP)
 *
 * @param {Object} extraction - LLM extraction result
 * @param {string} extraction.return_by_date - Extracted return-by date
 * @param {number} extraction.return_window_days - Extracted window
 * @param {string} extraction.evidence_quote - Quote from source
 * @param {string} sourceBody - Original email body
 * @returns {{valid: boolean, errors: string[], validated: Object}}
 */
function validateExtraction(extraction, sourceBody) {
  const errors = [];
  const validated = {};

  if (!extraction) {
    return { valid: false, errors: ['No extraction provided'], validated };
  }

  // Validate return_by_date
  if (extraction.return_by_date) {
    if (extraction.evidence_quote && dateAppearsInQuote(extraction.evidence_quote, extraction.return_by_date)) {
      validated.return_by_date = extraction.return_by_date;
      validated.evidence_quote = extraction.evidence_quote;
      console.log(EVIDENCE_LOG_PREFIX, 'VALIDATED return_by_date:', extraction.return_by_date);
    } else {
      // Try to find the date in the source
      const quote = findDateQuote(sourceBody, extraction.return_by_date);
      if (quote) {
        validated.return_by_date = extraction.return_by_date;
        validated.evidence_quote = quote;
        console.log(EVIDENCE_LOG_PREFIX, 'VALIDATED return_by_date with new quote');
      } else {
        errors.push(`return_by_date "${extraction.return_by_date}" not found in source`);
        console.log(EVIDENCE_LOG_PREFIX, 'REJECTED return_by_date: not found in source');
      }
    }
  }

  // Validate return_window_days
  if (extraction.return_window_days) {
    if (extraction.evidence_quote && daysAppearsInQuote(extraction.evidence_quote, extraction.return_window_days)) {
      validated.return_window_days = extraction.return_window_days;
      if (!validated.evidence_quote) {
        validated.evidence_quote = extraction.evidence_quote;
      }
      console.log(EVIDENCE_LOG_PREFIX, 'VALIDATED return_window_days:', extraction.return_window_days);
    } else {
      // Try to find the days in the source
      const quote = findDaysQuote(sourceBody, extraction.return_window_days);
      if (quote) {
        validated.return_window_days = extraction.return_window_days;
        if (!validated.evidence_quote) {
          validated.evidence_quote = quote;
        }
        console.log(EVIDENCE_LOG_PREFIX, 'VALIDATED return_window_days with new quote');
      } else {
        errors.push(`return_window_days "${extraction.return_window_days}" not found in source`);
        console.log(EVIDENCE_LOG_PREFIX, 'REJECTED return_window_days: not found in source');
      }
    }
  }

  // Consider valid if we got at least one validated field
  const valid = Object.keys(validated).length > 0 && validated.evidence_quote;

  return { valid, errors, validated };
}

/**
 * @typedef {Object} ValidationResult
 * @property {boolean} valid - Whether extraction passed validation
 * @property {string[]} errors - List of validation errors
 * @property {Object} validated - Validated fields only
 * @property {string} [validated.return_by_date]
 * @property {number} [validated.return_window_days]
 * @property {string} [validated.evidence_quote]
 */
