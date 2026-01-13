/**
 * Mailq Background Service Worker
 * Handles email classification and organization
 */

// InboxSDK MV3 pageWorld injection handler + sync trigger
// Required for InboxSDK to access Gmail's page context
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

  // Allow triggering sync from content script or test
  if (message.type === 'SYNC_LABEL_CACHE') {
    (async () => {
      try {
        const token = await getAuthToken();
        if (token && typeof syncFromGmail === 'function') {
          const result = await syncFromGmail(token);
          sendResponse({ success: true, ...result });
        } else {
          sendResponse({ success: false, error: 'No token or sync function' });
        }
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }
});

// Load all dependencies using importScripts
// Directory structure aligned with mailq/ backend for consistency
importScripts(
  'modules/shared/config.js',
  // shared/ - Cross-cutting utilities (mailq/shared/)
  'modules/shared/signatures.js',  // Must load before utils.js (generateDedupeKey dependency)
  'modules/shared/utils.js',
  // classification/ - Email classification pipeline (mailq/classification/)
  'modules/classification/detectors.js',
  'modules/classification/verifier.js',
  // storage/ - Data persistence (mailq/storage/)
  'modules/storage/budget.js',
  'modules/storage/cache.js',
  // shared/ - Config and notifications
  'modules/shared/config-sync.js',
  // observability/ - Logging and telemetry (mailq/observability/)
  'modules/observability/telemetry.js',
  // gmail/ - Gmail API integration (mailq/gmail/)
  'modules/gmail/auth.js',
  // classification/ - Mapper and classifier
  'modules/classification/mapper.js',
  // storage/ - Classification logger
  'modules/storage/logger.js',
  // storage/ - Label cache for content script badge rendering
  'modules/storage/label-cache.js',
  // observability/ - Structured logging
  'modules/observability/structured-logger.js',
  // classification/ - Main classifier (depends on detectors, verifier, mapper)
  'modules/classification/classifier.js',
  // gmail/ - Gmail API client (depends on auth, cache, budget)
  'modules/gmail/api.js',
  // shared/ - Chrome notifications
  'modules/shared/notifications.js',
  // digest/ - Digest generation (mailq/digest/)
  'modules/digest/summary-email.js',
  'modules/digest/context-digest.js',
  // automation/ - Extension-specific auto-organize
  'modules/automation/auto-organize.js'
);

console.log(`🚀 Mailq: Background service worker loaded v${CONFIG.VERSION}`);
console.log('💡 Tip: Run showStats() in console to see cost breakdown');

// Global mutex to prevent concurrent organize sessions
let isOrganizing = false;

const LAST_DIGEST_ATTEMPT_KEY = 'mailq_last_digest_attempt_at';
const DIGEST_PENDING_FLAG_KEY = 'mailq_digest_pending';
const DIGEST_COOLDOWN_MINUTES = 1;
const PASSIVE_DIGEST_ENABLED = CONFIG.ENABLE_PASSIVE_DIGEST_TRIGGERS !== false;

/**
 * Send message to tab with auto-retry and content script injection
 */
async function sendMessageToTab(tabId, message) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, message);
    return response;
  } catch (error) {
    if (error.message.includes('Receiving end does not exist')) {
      console.log(`⚠️ Content script not ready in tab ${tabId}, injecting...`);

      try {
        // Re-inject the content script
        await chrome.scripting.executeScript({
          target: { tabId: tabId },
          files: ['dist/content.bundle.js']
        });

        // Wait a bit for script to initialize
        await new Promise(resolve => setTimeout(resolve, 100));

        // Retry the message
        const response = await chrome.tabs.sendMessage(tabId, message);
        console.log(`✅ Message sent after re-injection`);
        return response;
      } catch (injectError) {
        console.error(`❌ Failed to inject content script:`, injectError);
        throw injectError;
      }
    }
    throw error;
  }
}

/**
 * Track user label corrections for learning
 */
