/**
 * Auto-Organize Module
 *
 * Enables continuous inbox zero by automatically processing emails at regular intervals.
 * Uses Chrome Alarms API for reliable background processing.
 * Fully automatic - runs in the background without user intervention.
 */

const AUTO_ORGANIZE_ALARM = 'mailq-auto-organize';
const AUTO_ORGANIZE_SETTINGS_KEY = 'mailq_auto_organize_settings';

// Default settings
const DEFAULT_SETTINGS = {
  enabled: true,  // Keep inbox sweeping enabled out of the box
  intervalMinutes: 5,  // Sweep every 5 minutes for near real-time cleanup
  notifyOnZero: false,  // Silence notifications when running continuously
  onlyWhenGmailOpen: false  // Run even if Gmail tab is closed (uses Gmail API)
};

/**
 * Get auto-organize settings
 */
async function getAutoOrganizeSettings() {
  try {
    const result = await chrome.storage.sync.get(AUTO_ORGANIZE_SETTINGS_KEY);
    return {
      ...DEFAULT_SETTINGS,
      ...(result[AUTO_ORGANIZE_SETTINGS_KEY] || {})
    };
  } catch (error) {
    console.warn('⚠️ Failed to get auto-organize settings:', error);
    return DEFAULT_SETTINGS;
  }
}

/**
 * Save auto-organize settings
 */
async function saveAutoOrganizeSettings(settings) {
  try {
    await chrome.storage.sync.set({
      [AUTO_ORGANIZE_SETTINGS_KEY]: settings
    });
    console.log('✅ Auto-organize settings saved:', settings);

    // Update alarm based on new settings
    await setupAutoOrganize(settings.enabled, settings.intervalMinutes);

    return true;
  } catch (error) {
    console.error('❌ Failed to save auto-organize settings:', error);
    return false;
  }
}

/**
 * Setup auto-organize alarm
 * @param {boolean} enabled - Whether to enable auto-organize
 * @param {number} intervalMinutes - Check interval in minutes (5, 10, 15, 30)
 */
async function setupAutoOrganize(enabled, intervalMinutes = 15, options = {}) {
  try {
    // Clear any existing alarm
    await chrome.alarms.clear(AUTO_ORGANIZE_ALARM);

    // Check global config flag (for manual validation mode)
    if (CONFIG.ENABLE_AUTO_ORGANIZE === false) {
      console.log('🔕 Auto-organize disabled via CONFIG.ENABLE_AUTO_ORGANIZE');
      return;
    }

    if (!enabled) {
      console.log('🔕 Auto-organize disabled');
      return;
    }

    // Validate interval
    const validIntervals = [5, 10, 15, 30, 60];
    if (!validIntervals.includes(intervalMinutes)) {
      console.warn(`⚠️ Invalid interval ${intervalMinutes}, using 15 minutes`);
      intervalMinutes = 15;
    }

    // Create new alarm
    await chrome.alarms.create(AUTO_ORGANIZE_ALARM, {
      periodInMinutes: intervalMinutes,
      delayInMinutes: 1  // Start first check in 1 minute
    });

    console.log(`🔔 Auto-organize enabled: every ${intervalMinutes} minutes`);

    if (!options.silent) {
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: 'MailQ Auto-Organize Enabled',
        message: `Your inbox will be organized automatically every ${intervalMinutes} minutes.`,
        priority: 1
      });
    }

  } catch (error) {
    console.error('❌ Failed to setup auto-organize:', error);
  }
}

/**
 * Handle alarm trigger - process inbox automatically
 */
async function handleAutoOrganizeAlarm(alarm) {
  if (alarm.name !== AUTO_ORGANIZE_ALARM) {
    return;  // Not our alarm
  }

  console.log('\n🔔 Auto-organize alarm triggered');

  // Check global config flag first (for manual validation mode)
  if (CONFIG.ENABLE_AUTO_ORGANIZE === false) {
    console.log('⏸️  Auto-organize disabled via CONFIG.ENABLE_AUTO_ORGANIZE');
    return;
  }

  try {
    // Check if already organizing (prevent concurrent sessions)
    // Note: isOrganizing is a global variable in background.js
    if (typeof isOrganizing !== 'undefined' && isOrganizing) {
      console.log('⏸️  Already organizing emails, skipping auto-organize');
      return;
    }

    // Check if still enabled
    const settings = await getAutoOrganizeSettings();

    if (!settings.enabled) {
      console.log('⏸️  Auto-organize is disabled, skipping');
      await chrome.alarms.clear(AUTO_ORGANIZE_ALARM);
      return;
    }

    // If setting requires Gmail to be open, check for Gmail tabs
    if (settings.onlyWhenGmailOpen) {
      const gmailTabs = await chrome.tabs.query({
        url: 'https://mail.google.com/*'
      });

      if (gmailTabs.length === 0) {
        console.log('⏸️  Gmail not open, skipping (as per settings)');
        return;
      }
    }

    // Run organization process
    console.log('🚀 Running automatic inbox organization...');

    const nowIso = new Date().toISOString();

    // Mark session start time for digest generation
    await chrome.storage.local.set({
      mailq_organize_session_start: nowIso
    });
    console.log('📍 Organize session start time recorded');

    const result = await organizeInboxSilently();

    await chrome.storage.local.set({
      mailq_last_auto_organize_at: nowIso
    });

    // Show notification if inbox reached zero and user wants notifications
    if (settings.notifyOnZero && result.processedCount > 0 && result.remainingCount === 0) {
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: '🎉 Inbox Zero Achieved!',
        message: `Processed ${result.processedCount} emails. Your inbox is now empty.`,
        priority: 2
      });
    }

    console.log(`✅ Auto-organize complete: ${result.processedCount} emails processed, ${result.remainingCount} remaining`);

    if (result.processedCount > 0) {
      await chrome.storage.local.set({
        mailq_digest_pending: true,
        mailq_last_digest_candidate_at: nowIso,
        mailq_digest_needs_refresh: Date.now()  // Signal content script to refresh digest
      });
      console.log('📬 Digest marked pending, signaled content script to refresh');
    } else {
      await chrome.storage.local.set({ mailq_digest_pending: false });
    }

  } catch (error) {
    console.error('❌ Auto-organize failed:', error);

    // Don't show error notifications for every failure (could be annoying)
    // Just log to console
  }
}

