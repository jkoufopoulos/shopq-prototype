/**
 * Amazon-specific DOM scraping for the thank-you page.
 * Targets: /gp/buy/thankyou
 *
 * ES module — imported by capture.js (webpack bundled).
 */

const AMAZON_ORDER_ID_REGEX = /\d{3}-\d{7}-\d{7}/;

/**
 * Scrape order data from an Amazon order confirmation page.
 *
 * @returns {{ order_id: string, items: string[], amount: number|null, order_date: string } | null}
 */
export function scrapeAmazonOrder() {
  // Only run on the thank-you page
  if (!window.location.pathname.includes('/gp/buy/thankyou')) {
    return null;
  }

  const pageText = document.body?.innerText || '';

  // Extract order ID
  const orderIdMatch = pageText.match(AMAZON_ORDER_ID_REGEX);
  if (!orderIdMatch) {
    console.log('[Reclaim:Amazon] No order ID found on page');
    return null;
  }
  const order_id = orderIdMatch[0];

  // Extract items from order summary
  const items = extractItems();

  // Extract order total
  const amount = extractAmount(pageText);

  // Order date = today (confirmation page = just ordered)
  const order_date = new Date().toISOString().split('T')[0];

  return { order_id, items, amount, order_date };
}

/**
 * Extract item names from the order summary section.
 *
 * @returns {string[]}
 */
function extractItems() {
  const items = [];

  // Amazon thank-you page product titles — try multiple selectors
  const selectors = [
    '.a-fixed-left-grid .a-col-right .a-row:first-child',
    '.item-title',
    '.product-title',
    '[data-component="purchasedItems"] .a-text-bold',
  ];

  for (const selector of selectors) {
    const elements = document.querySelectorAll(selector);
    if (elements.length > 0) {
      elements.forEach(el => {
        const text = el.textContent?.trim();
        if (text && text.length > 2 && text.length < 200) {
          items.push(text);
        }
      });
      if (items.length > 0) break;
    }
  }

  // Fallback: look for any product-looking text near the order ID
  if (items.length === 0) {
    const headings = document.querySelectorAll('h5, h6, .a-text-bold');
    headings.forEach(el => {
      const text = el.textContent?.trim();
      if (text && text.length > 10 && text.length < 200 && !text.includes('Order') && !text.includes('Total')) {
        items.push(text);
      }
    });
  }

  return items;
}

/**
 * Extract the order total amount.
 *
 * @param {string} pageText
 * @returns {number|null}
 */
function extractAmount(pageText) {
  // Look for "Order Total: $XX.XX" pattern
  const totalMatch = pageText.match(/Order\s+Total[:\s]*\$?([\d,]+\.?\d*)/i);
  if (totalMatch) {
    const amount = parseFloat(totalMatch[1].replace(/,/g, ''));
    if (!isNaN(amount)) return amount;
  }

  // Fallback: "Grand Total: $XX.XX"
  const grandMatch = pageText.match(/Grand\s+Total[:\s]*\$?([\d,]+\.?\d*)/i);
  if (grandMatch) {
    const amount = parseFloat(grandMatch[1].replace(/,/g, ''));
    if (!isNaN(amount)) return amount;
  }

  return null;
}
