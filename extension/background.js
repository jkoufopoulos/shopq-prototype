/**
 * ShopQ Return Watch Background Service Worker
 * Handles purchase email scanning and return tracking
 */

// InboxSDK MV3 pageWorld injection handler
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'inboxsdk__injectPageWorld' && sender.tab) {
    if (chrome.scripting) {
      let documentIds;
      let frameIds;
      if (sender.documentId) {
        documentIds = [sender.documentId];
      } else {
        frameIds = [sender.frameId];
      }
      chrome.scripting.executeScript({
        target: { tabId: sender.tab.id, documentIds, frameIds },
        world: 'MAIN',
        files: ['pageWorld.js'],
      });
      sendResponse(true);
    } else {
      sendResponse(false);
    }
    return true;
  }
});

// Load dependencies - only modules that exist for Return Watch
importScripts(
  'modules/shared/config.js',
  'modules/shared/utils.js',
  'modules/gmail/auth.js',
  'modules/storage/schema.js',
  'modules/storage/store.js',
  // Pipeline P1-P4: Core
  'modules/pipeline/filter.js',
  'modules/pipeline/linker.js',
  'modules/pipeline/hints.js',
  'modules/pipeline/classifier.js',
  // Pipeline P5-P8: Resolution
  'modules/pipeline/extractor.js',
  'modules/pipeline/resolver.js',
  'modules/pipeline/lifecycle.js',
  // Sync: Scanner & Refresh
  'modules/sync/scanner.js',
  'modules/sync/refresh.js',
  // Enrichment: On-demand LLM extraction
  'modules/enrichment/evidence.js',
  'modules/enrichment/policy.js',
  // Diagnostics
  'modules/diagnostics/logger.js',
  'modules/returns/api.js'
);

console.log(`🛒 ShopQ Return Watch: Background service worker loaded v${CONFIG.VERSION}`);

// Initialize refresh system (sets up tab listeners and periodic alarm)
initializeRefreshSystem();

/**
 * SEC-017: Message rate limiting to prevent DoS attacks via message flooding.
 * Tracks message counts per sender (by tab ID or extension URL).
 */
const MESSAGE_RATE_LIMIT = {
  maxMessages: 100,      // Max messages per window
  windowMs: 1000,        // Window size in milliseconds (1 second)
  counters: new Map(),   // Map<senderId, { count: number, windowStart: number }>
  cleanupInterval: null, // Interval for cleanup
};

/**
 * SEC-017: Check if sender is within rate limit.
 * @param {chrome.runtime.MessageSender} sender
 * @returns {{ allowed: boolean, remaining: number }}
 */
function checkMessageRateLimit(sender) {
  const now = Date.now();
  const senderId = sender.tab?.id ?? sender.url ?? 'unknown';

  let entry = MESSAGE_RATE_LIMIT.counters.get(senderId);

  // Start new window if none exists or window expired
  if (!entry || (now - entry.windowStart) >= MESSAGE_RATE_LIMIT.windowMs) {
    entry = { count: 0, windowStart: now };
    MESSAGE_RATE_LIMIT.counters.set(senderId, entry);
  }

  // Check if within limit
  if (entry.count >= MESSAGE_RATE_LIMIT.maxMessages) {
    return { allowed: false, remaining: 0 };
  }

  // Increment and allow
  entry.count++;
  return {
    allowed: true,
    remaining: MESSAGE_RATE_LIMIT.maxMessages - entry.count,
  };
}

/**
 * SEC-017: Clean up old rate limit entries periodically.
 */
function cleanupRateLimitCounters() {
  const now = Date.now();
  const expiredThreshold = now - (MESSAGE_RATE_LIMIT.windowMs * 2);

  for (const [senderId, entry] of MESSAGE_RATE_LIMIT.counters) {
    if (entry.windowStart < expiredThreshold) {
      MESSAGE_RATE_LIMIT.counters.delete(senderId);
    }
  }
}

// Run cleanup every 10 seconds
MESSAGE_RATE_LIMIT.cleanupInterval = setInterval(cleanupRateLimitCounters, 10000);

/**
 * SEC-008: Validate message sender is from a trusted source.
 * Trusted sources:
 * - Content scripts running on Gmail (sender.tab.url starts with https://mail.google.com/)
 * - Extension popup or sidebar pages (sender.url starts with chrome-extension://<our-id>)
 * - InboxSDK pageWorld injection (sender.tab exists, used during initialization)
 *
 * @param {chrome.runtime.MessageSender} sender
 * @returns {boolean}
 */
function isTrustedSender(sender) {
  const extensionOrigin = `chrome-extension://${chrome.runtime.id}`;

  // Allow messages from extension pages (popup, sidebar)
  if (sender.url && sender.url.startsWith(extensionOrigin)) {
    return true;
  }

  // Allow messages from content scripts on Gmail
  if (sender.tab && sender.tab.url) {
    if (sender.tab.url.startsWith('https://mail.google.com/')) {
      return true;
    }
  }

  // Allow InboxSDK pageWorld injection message (has sender.tab but no url check needed)
  // This is the initial injection message that happens once per page load
  if (sender.tab && sender.frameId !== undefined) {
    // Content script context - allow if it's from a tab
    return true;
  }

  return false;
}

