/**
 * Refresh & Sync Trigger Logic
 *
 * Manages when to scan for new purchase emails:
 *
 * Triggers:
 * - on_gmail_load: When Gmail tab loads, if >6h since last scan
 * - on_tab_focus: When Gmail tab focused, if >10min since last scan
 * - periodic: Every 45min while Gmail is active
 * - manual_refresh: User clicks refresh button
 *
 * Window sizes:
 * - Full scan: 14 days (on_gmail_load, first scan)
 * - Focus scan: 7 days (on_tab_focus)
 * - Periodic scan: 3 days (periodic)
 * - Manual scan: 7 days (manual_refresh)
 */

const REFRESH_LOG_PREFIX = '[ReturnWatch:Refresh]';

// ============================================================
// CONSTANTS
// ============================================================

/**
 * Refresh timing configuration (in milliseconds).
 */
const REFRESH_CONFIG = {
  // Minimum time between scans (10 minutes)
  FOCUS_THRESHOLD_MS: 10 * 60 * 1000,

  // Time to consider scan stale (6 hours)
  STALE_THRESHOLD_MS: 6 * 60 * 60 * 1000,

  // Periodic scan interval (45 minutes)
  PERIODIC_INTERVAL_MS: 45 * 60 * 1000,

  // Chrome alarm name for periodic scans
  PERIODIC_ALARM_NAME: 'returnwatch_periodic_scan',
};

/**
 * Scan window sizes (in days).
 */
const SCAN_WINDOWS = {
  FULL: 60,      // Full scan (on_gmail_load, first scan) - 60 days to catch most return windows
  FOCUS: 7,      // Tab focus scan
  PERIODIC: 3,   // Periodic background scan
  MANUAL: 30,    // Manual refresh - 30 days
};

// ============================================================
// STATE MANAGEMENT
// ============================================================

/**
 * In-memory state for refresh logic.
 */
const refreshState = {
  // Is a scan currently running?
  scanInProgress: false,

  // Last scan start time (epoch ms)
  lastScanStart: 0,

  // Last scan end time (epoch ms)
  lastScanEnd: 0,

  // Is Gmail tab active?
  gmailTabActive: false,

  // Gmail tab ID (if known)
  gmailTabId: null,
};

/**
 * Check if enough time has passed since last scan.
 *
 * @param {number} thresholdMs - Minimum time between scans
 * @returns {boolean}
 */
function shouldScan(thresholdMs) {
  if (refreshState.scanInProgress) {
    return false;
  }

  const timeSinceLastScan = Date.now() - refreshState.lastScanEnd;
  return timeSinceLastScan >= thresholdMs;
}

/**
 * Check if last scan is stale (needs full refresh).
 *
 * @returns {boolean}
 */
function isLastScanStale() {
  if (refreshState.lastScanEnd === 0) {
    return true; // Never scanned
  }

  const timeSinceLastScan = Date.now() - refreshState.lastScanEnd;
  return timeSinceLastScan >= REFRESH_CONFIG.STALE_THRESHOLD_MS;
}

// ============================================================
// SCAN TRIGGERS
// ============================================================

/**
 * Trigger a scan with the specified window.
 *
 * @param {number} window_days - Days to scan back
 * @param {string} trigger - What triggered this scan
 * @returns {Promise<ScanResult|null>}
 */
async function triggerScan(window_days, trigger) {
  // Wait for any pending pipeline reset (e.g., extension reload clears stale data)
  if (typeof pipelineResetComplete !== 'undefined') {
    await pipelineResetComplete;
  }

  if (refreshState.scanInProgress) {
    console.log(REFRESH_LOG_PREFIX, 'SCAN_SKIPPED', 'already in progress');
    return null;
  }

  refreshState.scanInProgress = true;
  refreshState.lastScanStart = Date.now();

  console.log(REFRESH_LOG_PREFIX, 'SCAN_TRIGGER', trigger, `window=${window_days}d`);

  try {
    const result = await scanPurchases({
      window_days,
      incremental: true, // Always incremental — processed email IDs prevent duplicate work
      skipPersistence: true, // Don't save to backend DB — sidebar reads from IndexedDB
    });

    refreshState.lastScanEnd = Date.now();
    console.log(REFRESH_LOG_PREFIX, 'SCAN_SUCCESS', trigger, result.stats);

    return result;

  } catch (error) {
    console.error(REFRESH_LOG_PREFIX, 'SCAN_FAILED', trigger, error.message);
    throw error;

  } finally {
    refreshState.scanInProgress = false;
  }
}

