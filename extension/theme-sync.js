// Sync theme before first paint to prevent FOUC.
// Sets system preference immediately, then corrects from storage.
(function() {
  var d = document.documentElement;
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    d.setAttribute('data-theme', 'dark');
  }
  try {
    chrome.storage.local.get('reclaim_theme_preference', function(r) {
      var p = r && r.reclaim_theme_preference;
      if (p === 'light') d.setAttribute('data-theme', 'light');
      else if (p === 'dark') d.setAttribute('data-theme', 'dark');
      // 'system' or absent: already handled by matchMedia above
    });
  } catch(e) {}
})();
