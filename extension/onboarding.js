/**
 * Reclaim Onboarding Script
 * Handles the "Get Started" button on the welcome page.
 */
document.getElementById('get-started').addEventListener('click', async () => {
  // Find existing Gmail tab or open new one
  const tabs = await chrome.tabs.query({ url: 'https://mail.google.com/*' });

  if (tabs.length > 0) {
    await chrome.tabs.update(tabs[0].id, { active: true });
    await chrome.windows.update(tabs[0].windowId, { focused: true });
  } else {
    await chrome.tabs.create({ url: 'https://mail.google.com/' });
  }

  // Close the onboarding tab
  window.close();
});