/**
 * Handle Gmail tab load event.
 * Triggers full scan if >6h since last scan or first scan.
 *
 * @returns {Promise<ScanResult|null>}
 */
async function onGmailLoad() {
  console.log(REFRESH_LOG_PREFIX, 'ON_GMAIL_LOAD');

  // Check if scan is stale
  if (!isLastScanStale()) {
    console.log(REFRESH_LOG_PREFIX, 'SKIP', 'scan not stale');
    return null;
  }

  return triggerScan(SCAN_WINDOWS.FULL, 'gmail_load');
}

/**
 * Handle Gmail tab focus event.
 * Triggers scan if >10min since last scan.
 *
 * @returns {Promise<ScanResult|null>}
 */
async function onTabFocus() {
  console.log(REFRESH_LOG_PREFIX, 'ON_TAB_FOCUS');

  if (!shouldScan(REFRESH_CONFIG.FOCUS_THRESHOLD_MS)) {
    console.log(REFRESH_LOG_PREFIX, 'SKIP', 'too soon since last scan');
    return null;
  }

  return triggerScan(SCAN_WINDOWS.FOCUS, 'tab_focus');
}

/**
 * Handle periodic scan alarm.
 *
 * @returns {Promise<ScanResult|null>}
 */
async function onPeriodicAlarm() {
  console.log(REFRESH_LOG_PREFIX, 'ON_PERIODIC');

  // Only scan if Gmail is active
  if (!refreshState.gmailTabActive) {
    console.log(REFRESH_LOG_PREFIX, 'SKIP', 'Gmail not active');
    return null;
  }

  if (!shouldScan(REFRESH_CONFIG.FOCUS_THRESHOLD_MS)) {
    console.log(REFRESH_LOG_PREFIX, 'SKIP', 'too soon since last scan');
    return null;
  }

  return triggerScan(SCAN_WINDOWS.PERIODIC, 'periodic');
}

/**
 * Handle manual refresh request from user.
 *
 * @returns {Promise<ScanResult>}
 */
async function onManualRefresh() {
  console.log(REFRESH_LOG_PREFIX, 'ON_MANUAL_REFRESH');

  // Always honor manual refresh (don't check timing)
  if (refreshState.scanInProgress) {
    throw new Error('Scan already in progress');
  }

  return triggerScan(SCAN_WINDOWS.MANUAL, 'manual');
}

// ============================================================
// CHROME ALARM MANAGEMENT
// ============================================================

/**
 * Start the periodic scan alarm.
 */
async function startPeriodicAlarm() {
  const existing = await chrome.alarms.get(REFRESH_CONFIG.PERIODIC_ALARM_NAME);
  if (existing) {
    console.log(REFRESH_LOG_PREFIX, 'PERIODIC_ALARM_ALREADY_EXISTS',
      `interval=${existing.periodInMinutes}min`);
    return;
  }

  chrome.alarms.create(REFRESH_CONFIG.PERIODIC_ALARM_NAME, {
    periodInMinutes: REFRESH_CONFIG.PERIODIC_INTERVAL_MS / 60000,
  });
  console.log(REFRESH_LOG_PREFIX, 'PERIODIC_ALARM_STARTED',
    `interval=${REFRESH_CONFIG.PERIODIC_INTERVAL_MS / 60000}min`);
}

/**
 * Stop the periodic scan alarm.
 */
