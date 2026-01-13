/**
 * MailQ Sidebar Inner Script
 * Runs inside the iframe to receive content updates via postMessage
 */

// Listen for messages from parent (content script)
window.addEventListener('message', (event) => {
  // Handle digest content updates
  if (event.data?.type === 'MAILQ_UPDATE_DIGEST') {
    const contentEl = document.getElementById('mailq-content');
    if (contentEl && event.data.html) {
      contentEl.innerHTML = event.data.html;
    }
  }

  // Handle nav state updates (back button visibility based on route)
  if (event.data?.type === 'MAILQ_UPDATE_NAV') {
    const backBtn = document.getElementById('mailq-back-btn');
    if (backBtn) {
      if (event.data.showBack) {
        backBtn.classList.remove('hidden');
      } else {
        backBtn.classList.add('hidden');
      }
    }
  }
});

// Signal to parent that iframe is ready
window.addEventListener('DOMContentLoaded', () => {
  window.parent.postMessage({ type: 'MAILQ_SIDEBAR_READY' }, '*');

  // Close button - close the sidebar
  const closeBtn = document.getElementById('mailq-close-btn');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      window.parent.postMessage({ type: 'MAILQ_CLOSE_SIDEBAR' }, '*');
    });
  }

  // Back button - navigate to inbox
  const backBtn = document.getElementById('mailq-back-btn');
  if (backBtn) {
    backBtn.addEventListener('click', () => {
      window.parent.postMessage({ type: 'MAILQ_GO_TO_INBOX' }, '*');
      backBtn.classList.add('hidden');
    });
  }

  // Listen for link clicks to show back button
  document.addEventListener('click', (event) => {
    const anchor = event.target.closest('a');
    if (anchor && anchor.href && anchor.href.includes('mail.google.com')) {
      // Show back button when user clicks an email link
      if (backBtn) backBtn.classList.remove('hidden');
    }
  }, true);
});
