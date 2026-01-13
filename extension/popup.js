/**
 * ShopQ Return Watch Popup Script
 * Handles popup UI interactions for Return Watch feature
 */

const API_BASE_URL = 'https://shopq-api-488078904670.us-central1.run.app';

// Get user ID from storage
async function getUserId() {
  try {
    const data = await chrome.storage.local.get('userId');
    return data.userId || 'default_user';
  } catch {
    return 'default_user';
  }
}

// Update return counts display
async function updateReturnCounts() {
  try {
    const userId = await getUserId();
    const response = await fetch(
      `${API_BASE_URL}/api/returns/counts?user_id=${encodeURIComponent(userId)}`,
      {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      }
    );

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();

    document.getElementById('expiringCount').textContent = data.expiring_soon || 0;
    document.getElementById('activeCount').textContent = data.active || 0;

    // Highlight if there are expiring items
    const expiringEl = document.getElementById('expiringCount');
    if (data.expiring_soon > 0) {
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
    // Trigger background to scan for purchase emails
    await chrome.runtime.sendMessage({ type: 'SCAN_FOR_PURCHASES' });

    btn.textContent = 'Scanning...';
    status.textContent = 'Checking recent emails for purchases';
    status.style.color = '#1a73e8';

    // Wait a moment then refresh counts
    setTimeout(async () => {
      await updateReturnCounts();
      btn.textContent = 'Scan for Purchases';
      btn.disabled = false;
      status.textContent = 'Scan complete';
    }, 3000);

  } catch (error) {
    btn.textContent = 'Error';
    status.textContent = error.message;
    status.style.color = '#c5221f';

    setTimeout(() => {
      btn.textContent = 'Scan for Purchases';
      btn.disabled = false;
    }, 2000);
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

// Initialize
updateReturnCounts();

// Close popup when mouse leaves (with small delay)
let closeTimeout;
document.body.addEventListener('mouseleave', () => {
  closeTimeout = setTimeout(() => window.close(), 500);
});
document.body.addEventListener('mouseenter', () => {
  clearTimeout(closeTimeout);
});