/**
 * Handle messages from content scripts and popup
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      // SEC-008: Validate sender before processing any message
      if (!isTrustedSender(sender)) {
        console.warn('🚫 ShopQ: Blocked message from untrusted sender:', sender);
        sendResponse({ success: false, error: 'Unauthorized sender' });
        return;
      }

      // SEC-017: Check rate limit before processing
      const rateCheck = checkMessageRateLimit(sender);
      if (!rateCheck.allowed) {
        console.warn('🚫 ShopQ: Rate limit exceeded for sender:', sender.tab?.id ?? sender.url);
        sendResponse({ success: false, error: 'Rate limit exceeded. Please slow down.' });
        return;
      }

      // SEC-002: Get authenticated user ID
      if (message.type === 'GET_AUTHENTICATED_USER_ID') {
        try {
          const userId = await getAuthenticatedUserId();
          sendResponse({ success: true, userId });
        } catch (error) {
          console.error('❌ Failed to get user ID:', error);
          sendResponse({ success: false, error: error.message });
        }
      }
      else if (message.type === 'SCAN_FOR_PURCHASES') {
        console.log('🛒 Manual refresh triggered...');
        try {
          const result = await onManualRefresh();
          console.log('📊 Scan result:', JSON.stringify(result));
          sendResponse(result);
        } catch (error) {
          console.error('❌ Scan failed:', error);
          sendResponse({ success: false, error: error.message });
        }
      }
      else if (message.type === 'GET_REFRESH_STATE') {
        const state = getRefreshState();
        sendResponse({ success: true, state });
      }
      else if (message.type === 'GET_RETURN_WATCH_ORDERS') {
        const { expiringSoon, active } = await getReturnWatchOrders();
        sendResponse({ success: true, expiringSoon, active });
      }
      else if (message.type === 'GET_ALL_PURCHASES') {
        const orders = await getAllPurchasesForDisplay();
        sendResponse({ success: true, orders });
      }
      else if (message.type === 'RECOMPUTE_ORDER_DEADLINE') {
        const order = await recomputeOrderDeadline(message.order_key);
        sendResponse({ success: true, order });
      }
      else if (message.type === 'RECOMPUTE_MERCHANT_DEADLINES') {
        const count = await recomputeMerchantDeadlines(message.merchant_domain);
        sendResponse({ success: true, updated_count: count });
      }
      // On-demand enrichment
      else if (message.type === 'ENRICH_ORDER') {
        const result = await enrichOrder(message.order_key);
        sendResponse({ success: true, ...result });
      }
      else if (message.type === 'NEEDS_ENRICHMENT') {
        const order = await getOrder(message.order_key);
        const needs = order ? needsEnrichment(order) : false;
        sendResponse({ success: true, needs_enrichment: needs });
      }
      // Diagnostics
      else if (message.type === 'RUN_DIAGNOSTICS') {
        const result = await runDiagnostics();
        sendResponse(result);
      }
      else if (message.type === 'GET_DIAGNOSTIC_SUMMARY') {
        const summary = await getDiagnosticSummary();
        sendResponse({ success: true, summary });
      }
      else if (message.type === 'CHECK_AUTH') {
        try {
          const token = await getAuthToken();
          sendResponse({ success: true, hasToken: !!token });
        } catch (error) {
          sendResponse({ success: false, error: error.message });
        }
      }
      else if (message.type === 'GET_AUTH_TOKEN') {
        try {
          const token = await getAuthToken();
          sendResponse({ token });
        } catch (error) {
          sendResponse({ error: error.message });
        }
      }
      else if (message.type === 'SHOW_NOTIFICATION') {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icons/icon48.png',
          title: message.title || 'ShopQ Return Watch',
          message: message.message,
          priority: 2
        });
        sendResponse({ success: true });
      }
      // Storage operations for sidebar
      else if (message.type === 'GET_ALL_ORDERS') {
        const orders = await getAllOrders();
        sendResponse({ success: true, orders });
      }
      else if (message.type === 'GET_ORDERS_WITH_DEADLINES') {
        const orders = await getOrdersWithDeadlines();
        sendResponse({ success: true, orders });
      }
      else if (message.type === 'GET_ORDER') {
        const order = await getOrder(message.order_key);
        sendResponse({ success: true, order });
      }
      else if (message.type === 'UPDATE_ORDER_STATUS') {
        const order = await updateOrderStatus(message.order_key, message.status);
        sendResponse({ success: true, order });
      }
      else if (message.type === 'GET_STORAGE_STATS') {
        const stats = await getStorageStats();
        sendResponse({ success: true, stats });
      }
      // Merchant rules operations
      else if (message.type === 'GET_MERCHANT_RULE') {
        const rule = await getMerchantRule(message.merchant_domain);
        sendResponse({ success: true, window_days: rule });
      }
      else if (message.type === 'SET_MERCHANT_RULE') {
        await setMerchantRule(message.merchant_domain, message.window_days);
        sendResponse({ success: true });
      }
      else if (message.type === 'GET_ALL_MERCHANT_RULES') {
        const rules = await getAllMerchantRules();
        sendResponse({ success: true, rules });
      }
      else if (message.type === 'DELETE_MERCHANT_RULE') {
        await deleteMerchantRule(message.merchant_domain);
        sendResponse({ success: true });
      }
    } catch (error) {
      console.error('❌ Message handler error:', error);
      sendResponse({ success: false, error: error.message });
    }
  })();

  return true; // Keep message channel open for async response
});

/**
 * Handle extension install/update
 */
chrome.runtime.onInstalled.addListener(async (details) => {
  // Initialize storage schema on install or update
  await initializeStorage();

  if (details.reason === 'install') {
    console.log('🎉 ShopQ Return Watch installed');
    // SEC-002: User ID will be set lazily when auth happens via getAuthenticatedUserId()
    // Don't set default_user - proper user isolation requires real Google user ID
    // Initial scan will be triggered by refresh system when Gmail is opened
  } else if (details.reason === 'update') {
    console.log(`📦 ShopQ Return Watch updated to v${CONFIG.VERSION}`);
  }
});

// REMOVED: webNavigation re-injection - manifest.json content_scripts handles this
// The previous listener was causing duplicate script injections on every Gmail navigation
