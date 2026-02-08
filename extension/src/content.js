/**
 * Reclaim Content Script (ES Module Entry Point)
 *
 * Bundled by webpack with InboxSDK. Implements the Visual Layer for Gmail.
 *
 * Architecture (Phase 3 refactor):
 *   DisposeBag           — lifecycle cleanup utility
 *   ThreadBadgeManager   — thread row badges (type + critical) via Kefir streams
 *   SidebarMessageRouter — origin-validated postMessage dispatch (replaces if/else chain)
 *   SidebarController    — iframe panel, order CRUD, expiring indicator, nav persistence
 *
 * Cache pattern: write-through (background writes, content reads on InboxSDK handler fire)
 * Disposal: 30-second context check → disposeAll() → refresh banner on extension reload
 */

import * as InboxSDK from '@inboxsdk/core';
import Kefir from 'kefir';
import DOMPurify from 'dompurify';
import {
  API_BASE_URL,
  DIGEST_REFRESH_DEBOUNCE_MS,
  SIDEBAR_REFRESH_INTERVAL_MS,
  LABEL_CACHE_KEY,
  TOAST_DURATION_MS,
  TOAST_FADEOUT_MS,
  EXPIRING_SOON_DAYS,
  CRITICAL_DAYS,
} from './config.js';

// Prevent multiple initializations - use a global flag
if (window.__SHOPQ_INITIALIZED__) {
  console.log('Reclaim: Already initialized, skipping duplicate');
} else {
  window.__SHOPQ_INITIALIZED__ = true;
  initReclaim();
}

function initReclaim() {
console.log('Reclaim: Content script loaded (bundled)');

// =============================================================================
// HTML SANITIZATION (XSS Protection)
// =============================================================================

/**
 * Sanitize HTML content to prevent XSS attacks.
 * Use this for any HTML content from external sources (API responses, etc.)
 * @param {string} html - Raw HTML string
 * @returns {string} Sanitized HTML safe for innerHTML
 */
function sanitizeHtml(html) {
  if (!html) return '';
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'a', 'ul', 'ol', 'li', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'tr', 'td', 'th', 'thead', 'tbody'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'style', 'class'],
    ALLOW_DATA_ATTR: false,
  });
}

// =============================================================================
// MESSAGE HELPERS
// =============================================================================

/**
 * Send a message to the service worker with a timeout.
 * Rejects if no response within timeoutMs (service worker may be suspended).
 */
