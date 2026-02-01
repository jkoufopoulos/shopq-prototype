/**
 * ShopQ Return Watch Popup Script
 * Handles popup UI interactions for Return Watch feature
 */

// Update return counts display using local storage via background script
async function updateReturnCounts() {
  try {
    const result = await chrome.runtime.sendMessage({ type: 'GET_VISIBLE_ORDERS' });
    const orders = result.orders || [];

    // Derive expiring count: orders with return_by_date within 7 days
    const now = new Date();
    const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
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
