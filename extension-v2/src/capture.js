/**
 * Reclaim v2 Content Script
 * Detects order confirmation pages and captures order data.
 *
 * Webpack entry point — bundled to dist/capture.bundle.js.
 */

import { isOrderConfirmationPage } from '../modules/capture/detector.js';
import { scrapeAmazonOrder } from '../modules/capture/amazon.js';

const LOG_PREFIX = '[Reclaim:Capture]';

/**
 * Deduplicate flag key for this page.
 * Prevents re-capturing if the content script runs again on the same page.
 */
function getCaptureFlag() {
  return `reclaim_captured_${window.location.href}`;
}

/**
 * Check if this page was already captured in this session.
 */
function alreadyCaptured() {
  try {
    return sessionStorage.getItem(getCaptureFlag()) === '1';
  } catch {
    return false;
  }
}

/**
 * Mark this page as captured.
 */
function markCaptured() {
  try {
    sessionStorage.setItem(getCaptureFlag(), '1');
  } catch {
    // sessionStorage may be unavailable
  }
}

/**
 * Determine merchant domain from the current page hostname.
 * Strips www. prefix and returns the base domain.
 *
 * @returns {string}
 */
function getMerchantDomain() {
  return window.location.hostname.replace(/^www\./, '');
}

/**
 * Determine a display-friendly merchant name from the domain.
 *
 * @param {string} domain
 * @returns {string}
 */
function getMerchantName(domain) {
  const names = {
    'amazon.com': 'Amazon',
    'amazon.co.uk': 'Amazon UK',
    'amazon.ca': 'Amazon CA',
  };
  return names[domain] || domain.split('.')[0].charAt(0).toUpperCase() + domain.split('.')[0].slice(1);
}

/**
 * Main capture flow.
 */
function run() {
  // Guard: already captured this page
  if (alreadyCaptured()) {
    console.log(LOG_PREFIX, 'Already captured this page, skipping');
    return;
  }

  // Step 1: Is this an order confirmation page?
  if (!isOrderConfirmationPage()) {
    return;
  }

  console.log(LOG_PREFIX, 'Order confirmation page detected:', window.location.href);

  // Step 2: Identify merchant
  const domain = getMerchantDomain();

  // Step 3: Scrape order data (merchant-specific)
  let orderData = null;

  if (domain.includes('amazon.')) {
    orderData = scrapeAmazonOrder();
  }

  // Future: add more merchant scrapers here
  // if (domain.includes('target.')) { ... }

  if (!orderData) {
    console.log(LOG_PREFIX, 'Could not scrape order data from', domain);
    return;
  }

  // Step 4: Send to service worker
  const message = {
    type: 'ORDER_CAPTURED',
    data: {
      merchant_domain: domain,
      merchant_name: getMerchantName(domain),
      order_id: orderData.order_id,
      items: orderData.items,
      amount: orderData.amount,
      order_date: orderData.order_date,
      capture_url: window.location.href,
    },
  };

  console.log(LOG_PREFIX, 'Sending captured order:', message.data.order_id);

  chrome.runtime.sendMessage(message, (response) => {
    if (chrome.runtime.lastError) {
      console.error(LOG_PREFIX, 'Failed to send message:', chrome.runtime.lastError.message);
      return;
    }
    if (response?.success) {
      console.log(LOG_PREFIX, 'Order saved successfully:', response.order_key);
      markCaptured();
    } else {
      console.error(LOG_PREFIX, 'Order save failed:', response?.error);
    }
  });
}

// Run after DOM is ready
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  run();
} else {
  document.addEventListener('DOMContentLoaded', run);
}
