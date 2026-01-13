/**
 * User Notifications Module
 */

function showSuccess(message) {
  try {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'Mailq',
      message,
      priority: 1
    }, () => {
      if (chrome.runtime.lastError) {
        console.warn('⚠️ Notification error:', chrome.runtime.lastError.message);
      }
    });
  } catch (e) {
    console.warn('⚠️ Could not show notification:', e);
  }
}

function showError(message) {
  try {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'Mailq Error',
      message,
      priority: 2
    }, () => {
      if (chrome.runtime.lastError) {
        console.warn('⚠️ Notification error:', chrome.runtime.lastError.message);
      }
    });
  } catch (e) {
    console.warn('⚠️ Could not show notification:', e);
  }
}

async function showSpendStats() {
  const { getDailyReport } = await import('./telemetry.js');
  const report = await getDailyReport();

  if (report) {
    showSuccess(
      `Today: ${report.total_emails} emails, $${report.total_spend.toFixed(4)} spent`
    );
  }
}