/**
 * Organize inbox silently (no user interaction)
 * Returns summary of what was processed
 */
async function organizeInboxSilently() {
  try {
    // Get auth token
    let token = await getAuthToken();

    // Check budget
    const budgetCheck = await checkBudget();
    if (!budgetCheck.allowed) {
      console.warn(`⚠️ Budget limit reached: ${budgetCheck.reason}`);
      return {
        success: false,
        processedCount: 0,
        remainingCount: 0,
        error: budgetCheck.reason
      };
    }

    // Fetch unlabeled emails with random batch size (25-50)
    const batchSize = Math.floor(Math.random() * (CONFIG.MAX_EMAILS_PER_BATCH - CONFIG.MIN_EMAILS_PER_BATCH + 1)) + CONFIG.MIN_EMAILS_PER_BATCH;
    const emails = await getUnlabeledEmails(token, batchSize);

    if (emails.length === 0) {
      console.log('✅ Inbox already at zero!');
      return {
        success: true,
        processedCount: 0,
        remainingCount: 0
      };
    }

    console.log(`📬 Found ${emails.length} unlabeled emails to process`);

    // Classify emails
    const classifications = await classifyEmails(emails);

    // DISABLED: Gmail labels and archive - visual layer only
    // Labels and archive functionality disabled to test visual-only layer
    // const emailsWithLabels = classifications.map((result, i) => ({
    //   ...emails[i],
    //   labels: result.labels
    // }));
    // const labelResults = await applyLabels(token, emailsWithLabels, true);

    // Instead, just populate the label cache for badge rendering
    // IMPORTANT: Use result.threadId not emails[i].threadId - order may differ!
    let successCount = 0;
    for (const result of classifications) {
      // Each classification result includes its own email metadata (threadId, subject, etc.)
      if (result.threadId && typeof storeLabelCache === 'function') {
        await storeLabelCache(result.threadId, {
          type: result.type,
          importance: result.importance,
          client_label: result.client_label
        }, {
          subject: result.subject,
          from: result.from,
          snippet: result.snippet,
          messageId: result.id,
          date: result.date || new Date().toISOString()
        });
        successCount++;
        console.log(`💾 Cached: ${result.threadId.slice(0,8)}... → ${result.type}/${result.importance}`);
      }
    }
    console.log(`✅ Cached ${successCount} threads for badge rendering (no Gmail labels applied)`);

    // Log all classifications
    for (let i = 0; i < classifications.length; i++) {
      try {
        // logger.logClassification(email, classification, labels, context)
        if (typeof logger !== 'undefined') {
          await logger.logClassification(
            emails[i],
            classifications[i],
            classifications[i].labels,
            { source: 'auto-organize' }
          );
        }
      } catch (error) {
        console.warn(`⚠️ Failed to log classification for ${emails[i].id}:`, error);
      }
    }

    // Record budget usage
    await recordBudget(classifications);

    // Check if more emails remain
    const remaining = await getUnlabeledEmails(token, 1);

    return {
      success: true,
      processedCount: successCount,
      remainingCount: remaining.length,
      classifications: classifications
    };

  } catch (error) {
    console.error('❌ Silent organization failed:', error);
    return {
      success: false,
      processedCount: 0,
      remainingCount: 0,
      error: error.message
    };
  }
}

/**
 * Get auto-organize status (for UI display)
 */
async function getAutoOrganizeStatus() {
  const settings = await getAutoOrganizeSettings();

  // Check if alarm is actually set
  const alarm = await chrome.alarms.get(AUTO_ORGANIZE_ALARM);

  return {
    enabled: settings.enabled && !!alarm,
    intervalMinutes: settings.intervalMinutes,
    notifyOnZero: settings.notifyOnZero,
    onlyWhenGmailOpen: settings.onlyWhenGmailOpen,
    nextCheckTime: alarm ? new Date(alarm.scheduledTime) : null,
    alarmExists: !!alarm
  };
}

/**
 * Manually trigger auto-organize (for testing)
 */
async function triggerAutoOrganizeNow() {
  console.log('🧪 Manually triggering auto-organize...');
  await handleAutoOrganizeAlarm({ name: AUTO_ORGANIZE_ALARM });
}

// Export functions for use in background.js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    setupAutoOrganize,
    handleAutoOrganizeAlarm,
    getAutoOrganizeSettings,
    saveAutoOrganizeSettings,
    getAutoOrganizeStatus,
    triggerAutoOrganizeNow,
    organizeInboxSilently
  };
}
