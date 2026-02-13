/**
 * Generic order confirmation page detection.
 * Uses URL heuristics and content signals to determine
 * if the current page is an order confirmation.
 *
 * ES module — imported by capture.js (webpack bundled).
 */

const CONFIRMATION_URL_PATTERNS = [
  /\/order-confirmation/i,
  /\/checkout\/thank-?you/i,
  /\/order\/complete/i,
  /\/gp\/buy\/thankyou/i,
  /\/checkout\/success/i,
  /\/order\/success/i,
  /\/purchase\/confirmed/i,
];

const CONFIRMATION_TEXT_SIGNALS = [
  /order\s+(has been\s+)?confirmed/i,
  /thank\s+you\s+for\s+your\s+order/i,
  /order\s*#\s*\d/i,
  /your\s+order\s+has\s+been\s+placed/i,
  /order\s+placed\s+successfully/i,
];

/**
 * Check if the current page is an order confirmation page.
 *
 * @returns {boolean}
 */
export function isOrderConfirmationPage() {
  const url = window.location.href;

  // Check URL patterns
  for (const pattern of CONFIRMATION_URL_PATTERNS) {
    if (pattern.test(url)) {
      return true;
    }
  }

  // Check page text content (limited to visible text, first 5000 chars for perf)
  const bodyText = (document.body?.innerText || '').slice(0, 5000);
  for (const pattern of CONFIRMATION_TEXT_SIGNALS) {
    if (pattern.test(bodyText)) {
      return true;
    }
  }

  return false;
}
