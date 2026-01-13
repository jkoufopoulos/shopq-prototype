/**
 * ShopQ Popup Script
 * Handles popup UI interactions
 */

const LABEL_CACHE_KEY = 'shopq_label_cache';

// Update cache count display
async function updateCacheCount() {
  try {
    const data = await chrome.storage.local.get(LABEL_CACHE_KEY);
    const cache = data[LABEL_CACHE_KEY] || {};
    const count = Object.keys(cache).length;
    document.getElementById('cacheCount').textContent = count.toLocaleString();
  } catch (error) {
    document.getElementById('cacheCount').textContent = 'Error';
  }
}

// Organize button - send message to background
document.getElementById('organize').addEventListener('click', async () => {
  const btn = document.getElementById('organize');
  const status = document.getElementById('statusMessage');
  btn.textContent = 'Organizing...';
  btn.disabled = true;
  if (status) status.textContent = '';

  try {
    await chrome.runtime.sendMessage({ type: 'ORGANIZE_NOW' });
    btn.textContent = 'Done!';
    updateCacheCount();
    // Badges update dynamically now - no refresh needed
    if (status) {
      status.textContent = 'Badges will appear shortly';
      status.style.color = '#1a73e8';
    }
    setTimeout(() => {
      btn.textContent = 'Organize Inbox';
      btn.disabled = false;
    }, 1500);
  } catch (error) {
    btn.textContent = 'Error';
    if (status) {
      status.textContent = error.message;
      status.style.color = '#c5221f';
    }
    setTimeout(() => {
      btn.textContent = 'Organize Inbox';
      btn.disabled = false;
    }, 1500);
  }
});

// Clear cache button
document.getElementById('clearCache').addEventListener('click', async () => {
  const btn = document.getElementById('clearCache');
  btn.textContent = 'Clearing...';
  btn.disabled = true;

  try {
    await chrome.storage.local.remove(LABEL_CACHE_KEY);
    btn.textContent = 'Cleared!';
    updateCacheCount();
    setTimeout(() => {
      btn.textContent = 'Clear Badge Cache';
      btn.disabled = false;
    }, 1500);
  } catch (error) {
    btn.textContent = 'Error';
    setTimeout(() => {
      btn.textContent = 'Clear Badge Cache';
      btn.disabled = false;
    }, 1500);
  }
});

// Initialize
updateCacheCount();

// Close popup when mouse leaves (with small delay to prevent accidental closes)
let closeTimeout;
document.body.addEventListener('mouseleave', () => {
  closeTimeout = setTimeout(() => window.close(), 300);
});
document.body.addEventListener('mouseenter', () => {
  clearTimeout(closeTimeout);
});
