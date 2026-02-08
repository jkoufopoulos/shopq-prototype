/**
 * Reclaim Content Script (ES Module Entry Point)
 *
 * Bundled by webpack with InboxSDK. Implements the Returns Sidebar for Gmail.
 *
 * Architecture:
 *   DisposeBag           — lifecycle cleanup utility
 *   SidebarMessageRouter — origin-validated postMessage dispatch
 *   SidebarController    — iframe panel, order CRUD, expiring indicator, nav persistence
 *
 * Disposal: 30-second context check → disposeAll() → refresh banner on extension reload
 */

import * as InboxSDK from '@inboxsdk/core';
import {
  SIDEBAR_REFRESH_INTERVAL_MS,
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
// CLEANUP: Remove any stale Reclaim elements from previous loads
// =============================================================================

(function cleanupStaleElements() {
  // IMPORTANT: Do NOT reset html/body styles - this interferes with Gmail's dark mode
  document.getElementById('reclaim-refresh-banner')?.remove();
  document.getElementById('reclaim-sidebar-panel')?.remove();
  console.log('Reclaim: Cleaned up stale elements');
})();

// =============================================================================
// CONFIGURATION
// =============================================================================

// Registered InboxSDK App ID
const SHOPQ_APP_ID = 'sdk_mailqapp_8eb273b616';

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

  const container = document.createElement('div');
  Object.assign(container.style, {
    position: 'fixed', top: '0', left: '0', right: '0',
    background: '#1a73e8', color: 'white', padding: '8px 16px',
    textAlign: 'center', fontFamily: "'Google Sans', Roboto, sans-serif",
    fontSize: '14px', zIndex: '99999', display: 'flex',
    justifyContent: 'center', alignItems: 'center', gap: '12px',
  });

  const msg = document.createElement('span');
  msg.textContent = 'Reclaim was updated. Please refresh this page to continue.';

  const refreshBtn = document.createElement('button');
  refreshBtn.textContent = 'Refresh';
  Object.assign(refreshBtn.style, {
    background: 'white', color: '#1a73e8', border: 'none',
    padding: '6px 16px', borderRadius: '4px', fontWeight: '500', cursor: 'pointer',
  });
  refreshBtn.addEventListener('click', () => location.reload());

  const dismissBtn = document.createElement('button');
  dismissBtn.textContent = 'Dismiss';
  Object.assign(dismissBtn.style, {
    background: 'transparent', color: 'white',
    border: '1px solid rgba(255,255,255,0.5)',
    padding: '6px 12px', borderRadius: '4px', cursor: 'pointer',
  });
  dismissBtn.addEventListener('click', () => banner.remove());

  container.append(msg, refreshBtn, dismissBtn);
  banner.appendChild(container);
  document.body.appendChild(banner);
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

      panelView.open();
      console.log('Reclaim: Reclaim sidebar opened on initial load');

    } catch (error) {
      console.error('Reclaim: Failed to add Reclaim sidebar panel:', error);
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

// Module-scope reference
let sidebarController = null;

// Global dispose bag for cleanup on extension invalidation
const globalDisposeBag = new DisposeBag();

/**
 * Dispose all managed resources (sidebar controller, global listeners).
 * Called when extension context is invalidated.
 */
function disposeAll() {
  console.log('Reclaim: Disposing all resources...');
  if (sidebarController) {
    sidebarController.dispose();
    sidebarController = null;
  }
  globalDisposeBag.dispose();
}

// =============================================================================
// INITIALIZATION
// =============================================================================

/**
 * Initialize InboxSDK and the returns sidebar.
 */
async function initializeVisualLayer() {
  if (!isExtensionContextValid()) {
    console.warn('Reclaim: Extension context invalidated - showing refresh banner');
    showRefreshBanner();
    return;
  }

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

    // Initialize returns sidebar
    const extensionOrigin = chrome.runtime.getURL('').slice(0, -1);
    const router = new SidebarMessageRouter(extensionOrigin);
    sidebarController = new SidebarController(router);
    await sidebarController.init(sdk);
  } catch (error) {
    console.error('Reclaim: Failed to load InboxSDK:', error.message);
    if (!isExtensionContextValid() || error.message?.includes('Extension context invalidated')) {
      showRefreshBanner();
    }
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeVisualLayer);
} else {
  initializeVisualLayer();
}

} // End of initReclaim()