function sendMessageWithTimeout(message, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Message timeout (${timeoutMs}ms): ${message.type}`));
    }, timeoutMs);

    chrome.runtime.sendMessage(message).then((response) => {
      clearTimeout(timer);
      resolve(response);
    }).catch((err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

// =============================================================================
// CLEANUP: Remove any stale Reclaim elements/styles from previous loads
// =============================================================================

(function cleanupStaleElements() {
  // Remove old drawer/iframe elements only
  // IMPORTANT: Do NOT reset html/body styles - this interferes with Gmail's dark mode
  document.getElementById('reclaim-digest-iframe')?.remove();
  document.getElementById('reclaim-nav-button')?.remove();
  document.getElementById('reclaim-refresh-banner')?.remove();
  document.getElementById('reclaim-layout-styles')?.remove();
  document.getElementById('reclaim-sidebar-panel')?.remove();

  // Remove any Reclaim-specific classes only
  document.documentElement.classList.remove('reclaim-drawer-open');

  console.log('Reclaim: Cleaned up stale elements');
})();

// =============================================================================
// DIGEST REFRESH (for continuous organization)
// =============================================================================

// Global function to trigger digest refresh (set by initializeDigestSidebar)
let triggerDigestRefresh = null;
let lastDigestRefreshTime = 0;

// =============================================================================
// CONFIGURATION
// =============================================================================

// Registered InboxSDK App ID
const SHOPQ_APP_ID = 'sdk_mailqapp_8eb273b616';

// =============================================================================
// THREAD BADGE MANAGER
// =============================================================================

/**
 * Manages thread row badges (type + critical) using InboxSDK Observable streams.
 * Owns the thread row registry, label cache, and all badge rendering logic.
 */
class ThreadBadgeManager {
  static MAX_REGISTRY_SIZE = 500;

  static TYPE_DISPLAY_NAMES = {
    'Event': 'Event',
    'Notification': 'Notif',
    'Newsletter': 'Newsletter',
    'Promotion': 'Promo',
    'Receipt': 'Receipt',
    'Message': 'Message',
    'Otp': 'OTP'
  };

  static CLIENT_LABEL_TO_TYPE = {
    'receipts': 'Receipt',
    'messages': 'Message',
    'action-required': null
  };

  static TYPE_COLORS = {
    'Event': { foreground: '#7b1fa2', background: '#f3e5f5' },
    'Newsletter': { foreground: '#2e7d32', background: '#e8f5e9' },
    'Receipt': { foreground: '#ef6c00', background: '#fff3e0' },
    'Notification': { foreground: '#00838f', background: '#e0f7fa' },
    'Promotion': { foreground: '#c2185b', background: '#fce4ec' },
    'Message': { foreground: '#1565c0', background: '#e3f2fd' },
    'Otp': { foreground: '#d84315', background: '#fbe9e7' }
  };

  static getTypeColor(typeName) {
    return ThreadBadgeManager.TYPE_COLORS[typeName] || { foreground: '#5f6368', background: '#f1f3f4' };
  }

  static buildTypeLabelDescriptor(typeName) {
    const title = ThreadBadgeManager.TYPE_DISPLAY_NAMES[typeName] || typeName;
    const color = ThreadBadgeManager.getTypeColor(typeName);
    return { title, foregroundColor: color.foreground, backgroundColor: color.background };
  }

  static createLabelStream() {
    const pool = Kefir.pool();
    return {
      observable: pool,
      update: (descriptor) => pool.plug(Kefir.constant(descriptor)),
      clear: () => pool.plug(Kefir.constant(null))
    };
  }

  constructor() {
    this._registry = new Map();
    this._cache = {};
    this._cacheReadyResolve = null;
    this._cacheReady = new Promise(resolve => { this._cacheReadyResolve = resolve; });
    this._handlerCallCount = 0;
    this._seenThreadIds = [];

    // Bind for use as InboxSDK callback
    this.handleThreadRow = this.handleThreadRow.bind(this);
  }

  get cache() { return this._cache; }
  get seenThreadIds() { return [...this._seenThreadIds]; }
  get registrySize() { return this._registry.size; }

  async init() {
    try {
      const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
      this._cache = data[LABEL_CACHE_KEY] || {};
      console.log(`Reclaim: Preloaded ${Object.keys(this._cache).length} cached threads`);
    } catch (error) {
      console.error('Reclaim: Failed to preload cache:', error);
      this._cache = {};
    }
    this._cacheReadyResolve();
  }

  dispose() {
    this._registry.clear();
    this._cache = {};
    this._seenThreadIds = [];
    this._handlerCallCount = 0;
  }

  updateCache(newCache) {
    const oldCache = this._cache;
    this._cache = newCache;
    console.log(`Reclaim: Cache updated, ${Object.keys(this._cache).length} threads, ${this._registry.size} rows registered`);

    for (const [threadId] of this._registry) {
      const oldData = oldCache[threadId];
      const newData = newCache[threadId];
      if (JSON.stringify(oldData) !== JSON.stringify(newData)) {
        console.log(`Reclaim: Updating badges for thread ${threadId}`);
        this._applyBadgesFromCache(threadId, newData);
      }
    }
  }

  async handleThreadRow(threadRowView) {
    try {
      await this._cacheReady;

      this._handlerCallCount++;
      const threadId = await threadRowView.getThreadIDAsync();

      if (this._handlerCallCount <= 5) {
        const cacheKeys = Object.keys(this._cache).slice(0, 3);
        console.log(`Reclaim: Handler #${this._handlerCallCount} - threadId: ${threadId}, cache sample: ${cacheKeys.join(', ')}`);
      }

      if (!threadId) return;

      if (this._seenThreadIds.length < 50 && !this._seenThreadIds.includes(threadId)) {
        this._seenThreadIds.push(threadId);
      }

      if (this._registry.has(threadId)) {
        this._applyBadgesFromCache(threadId, this._cache[threadId]);
        return;
      }

      // Evict oldest entry if registry is full
      if (this._registry.size >= ThreadBadgeManager.MAX_REGISTRY_SIZE) {
        const oldestKey = this._registry.keys().next().value;
        this._registry.delete(oldestKey);
      }

      const typeStream = ThreadBadgeManager.createLabelStream();
      const criticalStream = ThreadBadgeManager.createLabelStream();

      threadRowView.addLabel(typeStream.observable);
      threadRowView.addLabel(criticalStream.observable);

      this._registry.set(threadId, { typeStream, criticalStream, threadRowView });

      const labelData = this._cache[threadId];
      if (labelData) {
        this._applyBadgesFromCache(threadId, labelData);
      }

      threadRowView.on('destroy', () => {
        this._registry.delete(threadId);
      });

    } catch (error) {
      console.debug('Reclaim: Error handling thread row:', error);
    }
  }

  _applyBadgesFromCache(threadId, labelData) {
    const entry = this._registry.get(threadId);
    if (!entry) return;

    const displayType = labelData?.type || ThreadBadgeManager.CLIENT_LABEL_TO_TYPE[labelData?.clientLabel];
    if (displayType) {
      const descriptor = ThreadBadgeManager.buildTypeLabelDescriptor(displayType);
      console.log(`Reclaim: Updating type badge for ${threadId}:`, descriptor.title);
      entry.typeStream.update(descriptor);
    } else {
      entry.typeStream.clear();
    }

    if (labelData?.importance === 'critical') {
      entry.criticalStream.update({
        title: 'CRITICAL',
        foregroundColor: '#c62828',
        backgroundColor: '#ffebee'
      });
      const element = entry.threadRowView.getElement();
      if (element) {
        element.classList.add('reclaim-critical-row');
      }
    } else {
      entry.criticalStream.clear();
      const element = entry.threadRowView.getElement();
      if (element) {
        element.classList.remove('reclaim-critical-row');
      }
    }
  }
}

// Module-scope reference (created in initializeVisualLayer)
let badgeManager = null;

// =============================================================================
// DISPOSE BAG (lifecycle cleanup utility)
// =============================================================================

/**
 * Tracks disposable resources (listeners, intervals, observers) and
 * cleans them all up in one dispose() call.
 */
class DisposeBag {
  constructor() {
    this._disposers = [];
  }

  addListener(target, event, handler, options) {
    target.addEventListener(event, handler, options);
    this._disposers.push(() => target.removeEventListener(event, handler, options));
  }

  addInterval(id) {
    this._disposers.push(() => clearInterval(id));
  }

  addTimeout(id) {
    this._disposers.push(() => clearTimeout(id));
  }

  addObserver(observer) {
    this._disposers.push(() => observer.disconnect());
  }

  addCustom(disposeFn) {
    this._disposers.push(disposeFn);
  }

  dispose() {
    for (const fn of this._disposers) {
      try { fn(); } catch (e) { /* ignore cleanup errors */ }
    }
    this._disposers = [];
  }
}

// =============================================================================
// SIDEBAR MESSAGE ROUTER
// =============================================================================

/**
 * Replaces the monolithic if/else chain for iframe postMessage handling.
 * Validates origin once, dispatches to registered handlers by message type.
 */
class SidebarMessageRouter {
  constructor(extensionOrigin) {
    this._extensionOrigin = extensionOrigin;
    this._handlers = new Map();
    this._listener = null;
  }

  register(messageType, handler) {
    this._handlers.set(messageType, handler);
    return this; // chainable
  }

  start() {
    this._listener = async (event) => {
      if (event.origin !== this._extensionOrigin) return;
      const type = event.data?.type;
      if (!type) return;
      const handler = this._handlers.get(type);
      if (handler) {
        try {
          await handler(event.data);
        } catch (err) {
          console.error(`Reclaim: Message handler error for ${type}:`, err);
        }
      }
    };
    window.addEventListener('message', this._listener);
  }

  dispose() {
    if (this._listener) {
      window.removeEventListener('message', this._listener);
      this._listener = null;
    }
    this._handlers.clear();
  }
}

/**
 * Check if extension context is still valid
 * Returns false if extension was reloaded and this content script is orphaned
 */
