/**
 * Reclaim Popup Script
 * Handles popup UI interactions for Reclaim feature
 */

// Update return counts display using local storage via background script
async function updateReturnCounts() {
  try {
    const result = await chrome.runtime.sendMessage({ type: 'GET_VISIBLE_ORDERS' });
    const orders = result.orders || [];

    // Derive expiring count: orders with return_by_date within threshold
    const now = new Date();
    const sevenDaysMs = CONFIG.EXPIRING_SOON_DAYS * 24 * 60 * 60 * 1000;
    let expiringCount = 0;

    for (const order of orders) {
      if (!order.return_by_date) continue;
      const deadline = new Date(order.return_by_date);
      const diff = deadline - now;
      if (diff >= 0 && diff <= sevenDaysMs) {
        expiringCount++;
      }
    }

    document.getElementById('expiringCount').textContent = expiringCount;
    document.getElementById('activeCount').textContent = orders.length;

    // Highlight if there are expiring items
    const expiringEl = document.getElementById('expiringCount');
    if (expiringCount > 0) {
      expiringEl.classList.add('urgent');
    } else {
      expiringEl.classList.remove('urgent');
    }
  } catch (error) {
    console.error('Failed to fetch return counts:', error);
    document.getElementById('expiringCount').textContent = '-';
    document.getElementById('activeCount').textContent = '-';
  }
}

// Scan for purchases button
document.getElementById('scanEmails').addEventListener('click', async () => {
  const btn = document.getElementById('scanEmails');
  const status = document.getElementById('statusMessage');

  btn.textContent = 'Scanning...';
  btn.disabled = true;
  status.textContent = '';

  try {
    status.textContent = 'Checking recent emails for purchases';
    status.style.color = 'var(--rc-accent-primary)';

    // Wait for scan to actually complete
    const result = await chrome.runtime.sendMessage({ type: 'SCAN_FOR_PURCHASES' });

    await updateReturnCounts();
    btn.textContent = 'Scan for Purchases';
    btn.disabled = false;

    if (result && result.success === false) {
      status.textContent = result.error || 'Scan failed';
      status.style.color = 'var(--rc-status-critical-text)';
    } else {
      status.textContent = 'Scan complete';
    }
  } catch (error) {
    btn.textContent = 'Scan for Purchases';
    btn.disabled = false;
    status.textContent = error.message || 'Scan failed';
    status.style.color = 'var(--rc-status-critical-text)';
  }
});

// Open sidebar button - opens Gmail and focuses the sidebar
document.getElementById('openSidebar').addEventListener('click', async () => {
  // Find existing Gmail tab or open new one
  const tabs = await chrome.tabs.query({ url: 'https://mail.google.com/*' });

  if (tabs.length > 0) {
    // Focus existing Gmail tab
    await chrome.tabs.update(tabs[0].id, { active: true });
    await chrome.windows.update(tabs[0].windowId, { focused: true });
  } else {
    // Open new Gmail tab
    await chrome.tabs.create({ url: 'https://mail.google.com/' });
  }

  // Close popup
  window.close();
});

// Initialize theme
initTheme().then(async () => {
  const toggleBtn = document.getElementById('theme-toggle');
  if (toggleBtn) {
    const state = await getThemeToggleState();
    toggleBtn.innerHTML = state.icon;
    toggleBtn.title = state.label;
    toggleBtn.addEventListener('click', async () => {
      await cycleTheme();
      const newState = await getThemeToggleState();
      toggleBtn.innerHTML = newState.icon;
      toggleBtn.title = newState.label;
    });
  }
});

// Initialize
updateReturnCounts();