async function trackLabelCorrection(email, predictedLabels, currentLabels, result) {
  console.log('📝 User correction received:', {
    from: email.from,
    predicted: predictedLabels,
    actual: currentLabels
  });

  // Send to backend for learning
  try {
    const token = await getAuthToken();
    const response = await fetch(`${CONFIG.MAILQ_API_URL}/api/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        email_id: email.id,
        user_id: 'default',
        from: email.from,
        subject: email.subject,
        snippet: email.snippet || '',
        predicted_labels: predictedLabels,
        actual_labels: currentLabels,
        predicted_result: result || {}
      })
    });

    if (response.ok) {
      const data = await response.json();
      console.log('✅ Feedback sent to API:', data.message);
    } else {
      console.warn('⚠️ Feedback API error:', response.status, await response.text());
    }
  } catch (error) {
    console.warn('⚠️ Failed to send feedback:', error);
  }
}

/**
 * Handle extension installation and updates
 */
chrome.runtime.onInstalled.addListener(async (details) => {
  console.log('✅ Mailq extension installed');

  if (details.reason === 'install') {
    try {
      const response = await fetch(`${CONFIG.MAILQ_API_URL}/health`);
      const health = await response.json();
      console.log('✅ Mailq API healthy:', health);
    } catch (error) {
      console.error('❌ API health check failed:', error);
    }
  }

  if (details.reason === 'update') {
    console.log('🔄 Re-injecting content scripts into Gmail tabs...');
    const tabs = await chrome.tabs.query({ url: 'https://mail.google.com/*' });

    for (const tab of tabs) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['dist/content.bundle.js']
        });
        console.log(`✅ Re-injected content script into tab ${tab.id}`);
      } catch (error) {
        console.error(`❌ Failed to inject into tab ${tab.id}:`, error);
      }
    }
  }
});

/**
 * Handle messages from content scripts and popup
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Handle async messages
  (async () => {
    try {
      if (message.type === 'LABEL_CORRECTION') {
        await trackLabelCorrection(
          message.email,
          message.predictedLabels,
          message.currentLabels,
          message.result
        );
        sendResponse({ success: true });
      }
      else if (message.type === 'GET_AUTO_ORGANIZE_SETTINGS') {
        const settings = await getAutoOrganizeSettings();
        sendResponse(settings);
      }
      else if (message.type === 'SAVE_AUTO_ORGANIZE_SETTINGS') {
        const success = await saveAutoOrganizeSettings(message.settings);
        sendResponse({ success });
      }
      else if (message.type === 'ORGANIZE_NOW') {
        console.log('🧪 Manual organize triggered');

        // Fetch user info for personalized digest (runs once, cached)
        try {
          const token = await getAuthToken();
          const stored = await chrome.storage.local.get(['userName', 'userCity', 'userRegion']);
          if (!stored.userName) {
            const profileResponse = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (profileResponse.ok) {
              const profile = await profileResponse.json();
              if (profile.given_name) {
                await chrome.storage.local.set({ userName: profile.given_name });
                console.log(`👤 User name cached: ${profile.given_name}`);
              }
            }
          }
          if (!stored.userCity) {
            const locationResponse = await fetch('https://ipapi.co/json/');
            if (locationResponse.ok) {
              const location = await locationResponse.json();
              if (location.city) {
                await chrome.storage.local.set({
                  userCity: location.city,
                  userRegion: location.region || location.region_code
                });
                console.log(`📍 Location cached: ${location.city}, ${location.region}`);
              }
            }
          }
        } catch (e) {
          console.warn('⚠️ Failed to cache user info (non-critical):', e.message);
        }

        let result;
        try {
          result = await organizeInboxSilently();
          console.log('📊 Organize result:', JSON.stringify(result));
        } catch (err) {
          console.error('❌ Organize failed with error:', err.message, err.stack);
          result = { success: false, error: err.message };
        }

        // Email digest DISABLED - digest now shown in sidebar drawer only
        // No page reload needed - content script listens for storage.onChanged
        // and will update badges automatically via InboxSDK
        if (result.success && result.processedCount > 0) {
          console.log('✅ Classification complete. Content script will update via storage listener.');
          console.log('ℹ️  Digest available via MailQ button in Gmail header (no email sent)');
        }

        sendResponse(result);
      }
      else if (message.type === 'SHOW_NOTIFICATION') {
        // Show Chrome notification for selector warnings
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icons/icon48.png',
          title: message.title || 'MailQ',
          message: message.message,
          priority: 2
        });
        sendResponse({ success: true });
      }
      else if (message.type === 'CHECK_AUTH') {
        // Test hook to check if OAuth is working
        try {
          const token = await getAuthToken();
          sendResponse({ success: true, hasToken: !!token, tokenLength: token?.length || 0 });
        } catch (error) {
          sendResponse({ success: false, error: error.message });
        }
      }
      else if (message.type === 'SELECTOR_HEALTH_CHECK') {
        // Log selector health telemetry (informational only - Gmail UI changes frequently)
        console.log('ℹ️  Gmail selector health check:', message.health);

        // Optionally send to backend API for tracking
        try {
          const token = await getAuthToken();
          await fetch(`${CONFIG.MAILQ_API_URL}/api/telemetry/selector-health`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
              timestamp: message.timestamp,
              health: message.health,
              user_agent: navigator.userAgent
            })
          });
          console.log('📊 Selector health telemetry sent to backend');
        } catch (error) {
          console.warn('⚠️ Failed to send selector telemetry:', error);
        }

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
 * Handle extension icon click - Main entry point
 */
chrome.action.onClicked.addListener(async (tab) => {
  try {
    console.log('🎯 Mailq icon clicked');

    // Check if already organizing (prevent concurrent sessions)
    if (isOrganizing) {
      console.log('⏸️  Already organizing emails, skipping duplicate request');
      return;
    }

    isOrganizing = true;
    console.log('🔒 Organize session lock acquired');

    // Set session start timestamp for digest generation
    await chrome.storage.local.set({
      mailq_organize_session_start: new Date().toISOString()
    });

    // Step 1: Get OAuth token
    const token = await getAuthToken();
    console.log('✅ OAuth token obtained');

    // Step 1.5: Fetch user info for personalized digest (cached for performance)
    try {
      const stored = await chrome.storage.local.get(['userName', 'userCity', 'userRegion']);
      if (!stored.userName) {
        // Fetch user's first name from Google profile
        const profileResponse = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (profileResponse.ok) {
          const profile = await profileResponse.json();
          if (profile.given_name) {
            await chrome.storage.local.set({ userName: profile.given_name });
            console.log(`👤 User name cached: ${profile.given_name}`);
          }
        }
      }
      if (!stored.userCity) {
        // Fetch location from IP
        const locationResponse = await fetch('https://ipapi.co/json/');
        if (locationResponse.ok) {
          const location = await locationResponse.json();
          if (location.city) {
            await chrome.storage.local.set({
              userCity: location.city,
              userRegion: location.region || location.region_code
            });
            console.log(`📍 Location cached: ${location.city}, ${location.region}`);
          }
        }
      }
    } catch (e) {
      console.warn('⚠️ Failed to cache user info (non-critical):', e.message);
    }

    // Step 2: Fetch unlabeled emails from Inbox
    // Random batch size (25-50) spreads out processing per click
    const batchSize = Math.floor(Math.random() * (CONFIG.MAX_EMAILS_PER_BATCH - CONFIG.MIN_EMAILS_PER_BATCH + 1)) + CONFIG.MIN_EMAILS_PER_BATCH;
    console.log(`🔍 Searching for unlabeled emails in Inbox (batch: ${batchSize})...`);
    const emails = await getUnlabeledEmails(token, batchSize);
    console.log(`📧 Found ${emails.length} unlabeled emails to organize`);

    if (emails.length === 0) {
      console.log('✨ Inbox already organized!');
      return;
    }

    // Step 3: Classify emails using API
    console.log('🤖 Classifying emails...');
    const classified = await classifyEmails(emails);
    console.log(`✅ Classified ${classified.length} emails`);

    // Step 4: Populate label cache for visual layer (badges, dimming)
    // NOTE: Gmail labels and auto-archive DISABLED - visual layer only
    console.log('💾 Populating label cache for visual layer...');
    let cacheCount = 0;
    for (const item of classified) {
      if (item.threadId && typeof storeLabelCache === 'function') {
        await storeLabelCache(item.threadId, {
          type: item.type,
          importance: item.importance,
          client_label: item.client_label
        }, {
          // Email metadata for digest generation
          subject: item.subject,
          from: item.from,
          snippet: item.snippet,
          messageId: item.id,
          date: item.date || new Date().toISOString()
        });
        cacheCount++;
      }
    }
    console.log(`✅ Cached ${cacheCount} threads for badge rendering`);
    console.log('ℹ️  Emails remain in Inbox (no Gmail labels, no archive)');

    // Step 5: Digest email DISABLED - using sidebar drawer instead
    // The digest is now available via the MailQ nav button in Gmail's header
    console.log('ℹ️  Digest available via MailQ button in Gmail header');

    // Backend stats already logged per-request in classifier.js
    console.log('📊 Classification complete!');

  } catch (error) {
    console.error('❌ Error:', error);

    // Show user-friendly error notification
    if (typeof showError === 'function') {
      // Detect specific error types and provide helpful messages
      if (error.message && error.message.includes('409')) {
        showError('Label conflict detected. Some labels already exist. Please try again.');
      } else if (error.message && error.message.includes('401')) {
        showError('Authentication failed. Please sign in to Gmail again.');
      } else if (error.message && error.message.includes('403')) {
        showError('Permission denied. Please check Gmail API permissions.');
      } else if (error.message && error.message.includes('429')) {
        showError('Rate limit exceeded. Please wait a moment and try again.');
      } else {
        showError('Failed to organize emails. Check console for details.');
      }
    }
  } finally {
    // Always release lock
    isOrganizing = false;
    console.log('🔓 Organize session lock released');
  }
});

// ============================================================================
// CLEANUP: Re-archive labeled emails stuck in inbox
// ============================================================================

/**
 * Cleanup function: Find emails with MailQ labels that are still in inbox
 * and re-archive them. This fixes cases where archiving failed silently.
 *
 * Usage in console: cleanupLabeledInbox()
 */
async function cleanupLabeledInbox() {
  try {
    console.log('🧹 Starting cleanup: Finding labeled emails stuck in inbox...');

    // Step 1: Get OAuth token
    const token = await getAuthToken();
    console.log('✅ OAuth token obtained');

    // Step 2: Search for emails that have MailQ labels AND are in inbox
    // This is the opposite of our normal search - we want labeled emails in inbox
    const mailqLabels = [
      'MailQ/Receipts',
      'MailQ/Shopping',
      'MailQ/Messages',
      'MailQ/Work',
      'MailQ/Newsletters',
      'MailQ/Notifications',
      'MailQ/Events',
      'MailQ/Finance',
      'MailQ/Action-Required',
      'MailQ/Promotions',
      'MailQ/Personal'
    ];

    // Build query: in:inbox AND (has any MailQ label)
    const labelQuery = mailqLabels.map(l => `label:${l}`).join(' OR ');
    const query = `in:inbox (${labelQuery})`;

    console.log('🔍 Search query:', query);

    const encodedQuery = encodeURIComponent(query);
    const response = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/threads?q=${encodedQuery}&maxResults=100`,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      throw new Error(`Gmail API error: ${response.status}`);
    }

    const data = await response.json();
    const threads = data.threads || [];

    console.log(`📬 Found ${threads.length} labeled emails still in inbox`);

    if (threads.length === 0) {
      console.log('✨ Inbox is clean! No labeled emails found.');
      return { success: true, cleaned: 0 };
    }

    // Step 3: Archive each thread by removing INBOX label
    let successCount = 0;
    let errors = [];

    for (let i = 0; i < threads.length; i++) {
      const thread = threads[i];

      try {
        console.log(`🔧 [${i + 1}/${threads.length}] Archiving thread ${thread.id}...`);

        const archiveResponse = await fetchWithRetry(
          `https://gmail.googleapis.com/gmail/v1/users/me/threads/${thread.id}/modify`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              removeLabelIds: ['INBOX', 'UNREAD', 'IMPORTANT']
            })
          },
          3  // Retry up to 3 times
        );

        if (!archiveResponse.ok) {
          const errorText = await archiveResponse.text();
          throw new Error(`API error ${archiveResponse.status}: ${errorText}`);
        }

        const result = await archiveResponse.json();
        console.log(`✅ [${i + 1}/${threads.length}] Archived thread ${thread.id}`);
        console.log(`   Messages in thread: ${result.messages?.length || 'unknown'}`);

        // Verify INBOX was actually removed
        const stillInInbox = result.messages?.[0]?.labelIds?.includes('INBOX');
        if (stillInInbox) {
          console.warn(`⚠️  WARNING: Thread ${thread.id} still has INBOX label after archive attempt!`);
          errors.push({ thread: thread.id, error: 'INBOX label still present after removal' });
        } else {
          successCount++;
        }

      } catch (err) {
        console.error(`❌ Failed to archive thread ${thread.id}:`, err);
        errors.push({ thread: thread.id, error: err.message });
      }
    }

    console.log(`\n📊 Cleanup Results: ${successCount}/${threads.length} successfully archived`);

    if (errors.length > 0) {
      console.warn(`⚠️ ${errors.length} errors:`, errors);
    }

    return {
      success: true,
      cleaned: successCount,
      total: threads.length,
      errors: errors
    };

  } catch (error) {
    console.error('❌ Cleanup failed:', error);
    return {
      success: false,
      error: error.message
    };
  }
}