function isExtensionContextValid() {
  try {
    // Try to access chrome.runtime.id - throws if context is invalidated
    return !!chrome.runtime?.id;
  } catch (e) {
    return false;
  }
}

/**
 * Show a banner prompting user to refresh the page
 */
function showRefreshBanner() {
  // Remove any existing banner first
  const existing = document.getElementById('reclaim-refresh-banner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'reclaim-refresh-banner';
  banner.innerHTML = `
    <div style="
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      background: #1a73e8;
      color: white;
      padding: 8px 16px;
      text-align: center;
      font-family: 'Google Sans', Roboto, sans-serif;
      font-size: 14px;
      z-index: 99999;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 12px;
    ">
      <span>Reclaim was updated. Please refresh this page to continue.</span>
      <button onclick="location.reload()" style="
        background: white;
        color: #1a73e8;
        border: none;
        padding: 6px 16px;
        border-radius: 4px;
        font-weight: 500;
        cursor: pointer;
      ">Refresh</button>
      <button onclick="this.parentElement.remove()" style="
        background: transparent;
        color: white;
        border: 1px solid rgba(255,255,255,0.5);
        padding: 6px 12px;
        border-radius: 4px;
        cursor: pointer;
      ">Dismiss</button>
    </div>
  `;
  document.body.appendChild(banner);
}

// Global dispose bag for cleanup on extension invalidation
const globalDisposeBag = new DisposeBag();

/**
 * Dispose all managed resources (badge manager, sidebar controller, global listeners).
 * Called when extension context is invalidated.
 */
function disposeAll() {
  console.log('Reclaim: Disposing all resources...');
  if (badgeManager) {
    badgeManager.dispose();
    badgeManager = null;
  }
  if (sidebarController) {
    sidebarController.dispose();
    sidebarController = null;
  }
  globalDisposeBag.dispose();
  triggerDigestRefresh = null;
}

/**
 * Initialize InboxSDK
 */
async function initializeVisualLayer() {
  // Check if extension context is still valid
  if (!isExtensionContextValid()) {
    console.warn('Reclaim: Extension context invalidated - showing refresh banner');
    showRefreshBanner();
    return;
  }

  // Create and initialize badge manager
  badgeManager = new ThreadBadgeManager();
  await badgeManager.init();

  // Listen for cache updates from background and update badges dynamically
  const storageListener = (changes, areaName) => {
    if (areaName !== 'local') return;

    // Handle label cache updates (for badges)
    if (changes[LABEL_CACHE_KEY] && badgeManager) {
      const newCache = changes[LABEL_CACHE_KEY].newValue || {};
      badgeManager.updateCache(newCache);
    }

    // Handle digest refresh signal (from auto-organize)
    if (changes.shopq_digest_needs_refresh && triggerDigestRefresh) {
      console.log('Reclaim: Digest refresh signal received from auto-organize');
      triggerDigestRefresh();
      chrome.storage.local.remove('shopq_digest_needs_refresh');
    }
  };
  chrome.storage.onChanged.addListener(storageListener);
  globalDisposeBag.addCustom(() => chrome.storage.onChanged.removeListener(storageListener));

  // Periodic extension context check (detect extension reload while page stays open)
  const contextCheckInterval = setInterval(() => {
    if (!isExtensionContextValid()) {
      console.warn('Reclaim: Extension context invalidated - cleaning up');
      clearInterval(contextCheckInterval);
      disposeAll();
      showRefreshBanner();
    }
  }, 30000);
  globalDisposeBag.addInterval(contextCheckInterval);

  console.log('Reclaim: Attempting InboxSDK.load with app ID:', SHOPQ_APP_ID);

  try {
    const sdk = await InboxSDK.load(2, SHOPQ_APP_ID);
    console.log('Reclaim: InboxSDK loaded successfully');

    // Register thread row handler for badges
    sdk.Lists.registerThreadRowViewHandler(badgeManager.handleThreadRow);
    console.log('Reclaim: Thread row handler registered');

    // Add digest sidebar panel via InboxSDK
    await initializeDigestSidebar(sdk);
  } catch (error) {
    console.error('Reclaim: Failed to load InboxSDK:', error.message);
    // Check if this is due to extension context being invalidated
    if (!isExtensionContextValid() || error.message?.includes('Extension context invalidated')) {
      showRefreshBanner();
    }
  }
}

// =============================================================================
// TEST HOOKS (for E2E testing only - uses '*' for same-window communication)
// =============================================================================

// Listen for postMessage from page context (for E2E tests)
// Note: These hooks use '*' intentionally since they communicate within the same window
// for test purposes. The event.source check ensures only same-window messages are processed.
const testHookListener = async (event) => {
  if (event.source !== window) return;

  if (event.data?.type === 'SHOPQ_TEST_ORGANIZE') {
    console.log('Reclaim: Test hook - triggering organize...');
    try {
      const response = await chrome.runtime.sendMessage({ type: 'ORGANIZE_NOW' });
      window.postMessage({ type: 'SHOPQ_TEST_ORGANIZE_RESPONSE', response }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_ORGANIZE_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_CHECK_AUTH') {
    console.log('Reclaim: Test hook - checking auth...');
    try {
      const response = await chrome.runtime.sendMessage({ type: 'CHECK_AUTH' });
      window.postMessage({ type: 'SHOPQ_TEST_CHECK_AUTH_RESPONSE', response }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_CHECK_AUTH_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_CLEAR_CACHE') {
    console.log('Reclaim: Test hook - clearing cache...');
    try {
      await chrome.storage.local.remove('shopq_label_cache');
      window.postMessage({ type: 'SHOPQ_TEST_CLEAR_CACHE_RESPONSE', success: true }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_CLEAR_CACHE_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_SET_CACHE') {
    console.log('Reclaim: Test hook - setting cache with', Object.keys(event.data.cacheData || {}).length, 'entries...');
    try {
      await chrome.storage.local.set({ [LABEL_CACHE_KEY]: event.data.cacheData });
      if (badgeManager) {
        badgeManager.updateCache(event.data.cacheData);
      }
      window.postMessage({ type: 'SHOPQ_TEST_SET_CACHE_RESPONSE', success: true }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_SET_CACHE_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_GET_THREAD_IDS') {
    const ids = badgeManager ? badgeManager.seenThreadIds : [];
    console.log('Reclaim: Test hook - returning', ids.length, 'thread IDs');
    window.postMessage({ type: 'SHOPQ_TEST_GET_THREAD_IDS_RESPONSE', threadIds: ids }, '*');
  }

  if (event.data?.type === 'SHOPQ_TEST_GET_CACHE_STATUS') {
    console.log('Reclaim: Test hook - getting cache status...');
    try {
      const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
      const cache = data[LABEL_CACHE_KEY] || {};
      const entries = Object.entries(cache);
      window.postMessage({
        type: 'SHOPQ_TEST_GET_CACHE_STATUS_RESPONSE',
        count: entries.length,
        sample: entries.slice(0, 5).map(([id, v]) => ({ threadId: id.slice(0, 12), ...v }))
      }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_GET_CACHE_STATUS_RESPONSE', error: error.message }, '*');
    }
  }
};
globalDisposeBag.addListener(window, 'message', testHookListener);

// =============================================================================
// DIGEST SIDEBAR PANEL
// =============================================================================

// createDigestPanel removed - was unused code that could inject styles
// The active panel is showDigestDrawer() which uses position:fixed

/**
 * Fetch digest from API using cached classifications
 */
async function fetchDigest() {
  try {
    // Get cached classifications and user settings
    const storageData = await chrome.storage.local.get([LABEL_CACHE_KEY, 'userName', 'userCity', 'userRegion']);
    const cache = storageData[LABEL_CACHE_KEY] || {};
    const entries = Object.entries(cache);

    if (entries.length === 0) {
      return { empty: true, message: 'No classified emails yet. Click the Reclaim icon to organize your inbox first.' };
    }

    // Convert cache to digest format (current_data)
    // API expects: id (required), subject (required), plus optional fields
    const currentData = entries.slice(0, 50).map(([threadId, item]) => ({
      id: threadId,  // Required by SummaryRequest validator
      messageId: item.messageId || threadId,
      threadId: threadId,
      subject: item.subject || '(no subject)',
      snippet: item.snippet || '',
      from: item.from || '',
      type: item.type?.toLowerCase() || 'message',
      importance: item.importance || 'routine',
      client_label: item.clientLabel || 'everything-else',
      date: item.date || item.updatedAt || new Date().toISOString()
    }));

    // Call digest API with user info for personalized greeting/weather
    const requestPayload = {
      current_data: currentData,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      client_now: new Date().toISOString(),
      user_name: storageData.userName || undefined,
      city: storageData.userCity || undefined,
      region: storageData.userRegion || undefined
    };

    console.log('Reclaim: Digest request payload:', {
      emailCount: currentData.length,
      sampleEmail: currentData[0],
      timezone: requestPayload.timezone,
      user_name: requestPayload.user_name,
      city: requestPayload.city
    });

    const response = await fetch(`${API_BASE_URL}/api/context-digest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestPayload)
    });

    if (!response.ok) {
      // Try to get detailed error message from response
      let errorDetail = '';
      try {
        const errorBody = await response.json();
        errorDetail = errorBody.detail || JSON.stringify(errorBody);
      } catch {
        errorDetail = await response.text();
      }
      console.error('Reclaim: Digest API error:', response.status, errorDetail);
      throw new Error(`API error ${response.status}: ${errorDetail}`);
    }

    const result = await response.json();
    console.log('Reclaim: Digest API response:', result);
    return { success: true, data: result };
  } catch (error) {
    console.error('Reclaim: Failed to fetch digest:', error);

    // Detect extension context invalidated (happens after extension reload)
    if (error.message?.includes('Extension context invalidated') ||
        error.message?.includes('context invalidated')) {
      return {
        error: true,
        message: 'Extension was updated. Please refresh Gmail (Cmd+R or F5).',
        needsRefresh: true
      };
    }

    return { error: true, message: error.message };
  }
}

/**
 * Build HTML for a digest result. Returns { html, needsRefresh, isEmpty, isError }.
 * Callers wire up interactive buttons after inserting the HTML.
 */
function buildDigestHtml(result) {
  if (result.empty) {
    return {
      html: `
        <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
          <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
          <p style="margin-bottom: 16px;">${sanitizeHtml(result.message)}</p>
          <button id="reclaim-organize-btn" style="
            padding: 8px 16px; background: #1a73e8; color: white;
            border: none; border-radius: 4px; cursor: pointer; font-size: 14px;
          ">Organize Inbox</button>
        </div>
      `,
      isEmpty: true,
      needsRefresh: false,
      isError: false,
    };
  }

  if (result.error) {
    if (result.needsRefresh) {
      return {
        html: `
          <div style="text-align: center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 16px;">🔄</div>
            <p style="font-weight: 500; color: #202124; margin-bottom: 8px;">Extension Updated</p>
            <p style="font-size: 13px; color: #5f6368; margin-bottom: 16px;">Please refresh Gmail to reconnect.</p>
            <button id="reclaim-refresh-btn" style="
              padding: 8px 16px; background: #1a73e8; color: white;
              border: none; border-radius: 4px; cursor: pointer;
            ">Refresh Gmail</button>
          </div>
        `,
        isEmpty: false,
        needsRefresh: true,
        isError: true,
      };
    }

    return {
      html: `
        <div style="text-align: center; padding: 40px 20px;">
          <p style="color: #c5221f; margin-bottom: 16px;">Error: ${sanitizeHtml(result.message)}</p>
          <button id="reclaim-retry-btn" style="
            padding: 8px 16px; background: #1a73e8; color: white;
            border: none; border-radius: 4px; cursor: pointer;
          ">Retry</button>
        </div>
      `,
      isEmpty: false,
      needsRefresh: false,
      isError: true,
    };
  }

  if (result.data?.html) {
    return {
      html: `<div style="line-height: 1.6;">${sanitizeHtml(result.data.html)}</div>`,
      isEmpty: false,
      needsRefresh: false,
      isError: false,
    };
  }

  if (result.data?.narrative) {
    return {
      html: `<div style="line-height: 1.6;">${sanitizeHtml(result.data.narrative)}</div>`,
      isEmpty: false,
      needsRefresh: false,
      isError: false,
    };
  }

  return {
    html: `
      <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
        <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
        <p>No digest content available.</p>
      </div>
    `,
    isEmpty: true,
    needsRefresh: false,
    isError: false,
  };
}

/**
 * Render digest content into the panel
 */
function renderDigestContent(panel, result) {
  const contentEl = panel.querySelector('.reclaim-digest-content');
  const digestMeta = buildDigestHtml(result);
  contentEl.innerHTML = digestMeta.html;
  wireDigestButtons(contentEl, digestMeta, () => refreshDigest(panel));
}

/**
 * Refresh the digest
 */
async function refreshDigest(panel) {
  const contentEl = panel.querySelector('.reclaim-digest-content');
  contentEl.innerHTML = `
    <div class="reclaim-digest-loading">
      <div class="spinner"></div>
      <span>Loading digest...</span>
    </div>
  `;

  const result = await fetchDigest();
  renderDigestContent(panel, result);
}

/**
 * Wire interactive buttons inside a container after inserting digest HTML.
 * Handles Organize, Refresh Gmail, and Retry buttons.
 */
function wireDigestButtons(container, digestMeta, retryFn) {
  if (digestMeta.isEmpty) {
    container.querySelector('#reclaim-organize-btn')?.addEventListener('click', async () => {
      try {
        await chrome.runtime.sendMessage({ type: 'ORGANIZE_NOW' });
        container.innerHTML = `
          <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
            <div style="font-size: 32px; margin-bottom: 12px;">⏳</div>
            <p>Organizing inbox...</p>
          </div>
        `;
      } catch (e) {
        console.error('Reclaim: Failed to trigger organize:', e);
      }
    });
  }
  if (digestMeta.needsRefresh) {
    container.querySelector('#reclaim-refresh-btn')?.addEventListener('click', () => {
      window.location.reload();
    });
  }
  if (digestMeta.isError && !digestMeta.needsRefresh && retryFn) {
    container.querySelector('#reclaim-retry-btn')?.addEventListener('click', retryFn);
  }
}

/**
 * Create the digest content element for the sidebar
 */
function createDigestPanelContent() {
  const container = document.createElement('div');
  container.id = 'reclaim-digest-panel';
  container.style.cssText = `
    height: 100%;
    display: flex;
    flex-direction: column;
    font-family: 'Google Sans', Roboto, sans-serif;
    background: white;
  `;

  container.innerHTML = `
    <div style="
      flex: 1;
      overflow-y: auto;
      padding: 16px;
    " id="reclaim-digest-content">
      <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 200px;
        color: #5f6368;
      ">
        <div style="
          width: 32px;
          height: 32px;
          border: 3px solid #e0e0e0;
          border-top-color: #1a73e8;
          border-radius: 50%;
          animation: reclaim-spin 1s linear infinite;
          margin-bottom: 12px;
        "></div>
        <span>Loading digest...</span>
      </div>
    </div>
    <style>
      @keyframes reclaim-spin {
        to { transform: rotate(360deg); }
      }
      #reclaim-digest-panel a { color: #1a73e8; text-decoration: none; }
      #reclaim-digest-panel a:hover { text-decoration: underline; }
    </style>
  `;

  fetchDigest().then(result => {
    const content = container.querySelector('#reclaim-digest-content');
    if (!content) return;

    const digestMeta = buildDigestHtml(result);
    content.innerHTML = digestMeta.html;
    wireDigestButtons(content, digestMeta, () => {
      const newContent = createDigestPanelContent();
      container.replaceWith(newContent);
    });
  });

  return container;
}

// =============================================================================
// SIDEBAR CONTROLLER
// =============================================================================

/**
 * Owns the returns sidebar iframe, panel registration, periodic refresh,
 * navigation persistence, and all order fetch/update methods.
 */
class SidebarController {
  constructor(router) {
    this._router = router;
    this._extensionOrigin = chrome.runtime.getURL('').slice(0, -1);
    this._panelEl = null;
    this._iframe = null;
    this._iframeReady = false;
    this._refreshInterval = null;
    this._shouldBeOpen = true;
    this._isNavigating = false;
    this._disposed = false;
  }

  get triggerRefresh() {
    return () => {
      const now = Date.now();
      if (now - lastDigestRefreshTime < DIGEST_REFRESH_DEBOUNCE_MS) {
        console.log('Reclaim: Returns refresh debounced (too soon)');
        return;
      }
      lastDigestRefreshTime = now;
      console.log('Reclaim: External returns refresh triggered');
      this._fetchVisibleOrders();
    };
  }

  postToSidebar(message) {
    if (this._iframeReady && this._iframe?.contentWindow) {
      this._iframe.contentWindow.postMessage(message, this._extensionOrigin);
    }
  }

  async init(sdk) {
    console.log('Reclaim: Setting up Reclaim sidebar with IFRAME ISOLATION...');

    this._panelEl = document.createElement('div');
    this._panelEl.id = 'reclaim-returns-panel';
    this._panelEl.style.cssText = `
      width: 100%;
      height: 100%;
      display: flex;
      min-width: 0;
      overflow: hidden;
      contain: layout paint style;
    `;

    this._iframe = document.createElement('iframe');
    this._iframe.src = chrome.runtime.getURL('returns-sidebar.html');
    this._iframe.id = 'reclaim-returns-iframe';
    this._iframe.style.cssText = `
      width: 100%;
      height: 100%;
      border: none;
      display: block;
      background: #fff;
    `;
    this._panelEl.appendChild(this._iframe);

    this._registerMessageHandlers();
    this._router.start();

    try {
      console.log('Reclaim: Calling sdk.Global.addSidebarContentPanel...');
      const iconDataUrl = 'data:image/svg+xml,' + encodeURIComponent(`
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
          <line x1="12" y1="22.08" x2="12" y2="12"></line>
        </svg>
      `);

      const panelView = await sdk.Global.addSidebarContentPanel({
        el: this._panelEl,
        title: 'Reclaim',
        iconUrl: iconDataUrl,
      });

      console.log('Reclaim: Reclaim sidebar registered successfully:', panelView);
      this._wirePanelLifecycle(panelView, sdk);

      triggerDigestRefresh = this.triggerRefresh;

      panelView.open();
      console.log('Reclaim: Reclaim sidebar opened on initial load');

    } catch (error) {
      console.error('Reclaim: Failed to add Reclaim sidebar panel:', error);
      console.log('Reclaim: Falling back to manual button injection...');
      injectReclaimButton();

      const observer = new MutationObserver(() => {
        if (!document.getElementById('reclaim-nav-button')) {
          injectReclaimButton();
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  dispose() {
    this._disposed = true;
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
    this._router.dispose();
    this._iframeReady = false;
  }

  _wirePanelLifecycle(panelView, sdk) {
    panelView.on('activate', () => {
      if (this._disposed) return;
      console.log('Reclaim: Reclaim panel activated');
      this._fetchVisibleOrders();

      if (!this._refreshInterval) {
        this._refreshInterval = setInterval(() => {
          if (this._iframeReady) {
            this._fetchVisibleOrders();
          }
        }, SIDEBAR_REFRESH_INTERVAL_MS);
      }
    });

    panelView.on('deactivate', () => {
      if (this._disposed) return;
      console.log('Reclaim: Reclaim panel deactivated, isNavigating:', this._isNavigating);

      if (this._refreshInterval) {
        clearInterval(this._refreshInterval);
        this._refreshInterval = null;
      }

      if (!this._isNavigating) {
        this._shouldBeOpen = false;
        console.log('Reclaim: User closed sidebar');
      }
    });

    sdk.Router.handleAllRoutes((routeView) => {
      if (this._disposed) return;
      console.log('Reclaim: Route changed to:', routeView.getRouteID());
      this._isNavigating = true;

      setTimeout(() => {
        this._isNavigating = false;
        if (this._shouldBeOpen) {
          try {
            panelView.open();
            console.log('Reclaim: Re-opened sidebar after navigation');
          } catch (e) {
            console.log('Reclaim: Could not re-open sidebar:', e.message);
          }
        }
      }, 150);
    });
  }

  _registerMessageHandlers() {
    const ctrl = this;

    this._router.register('SHOPQ_RETURNS_SIDEBAR_READY', async () => {
      console.log('Reclaim: Returns sidebar iframe ready');
      ctrl._iframeReady = true;
      ctrl.postToSidebar({
        type: 'SHOPQ_CONFIG_INIT',
        config: {
          DATE_REFRESH_INTERVAL_MS: SIDEBAR_REFRESH_INTERVAL_MS,
          TOAST_DURATION_MS,
          TOAST_FADEOUT_MS,
          EXPIRING_SOON_DAYS,
          CRITICAL_DAYS,
        }
      });
      await ctrl._fetchVisibleOrders();
    });

    this._router.register('SHOPQ_GET_ORDERS', async () => {
      console.log('Reclaim: Fetching visible orders...');
      await ctrl._fetchVisibleOrders();
    });

    this._router.register('SHOPQ_GET_RETURNED_ORDERS', async () => {
      console.log('Reclaim: Fetching returned orders...');
      await ctrl._fetchReturnedOrders();
    });

    this._router.register('SHOPQ_UPDATE_ORDER_STATUS', async (data) => {
      console.log('Reclaim: Updating order status:', data.order_key, data.status);
      await ctrl._updateOrderStatus(data.order_key, data.status);
    });

    this._router.register('SHOPQ_ENRICH_ORDER', async (data) => {
      console.log('Reclaim: Enriching order:', data.order_key);
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'ENRICH_ORDER',
          order_key: data.order_key
        });
        ctrl.postToSidebar({ type: 'SHOPQ_ENRICH_RESULT', ...result });
      } catch (err) {
        console.error('Reclaim: Enrichment failed:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_ENRICH_RESULT', state: 'error', error: err.message });
      }
    });

    this._router.register('SHOPQ_SET_MERCHANT_RULE', async (data) => {
      console.log('Reclaim: Setting merchant rule:', data.merchant_domain, data.window_days);
      try {
        await chrome.runtime.sendMessage({
          type: 'SET_MERCHANT_RULE',
          merchant_domain: data.merchant_domain,
          window_days: data.window_days
        });
        await chrome.runtime.sendMessage({
          type: 'RECOMPUTE_MERCHANT_DEADLINES',
          merchant_domain: data.merchant_domain
        });
        ctrl.postToSidebar({ type: 'SHOPQ_MERCHANT_RULE_SET', merchant_domain: data.merchant_domain });
        await ctrl._fetchVisibleOrders();
      } catch (err) {
        console.error('Reclaim: Set merchant rule failed:', err);
      }
    });

    this._router.register('SHOPQ_GET_ORDER', async (data) => {
      console.log('Reclaim: Getting order:', data.order_key);
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'GET_ORDER',
          order_key: data.order_key
        });
        ctrl.postToSidebar({ type: 'SHOPQ_ORDER_DATA', order: result.order });
      } catch (err) {
        console.error('Reclaim: Get order failed:', err);
      }
    });

    this._router.register('SHOPQ_UPDATE_ORDER_RETURN_DATE', async (data) => {
      console.log('Reclaim: Updating order return date:', data.order_key, data.return_by_date);
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'UPDATE_ORDER_RETURN_DATE',
          order_key: data.order_key,
          return_by_date: data.return_by_date
        });
        ctrl.postToSidebar({ type: 'SHOPQ_ORDER_RETURN_DATE_UPDATED', order_key: data.order_key, ...result });
        await ctrl._fetchVisibleOrders();
      } catch (err) {
        console.error('Reclaim: Failed to update return date:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_ORDER_RETURN_DATE_UPDATED', error: err.message });
      }
    });

    this._router.register('SHOPQ_CLOSE_SIDEBAR', () => {
      console.log('Reclaim: Closing sidebar');
      const shopqIcon = document.querySelector('[data-tooltip="Reclaim"]');
      if (shopqIcon) {
        shopqIcon.click();
      }
    });

    this._router.register('SHOPQ_RESCAN_EMAILS', async () => {
      console.log('Reclaim: Manual rescan requested...');
      try {
        const result = await chrome.runtime.sendMessage({ type: 'SCAN_FOR_PURCHASES' });
        console.log('Reclaim: Rescan complete:', result);
        ctrl.postToSidebar({ type: 'SHOPQ_SCAN_COMPLETE', result });
        await ctrl._fetchVisibleOrders();
      } catch (err) {
        console.error('Reclaim: Rescan failed:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_SCAN_COMPLETE', error: err.message });
      }
    });

    // Delivery modal message handlers
    this._router.register('SHOPQ_GET_USER_ADDRESS', async () => {
      try {
        const result = await chrome.runtime.sendMessage({ type: 'GET_USER_ADDRESS' });
        ctrl.postToSidebar({ type: 'SHOPQ_USER_ADDRESS', address: result?.address || null });
      } catch (err) {
        console.error('Reclaim: Failed to get user address:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_USER_ADDRESS', address: null });
      }
    });

    this._router.register('SHOPQ_SET_USER_ADDRESS', async (data) => {
      try {
        await chrome.runtime.sendMessage({ type: 'SET_USER_ADDRESS', address: data.address });
      } catch (err) {
        console.error('Reclaim: Failed to save address:', err);
      }
    });

    this._router.register('SHOPQ_GET_DELIVERY_LOCATIONS', async (data) => {
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'GET_DELIVERY_LOCATIONS',
          address: data.address
        });
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_LOCATIONS', locations: result?.locations || [] });
      } catch (err) {
        console.error('Reclaim: Failed to get delivery locations:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_LOCATIONS', locations: [], error: err.message });
      }
    });

    this._router.register('SHOPQ_GET_DELIVERY_QUOTE', async (data) => {
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'GET_DELIVERY_QUOTE',
          order_key: data.order_key,
          pickup_address: data.pickup_address,
          dropoff_location_id: data.dropoff_location_id
        });
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_QUOTE', quote: result?.quote || result, error: result?.error });
      } catch (err) {
        console.error('Reclaim: Failed to get delivery quote:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_QUOTE', error: err.message });
      }
    });

    this._router.register('SHOPQ_CONFIRM_DELIVERY', async (data) => {
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'CONFIRM_DELIVERY',
          delivery_id: data.delivery_id
        });
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_CONFIRMED', delivery: result?.delivery || result, error: result?.error });
      } catch (err) {
        console.error('Reclaim: Failed to confirm delivery:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_CONFIRMED', error: err.message });
      }
    });

    this._router.register('SHOPQ_CANCEL_DELIVERY', async (data) => {
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'CANCEL_DELIVERY',
          delivery_id: data.delivery_id
        });
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_CANCELED', error: result?.error });
      } catch (err) {
        console.error('Reclaim: Failed to cancel delivery:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_DELIVERY_CANCELED', error: err.message });
      }
    });

    this._router.register('SHOPQ_GET_ACTIVE_DELIVERIES', async () => {
      try {
        const result = await chrome.runtime.sendMessage({ type: 'GET_ACTIVE_DELIVERIES' });
        ctrl.postToSidebar({ type: 'SHOPQ_ACTIVE_DELIVERIES', deliveries: result?.deliveries || [] });
      } catch (err) {
        console.error('Reclaim: Failed to get active deliveries:', err);
        ctrl.postToSidebar({ type: 'SHOPQ_ACTIVE_DELIVERIES', deliveries: [] });
      }
    });
  }

  async _fetchVisibleOrders() {
    try {
      const result = await sendMessageWithTimeout({ type: 'GET_VISIBLE_ORDERS' });
      const orders = result.orders || [];
      this.postToSidebar({ type: 'SHOPQ_ORDERS_DATA', orders });
      this._updateExpiringIndicator(orders);
    } catch (err) {
      console.error('Reclaim: Failed to fetch visible orders:', err);
      this.postToSidebar({
        type: 'SHOPQ_RETURNS_ERROR',
        message: 'Could not load returns. Check your connection.'
      });
    }
  }

  async _fetchReturnedOrders() {
    try {
      const result = await sendMessageWithTimeout({ type: 'GET_RETURNED_ORDERS' });
      const orders = result.orders || [];
      this.postToSidebar({ type: 'SHOPQ_RETURNED_ORDERS_DATA', orders });
    } catch (err) {
      console.error('Reclaim: Failed to fetch returned orders:', err);
    }
  }

  async _updateOrderStatus(orderKey, newStatus) {
    try {
      await sendMessageWithTimeout({
        type: 'UPDATE_ORDER_STATUS',
        order_key: orderKey,
        status: newStatus
      });
      this.postToSidebar({ type: 'SHOPQ_STATUS_UPDATED', order_key: orderKey, status: newStatus });
      await this._fetchVisibleOrders();
      await this._fetchReturnedOrders();
    } catch (err) {
      console.error('Reclaim: Failed to update order status:', err);
    }
  }

  _updateExpiringIndicator(orders) {
    const shopqIcon = document.querySelector('[data-tooltip="Reclaim"]');
    if (!shopqIcon) {
      console.log('Reclaim: Could not find sidebar icon for expiring indicator');
      return;
    }

    const now = new Date();
    const sevenDaysFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

    const expiringCount = orders.filter(order => {
      const status = order.order_status || order.status;
      const returnDate = order.return_by_date || order.return_deadline;
      if (status !== 'active' || !returnDate) return false;
      const deadline = new Date(returnDate);
      return deadline >= now && deadline <= sevenDaysFromNow;
    }).length;

    console.log('Reclaim: Expiring returns count:', expiringCount);

    const existingDot = shopqIcon.querySelector('.reclaim-expiring-dot');

    if (expiringCount > 0) {
      shopqIcon.classList.add('reclaim-has-expiring');
      shopqIcon.style.position = 'relative';

      if (!existingDot) {
        const dot = document.createElement('div');
        dot.className = 'reclaim-expiring-dot';
        dot.textContent = expiringCount > 9 ? '9+' : expiringCount;
        dot.title = `${expiringCount} return${expiringCount > 1 ? 's' : ''} expiring soon`;
        shopqIcon.appendChild(dot);
        console.log('Reclaim: Added expiring returns indicator');
      } else {
        existingDot.textContent = expiringCount > 9 ? '9+' : expiringCount;
        existingDot.title = `${expiringCount} return${expiringCount > 1 ? 's' : ''} expiring soon`;
      }
    } else {
      shopqIcon.classList.remove('reclaim-has-expiring');
      if (existingDot) {
        existingDot.remove();
        console.log('Reclaim: Removed expiring returns indicator');
      }
    }
  }
}

// Module-scope reference (created in initializeDigestSidebar)
let sidebarController = null;

/**
 * Initialize the returns sidebar using InboxSDK's Global sidebar API.
 * Creates a SidebarController that owns the iframe, router, and all panel lifecycle.
 */
async function initializeDigestSidebar(sdk) {
  const extensionOrigin = chrome.runtime.getURL('').slice(0, -1);
  const router = new SidebarMessageRouter(extensionOrigin);
  sidebarController = new SidebarController(router);
  await sidebarController.init(sdk);
}

/**
 * Load digest content into a panel element
 * PHASE 3: Uses iframe postMessage to avoid Gmail layout issues
 */
async function loadDigestIntoPanel(panelEl) {
  const sendToIframe = panelEl._sendToIframe;

  if (!sendToIframe) {
    console.error('Reclaim: sendToIframe function not found on panelEl');
    return;
  }

  sendToIframe(`
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #5f6368;">
      <div class="spinner"></div>
      <span>Loading digest...</span>
    </div>
  `);

  const result = await fetchDigest();
  const digestMeta = buildDigestHtml(result);

  if (panelEl._setCachedHtml) {
    panelEl._setCachedHtml(digestMeta.html);
    console.log('Reclaim: Digest content cached for navigation persistence');
  }

  sendToIframe(digestMeta.html);
  console.log('Reclaim: Digest content sent to iframe');
}

/**
 * Inject Reclaim button into Gmail's top nav
 */
function injectReclaimButton() {
  // Skip if already exists
  if (document.getElementById('reclaim-nav-button')) {
    return;
  }

  // Find the area where Gemini/Settings icons are (right side of header)
  const headerRight = document.querySelector('[data-ogsr-up]')?.closest('div')?.parentElement ||
                      document.querySelector('header')?.querySelector('[role="navigation"]') ||
                      document.querySelector('[aria-label="Support"]')?.closest('div')?.parentElement;

  if (!headerRight) {
    console.log('Reclaim: Header area not found, retrying...');
    setTimeout(injectReclaimButton, 1000);
    return;
  }

  // Create Reclaim button matching Gmail's style
  const button = document.createElement('div');
  button.id = 'reclaim-nav-button';
  button.innerHTML = `
    <style>
      #reclaim-nav-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        cursor: pointer;
        margin: 0 4px;
        transition: background 0.2s;
      }
      #reclaim-nav-button:hover { background: rgba(255,255,255,0.1); }
      #reclaim-nav-button img { width: 24px; height: 24px; }
      #reclaim-nav-button.active { background: rgba(138, 180, 248, 0.2); }
    </style>
    <img src="${chrome.runtime.getURL('icons/icon48.png')}" alt="Reclaim Digest" title="Reclaim Digest">
  `;

  button.addEventListener('click', () => {
    button.classList.toggle('active');
    toggleDigestDrawer();
  });

  // Try to insert before the profile picture (last item)
  const profilePic = headerRight.querySelector('img[aria-label]')?.closest('a, div') || headerRight.lastElementChild;
  if (profilePic) {
    profilePic.parentElement.insertBefore(button, profilePic);
    console.log('Reclaim: Nav button injected successfully');
  } else {
    headerRight.appendChild(button);
    console.log('Reclaim: Nav button appended to header');
  }
}

/**
 * Toggle the digest drawer open/closed
 */
function toggleDigestDrawer() {
  const existing = document.getElementById('reclaim-digest-iframe');
  if (existing) {
    existing.remove();
    return;
  }

  // Create drawer as iframe for isolation
  const iframe = document.createElement('iframe');
  iframe.id = 'reclaim-digest-iframe';
  iframe.style.cssText = `
    position: fixed !important;
    top: 0 !important;
    right: 0 !important;
    width: 360px !important;
    height: 100vh !important;
    height: 100dvh !important;
    border: none !important;
    z-index: 2147483647 !important;
    background: white !important;
    box-shadow: -2px 0 8px rgba(0,0,0,0.15) !important;
  `;
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument;
  doc.open();
  doc.write(`
    <!DOCTYPE html>
    <html><head>
      <meta charset="UTF-8">
      <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; font-family: 'Google Sans', Roboto, sans-serif; }
        .drawer { display: flex; flex-direction: column; height: 100%; }
        .header {
          padding: 16px 20px;
          border-bottom: 1px solid #e0e0e0;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .header h2 { font-size: 18px; font-weight: 500; color: #202124; }
        .close-btn {
          background: none;
          border: none;
          font-size: 24px;
          cursor: pointer;
          color: #5f6368;
          padding: 4px 8px;
          border-radius: 4px;
        }
        .close-btn:hover { background: #f1f3f4; }
        .content { flex: 1; overflow-y: auto; padding: 16px 20px; }
        .loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 200px;
          color: #5f6368;
        }
        .spinner {
          width: 32px;
          height: 32px;
          border: 3px solid #e0e0e0;
          border-top-color: #1a73e8;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin-bottom: 12px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        a { color: #1a73e8; text-decoration: none; }
        a:hover { text-decoration: underline; }
      </style>
    </head>
    <body>
      <div class="drawer">
        <div class="header">
          <h2>Reclaim Digest</h2>
          <button class="close-btn" id="close-btn">&times;</button>
        </div>
        <div class="content" id="content">
          <div class="loading">
            <div class="spinner"></div>
            <span>Loading digest...</span>
          </div>
        </div>
      </div>
    </body></html>
  `);
  doc.close();

  // Close button
  doc.getElementById('close-btn').addEventListener('click', () => {
    iframe.remove();
    document.getElementById('reclaim-nav-button')?.classList.remove('active');
  });

  // Load digest content
  fetchDigest().then(result => {
    const content = doc.getElementById('content');
    if (!content) return;

    const digestMeta = buildDigestHtml(result);
    content.innerHTML = digestMeta.html;
    wireDigestButtons(content, digestMeta);
  });
}

// =============================================================================
// INITIALIZATION
// =============================================================================

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeVisualLayer);
} else {
  initializeVisualLayer();
}

} // End of initReclaim()
