/**
 * ShopQ Content Script (ES Module Entry Point)
 *
 * This file is bundled by webpack with InboxSDK.
 * Implements the Visual Layer for Gmail:
 * 1. Type Badges: Blue badges showing email type (Newsletter, Event, etc.)
 * 2. Critical Badges: Red badge + row border for critical importance
 * 3. Dimming: Reduce prominence of Everything-Else emails
 * 4. Digest Sidebar: Global sidebar panel showing email digest
 *
 * Uses Write-Through Cache pattern:
 * - Background service stores {threadId → {type, importance, clientLabel}} at classification time
 * - Content script reads from cache when InboxSDK handler fires
 */

import * as InboxSDK from '@inboxsdk/core';
import Kefir from 'kefir';

console.log('ShopQ: Content script loaded (bundled)');

// =============================================================================
// CLEANUP: Remove any stale ShopQ elements/styles from previous loads
// =============================================================================

(function cleanupStaleElements() {
  // Remove old drawer/iframe elements only
  // IMPORTANT: Do NOT reset html/body styles - this interferes with Gmail's dark mode
  document.getElementById('mailq-digest-iframe')?.remove();
  document.getElementById('mailq-nav-button')?.remove();
  document.getElementById('mailq-refresh-banner')?.remove();
  document.getElementById('mailq-layout-styles')?.remove();
  document.getElementById('mailq-sidebar-panel')?.remove();

  // Remove any ShopQ-specific classes only
  document.documentElement.classList.remove('mailq-drawer-open');

  console.log('ShopQ: Cleaned up stale elements');
})();

// =============================================================================
// THREAD ROW REGISTRY (for dynamic badge updates)
// =============================================================================

// Registry: threadId → { typeStream, criticalStream }
// Allows updating badges when cache changes without page reload
const threadRowRegistry = new Map();

// =============================================================================
// DIGEST REFRESH (for continuous organization)
// =============================================================================

// Global function to trigger digest refresh (set by initializeDigestSidebar)
let triggerDigestRefresh = null;
let lastDigestRefreshTime = 0;
const DIGEST_REFRESH_DEBOUNCE_MS = 5000;  // 5 second debounce

/**
 * Create an updateable label stream using Kefir
 * Returns an observable that can be passed to threadRowView.addLabel()
 */
function createLabelStream() {
  const pool = Kefir.pool();
  return {
    observable: pool,
    update: (descriptor) => pool.plug(Kefir.constant(descriptor)),
    clear: () => pool.plug(Kefir.constant(null))
  };
}

// =============================================================================
// API CONFIGURATION
// =============================================================================

const API_BASE_URL = 'https://shopq-api-488078904670.us-central1.run.app';

// =============================================================================
// CONFIGURATION
// =============================================================================

// Registered InboxSDK App ID
const SHOPQ_APP_ID = 'sdk_mailqapp_8eb273b616';
const LABEL_CACHE_KEY = 'shopq_label_cache';

// Badge display names for types
const TYPE_DISPLAY_NAMES = {
  'Event': 'Event',
  'Notification': 'Notif',
  'Newsletter': 'Newsletter',
  'Promotion': 'Promo',
  'Receipt': 'Receipt',
  'Message': 'Message',
  'Otp': 'OTP'
};

// Fallback type derivation when type is null (from Gmail label sync)
// Maps clientLabel → reasonable type for badge display
const CLIENT_LABEL_TO_TYPE = {
  'receipts': 'Receipt',
  'messages': 'Message',
  'action-required': null  // No badge - could be any type
  // 'everything-else' intentionally not mapped - should not show badge
};

// =============================================================================
// LABEL CACHE ACCESS
// =============================================================================

/**
 * Preload entire cache for faster lookups
 */
async function preloadCache() {
  try {
    const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
    return data[LABEL_CACHE_KEY] || {};
  } catch (error) {
    console.error('ShopQ: Failed to preload cache:', error);
    return {};
  }
}

// In-memory cache copy
let localCache = {};

// Cache ready promise to prevent race conditions
let cacheReadyResolve;
const cacheReady = new Promise(resolve => { cacheReadyResolve = resolve; });