// Make it available globally for console access
globalThis.cleanupLabeledInbox = cleanupLabeledInbox;

// ============================================================================
// AUTO-ORGANIZE: Continuous Inbox Zero
// ============================================================================

/**
 * Listen for alarms - handle auto-organize triggers
 */
chrome.alarms.onAlarm.addListener(async (alarm) => {
  console.log(`⏰ Alarm triggered: ${alarm.name}`);

  await handleAutoOrganizeAlarm(alarm);
});

/**
 * Initialize auto-organize on extension startup
 * Restores alarms if they were previously enabled
 */
chrome.runtime.onStartup.addListener(async () => {
  console.log('🔄 Extension startup - restoring settings...');

  try {
    // Restore auto-organize
    const settings = await getAutoOrganizeSettings();
    if (settings.enabled) {
      await setupAutoOrganize(settings.enabled, settings.intervalMinutes, { silent: true });
      console.log(`✅ Auto-organize restored: every ${settings.intervalMinutes} minutes`);
    }

    // Sync label cache from Gmail (catches changes made on other devices)
    try {
      const token = await getAuthToken({ forceRefresh: false });
      if (token && typeof syncFromGmail === 'function') {
        const result = await syncFromGmail(token);
        console.log(`✅ Label cache synced: ${result.synced} threads`);
      }
    } catch (syncError) {
      console.warn('⚠️ Label cache sync skipped:', syncError.message);
    }
  } catch (error) {
    console.error('❌ Failed to restore settings:', error);
  }
});

