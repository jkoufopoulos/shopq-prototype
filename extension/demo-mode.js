// Convenience helper injected into the MAIN world so toggleDemoMode()
// works directly from the DevTools console on mail.google.com.
window.toggleDemoMode = function () {
  var iframe = document.getElementById('reclaim-returns-iframe');
  if (!iframe) { console.warn('[Reclaim] Sidebar iframe not found'); return; }
  iframe.contentWindow.postMessage({ type: 'RECLAIM_TOGGLE_DEMO_MODE' }, '*');
};