// =============================================================================
// INBOXSDK VISUAL LAYER
// =============================================================================

/**
 * Get colors for type badges (distinct colors per type)
 */
function getTypeColor(typeName) {
  const colors = {
    'Event': { foreground: '#7b1fa2', background: '#f3e5f5' },      // Purple
    'Newsletter': { foreground: '#2e7d32', background: '#e8f5e9' }, // Green
    'Receipt': { foreground: '#ef6c00', background: '#fff3e0' },    // Orange
    'Notification': { foreground: '#00838f', background: '#e0f7fa' }, // Teal
    'Promotion': { foreground: '#c2185b', background: '#fce4ec' },  // Pink
    'Message': { foreground: '#1565c0', background: '#e3f2fd' },    // Blue
    'Otp': { foreground: '#d84315', background: '#fbe9e7' }         // Deep Orange
  };
  return colors[typeName] || { foreground: '#5f6368', background: '#f1f3f4' }; // Grey fallback
}

/**
 * Build a label descriptor for a type badge
 */
function buildTypeLabelDescriptor(typeName) {
  const title = TYPE_DISPLAY_NAMES[typeName] || typeName;
  return {
    title,
    foregroundColor: getTypeColor(typeName).foreground,
    backgroundColor: getTypeColor(typeName).background
  };
}

/**
 * Apply badges from cache data to a registered thread row
 * Uses Observable streams to enable dynamic updates
 */
function applyBadgesFromCache(threadId, labelData) {
  const entry = threadRowRegistry.get(threadId);
  if (!entry) return;

  // Type badge
  const displayType = labelData?.type || CLIENT_LABEL_TO_TYPE[labelData?.clientLabel];
  if (displayType) {
    const descriptor = buildTypeLabelDescriptor(displayType);
    console.log(`ShopQ: Updating type badge for ${threadId}:`, descriptor.title);
    entry.typeStream.update(descriptor);
  } else {
    entry.typeStream.clear();
  }

  // Critical badge
  if (labelData?.importance === 'critical') {
    entry.criticalStream.update({
      title: 'CRITICAL',
      foregroundColor: '#c62828',
      backgroundColor: '#ffebee'
    });
    // Add red border
    const element = entry.threadRowView.getElement();
    if (element) {
      element.classList.add('mailq-critical-row');
    }
  } else {
    entry.criticalStream.clear();
    // Remove red border
    const element = entry.threadRowView.getElement();
    if (element) {
      element.classList.remove('mailq-critical-row');
    }
  }
}

// Debug counter
let handlerCallCount = 0;

// Store thread IDs seen by handlers (for test hook)
const seenThreadIds = [];

/**
 * Handle each thread row - register Observable streams for dynamic badge updates
 */