/**
 * Also restore on extension install/update
 */
chrome.runtime.onInstalled.addListener(async (details) => {
  console.log(`📦 Extension ${details.reason}:`, details);

  try {
    const settings = await getAutoOrganizeSettings();
    if (settings.enabled) {
      await setupAutoOrganize(settings.enabled, settings.intervalMinutes, { silent: true });
      console.log(`✅ Auto-organize scheduled after ${details.reason}`);
    }

    // Sync label cache from Gmail on install/update
    try {
      const token = await getAuthToken({ forceRefresh: false });
      if (token && typeof syncFromGmail === 'function') {
        const result = await syncFromGmail(token);
        console.log(`✅ Label cache synced after ${details.reason}: ${result.synced} threads`);
      }
    } catch (syncError) {
      console.warn('⚠️ Label cache sync skipped:', syncError.message);
    }
  } catch (error) {
    console.error('❌ Failed to restore settings after install/update:', error);
  }
});

function isGmailTab(tab) {
  if (!tab || !tab.url) {
    return false;
  }

  return tab.url.startsWith('https://mail.google.com');
}

async function maybeSendDigest(trigger, tab) {
  if (!PASSIVE_DIGEST_ENABLED) {
    return;
  }
  try {
    if (!isGmailTab(tab) || !tab.active) {
      return;
    }

    const now = Date.now();
    const nowIso = new Date(now).toISOString();
    const minIntervalMs = DIGEST_COOLDOWN_MINUTES * 60 * 1000;

    const attemptData = await chrome.storage.local.get(LAST_DIGEST_ATTEMPT_KEY);
    const lastAttempt = attemptData[LAST_DIGEST_ATTEMPT_KEY];
    if (lastAttempt) {
      const diff = now - new Date(lastAttempt).getTime();
      if (diff < minIntervalMs) {
        return;
      }
    }

    const lastDigestSentAt = await getLastDigestSentAt();
    if (lastDigestSentAt) {
      const diffSinceDigest = now - new Date(lastDigestSentAt).getTime();
      if (diffSinceDigest < minIntervalMs) {
        return;
      }
    }

    const pendingData = await chrome.storage.local.get(DIGEST_PENDING_FLAG_KEY);
    let digestPending = pendingData[DIGEST_PENDING_FLAG_KEY];

    if (!digestPending) {
      const storageKeys = await chrome.storage.local.get([
        'mailq_last_auto_organize_at',
        'mailq_last_digest_organize_at'
      ]);
      const timestamps = [
        storageKeys.mailq_last_auto_organize_at,
        storageKeys.mailq_last_digest_organize_at
      ]
        .filter(Boolean)
        .map((iso) => {
          const parsed = Date.parse(iso);
          return Number.isNaN(parsed) ? null : parsed;
        })
        .filter((value) => value !== null);

      const lastOrganizeMs = timestamps.length ? Math.max(...timestamps) : null;
      const needsOrganize = !lastOrganizeMs || (now - lastOrganizeMs) > minIntervalMs;

      if (needsOrganize) {
        console.log('🔄 No pending digest detected; running organize pass before summary...');
        try {
          const organizeResult = await organizeInboxSilently();
          if (organizeResult?.success) {
            if (organizeResult.processedCount > 0) {
              await chrome.storage.local.set({ [DIGEST_PENDING_FLAG_KEY]: true });
              digestPending = true;
            }
            await chrome.storage.local.set({
              mailq_last_digest_organize_at: new Date(now).toISOString()
            });
          } else {
            console.warn('⚠️ Organize pass before digest failed or returned no results:', organizeResult?.error);
          }
        } catch (organizeError) {
          console.error('❌ Failed to organize inbox before digest:', organizeError);
        }

        if (!digestPending) {
          const pendingRefresh = await chrome.storage.local.get(DIGEST_PENDING_FLAG_KEY);
          digestPending = pendingRefresh[DIGEST_PENDING_FLAG_KEY];
        }
      }
    }

    if (!digestPending && lastDigestSentAt) {
      const diffSinceDigest = now - new Date(lastDigestSentAt).getTime();
      if (diffSinceDigest < minIntervalMs) {
        return;
      }
    }

    await chrome.storage.local.set({ [LAST_DIGEST_ATTEMPT_KEY]: nowIso });

    console.log(`📬 Digest check triggered via ${trigger}`);
    const result = await generateAndSendSummaryEmail({ trigger });

    if (result && result.success) {
      console.log('✅ Digest sent after user activity');
    } else if (result && result.error === 'No classifications to summarize') {
      console.log('ℹ️ No new classifications to summarize at this time');
    }
  } catch (error) {
    console.error('❌ Digest trigger failed:', error);
  }
}

if (PASSIVE_DIGEST_ENABLED) {
  chrome.tabs.onActivated.addListener(async (activeInfo) => {
    try {
      const tab = await chrome.tabs.get(activeInfo.tabId);
      await maybeSendDigest('tab-activated', tab);
    } catch (error) {
      console.error('❌ Failed to handle tab activation for digest:', error);
    }
  });

  chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.active) {
      await maybeSendDigest('tab-updated', tab);
    }
  });
} else {
  console.log('ℹ️ Passive digest triggers disabled');
}

// Ensure alarm exists whenever the service worker wakes up
getAutoOrganizeSettings()
  .then(async (settings) => {
    if (settings.enabled) {
      await setupAutoOrganize(settings.enabled, settings.intervalMinutes, { silent: true });
    }
  })
  .catch((error) => {
    console.error('❌ Failed to initialize auto-organize on startup:', error);
  });

console.log('✅ Auto-organize listeners registered');
