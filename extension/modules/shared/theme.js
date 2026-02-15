/**
 * Reclaim Theme Utility
 * Manages theme preference (light/dark/system) and applies it to the DOM.
 * Loaded via <script> tag — exposes globals on window.
 */

const THEME_STORAGE_KEY = 'reclaim_theme_preference';

/** @returns {'light'|'dark'} */
function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** @returns {Promise<'light'|'dark'|'system'>} */
async function getThemePreference() {
  try {
    const result = await chrome.storage.local.get(THEME_STORAGE_KEY);
    return result[THEME_STORAGE_KEY] || 'system';
  } catch {
    return 'system';
  }
}

/** @param {'light'|'dark'|'system'} pref */
async function setThemePreference(pref) {
  try {
    await chrome.storage.local.set({ [THEME_STORAGE_KEY]: pref });
  } catch (e) {
    console.warn('Reclaim: Failed to save theme preference:', e);
  }
}

/** @param {'light'|'dark'|'system'} pref */
function applyTheme(pref) {
  const resolved = pref === 'system' ? getSystemTheme() : pref;
  document.documentElement.setAttribute('data-theme', resolved);
}

/**
 * Initialize theme: apply saved preference + listen for system changes.
 * Call once on DOMContentLoaded.
 */
async function initTheme() {
  const pref = await getThemePreference();
  applyTheme(pref);

  // Re-apply when system preference changes (only matters when pref === 'system')
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', async () => {
    const current = await getThemePreference();
    if (current === 'system') {
      applyTheme('system');
    }
  });
}

/** Cycle: system → light → dark → system. Returns the new preference. */
async function cycleTheme() {
  const current = await getThemePreference();
  const next = current === 'system' ? 'light' : current === 'light' ? 'dark' : 'system';
  await setThemePreference(next);
  applyTheme(next);
  return next;
}

/** @returns {{icon: string, label: string}} for the current preference */
async function getThemeToggleState() {
  const pref = await getThemePreference();
  const states = {
    system: {
      icon: '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10zm0-2V4a8 8 0 1 0 0 16z"/></svg>',
      label: 'Theme: System',
    },
    light: {
      icon: '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41L5.99 4.58zm12.37 12.37a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0a.996.996 0 0 0 0-1.41l-1.06-1.06zm1.06-10.96a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06zM7.05 18.36a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06z"/></svg>',
      label: 'Theme: Light',
    },
    dark: {
      icon: '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z"/></svg>',
      label: 'Theme: Dark',
    },
  };
  return states[pref] || states.system;
}