function stopPeriodicAlarm() {
  chrome.alarms.clear(REFRESH_CONFIG.PERIODIC_ALARM_NAME);
  console.log(REFRESH_LOG_PREFIX, 'PERIODIC_ALARM_STOPPED');
}

/**
 * Handle Chrome alarm events.
 *
 * @param {chrome.alarms.Alarm} alarm
 */
function handleAlarm(alarm) {
  if (alarm.name === REFRESH_CONFIG.PERIODIC_ALARM_NAME) {
    onPeriodicAlarm().catch(error => {
      console.error(REFRESH_LOG_PREFIX, 'PERIODIC_ALARM_ERROR', error.message);
    });
  }
}

// ============================================================
// TAB TRACKING
// ============================================================

/**
 * Check if a URL is Gmail.
 *
 * @param {string} url
 * @returns {boolean}
 */
function isGmailUrl(url) {
  if (!url) return false;
  return url.startsWith('https://mail.google.com/');
}

/**
 * Handle tab activation (focus).
 *
 * @param {Object} activeInfo - Chrome tab activation info
 */
async function handleTabActivated(activeInfo) {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);

    if (isGmailUrl(tab.url)) {
      refreshState.gmailTabActive = true;
      refreshState.gmailTabId = tab.id;

      // Trigger focus scan
      onTabFocus().catch(error => {
        console.error(REFRESH_LOG_PREFIX, 'TAB_FOCUS_ERROR', error.message);
      });
    } else {
      refreshState.gmailTabActive = false;
    }
  } catch (error) {
    // Tab might not exist
    console.warn(REFRESH_LOG_PREFIX, 'TAB_GET_ERROR', error.message);
  }
}

/**
 * Handle tab update (URL change).
 *
 * @param {number} tabId
 * @param {Object} changeInfo
 * @param {Object} tab
 */
function handleTabUpdated(tabId, changeInfo, tab) {
  if (changeInfo.status === 'complete' && isGmailUrl(tab.url)) {
    refreshState.gmailTabActive = true;
    refreshState.gmailTabId = tabId;

    // Gmail just loaded
    onGmailLoad().catch(error => {
      console.error(REFRESH_LOG_PREFIX, 'GMAIL_LOAD_ERROR', error.message);
    });
  }
}

/**
 * Handle tab removal.
 *
 * @param {number} tabId
 */
function handleTabRemoved(tabId) {
  if (tabId === refreshState.gmailTabId) {
    refreshState.gmailTabActive = false;
    refreshState.gmailTabId = null;
  }
}

// ============================================================
// INITIALIZATION
// ============================================================

/**
 * Initialize refresh system.
 * Sets up listeners and starts periodic alarm.
 */
function initializeRefreshSystem() {
  console.log(REFRESH_LOG_PREFIX, 'INITIALIZING');

  // Scan on Gmail page load
  chrome.tabs.onUpdated.addListener(handleTabUpdated);

  // Tab removal listener for state cleanup
  chrome.tabs.onRemoved.addListener(handleTabRemoved);

  // Track Gmail tab state (useful for periodic alarm gating)
  chrome.tabs.query({ url: 'https://mail.google.com/*' }, (tabs) => {
    if (tabs.length > 0) {
      refreshState.gmailTabActive = true;
      refreshState.gmailTabId = tabs[0].id;
    }
  });

  // Enable periodic background scanning (every 45 minutes)
  chrome.alarms.onAlarm.addListener(handleAlarm);
  startPeriodicAlarm();

  console.log(REFRESH_LOG_PREFIX, 'INITIALIZED');
}

/**
 * Get current refresh state (for debugging/UI).
 *
 * @returns {Object}
 */
function getRefreshState() {
  return {
    scanInProgress: refreshState.scanInProgress,
    lastScanStart: refreshState.lastScanStart,
    lastScanEnd: refreshState.lastScanEnd,
    gmailTabActive: refreshState.gmailTabActive,
    timeSinceLastScan: refreshState.lastScanEnd
      ? Date.now() - refreshState.lastScanEnd
      : null,
  };
}