async function handleThreadRow(threadRowView) {
  try {
    // Wait for cache to be ready before processing
    await cacheReady;

    handlerCallCount++;
    const threadId = await threadRowView.getThreadIDAsync();

    // Log first few calls for debugging
    if (handlerCallCount <= 5) {
      const cacheKeys = Object.keys(localCache).slice(0, 3);
      console.log(`ShopQ: Handler #${handlerCallCount} - threadId: ${threadId}, cache sample: ${cacheKeys.join(', ')}`);
    }

    if (!threadId) return;

    // Store for test hook (limit to 50 to avoid memory issues)
    if (seenThreadIds.length < 50 && !seenThreadIds.includes(threadId)) {
      seenThreadIds.push(threadId);
    }

    // Skip if already registered (prevents duplicate badges on re-render)
    if (threadRowRegistry.has(threadId)) {
      // Just re-apply badges in case cache changed
      applyBadgesFromCache(threadId, localCache[threadId]);
      return;
    }

    // Create Observable streams for this row
    const typeStream = createLabelStream();
    const criticalStream = createLabelStream();

    // Register with InboxSDK using Observable pattern
    // These will update automatically when we emit new values
    threadRowView.addLabel(typeStream.observable);
    threadRowView.addLabel(criticalStream.observable);

    // Store in registry for later updates
    threadRowRegistry.set(threadId, {
      typeStream,
      criticalStream,
      threadRowView
    });

    // Apply initial badges from cache
    const labelData = localCache[threadId];
    if (labelData) {
      applyBadgesFromCache(threadId, labelData);
    }

    // Cleanup when row is destroyed (Gmail virtual scrolling)
    threadRowView.on('destroy', () => {
      threadRowRegistry.delete(threadId);
    });

  } catch (error) {
    console.debug('ShopQ: Error handling thread row:', error);
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
  const existing = document.getElementById('mailq-refresh-banner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'mailq-refresh-banner';
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
      <span>ShopQ was updated. Please refresh this page to continue.</span>
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

/**
 * Initialize InboxSDK
 */
async function initializeVisualLayer() {
  // Check if extension context is still valid
  if (!isExtensionContextValid()) {
    console.warn('ShopQ: Extension context invalidated - showing refresh banner');
    showRefreshBanner();
    return;
  }

  // Preload the cache
  localCache = await preloadCache();
  console.log(`ShopQ: Preloaded ${Object.keys(localCache).length} cached threads`);

  // Signal that cache is ready
  cacheReadyResolve();

  // Listen for cache updates from background and update badges dynamically
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== 'local') return;

    // Handle label cache updates (for badges)
    if (changes[LABEL_CACHE_KEY]) {
      const newCache = changes[LABEL_CACHE_KEY].newValue || {};
      const oldCache = localCache;
      localCache = newCache;

      console.log(`ShopQ: Cache updated, ${Object.keys(localCache).length} threads, ${threadRowRegistry.size} rows registered`);

      // Update badges for all registered thread rows
      for (const [threadId, entry] of threadRowRegistry) {
        const oldData = oldCache[threadId];
        const newData = newCache[threadId];

        // Only update if data changed
        if (JSON.stringify(oldData) !== JSON.stringify(newData)) {
          console.log(`ShopQ: Updating badges for thread ${threadId}`);
          applyBadgesFromCache(threadId, newData);
        }
      }
    }

    // Handle digest refresh signal (from auto-organize)
    if (changes.shopq_digest_needs_refresh && triggerDigestRefresh) {
      console.log('ShopQ: Digest refresh signal received from auto-organize');
      triggerDigestRefresh();
      // Clear the signal so it doesn't fire again
      chrome.storage.local.remove('shopq_digest_needs_refresh');
    }
  });

  console.log('ShopQ: Attempting InboxSDK.load with app ID:', SHOPQ_APP_ID);

  try {
    const sdk = await InboxSDK.load(2, SHOPQ_APP_ID);
    console.log('ShopQ: InboxSDK loaded successfully');

    // Register thread row handler for badges
    sdk.Lists.registerThreadRowViewHandler(handleThreadRow);
    console.log('ShopQ: Thread row handler registered');

    // Add digest sidebar panel via InboxSDK
    await initializeDigestSidebar(sdk);
  } catch (error) {
    console.error('ShopQ: Failed to load InboxSDK:', error.message);
    // Check if this is due to extension context being invalidated
    if (!isExtensionContextValid() || error.message?.includes('Extension context invalidated')) {
      showRefreshBanner();
    }
  }
}

// =============================================================================
// TEST HOOKS
// =============================================================================

// Listen for postMessage from page context (for E2E tests)
window.addEventListener('message', async (event) => {
  if (event.source !== window) return;

  if (event.data?.type === 'SHOPQ_TEST_ORGANIZE') {
    console.log('ShopQ: Test hook - triggering organize...');
    try {
      const response = await chrome.runtime.sendMessage({ type: 'ORGANIZE_NOW' });
      window.postMessage({ type: 'SHOPQ_TEST_ORGANIZE_RESPONSE', response }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_ORGANIZE_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_CHECK_AUTH') {
    console.log('ShopQ: Test hook - checking auth...');
    try {
      const response = await chrome.runtime.sendMessage({ type: 'CHECK_AUTH' });
      window.postMessage({ type: 'SHOPQ_TEST_CHECK_AUTH_RESPONSE', response }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_CHECK_AUTH_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_CLEAR_CACHE') {
    console.log('ShopQ: Test hook - clearing cache...');
    try {
      await chrome.storage.local.remove('shopq_label_cache');
      window.postMessage({ type: 'SHOPQ_TEST_CLEAR_CACHE_RESPONSE', success: true }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_CLEAR_CACHE_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_SET_CACHE') {
    console.log('ShopQ: Test hook - setting cache with', Object.keys(event.data.cacheData || {}).length, 'entries...');
    try {
      await chrome.storage.local.set({ [LABEL_CACHE_KEY]: event.data.cacheData });
      localCache = event.data.cacheData;
      window.postMessage({ type: 'SHOPQ_TEST_SET_CACHE_RESPONSE', success: true }, '*');
    } catch (error) {
      window.postMessage({ type: 'SHOPQ_TEST_SET_CACHE_RESPONSE', error: error.message }, '*');
    }
  }

  if (event.data?.type === 'SHOPQ_TEST_GET_THREAD_IDS') {
    console.log('ShopQ: Test hook - returning', seenThreadIds.length, 'thread IDs');
    window.postMessage({ type: 'SHOPQ_TEST_GET_THREAD_IDS_RESPONSE', threadIds: [...seenThreadIds] }, '*');
  }

  if (event.data?.type === 'SHOPQ_TEST_GET_CACHE_STATUS') {
    console.log('ShopQ: Test hook - getting cache status...');
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
});

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
      return { empty: true, message: 'No classified emails yet. Click the ShopQ icon to organize your inbox first.' };
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

    console.log('ShopQ: Digest request payload:', {
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
      console.error('ShopQ: Digest API error:', response.status, errorDetail);
      throw new Error(`API error ${response.status}: ${errorDetail}`);
    }

    const result = await response.json();
    console.log('ShopQ: Digest API response:', result);
    return { success: true, data: result };
  } catch (error) {
    console.error('ShopQ: Failed to fetch digest:', error);

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
 * Render digest content into the panel
 */
function renderDigestContent(panel, result) {
  const contentEl = panel.querySelector('.mailq-digest-content');

  if (result.empty) {
    contentEl.innerHTML = `
      <div class="mailq-digest-empty">
        <div class="icon">📭</div>
        <p>${result.message}</p>
        <button class="mailq-refresh-btn" id="mailq-organize-btn">Organize Inbox</button>
      </div>
    `;
    // Add click handler for organize button
    contentEl.querySelector('#mailq-organize-btn')?.addEventListener('click', async () => {
      try {
        await chrome.runtime.sendMessage({ type: 'ORGANIZE_NOW' });
        contentEl.innerHTML = `
          <div class="mailq-digest-loading">
            <div class="spinner"></div>
            <span>Organizing inbox...</span>
          </div>
        `;
      } catch (e) {
        console.error('ShopQ: Failed to trigger organize:', e);
      }
    });
    return;
  }

  if (result.error) {
    // Special handling for extension context invalidated
    if (result.needsRefresh) {
      contentEl.innerHTML = `
        <div class="mailq-digest-error" style="text-align: center;">
          <div style="font-size: 32px; margin-bottom: 12px;">🔄</div>
          <p style="font-weight: 500;">Extension Updated</p>
          <p style="font-size: 13px; margin-top: 8px; color: #5f6368;">Please refresh Gmail to reconnect.</p>
          <button class="mailq-refresh-btn" id="mailq-refresh-page-btn" style="margin-top: 16px;">Refresh Gmail</button>
        </div>
      `;
      contentEl.querySelector('#mailq-refresh-page-btn')?.addEventListener('click', () => {
        window.location.reload();
      });
      return;
    }

    contentEl.innerHTML = `
      <div class="mailq-digest-error">
        <p>Failed to load digest</p>
        <p style="font-size: 12px; margin-top: 8px;">${result.message}</p>
        <button class="mailq-refresh-btn" id="mailq-retry-btn">Retry</button>
      </div>
    `;
    contentEl.querySelector('#mailq-retry-btn')?.addEventListener('click', () => refreshDigest(panel));
    return;
  }

  // Render successful digest
  const data = result.data;

  // Check if we got HTML content or structured data
  if (data.html) {
    // If API returns HTML, render it directly
    contentEl.innerHTML = `
      <div class="mailq-digest-narrative">${data.html}</div>
      <button class="mailq-refresh-btn" id="mailq-refresh-btn" style="margin-top: 20px;">Refresh</button>
    `;
  } else if (data.narrative) {
    // If API returns narrative text
    contentEl.innerHTML = `
      <div class="mailq-digest-narrative">${data.narrative}</div>
      <button class="mailq-refresh-btn" id="mailq-refresh-btn" style="margin-top: 20px;">Refresh</button>
    `;
  } else {
    // Fallback: no digest content available
    contentEl.innerHTML = `
      <div class="mailq-digest-empty">
        <div class="icon">📊</div>
        <p>No digest available yet.</p>
        <p style="font-size: 12px; margin-top: 8px;">Classify some emails first, then refresh.</p>
        <button class="mailq-refresh-btn" id="mailq-refresh-btn">Refresh</button>
      </div>
    `;
  }

  contentEl.querySelector('#mailq-refresh-btn')?.addEventListener('click', () => refreshDigest(panel));
}

/**
 * Refresh the digest
 */
async function refreshDigest(panel) {
  const contentEl = panel.querySelector('.mailq-digest-content');
  contentEl.innerHTML = `
    <div class="mailq-digest-loading">
      <div class="spinner"></div>
      <span>Loading digest...</span>
    </div>
  `;

  const result = await fetchDigest();
  renderDigestContent(panel, result);
}

// Store reference to sidebar panel for toggling
let digestSidebarPanel = null;

/**
 * Create the digest content element for the sidebar
 */
function createDigestPanelContent() {
  const container = document.createElement('div');
  container.id = 'mailq-digest-panel';
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
    " id="mailq-digest-content">
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
          animation: mailq-spin 1s linear infinite;
          margin-bottom: 12px;
        "></div>
        <span>Loading digest...</span>
      </div>
    </div>
    <style>
      @keyframes mailq-spin {
        to { transform: rotate(360deg); }
      }
      #mailq-digest-panel a { color: #1a73e8; text-decoration: none; }
      #mailq-digest-panel a:hover { text-decoration: underline; }
    </style>
  `;

  // Load digest content
  fetchDigest().then(result => {
    const content = container.querySelector('#mailq-digest-content');
    if (!content) return;

    if (result.empty) {
      content.innerHTML = `
        <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
          <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
          <p style="margin-bottom: 16px;">${result.message}</p>
          <button id="mailq-organize-btn" style="
            padding: 8px 16px;
            background: #1a73e8;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
          ">Organize Inbox</button>
        </div>
      `;
      content.querySelector('#mailq-organize-btn')?.addEventListener('click', async () => {
        try {
          await chrome.runtime.sendMessage({ type: 'ORGANIZE_NOW' });
          content.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
              <div style="font-size: 32px; margin-bottom: 12px;">⏳</div>
              <p>Organizing inbox...</p>
            </div>
          `;
        } catch (e) {
          console.error('ShopQ: Failed to trigger organize:', e);
        }
      });
    } else if (result.error) {
      if (result.needsRefresh) {
        content.innerHTML = `
          <div style="text-align: center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 16px;">🔄</div>
            <p style="font-weight: 500; color: #202124; margin-bottom: 8px;">Extension Updated</p>
            <p style="font-size: 13px; color: #5f6368; margin-bottom: 16px;">Please refresh Gmail to reconnect.</p>
            <button id="mailq-refresh-btn" style="
              padding: 8px 16px;
              background: #1a73e8;
              color: white;
              border: none;
              border-radius: 4px;
              cursor: pointer;
            ">Refresh Gmail</button>
          </div>
        `;
        content.querySelector('#mailq-refresh-btn')?.addEventListener('click', () => {
          window.location.reload();
        });
      } else {
        content.innerHTML = `
          <div style="text-align: center; padding: 40px 20px;">
            <p style="color: #c5221f; margin-bottom: 16px;">Error: ${result.message}</p>
            <button id="mailq-retry-btn" style="
              padding: 8px 16px;
              background: #1a73e8;
              color: white;
              border: none;
              border-radius: 4px;
              cursor: pointer;
            ">Retry</button>
          </div>
        `;
        content.querySelector('#mailq-retry-btn')?.addEventListener('click', () => {
          // Refresh the panel
          const newContent = createDigestPanelContent();
          container.replaceWith(newContent);
        });
      }
    } else if (result.data?.html) {
      content.innerHTML = `<div style="line-height: 1.6;">${result.data.html}</div>`;
    } else if (result.data?.narrative) {
      content.innerHTML = `<div style="line-height: 1.6;">${result.data.narrative}</div>`;
    } else {
      content.innerHTML = `
        <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
          <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
          <p>No digest content available.</p>
        </div>
      `;
    }
  });

  return container;
}

/**
 * Initialize the returns sidebar using InboxSDK's Global sidebar API
 * This adds an icon to Gmail's native sidebar area (like Keep, Calendar, Tasks)
 * which should push Gmail content when opened.
 *
 * IFRAME ISOLATION: DOM changes inside iframe don't trigger Gmail's layout recalculation.
 */
async function initializeDigestSidebar(sdk) {
  console.log('ShopQ: Setting up Return Watch sidebar with IFRAME ISOLATION...');

  const panelEl = document.createElement('div');
  panelEl.id = 'shopq-returns-panel';
  panelEl.style.cssText = `
    width: 100%;
    height: 100%;
    display: flex;
    min-width: 0;
    overflow: hidden;
    contain: layout paint style;
  `;

  // Create iframe pointing to our returns sidebar HTML
  const iframe = document.createElement('iframe');
  iframe.src = chrome.runtime.getURL('returns-sidebar.html');
  iframe.id = 'shopq-returns-iframe';
  iframe.style.cssText = `
    width: 100%;
    height: 100%;
    border: none;
    display: block;
    background: #fff;
  `;
  panelEl.appendChild(iframe);

  // Track iframe ready state
  let iframeReady = false;
  let pendingReturns = null;

  // Listen for messages from iframe
  window.addEventListener('message', async (event) => {
    // Returns sidebar ready
    if (event.data?.type === 'SHOPQ_RETURNS_SIDEBAR_READY') {
      console.log('ShopQ: Returns sidebar iframe ready');
      iframeReady = true;
      // Fetch and send returns data
      await fetchAndSendReturns();
    }

    // Fetch returns request from sidebar
    if (event.data?.type === 'SHOPQ_FETCH_RETURNS') {
      console.log('ShopQ: Fetching returns data...');
      await fetchAndSendReturns();
    }

    // Update return status request
    if (event.data?.type === 'SHOPQ_UPDATE_RETURN_STATUS') {
      console.log('ShopQ: Updating return status:', event.data.returnId, event.data.status);
      await updateReturnStatus(event.data.returnId, event.data.status);
    }

    // Handle close button - close the sidebar panel
    if (event.data?.type === 'SHOPQ_CLOSE_SIDEBAR') {
      console.log('ShopQ: Closing sidebar');
      const shopqIcon = document.querySelector('[data-tooltip="Return Watch"]');
      if (shopqIcon) {
        shopqIcon.click();
      }
    }
  });

  // Fetch returns from API and send to iframe
  async function fetchAndSendReturns() {
    try {
      const userId = await getUserId();
      const response = await fetch(
        `${API_BASE_URL}/api/returns?user_id=${encodeURIComponent(userId)}`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      console.log('ShopQ: Fetched', data.cards?.length || 0, 'returns');

      if (iframeReady && iframe.contentWindow) {
        iframe.contentWindow.postMessage({
          type: 'SHOPQ_RETURNS_DATA',
          returns: data.cards || [],
        }, '*');
      } else {
        pendingReturns = data.cards || [];
      }
    } catch (error) {
      console.error('ShopQ: Failed to fetch returns:', error);
      if (iframeReady && iframe.contentWindow) {
        iframe.contentWindow.postMessage({
          type: 'SHOPQ_RETURNS_ERROR',
          message: error.message,
        }, '*');
      }
    }
  }

  // Update return status via API
  async function updateReturnStatus(returnId, newStatus) {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/returns/${encodeURIComponent(returnId)}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus }),
        }
      );

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      console.log('ShopQ: Status updated successfully');

      // Notify iframe of success
      if (iframeReady && iframe.contentWindow) {
        iframe.contentWindow.postMessage({
          type: 'SHOPQ_STATUS_UPDATED',
          returnId,
          status: newStatus,
        }, '*');
      }

      // Refresh the list
      await fetchAndSendReturns();
    } catch (error) {
      console.error('ShopQ: Failed to update status:', error);
    }
  }

  // Get user ID from storage
  async function getUserId() {
    try {
      const data = await chrome.storage.local.get('userId');
      return data.userId || 'default_user';
    } catch {
      return 'default_user';
    }
  }

  try {
    // Use InboxSDK's Global.addSidebarContentPanel API
    console.log('ShopQ: Calling sdk.Global.addSidebarContentPanel...');
    const panelView = await sdk.Global.addSidebarContentPanel({
      el: panelEl,
      title: 'Return Watch',
      iconUrl: chrome.runtime.getURL('icons/icon48.png'),
    });

    console.log('ShopQ: Return Watch sidebar registered successfully:', panelView);

    // Track sidebar state for persistence across navigation
    let sidebarShouldBeOpen = true;  // Start open by default
    let isNavigating = false;

    // Listen for panel visibility changes
    panelView.on('activate', () => {
      console.log('ShopQ: Return Watch panel activated');
      // Refresh returns data when panel opens
      fetchAndSendReturns();
    });

    panelView.on('deactivate', () => {
      console.log('ShopQ: Return Watch panel deactivated, isNavigating:', isNavigating);
      if (!isNavigating) {
        sidebarShouldBeOpen = false;
        console.log('ShopQ: User closed sidebar');
      }
    });

    // Keep sidebar open during navigation
    sdk.Router.handleAllRoutes((routeView) => {
      console.log('ShopQ: Route changed to:', routeView.getRouteID());
      isNavigating = true;

      setTimeout(() => {
        isNavigating = false;
        if (sidebarShouldBeOpen) {
          try {
            panelView.open();
            console.log('ShopQ: Re-opened sidebar after navigation');
          } catch (e) {
            console.log('ShopQ: Could not re-open sidebar:', e.message);
          }
        }
      }, 150);
    });

    // Expose refresh function for external triggers
    triggerDigestRefresh = () => {
      const now = Date.now();
      if (now - lastDigestRefreshTime < DIGEST_REFRESH_DEBOUNCE_MS) {
        console.log('ShopQ: Returns refresh debounced (too soon)');
        return;
      }
      lastDigestRefreshTime = now;

      console.log('ShopQ: External returns refresh triggered');
      fetchAndSendReturns();
    };

    // Auto-open on first load
    panelView.open();
    console.log('ShopQ: Return Watch sidebar opened on initial load');

  } catch (error) {
    console.error('ShopQ: Failed to add Return Watch sidebar panel:', error);
    console.log('ShopQ: Falling back to manual button injection...');
    injectShopQButton();

    const observer = new MutationObserver(() => {
      if (!document.getElementById('mailq-nav-button')) {
        injectShopQButton();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }
}

/**
 * Load digest content into a panel element
 * PHASE 3: Uses iframe postMessage to avoid Gmail layout issues
 */
async function loadDigestIntoPanel(panelEl) {
  // Get the sendToIframe function (set up in initializeDigestSidebar)
  const sendToIframe = panelEl._sendToIframe;

  if (!sendToIframe) {
    console.error('ShopQ: sendToIframe function not found on panelEl');
    return;
  }

  // Send loading state to iframe
  sendToIframe(`
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #5f6368;">
      <div class="spinner"></div>
      <span>Loading digest...</span>
    </div>
  `);

  const result = await fetchDigest();

  // Build the content HTML
  let contentHtml;

  if (result.empty) {
    contentHtml = `
      <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
        <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
        <p>${result.message}</p>
      </div>
    `;
  } else if (result.error) {
    contentHtml = `
      <div style="text-align: center; padding: 40px 20px;">
        <p style="color: #c5221f;">${result.message}</p>
      </div>
    `;
  } else if (result.data?.html) {
    console.log('ShopQ: Digest HTML received, length:', result.data.html?.length);
    contentHtml = `<div style="line-height: 1.6;">${result.data.html}</div>`;
  } else if (result.data?.narrative) {
    console.log('ShopQ: Digest narrative received, length:', result.data.narrative?.length);
    contentHtml = `<div style="line-height: 1.6;">${result.data.narrative}</div>`;
  } else {
    contentHtml = `<p style="text-align: center; color: #5f6368;">No digest available.</p>`;
  }

  // Cache the content for navigation persistence
  if (panelEl._setCachedHtml) {
    panelEl._setCachedHtml(contentHtml);
    console.log('ShopQ: Digest content cached for navigation persistence');
  }

  // Send content to iframe via postMessage (isolated from Gmail's DOM)
  sendToIframe(contentHtml);
  console.log('ShopQ: Digest content sent to iframe');
}

/**
 * Inject ShopQ button into Gmail's top nav
 */
function injectShopQButton() {
  // Skip if already exists
  if (document.getElementById('mailq-nav-button')) {
    return;
  }

  // Find the area where Gemini/Settings icons are (right side of header)
  const headerRight = document.querySelector('[data-ogsr-up]')?.closest('div')?.parentElement ||
                      document.querySelector('header')?.querySelector('[role="navigation"]') ||
                      document.querySelector('[aria-label="Support"]')?.closest('div')?.parentElement;

  if (!headerRight) {
    console.log('ShopQ: Header area not found, retrying...');
    setTimeout(injectShopQButton, 1000);
    return;
  }

  // Create ShopQ button matching Gmail's style
  const button = document.createElement('div');
  button.id = 'mailq-nav-button';
  button.innerHTML = `
    <style>
      #mailq-nav-button {
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
      #mailq-nav-button:hover { background: rgba(255,255,255,0.1); }
      #mailq-nav-button img { width: 24px; height: 24px; }
      #mailq-nav-button.active { background: rgba(138, 180, 248, 0.2); }
    </style>
    <img src="${chrome.runtime.getURL('icons/icon48.png')}" alt="ShopQ Digest" title="ShopQ Digest">
  `;

  button.addEventListener('click', () => {
    button.classList.toggle('active');
    toggleDigestDrawer();
  });

  // Try to insert before the profile picture (last item)
  const profilePic = headerRight.querySelector('img[aria-label]')?.closest('a, div') || headerRight.lastElementChild;
  if (profilePic) {
    profilePic.parentElement.insertBefore(button, profilePic);
    console.log('ShopQ: Nav button injected successfully');
  } else {
    headerRight.appendChild(button);
    console.log('ShopQ: Nav button appended to header');
  }
}

/**
 * Toggle the digest drawer open/closed
 */
function toggleDigestDrawer() {
  const existing = document.getElementById('mailq-digest-iframe');
  if (existing) {
    existing.remove();
    return;
  }

  // Create drawer as iframe for isolation
  const iframe = document.createElement('iframe');
  iframe.id = 'mailq-digest-iframe';
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
          <h2>ShopQ Digest</h2>
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
    document.getElementById('mailq-nav-button')?.classList.remove('active');
  });

  // Load digest content
  fetchDigest().then(result => {
    const content = doc.getElementById('content');
    if (!content) return;

    if (result.empty) {
      content.innerHTML = `
        <div style="text-align: center; padding: 40px 20px; color: #5f6368;">
          <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
          <p>${result.message}</p>
        </div>
      `;
    } else if (result.error) {
      content.innerHTML = `
        <div style="text-align: center; padding: 40px 20px;">
          <p style="color: #c5221f;">${result.message}</p>
        </div>
      `;
    } else if (result.data?.html) {
      content.innerHTML = `<div style="line-height: 1.6;">${result.data.html}</div>`;
    } else if (result.data?.narrative) {
      content.innerHTML = `<div style="line-height: 1.6;">${result.data.narrative}</div>`;
    } else {
      content.innerHTML = `<p style="text-align: center; color: #5f6368;">No digest available.</p>`;
    }
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
